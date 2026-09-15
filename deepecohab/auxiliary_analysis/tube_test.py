import datetime as dt
from typing import Literal

import polars as pl

from deepecohab.core import grids, transforms
from deepecohab.core.data_model import CALENDAR_COLUMNS, Recording


def _tunnel_entry_by_antenna(recording: Recording) -> dict[str, str]:
	"""Map from each antenna to the directional tunnel a crossing there leads into.

	``antenna_combinations`` is keyed ``"<previous>_<current>"``, so ``"1_2" -> "c1_c2"`` says
	that tunnel is entered at antenna 1; inverting on the first component gives the
	tunnel per antenna. Antennas with no candidate tunnel, or with several, are left
	out: several means the antenna is not at a tunnel mouth, and there the in-and-out
	reading of a repeat read does not hold.
	"""
	tunnels_map = recording.layout.tunnels_map
	candidates: dict[str, set[str]] = {}

	for antenna_pair, position in recording.layout.antenna_combinations.items():
		if position not in tunnels_map:  # a cage, so not a tunnel traversal
			continue
		entry_antenna = antenna_pair.split("_", 1)[0]
		candidates.setdefault(entry_antenna, set()).add(position)

	return {
		antenna: next(iter(positions))
		for antenna, positions in candidates.items()
		if len(positions) == 1
	}


def _resolve_repeat_reads(registrations: pl.LazyFrame, recording: Recording) -> pl.LazyFrame:
	"""Frame with the return half of a repeat antenna read relabelled as tunnel time.

	Antennas sit at tunnel mouths, so two consecutive reads on one antenna are a
	single in-and-out excursion whose interval was spent inside the tunnel - yet
	``antenna_combinations`` maps that pair to the adjacent cage. Crossings alternate within a
	run of reads on one antenna, so every second row is a return and is relabelled to
	the tunnel that antenna leads into. This is the only evidence a retreat leaves.

	Only :func:`calculate_tube_test` uses this; see
	``docs/technical_documentation_writeup.md``.
	"""
	entry_tunnels = _tunnel_entry_by_antenna(recording)
	if not entry_tunnels:
		return registrations

	# Null for an antenna with no unambiguous tunnel, leaving the position untouched below.
	# Both when/then branches are evaluated column-wide, so replace_strict needs the default.
	entered_tunnel = pl.col("antenna").cast(pl.Utf8).replace_strict(entry_tunnels, default=None)

	return (
		registrations.with_columns(
			pl.struct("position", "antenna").rle_id().over("animal_id").alias("__run_id")
		)
		.with_columns(pl.int_range(pl.len()).over("animal_id", "__run_id").alias("__readout"))
		.with_columns(
			pl.when(pl.col("__readout").mod(2).eq(1) & entered_tunnel.is_not_null())
			.then(entered_tunnel.cast(pl.Categorical))
			.otherwise(pl.col("position"))
			.alias("position")
		)
		.drop("__run_id", "__readout")
	)


def _attach_pass(
	encounters: pl.LazyFrame, passes: pl.LazyFrame, animal_column: str, suffix: str
) -> pl.LazyFrame:
	"""Frame of encounters with one animal's tunnel pass attached.

	Spans within a stitched encounter are contiguous and hold two occupants
	throughout, so the pass wanted is that animal's latest one starting at or before
	the contact began.
	"""
	payload = ["direction", "previous_position", "next_position", "start", "end", *CALENDAR_COLUMNS]
	side = passes.rename(
		{"animal_id": animal_column} | {column: f"{column}{suffix}" for column in payload}
	).sort(f"start{suffix}")

	return encounters.sort("contact_start").join_asof(
		side,
		left_on="contact_start",
		right_on=f"start{suffix}",
		by=[animal_column, "position"],
		strategy="backward",
		# Both sides are globally sorted on the as-of key, which polars cannot verify per group.
		check_sortedness=False,
	)


def _orient_encounter(encounters: pl.LazyFrame, loser: str, winner: str) -> pl.LazyFrame:
	"""Frame casting each encounter into one candidate winner and loser orientation.

	Each encounter carries both animals' passes with no roles attached; both
	orientations are emitted and the retreat rules in :func:`calculate_tube_test` keep
	at most one. The calendar columns come from the winner's pass, so an encounter
	straddling an hour, phase or day boundary lands in exactly one cell.
	"""
	return encounters.select(
		"position",
		pl.col(f"animal_{winner}").alias("winner"),
		pl.col(f"animal_{loser}").alias("loser"),
		pl.col(f"direction_{loser}").alias("direction"),
		pl.col(f"direction_{winner}").alias("direction_winner"),
		pl.col(f"previous_position_{loser}").alias("previous_position"),
		pl.col(f"next_position_{loser}").alias("next_position"),
		pl.col(f"previous_position_{winner}").alias("previous_position_winner"),
		pl.col(f"next_position_{winner}").alias("next_position_winner"),
		pl.col(f"end_{loser}").alias("loser_exit"),
		pl.col(f"end_{winner}").alias("winner_exit"),
		*[pl.col(f"{column}_{winner}").alias(column) for column in CALENDAR_COLUMNS],
	)


