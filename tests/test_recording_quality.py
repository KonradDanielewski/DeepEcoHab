"""Tests for build_recording_quality (correct, interpolated and bad passes per animal and antenna).

The step reads ``recording.data`` rather than a produced table, so each case states a
raw antenna sequence and attaches it to the recording. Geometry comes from the linear
``ANALYSIS_ANTENNA_COMBINATIONS`` chain (1-2-3-4), where every skipped antenna has one
possible route, and from the default ring, where the antenna opposite the animal is
reachable both ways and so has none.
"""

import datetime as dt

import polars as pl
import strategies

from deepecohab.core import topology
from deepecohab.core.data_model import AnalysisParams, Boundary, Recording
from deepecohab.core.recording_pipeline import build_recording_quality

CHAIN = strategies.ANALYSIS_ANTENNA_COMBINATIONS
RING = strategies.ring_layout(*strategies.RING_LAYOUTS["default"])[0]


def quality(
	recording: Recording, reads: list[tuple[str, int]], inserted: set[int] = frozenset()
) -> pl.DataFrame:
	"""Run the step over ``(animal, antenna)`` reads, spaced ten seconds apart.

	``inserted`` names, by index, the reads preprocessing interpolated.
	"""
	start = recording.timeline.local_span[0] + dt.timedelta(hours=1)
	recording.data = pl.LazyFrame(
		{
			"datetime": [start + dt.timedelta(seconds=10 * index) for index in range(len(reads))],
			"antenna": [str(antenna) for _, antenna in reads],
			"time_under": [dt.timedelta(seconds=1)] * len(reads),
			"animal_id": [animal for animal, _ in reads],
			"inserted": [index in inserted for index in range(len(reads))],
		},
		schema=recording.data_schema,
	)
	return build_recording_quality(recording, AnalysisParams()).collect()


def cell(result: pl.DataFrame, animal: str, antenna: int) -> dict:
	"""The one row for an animal and antenna."""
	return result.filter(
		(pl.col("animal_id") == animal) & (pl.col("antenna") == str(antenna))
	).to_dicts()[0]


# --- routes ------------------------------------------------------------------


def test_route_names_the_antennas_that_did_not_fire():
	"""A step over a gap resolves to the antennas skipped, in the order crossed."""
	routes = topology.unique_routes(CHAIN)

	assert routes[("1", "3")] == ["2"]
	assert routes[("1", "4")] == ["2", "3"]
	assert routes[("4", "1")] == ["3", "2"]


def test_legal_steps_have_no_route():
	"""A pair the layout joins was not a miss, and neither was a repeat read."""
	routes = topology.unique_routes(CHAIN)

	assert ("1", "2") not in routes
	assert ("1", "1") not in routes


def test_ambiguous_steps_have_no_route():
	"""On a ring the opposite antenna is two equally short ways off, so it is left out."""
	routes = topology.unique_routes(RING)

	assert routes[("1", "3")] == ["2"]
	assert routes[("1", "7")] == ["8"]
	assert ("1", "5") not in routes


# --- the table ---------------------------------------------------------------


def test_missed_read_is_charged_to_the_skipped_antenna():
	"""Stepping 2 -> 4 means antenna 3 failed to read, and only antenna 3."""
	recording = strategies.analysis_recording(animal_ids=["A", "B"])
	result = quality(recording, [("A", 1), ("A", 2), ("A", 4)])

	assert cell(result, "A", 3) == {
		"animal_id": "A",
		"antenna": "3",
		"correct": 0,
		"interpolated": 0,
		"bad": 1,
		"miss_rate": 100.0,
	}
	assert [cell(result, "A", antenna)["bad"] for antenna in (1, 2, 4)] == [0, 0, 0]
	assert [cell(result, "A", antenna)["correct"] for antenna in (1, 2, 4)] == [1, 1, 1]


def test_miss_rate_is_the_share_of_passes_that_went_unrecorded():
	"""Antenna 3 reads twice and is skipped once, so one pass in three was missed."""
	recording = strategies.analysis_recording(animal_ids=["A"])
	result = quality(recording, [("A", a) for a in (1, 2, 3, 4, 3, 2, 4)])

	assert cell(result, "A", 3)["correct"] == 2
	assert cell(result, "A", 3)["bad"] == 1
	assert cell(result, "A", 3)["miss_rate"] == 100 / 3


def test_an_interpolated_pass_counts_as_missed_but_not_as_bad():
	"""Preprocessing filled antenna 3 in: the step 2 -> 3 -> 4 is whole, yet 3 did not read."""
	recording = strategies.analysis_recording(animal_ids=["A"])
	result = quality(recording, [("A", 1), ("A", 2), ("A", 3), ("A", 4)], inserted={2})

	assert cell(result, "A", 3) == {
		"animal_id": "A",
		"antenna": "3",
		"correct": 0,
		"interpolated": 1,
		"bad": 0,
		"miss_rate": 100.0,
	}
	assert result["correct"].sum() == 3


def test_a_step_across_a_recording_boundary_is_not_a_pass():
	"""Nothing recorded between the parts, so 1 -> 4 over the stop charges no antenna."""
	recording = strategies.analysis_recording(animal_ids=["A"])
	start = recording.timeline.local_span[0] + dt.timedelta(hours=1)
	recording.boundaries = [
		Boundary(
			start=start + dt.timedelta(seconds=11),
			end=start + dt.timedelta(seconds=19),
			kind="observed_record_gap",
		)
	]
	across = quality(recording, [("A", 1), ("A", 2), ("A", 4)])
	recording.boundaries = []
	within = quality(recording, [("A", 1), ("A", 2), ("A", 4)])

	assert across["bad"].sum() == 0
	assert within["bad"].sum() == 1


def test_ambiguous_step_is_charged_to_nobody():
	"""A step across the ring could have gone either way, so no antenna takes the blame."""
	recording = strategies.ring_recording(animal_ids=["A"])
	result = quality(recording, [("A", 1), ("A", 5)])

	assert result["bad"].sum() == 0
	assert result["correct"].sum() == 2


def test_grid_covers_every_animal_and_antenna():
	"""An animal the board never saw still gets a row per antenna, at zero."""
	recording = strategies.analysis_recording(animal_ids=["A", "B", "C"])
	result = quality(recording, [("A", 1), ("A", 2)])

	assert result.height == 3 * 4
	assert set(result["animal_id"].cast(pl.String)) == set(recording.cohort.animal_tags)
	assert set(result["antenna"].cast(pl.String)) == {"1", "2", "3", "4"}
	assert result.null_count().sum_horizontal().item() == 0
	assert result.filter(pl.col("animal_id") == "C")["miss_rate"].sum() == 0
