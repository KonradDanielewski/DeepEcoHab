"""Tests for recording events: what the model accepts, and the event_bouts table.

An event is metadata the experimenter declares, so its table is built from the config
alone. What matters is that it lands on the same hourly cells every analysis table is
keyed by - a cell the grid does not have would never join, and a plot would shade the
wrong bin.
"""

import datetime as dt

import polars as pl
import pytest
import strategies as strat
from hypothesis import given, settings, strategies as st
from pydantic import ValidationError

from deepecohab.core import grids
from deepecohab.core.data_model import CALENDAR_COLUMNS, AnalysisParams, Bout, Event, Recording
from deepecohab.core.recording_pipeline import build_event_bouts

# Recording windows for the property test; the last two cross the EU DST transitions.
WINDOWS = [
	("2023-05-24 00:00:00", "2023-05-26 23:00:00"),
	("2023-03-24 00:00:00", "2023-03-28 23:00:00"),
	("2023-10-27 00:00:00", "2023-10-31 23:00:00"),
]


def at(day: int, hour: int, minute: int = 0, second: int = 0) -> dt.datetime:
	"""An instant on the default fixture's clock, where experiment day 1 is 2023-05-24 UTC."""
	return dt.datetime(2023, 5, 23 + day, hour, minute, second, tzinfo=dt.UTC)


def event(name: str, *bouts: Bout) -> Event:
	return Event(name=name, description="", bouts=list(bouts))


def cells(recording: Recording) -> pl.DataFrame:
	return build_event_bouts(recording, AnalysisParams()).collect()


# --- the model ---------------------------------------------------------------
def test_different_events_may_overlap():
	"""Two stimuli presented at once in opposite cages, as in the social odour test."""
	recording = strat.analysis_recording(
		events=[
			event("C21 injection", Bout(start=at(1, 13, 0, 30), end=at(1, 13, 10, 30))),
			event("social", Bout(start=at(1, 13, 30), end=at(1, 14), position="cage_1")),
			event("non-social", Bout(start=at(1, 13, 30), end=at(1, 14), position="cage_3")),
		]
	)

	assert [declared.name for declared in recording.events] == [
		"C21 injection",
		"social",
		"non-social",
	]


@pytest.mark.parametrize("end", [at(1, 13), at(1, 12, 59)])
def test_bout_must_end_after_it_starts(end):
	with pytest.raises(ValidationError, match="must end after it starts"):
		Bout(start=at(1, 13), end=end)


def test_misspelt_bout_field_is_rejected():
	"""A typo must fail rather than silently drop the bout's position."""
	with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
		Bout.model_validate({"start": at(1, 13), "end": at(1, 14), "postion": "cage_1"})


def test_event_needs_a_bout():
	with pytest.raises(ValidationError):
		Event(name="empty", description="", bouts=[])


def test_bouts_of_one_event_may_not_overlap():
	with pytest.raises(ValidationError, match="overlap"):
		event(
			"social",
			Bout(start=at(1, 13), end=at(1, 14)),
			Bout(start=at(1, 13, 30), end=at(1, 15)),
		)


def test_bouts_of_one_event_may_abut():
	"""Bouts are half-open, so one may start the instant the previous one ends."""
	event("social", Bout(start=at(1, 13), end=at(1, 14)), Bout(start=at(1, 14), end=at(1, 15)))


@pytest.mark.parametrize(
	("events", "match"),
	[
		pytest.param(
			[
				event("x", Bout(start=at(1, 1), end=at(1, 2))),
				event("x", Bout(start=at(1, 3), end=at(1, 4))),
			],
			"unique",
			id="duplicate name",
		),
		pytest.param(
			[event("x", Bout(start=at(0, 23), end=at(1, 1)))], "outside", id="before the window"
		),
		pytest.param(
			[event("x", Bout(start=at(3, 22), end=at(4, 0)))], "outside", id="after the window"
		),
		pytest.param(
			[event("x", Bout(start=at(1, 1), end=at(1, 2), position="cage_9"))],
			"layout does not have",
			id="unknown position",
		),
		pytest.param(
			[event("x", Bout(start=at(1, 1), end=at(1, 2), position="undefined"))],
			"layout does not have",
			id="undefined sentinel",
		),
	],
)
def test_recording_rejects_events_it_cannot_place(events, match):
	with pytest.raises(ValidationError, match=match):
		strat.analysis_recording(events=events)


def test_config_without_events_still_loads():
	"""Configs written before events existed have no such key."""
	recording = strat.analysis_recording()
	config = recording.to_config()
	del config["events"]

	assert Recording.model_validate({**config, "data": recording.data}).events == []


def test_events_survive_a_config_round_trip():
	recording = strat.analysis_recording(
		events=[event("social", Bout(start=at(1, 13), end=at(1, 14), position="cage_1"))]
	)
	restored = Recording.model_validate({**recording.to_config(), "data": recording.data})

	assert restored.events == recording.events


