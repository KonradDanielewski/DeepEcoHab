"""Tests for calculate_features (per-animal metrics as value + exposure).

calculate_features collapses the upstream tables to one value per animal per hour for
seven metrics and pairs each with the opportunity it arose from, so a rate is
sum(value)/sum(exposure) at any grouping. It reads chasings_df, pairwise_meetings,
activity_df and main_df via Recording.load_results, which we monkeypatch with a
key-dispatching stub; the step is called directly. Fixtures live in one light_phase
occurrence (day 1, phase_count 1).
"""

import polars as pl
import pytest
import strategies

from deepecohab.core import antenna_analysis
from deepecohab.core.data_model import AnalysisParams, Recording

RECORDING = strategies.analysis_recording(animal_ids=["A", "B", "C"])
PHASE_ENUM = pl.Enum(["light_phase", "dark_phase"])
ANIMAL_ENUM = pl.Enum(RECORDING.cohort.animal_tags)

# Every pair-derived metric is exposed per animal the subject could have met.
PARTNERS = RECORDING.cohort.n_mice - 1

SOLO = {"activity", "time_alone"}
PAIRED = {"time_together", "pairwise_encounters", "n_chasing", "n_chased"}
PER_DETECTION = {"n_chasing_per_detection"}
METRICS = SOLO | PAIRED | PER_DETECTION

HOUR = 3600.0


def _base(n: int, hour: int) -> dict:
	return {
		"phase": pl.Series(["light_phase"] * n, dtype=PHASE_ENUM),
		"day": pl.Series([1] * n, dtype=pl.UInt16),
		"phase_count": pl.Series([1] * n, dtype=pl.UInt16),
		"hour": pl.Series([hour] * n, dtype=pl.UInt8),
	}


def chasings_frame(rows: list[tuple[str, str, int]], hour: int = 0) -> pl.LazyFrame:
	"""chasings_df rows (chaser, chased, chasings)."""
	return pl.LazyFrame(
		{
			**_base(len(rows), hour),
			"chaser": pl.Series([r[0] for r in rows], dtype=ANIMAL_ENUM),
			"chased": pl.Series([r[1] for r in rows], dtype=ANIMAL_ENUM),
			"chasings": pl.Series([r[2] for r in rows], dtype=pl.UInt32),
		}
	)


def activity_frame(rows: list[tuple[str, int, float, float]], hour: int = 0) -> pl.LazyFrame:
	"""activity_df rows (animal_id, visits, time_alone seconds, time_in_position seconds)."""
	return pl.LazyFrame(
		{
			**_base(len(rows), hour),
			"animal_id": pl.Series([r[0] for r in rows], dtype=ANIMAL_ENUM),
			"visits_to_position": pl.Series([r[1] for r in rows], dtype=pl.UInt32),
			"time_alone": strategies.seconds([float(r[2]) for r in rows]),
			"time_in_position": strategies.seconds([float(r[3]) for r in rows]),
		}
	)


def pairwise_frame(rows: list[tuple[str, str, float, int]], hour: int = 0) -> pl.LazyFrame:
	"""pairwise_meetings rows (animal_id, animal_id_2, time_together seconds, encounters).

	The position is a cage only because a fixture has to name one: calculate_features
	sums over positions without filtering, so tunnel co-presence counts too.
	"""
	return pl.LazyFrame(
		{
			**_base(len(rows), hour),
			"position": pl.Series(["cage_1"] * len(rows), dtype=pl.Categorical),
			"animal_id": pl.Series([r[0] for r in rows], dtype=ANIMAL_ENUM),
			"animal_id_2": pl.Series([r[1] for r in rows], dtype=ANIMAL_ENUM),
			"time_together": strategies.seconds([float(r[2]) for r in rows]),
			"pairwise_encounters": pl.Series([r[3] for r in rows], dtype=pl.UInt32),
		}
	)


def main_frame(rows: list[tuple[str, int]], hour: int = 0) -> pl.LazyFrame:
	"""main_df rows, one antenna registration each, from (animal_id, n_detections)."""
	animals = [animal for animal, detections in rows for _ in range(detections)]
	return pl.LazyFrame(
		{**_base(len(animals), hour), "animal_id": pl.Series(animals, dtype=ANIMAL_ENUM)}
	)