def calculate_tube_test(
	recording: Recording,
	max_dwell: float,
	winner_behavior: Literal["CHASE", "GUARD", "BOTH"],
) -> pl.LazyFrame:
	"""Frame counting tube test events per pair of animals, tunnel and hour.

	A tube test event is a head-on tunnel encounter: two animals hold the same tunnel
	at overlapping times having entered from opposite ends, and the loser backs out to
	the cage it came from. Contact comes from a sweep over real time overlap rather
	than a join on calendar columns, and contiguous spans of the same pair are
	stitched into one encounter.

	This is not a pipeline step: it reads ``main_df`` but is called explicitly, and
	sinking it to ``results/tube_test_df.parquet`` - which is what makes it readable
	afterwards by :meth:`Recording.load_results` and the plots - is the caller's call.

	Args:
		recording: the recording to score, with ``main_df`` already built.
		winner_behavior: which outcomes count - ``"CHASE"`` where the winner follows the
			loser into the cage it retreated to, ``"GUARD"`` where the winner returns to
			its own origin cage to hold the resource, or ``"BOTH"``.
		max_dwell: how long a tunnel pass may last, in seconds, keeping out the inflated
			intervals left by an animal lingering at a tunnel mouth.

	Returns:
		A ``tube_test`` count per winner, loser, tunnel and hour, on the dense grid.
	"""
	# Sorted at load so the order-dependent ops below (run-length encoding, shift().over) are chronological.
	registrations = recording.load_results("main_df").sort("datetime")

	tunnels = recording.layout.tunnel_names

	# One row per tunnel pass with the exact [start, end) bounds the sweep needs. `direction`
	# survives de-directionalisation and names the end entered from, which is the head-on test;
	# previous/next are taken before the tunnel filter, so they are the cages either side.
	passes = (
		_resolve_repeat_reads(registrations, recording)
		.with_columns(pl.col("position").alias("direction"))
		.pipe(transforms.remove_tunnel_directionality, recording)
		.with_columns(
			pl.col("position").shift(1).over("animal_id").alias("previous_position"),
			pl.col("position").shift(-1).over("animal_id").alias("next_position"),
		)
		.pipe(transforms.add_occupancy_bounds)
		.filter(
			pl.col("position").is_in(tunnels),
			pl.col("time_spent") <= dt.timedelta(seconds=max_dwell),
		)
		.select(
			"animal_id",
			"position",
			"direction",
			"previous_position",
			"next_position",
			"start",
			"end",
			*CALENDAR_COLUMNS,
		)
	)

	# Each stitched encounter is one contact, so its bounds are the first and last of its spans.
	encounters = (
		transforms.cooccupancy_spans(passes)
		.group_by("animal_id", "animal_id_2", "position", "meeting_id")
		.agg(pl.min("time").alias("contact_start"), pl.max("end").alias("contact_end"))
		.rename({"animal_id": "animal_a", "animal_id_2": "animal_b"})
	)

	encounters = _attach_pass(encounters, passes, "animal_a", "_a")
	encounters = _attach_pass(encounters, passes, "animal_b", "_b")
	# The recovered pass must span the whole contact, which it always does for one the sweep
	# produced. This asserts that, and keeps a zero-length interval out: its enter and leave
	# land on the same instant, so it can be ordered either way against a span boundary.
	encounters = encounters.filter(
		pl.col("end_a") >= pl.col("contact_end"), pl.col("end_b") >= pl.col("contact_end")
	)

	oriented = pl.concat(
		[
			_orient_encounter(encounters, loser="a", winner="b"),
			_orient_encounter(encounters, loser="b", winner="a"),
		]
	)

	# GUARD: the winner returns to its own origin cage. That is also the winner backing out,
	# so it doubles as the mutual-retreat test in the filter below.
	guard = pl.col("next_position_winner") == pl.col("previous_position_winner")
	# CHASE: the winner ends up in the cage the loser retreated to.
	chase = pl.col("next_position_winner") == pl.col("next_position")

	tube_events = oriented.filter(
		# head-on: the two entered the same tunnel from opposite ends
		pl.col("direction") != pl.col("direction_winner"),
		# the loser is the one that backed out to the cage it came from
		pl.col("next_position") == pl.col("previous_position"),
		# if the winner backed out too, the one that left first is the loser
		~guard | (pl.col("loser_exit") < pl.col("winner_exit")),
	)

	match winner_behavior:
		case "CHASE":
			tube_events = tube_events.filter(chase)
		case "GUARD":
			tube_events = tube_events.filter(guard)
		case "BOTH":
			tube_events = tube_events.filter(chase | guard)

	tube_test = tube_events.group_by([*CALENDAR_COLUMNS, "position", "winner", "loser"]).len(
		name="tube_test"
	)

	return grids.reindex_onto_grid(
		tube_test,
		recording,
		("winner", "loser"),
		ordered=True,
		positions=recording.layout.tunnel_names,
	)
