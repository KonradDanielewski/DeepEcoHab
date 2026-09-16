"""Tests for Project.generate_project_table and load_project_table.

The project table stacks every recording's features on one comparable timeline and
attaches cohort metadata, so results can be grouped by a recorded attribute across
recordings. Cohorts differ between recordings, so the animal_id and phase enums have to
be widened to strings before the concat, and recordings of different lengths stay ragged
rather than being padded or truncated.
"""

import datetime as dt
import json
import warnings
from pathlib import Path

import polars as pl
import pytest
import strategies as strat

from deepecohab.core.data_model import Bout, Event, Project, Recording

TZ = "UTC"
# Animals shuttle between neighbouring cages, which is enough to populate every table.
ROUTE = [1, 2, 3, 2]


def raw_reads(recording: Recording, hours: int) -> pl.DataFrame:
	"""Antenna registrations for every animal, walking the route once per hour.

	Each animal is offset by a few minutes so they overlap in cages without being
	perfectly synchronised, which gives the pairwise and chasing steps something to find.
	"""
	origin = recording.timeline.experiment_start
	rows = []

	for offset, animal in enumerate(recording.cohort.animal_tags):
		moment = origin + dt.timedelta(minutes=3 * offset)
		for hour in range(hours):
			for step, antenna in enumerate(ROUTE):
				rows.append(
					{
						"datetime": moment
						+ dt.timedelta(hours=hour, minutes=7 * step, seconds=offset),
						"antenna": antenna,
						"time_under": dt.timedelta(milliseconds=120),
						"animal_id": animal,
					}
				)

	return pl.DataFrame(rows, schema=recording.data_schema).sort("datetime")


def write_recording(directory: Path, recording: Recording, hours: int) -> tuple[Path, Path]:
	"""Persist a recording's metadata and raw data the way Project.add_recording reads them."""
	directory.mkdir(parents=True, exist_ok=True)
	metadata_path = directory / "metadata.json"
	data_path = directory / "data.parquet"

	metadata_path.write_text(
		json.dumps({"recording": recording.to_config()}, indent=2), encoding="utf-8"
	)
	raw_reads(recording, hours).write_parquet(data_path)
	return metadata_path, data_path


def make_recording(name: str, animal_ids: list[str], genotype: str, finish: str) -> Recording:
	recording = strat.analysis_recording(
		animal_ids=animal_ids, tz=TZ, start="2023-05-24 00:00:00", finish=finish
	)
	recording.name = name
	for animal in recording.cohort.animals:
		animal.genotype = genotype
	return recording


@pytest.fixture(scope="module")
def project(tmp_path_factory) -> Project:
	"""A two-recording project, analysed, with different cohorts and different lengths.

	The cohorts deliberately share no tags, so a concat that kept the per-recording
	animal_id enum would fail here rather than in production.
	"""
	root = tmp_path_factory.mktemp("project_table")
	sources = []

	for name, animals, genotype, finish, hours in (
		("wt_cohort", ["A", "B", "C"], "WT", "2023-05-27 00:00:00", 60),
		("ko_cohort", ["X", "Y"], "KO", "2023-05-26 00:00:00", 36),
	):
		recording = make_recording(name, animals, genotype, finish)
		sources.append(write_recording(root / "sources" / name, recording, hours))

	project = Project.create(
		project_name="table_test", experimenter="tester", location=root / "project"
	)
	project.add_recordings(sources)
	project.run_analysis()
	return project


def test_covers_every_recording_and_animal(project):
	table = project.generate_project_table().collect()

	assert set(table["recording"].unique()) == {"wt_cohort", "ko_cohort"}
	assert set(table["animal_id"].unique()) == {"A", "B", "C", "X", "Y"}


def test_row_count_is_the_sum_of_the_parts(project):
	"""Nothing is dropped or duplicated by the concat."""
	table = project.generate_project_table().collect()
	parts = sum(
		recording.load_results("feature_df", eager=True).height for recording in project.recordings
	)
	assert table.height == parts


def test_enums_are_widened_to_strings(project):
	"""Per-recording enum categories cannot survive a concat across cohorts."""
	table = project.generate_project_table().collect()

	assert table.schema["animal_id"] == pl.String
	assert table.schema["phase"] == pl.String


def test_metadata_travels_with_every_row(project):
	"""The point of the table: grouping by a recorded attribute spans recordings."""
	table = project.generate_project_table().collect()

	assert table["genotype"].null_count() == 0
	by_genotype = table.group_by("genotype").agg(pl.col("animal_id").n_unique().alias("animals"))
	assert dict(by_genotype.iter_rows()) == {"WT": 3, "KO": 2}