def run_features(monkeypatch, *, chasings, activity, pairwise, detections=None) -> pl.DataFrame:
	tables = {
		"chasings_df": chasings,
		"pairwise_meetings": pairwise,
		"activity_df": activity,
		"main_df": detections if detections is not None else main_frame([]),
	}
	monkeypatch.setattr(Recording, "load_results", lambda self, key, eager=False: tables[key])
	return antenna_analysis.calculate_features(RECORDING, AnalysisParams()).collect()


def quiet_hour(monkeypatch, activity, hour: int = 0) -> pl.DataFrame:
	"""Features for an hour with the given activity and no social events at all."""
	return run_features(
		monkeypatch,
		chasings=chasings_frame([("A", "B", 0)], hour),
		activity=activity,
		pairwise=pairwise_frame([("A", "B", 0.0, 0)], hour),
	)


def column_for(result: pl.DataFrame, metric: str, column: str) -> dict[str, float]:
	"""One column of a metric's rows, keyed by animal."""
	sub = result.filter(pl.col("metric") == metric)
	return dict(sub.select("animal_id", column).iter_rows())


def rate_for(result: pl.DataFrame, metric: str) -> dict[str, float]:
	"""The metric's rate per animal, aggregated the only correct way."""
	sub = (
		result.filter(pl.col("metric") == metric)
		.group_by("animal_id")
		.agg(pl.sum("value"), pl.sum("exposure"))
	)
	return {
		row["animal_id"]: row["value"] / row["exposure"]
		for row in sub.iter_rows(named=True)
		if row["exposure"]
	}


def test_output_is_long_with_value_and_exposure(monkeypatch):
	"""Result is long-format: one row per animal/metric, carrying both halves of a rate."""
	result = run_features(
		monkeypatch,
		chasings=chasings_frame([("A", "B", 1)]),
		activity=activity_frame([("A", 10, 0.0, HOUR), ("B", 20, 0.0, HOUR)]),
		pairwise=pairwise_frame([("A", "B", 5.0, 1)]),
	)
	assert set(result.columns) == {
		"phase",
		"day",
		"phase_count",
		"hour",
		"animal_id",
		"metric",
		"value",
		"exposure",
	}
	assert set(result["metric"].unique()) == METRICS
	assert result.schema["value"] == pl.Float64
	assert result.schema["exposure"] == pl.Float64


def test_values_are_raw_not_rescaled(monkeypatch):
	"""Magnitude survives: a value is the count itself, not a z-score of it."""
	result = quiet_hour(
		monkeypatch,
		activity_frame([("A", 10, 0.0, HOUR), ("B", 20, 0.0, HOUR), ("C", 0, 0.0, HOUR)]),
	)
	assert column_for(result, "activity", "value") == {"A": 10.0, "B": 20.0, "C": 0.0}


def test_solo_exposure_is_the_time_observed(monkeypatch):
	"""activity and time_alone are exposed against the animal's own observed time."""
	# A observed for a full hour, B for half of one, C not seen at all.
	result = quiet_hour(
		monkeypatch,
		activity_frame([("A", 10, 0.0, HOUR), ("B", 20, 0.0, HOUR / 2), ("C", 0, 0.0, 0.0)]),
	)
	for metric in SOLO:
		assert column_for(result, metric, "exposure") == {"A": 1.0, "B": 0.5, "C": 0.0}


def test_paired_exposure_counts_available_partners(monkeypatch):
	"""Pair-derived metrics are exposed per partner, so cohort size cancels out."""
	result = quiet_hour(monkeypatch, activity_frame([("A", 10, 0.0, HOUR), ("B", 20, 0.0, HOUR)]))
	for metric in PAIRED:
		assert column_for(result, metric, "exposure")["A"] == 1.0 * PARTNERS