# --- the event_bouts table ---------------------------------------------------
def test_short_bout_takes_one_cell_and_keeps_its_bounds():
	recording = strat.analysis_recording(
		events=[event("C21", Bout(start=at(1, 13, 0, 30), end=at(1, 13, 10, 30)))]
	)
	frame = cells(recording)
	row = frame.row(0, named=True)

	assert frame.select(CALENDAR_COLUMNS).rows() == [("dark_phase", 1, 2, 13)]
	assert (row["event"], row["position"], row["start"], row["end"]) == (
		"C21",
		None,
		at(1, 13, 0, 30),
		at(1, 13, 10, 30),
	)


def test_bout_ending_on_the_hour_stays_out_of_the_next():
	recording = strat.analysis_recording(
		events=[event("x", Bout(start=at(1, 13, 30), end=at(1, 14)))]
	)

	assert cells(recording)["hour"].to_list() == [13]


def test_bout_across_midnight_takes_a_cell_on_each_day():
	recording = strat.analysis_recording(
		events=[event("x", Bout(start=at(1, 23, 30), end=at(2, 0, 30)))]
	)

	assert cells(recording).select(CALENDAR_COLUMNS).rows() == [
		("dark_phase", 1, 2, 23),
		("light_phase", 2, 3, 0),
	]


def test_phase_boundary_inside_an_hour_splits_its_cell():
	"""With dark at 12:30 the 12:00 bin holds two phases, and the bout touches both."""
	recording = strat.analysis_recording(
		phases={"light_phase": dt.time(0, 0), "dark_phase": dt.time(12, 30)},
		events=[event("x", Bout(start=at(1, 12, 10), end=at(1, 12, 50)))],
	)

	assert cells(recording).select(CALENDAR_COLUMNS).rows() == [
		("light_phase", 1, 1, 12),
		("dark_phase", 1, 2, 12),
	]


def test_offset_datetimes_land_on_the_recording_clock():
	"""The TODO example: a Warsaw recording whose 13:00 dark onset is hour 0."""
	injection = Bout.model_validate(
		{"start": "2023-05-17T13:00:30+02:00", "end": "2023-05-17T13:10:30+02:00"}
	)
	recording = strat.analysis_recording(
		tz="Europe/Warsaw",
		start="2023-05-17 13:02:41",
		finish="2023-05-22 10:02:17",
		phases={"light_phase": dt.time(1, 0), "dark_phase": dt.time(13, 0)},
		start_from="dark_phase",
		events=[event("C21 injection", injection)],
	)
	frame = cells(recording)

	assert frame.select(CALENDAR_COLUMNS).rows() == [("dark_phase", 1, 1, 0)]
	assert frame.schema["start"] == pl.Datetime("us", time_zone="Europe/Warsaw")


def test_bout_instants_do_not_depend_on_the_offset_they_are_written_in():
	"""Polars must convert a bout's offset into the recording's zone, not relabel it.

	Config datetimes keep whatever offset they were written in. This bout straddles the
	spring-forward, so even its local notation changes offset between start and end.
	"""
	start = dt.datetime(2023, 3, 26, 0, 30, tzinfo=dt.UTC)
	end = dt.datetime(2023, 3, 26, 1, 30, tzinfo=dt.UTC)
	tables = []

	for start_offset, end_offset in [(1, 2), (0, 0), (-4, -4)]:
		bout = Bout.model_validate(
			{
				"start": start.astimezone(
					dt.timezone(dt.timedelta(hours=start_offset))
				).isoformat(),
				"end": end.astimezone(dt.timezone(dt.timedelta(hours=end_offset))).isoformat(),
			}
		)
		recording = strat.analysis_recording(
			tz="Europe/Warsaw",
			start="2023-03-24 00:00:00",
			finish="2023-03-28 23:00:00",
			events=[event("x", bout)],
		)
		tables.append(cells(recording))

	assert all(table.equals(tables[0]) for table in tables)
	assert tables[0].select("start", "end").row(0) == (start, end)


def test_no_events_give_an_empty_table_with_its_schema():
	frame = cells(strat.analysis_recording())

	assert frame.is_empty()
	assert frame.columns == ["event", "position", "start", "end", *CALENDAR_COLUMNS]


@settings(max_examples=60, deadline=None)
@given(
	tz=strat.timezones,
	phases=strat.phase_configs,
	window=st.sampled_from(WINDOWS),
	spans=st.lists(
		st.tuples(st.integers(0, 60 * 3600), st.integers(1, 30 * 3600)), min_size=1, max_size=4
	),
)
def test_every_bout_cell_is_a_grid_cell(tz, phases, window, spans):
	"""A cell the grid lacks would never join onto an analysis table, nor match a plot's bin."""
	first, last = window
	bare = strat.analysis_recording(tz=tz, start=first, finish=last, phases=phases)
	start, end = (moment.astimezone(dt.UTC) for moment in bare.timeline.local_span)
	events = [
		event(
			f"e{index}",
			Bout(
				start=start + dt.timedelta(seconds=offset),
				end=min(start + dt.timedelta(seconds=offset + length), end),
			),
		)
		for index, (offset, length) in enumerate(spans)
	]
	recording = strat.analysis_recording(
		tz=tz, start=first, finish=last, phases=phases, events=events
	)

	grid = grids.build_time_grid(recording).collect()

	assert cells(recording).join(grid, on=list(CALENDAR_COLUMNS), how="anti").is_empty()