def test_cohort_size_is_carried_so_the_correction_can_be_undone(project):
	table = project.generate_project_table().collect()
	sizes = table.group_by("recording").agg(pl.col("n_mice").unique().alias("sizes"))

	assert {row["recording"]: row["sizes"] for row in sizes.iter_rows(named=True)} == {
		"wt_cohort": [3],
		"ko_cohort": [2],
	}


def test_recordings_stay_ragged(project):
	"""A shorter recording contributes the days it has, with nothing padded in."""
	table = project.generate_project_table().collect()
	last_day = table.group_by("recording").agg(pl.max("day").alias("last"))
	days = {row["recording"]: row["last"] for row in last_day.iter_rows(named=True)}

	assert days["wt_cohort"] > days["ko_cohort"]


def test_rates_are_comparable_across_recordings(project):
	"""Both halves survive the concat, so a rate is a sum-then-divide over the table."""
	table = project.generate_project_table().collect()
	rates = (
		table.filter(pl.col("metric") == "activity")
		.group_by("genotype")
		.agg(pl.sum("value"), pl.sum("exposure"))
		.with_columns((pl.col("value") / pl.col("exposure")).alias("visits_per_hour"))
	)

	assert rates.height == 2
	assert (rates["visits_per_hour"] > 0).all()


def test_load_returns_what_generate_wrote(project):
	written = project.generate_project_table().collect()

	assert project.load_project_table(eager=True).equals(written)
	assert project.load_project_table().collect().equals(written)
	assert (project.project_location / Project.PROJECT_TABLE).is_file()


def test_load_before_generate_raises(tmp_path):
	empty = Project.create(project_name="empty", experimenter="tester", location=tmp_path / "p")
	with pytest.raises(FileNotFoundError, match="generate_project_table"):
		empty.load_project_table()


def test_generate_with_no_recordings_raises(tmp_path):
	empty = Project.create(project_name="empty", experimenter="tester", location=tmp_path / "p")
	with pytest.raises(ValueError, match="no recordings"):
		empty.generate_project_table()


def test_event_columns_are_added_and_null_for_recordings_that_declare_nothing(tmp_path_factory):
	"""One column per project event, plus Any event; null throughout for a recording
	that never declares the event, "Other hours" for one that declares it but this
	cell is neither during a bout nor at the same hour of another day.
	"""
	root = tmp_path_factory.mktemp("project_table_events")

	with_event = make_recording("with_event", ["A", "B"], "WT", "2023-05-27 00:00:00")
	with_event.events = [
		Event(
			name="Tone",
			description="a tone",
			bouts=[
				Bout(
					start=dt.datetime(2023, 5, 24, 5, 0, tzinfo=dt.UTC),
					end=dt.datetime(2023, 5, 24, 5, 10, tzinfo=dt.UTC),
				)
			],
		)
	]
	without_event = make_recording("without_event", ["X", "Y"], "KO", "2023-05-26 00:00:00")

	sources = [
		write_recording(root / "sources" / "with_event", with_event, 60),
		write_recording(root / "sources" / "without_event", without_event, 48),
	]

	project = Project.create(
		project_name="events", experimenter="tester", location=root / "project"
	)
	project.add_recordings(sources)
	project.run_analysis()

	table = project.generate_project_table().collect()

	assert "Tone" in table.columns
	assert "Any event" in table.columns

	declaring = table.filter(pl.col("recording") == "with_event")
	assert declaring.filter((pl.col("day") == 1) & (pl.col("hour") == 5))[
		"Tone"
	].unique().to_list() == ["During"]
	assert declaring.filter((pl.col("day") == 2) & (pl.col("hour") == 5))[
		"Tone"
	].unique().to_list() == ["Same hours, other days"]
	assert declaring.filter((pl.col("day") == 1) & (pl.col("hour") == 6))[
		"Tone"
	].unique().to_list() == ["Other hours"]
	assert declaring["Any event"].null_count() == 0

	silent = table.filter(pl.col("recording") == "without_event")
	assert silent["Tone"].null_count() == silent.height
	assert silent["Any event"].null_count() == silent.height


def test_names_selects_a_subset(project):
	table = project.generate_project_table(names=["wt_cohort"]).collect()
	assert set(table["recording"].unique()) == {"wt_cohort"}