def test_per_detection_exposure_is_the_detection_count(monkeypatch):
	"""n_chasing_per_detection reads the same chase count against antenna detections."""
	result = run_features(
		monkeypatch,
		chasings=chasings_frame([("A", "B", 4)]),
		activity=activity_frame([("A", 10, 0.0, HOUR), ("B", 20, 0.0, HOUR)]),
		pairwise=pairwise_frame([("A", "B", 0.0, 0)]),
		detections=main_frame([("A", 8), ("B", 2)]),
	)
	assert column_for(result, "n_chasing_per_detection", "value")["A"] == 4.0
	assert column_for(result, "n_chasing_per_detection", "exposure") == {"A": 8.0, "B": 2.0}
	assert rate_for(result, "n_chasing_per_detection") == {"A": 0.5, "B": 0.0}
	# The partner-hours row is a different question and keeps its own exposure.
	assert column_for(result, "n_chasing", "exposure")["A"] == 1.0 * PARTNERS


def test_time_alone_rate_is_a_fraction_of_time_observed(monkeypatch):
	"""Both halves are durations, so the rate is dimensionless - and 1 minus it is
	the fraction of time the animal had company.
	"""
	result = quiet_hour(
		monkeypatch, activity_frame([("A", 0, HOUR / 4, HOUR), ("B", 0, HOUR, HOUR)])
	)
	assert rate_for(result, "time_alone") == {"A": 0.25, "B": 1.0}


def test_rate_aggregates_correctly_across_hours(monkeypatch):
	"""The point of storing both halves: sum then divide, never average the rates.

	A makes 10 visits in a full hour and 30 in a half hour, so its rate over the pair
	is 40/1.5 visits per hour. Averaging the two hourly rates would say 35.
	"""
	result = run_features(
		monkeypatch,
		chasings=pl.concat(
			[chasings_frame([("A", "B", 0)], 0), chasings_frame([("A", "B", 0)], 1)]
		),
		activity=pl.concat(
			[
				activity_frame([("A", 10, 0.0, HOUR)], 0),
				activity_frame([("A", 30, 0.0, HOUR / 2)], 1),
			]
		),
		pairwise=pl.concat(
			[pairwise_frame([("A", "B", 0.0, 0)], 0), pairwise_frame([("A", "B", 0.0, 0)], 1)]
		),
	)
	assert rate_for(result, "activity")["A"] == 40 / 1.5

	hourly = result.filter((pl.col("metric") == "activity") & (pl.col("animal_id") == "A"))
	naive = (hourly["value"] / hourly["exposure"]).mean()
	assert naive == 35.0  # what averaging the rates would have given


def test_directional_proportion_comes_from_the_sibling_rows(monkeypatch):
	"""Chase win rate needs no metric of its own: the counts are stored side by side."""
	result = run_features(
		monkeypatch,
		chasings=chasings_frame([("A", "B", 3), ("B", "A", 1)]),
		activity=activity_frame([("A", 0, 0.0, HOUR), ("B", 0, 0.0, HOUR)]),
		pairwise=pairwise_frame([("A", "B", 0.0, 0)]),
	)
	chasing = column_for(result, "n_chasing", "value")
	chased = column_for(result, "n_chased", "value")

	assert chasing["A"] / (chasing["A"] + chased["A"]) == 0.75
	assert chasing["B"] / (chasing["B"] + chased["B"]) == 0.25


def test_unobserved_animal_contributes_nothing(monkeypatch):
	"""An animal with no observed time gets zero exposure, so it adds to neither sum.

	activity_df is reindexed onto the dense grid upstream, so a silent animal is present
	with zeros rather than missing - which is what keeps the metric rows complete.
	"""
	result = quiet_hour(monkeypatch, activity_frame([("A", 10, 0.0, HOUR), ("C", 0, 0.0, 0.0)]))
	unobserved = result.filter(pl.col("animal_id") == "C")

	assert unobserved.height == len(METRICS)
	assert unobserved["exposure"].to_list() == [0.0] * unobserved.height
	assert unobserved["value"].to_list() == [0.0] * unobserved.height


def test_no_nulls_anywhere(monkeypatch):
	"""Cells no upstream table mentioned are filled, not left null."""
	result = run_features(
		monkeypatch,
		chasings=chasings_frame([("A", "B", 1)]),
		activity=activity_frame([("A", 10, 0.0, HOUR), ("B", 20, 0.0, HOUR)]),
		pairwise=pairwise_frame([("A", "B", 5.0, 1)]),
	)
	assert result.null_count().sum_horizontal().item() == 0


def test_tunnel_co_presence_reaches_the_features(monkeypatch):
	"""Every position counts: features sums pairwise_meetings without filtering it.

	Time two animals spend together in a tunnel is contact - it is what the tube test
	reads as a contest - so leaving it out would understate togetherness exactly where
	it is most physical.
	"""
	tunnel = pairwise_frame([("A", "B", 5.0, 1)]).with_columns(
		pl.lit("tunnel_1", dtype=pl.Categorical).alias("position")
	)
	result = run_features(
		monkeypatch,
		chasings=chasings_frame([("A", "B", 0)]),
		activity=activity_frame([("A", 10, 0.0, HOUR), ("B", 20, 0.0, HOUR)]),
		pairwise=tunnel,
	)

	assert column_for(result, "time_together", "value")["A"] == pytest.approx(5.0 / HOUR)
	assert column_for(result, "pairwise_encounters", "value")["A"] == 1.0


def test_undefined_time_is_part_of_the_observed_exposure(monkeypatch):
	"""Time the analysis cannot place is still time the animal was watched for.

	``observed_hours`` is summed over every position, ``undefined`` included, so the
	denominator is the animal's whole timeline. Dropping it would inflate every rate for
	an animal whose antenna reads are patchy.
	"""
	activity = pl.concat(
		[
			activity_frame([("A", 6, 0.0, HOUR / 2)]).with_columns(
				pl.lit("cage_1", dtype=pl.Categorical).alias("position")
			),
			activity_frame([("A", 2, 0.0, HOUR / 2)]).with_columns(
				pl.lit("undefined", dtype=pl.Categorical).alias("position")
			),
		]
	)
	result = quiet_hour(monkeypatch, activity)

	assert column_for(result, "activity", "value")["A"] == 8.0
	assert column_for(result, "activity", "exposure")["A"] == 1.0


def test_one_animal_cohort_omits_the_paired_metrics(monkeypatch):
	"""With no partner available, a paired metric has no exposure to be read against.

	Its exposure would be ``observed_hours * 0``, so every rate over it would be 0/0.
	The solo and per-detection metrics still mean what they always did.
	"""
	lone = strategies.analysis_recording(animal_ids=["A"])
	animals = pl.Enum(lone.cohort.animal_tags)
	calendar = {
		"phase": pl.Enum(["light_phase", "dark_phase"]),
		"day": pl.UInt16,
		"phase_count": pl.UInt16,
		"hour": pl.UInt8,
	}
	one = {
		"phase": pl.Series(["light_phase"], dtype=calendar["phase"]),
		"day": pl.Series([1], dtype=pl.UInt16),
		"phase_count": pl.Series([1], dtype=pl.UInt16),
		"hour": pl.Series([0], dtype=pl.UInt8),
	}
	tables = {
		"activity_df": pl.LazyFrame(
			{
				**one,
				"animal_id": pl.Series(["A"], dtype=animals),
				"visits_to_position": pl.Series([4], dtype=pl.UInt32),
				"time_alone": strategies.seconds([HOUR]),
				"time_in_position": strategies.seconds([HOUR]),
			}
		),
		"main_df": pl.LazyFrame({**one, "animal_id": pl.Series(["A"], dtype=animals)}),
		# A lone cohort has no ordered pairs and no unordered ones, so both grids are empty.
		"chasings_df": pl.LazyFrame(
			schema={**calendar, "chaser": animals, "chased": animals, "chasings": pl.UInt32}
		),
		"pairwise_meetings": pl.LazyFrame(
			schema={
				**calendar,
				"position": pl.Categorical,
				"animal_id": animals,
				"animal_id_2": animals,
				"time_together": pl.Duration("us"),
				"pairwise_encounters": pl.UInt32,
			}
		),
	}
	monkeypatch.setattr(Recording, "load_results", lambda self, key, eager=False: tables[key])

	result = antenna_analysis.calculate_features(lone, AnalysisParams()).collect()

	assert set(result["metric"].unique()) == SOLO | PER_DETECTION
	assert dict(
		result.filter(pl.col("metric") == "time_alone").select("value", "exposure").iter_rows()
	) == {1.0: 1.0}
	assert result.null_count().sum_horizontal().item() == 0