def test_adding_a_trimmed_recording_warns_with_the_duration(tmp_path):
	"""Data dropped ahead of the experiment start is reported once, on add."""
	recording = strat.analysis_recording(
		tz=TZ,
		start="2023-05-24 09:30:00",
		finish="2023-05-27 00:00:00",
		phases={"light_phase": dt.time(7, 0), "dark_phase": dt.time(20, 0)},
		start_from="dark_phase",
	)
	recording.name = "late_start"
	metadata_path, data_path = write_recording(tmp_path / "src", recording, 12)

	project = Project.create(
		project_name="warns", experimenter="tester", location=tmp_path / "project"
	)
	with pytest.warns(UserWarning, match="10:30:00 of data recorded before it is left out"):
		project.add_recording(metadata_path, data_path)


def test_adding_a_late_started_recording_reports_the_short_first_phase(tmp_path):
	"""The other direction: recording began after the onset, so nothing is dropped.

	The nearest onset is the one just behind, which keeps the day that skipping forward
	would have cost, at the price of a slightly short first phase.
	"""
	recording = strat.analysis_recording(
		tz=TZ,
		# The lead has to clear LEAD_WARNING_THRESHOLD for the warning to be raised at all.
		start="2023-05-24 21:10:00",
		finish="2023-05-27 00:00:00",
		phases={"light_phase": dt.time(7, 0), "dark_phase": dt.time(20, 0)},
		start_from="dark_phase",
	)
	recording.name = "just_missed"
	metadata_path, data_path = write_recording(tmp_path / "src", recording, 12)

	assert recording.timeline.discarded_lead == dt.timedelta(0)
	project = Project.create(
		project_name="gains", experimenter="tester", location=tmp_path / "project"
	)
	with pytest.warns(UserWarning, match="started 1:10:00 into it.*no data is dropped"):
		project.add_recording(metadata_path, data_path)


@pytest.mark.parametrize(
	("start", "name"),
	[
		("2023-05-24 20:07:30", "late_by_minutes"),  # a short unrecorded lead
		("2023-05-24 19:52:30", "early_by_minutes"),  # a short discarded lead
	],
)
def test_a_lead_under_the_threshold_is_quiet(tmp_path, start, name):
	"""Acquisition is rarely started on the onset, so a few minutes either way is routine.

	The offset is still logged; it just does not warn, which is what keeps the warning
	worth reading on the recordings that are genuinely far off.
	"""
	recording = strat.analysis_recording(
		tz=TZ,
		start=start,
		finish="2023-05-27 00:00:00",
		phases={"light_phase": dt.time(7, 0), "dark_phase": dt.time(20, 0)},
		start_from="dark_phase",
	)
	recording.name = name
	metadata_path, data_path = write_recording(tmp_path / "src", recording, 12)

	line = recording.timeline
	assert (
		dt.timedelta(0) < (line.discarded_lead or line.unrecorded_lead) < dt.timedelta(minutes=30)
	)

	project = Project.create(
		project_name="quiet_lead", experimenter="tester", location=tmp_path / name
	)
	with warnings.catch_warnings():
		warnings.simplefilter("error")
		project.add_recording(metadata_path, data_path)


def test_adding_an_untrimmed_recording_is_quiet(tmp_path):
	recording = strat.analysis_recording(
		tz=TZ,
		start="2023-05-24 20:00:00",
		finish="2023-05-27 00:00:00",
		phases={"light_phase": dt.time(7, 0), "dark_phase": dt.time(20, 0)},
		start_from="dark_phase",
	)
	recording.name = "on_time"
	metadata_path, data_path = write_recording(tmp_path / "src", recording, 12)

	project = Project.create(
		project_name="quiet", experimenter="tester", location=tmp_path / "project"
	)
	with warnings.catch_warnings():
		warnings.simplefilter("error")
		project.add_recording(metadata_path, data_path)


def test_update_notes_persists_to_config_json(tmp_path):
	recording = strat.analysis_recording(
		tz=TZ, start="2023-05-24 00:00:00", finish="2023-05-25 00:00:00"
	)
	recording.name = "noted"
	metadata_path, data_path = write_recording(tmp_path / "src", recording, 6)

	project = Project.create(
		project_name="notes", experimenter="tester", location=tmp_path / "project"
	)
	project.add_recording(metadata_path, data_path)
	project["noted"].update_notes("checked the water bottles twice a day")

	reloaded = Project.load(tmp_path / "project")
	assert reloaded["noted"].notes == "checked the water bottles twice a day"
