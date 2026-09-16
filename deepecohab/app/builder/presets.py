"""Built-in plot builder presets.

Presets are full builder states as JSON, the same shape ``pages/builder.py`` keeps in
``dcc.Store``. Six ship with the package, naming only fields every project has. A
project-specific part - which event, or the days every recording shares - is resolved
against the open project rather than stored, so the same preset works everywhere.
"""

import copy
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
	from deepecohab import Project

#: The literal a slot substitutes wherever it appears in a preset's state.
EVENT_SLOT = "$event"


@dataclass(frozen=True)
class Preset:
	"""One built-in preset.

	Attributes:
		id: stable key, also used as the saved-preset id prefix.
		name: display name.
		description: what the preset shows and why.
		state: the builder state, with ``slot_key`` standing in for a project-specific
			field name where one is needed.
		slot_key: the placeholder :func:`resolve` substitutes, or ``None``.
		slot_label: what the slot picker asks.
		compute_filters: extra filters worked out from the project when the preset
			opens, merged over ``state["filters"]``.
	"""

	id: str
	name: str
	description: str
	state: dict[str, Any]
	slot_key: str | None = None
	slot_label: str = ""
	compute_filters: "Callable[[Project], dict[str, Any]] | None" = None


def shared_days(project: "Project") -> dict[str, Any]:
	"""A ``day`` filter picking only the days every recording in the project has.

	Pick-mode values are always strings: ``figure.apply_filters`` matches them against
	the column cast to ``String``, the same convention the filter widgets themselves use.
	"""
	shared = min(recording.timeline.days_range[1] for recording in project.recordings)
	return {"day": {"mode": "pick", "values": [str(day) for day in range(1, shared + 1)]}}


BUILTINS: tuple[Preset, ...] = (
	Preset(
		"time-alone-genotype-sex",
		"Time alone by genotype and sex",
		"One point per animal: its share of observed time spent without company.",
		{
			"measure_as": "rate",
			"kind": "box",
			"channels": {
				"x": ["genotype"],
				"y": ["value"],
				"color": ["sex"],
				"detail": ["recording", "animal_id"],
			},
			"filters": {"metric": {"mode": "pick", "values": ["time_alone"]}},
		},
	),
	Preset(
		"circadian-activity",
		"Circadian activity by genotype",
		"Visits per hour across the 24 hours after phase onset, pooled per genotype.",
		{
			"measure_as": "rate",
			"kind": "line",
			"channels": {"x": ["hour"], "y": ["value"], "color": ["genotype"]},
			"filters": {"metric": {"mode": "pick", "values": ["activity"]}},
		},
	),
	Preset(
		"together-shared-days",
		"Time together over the shared days",
		"Only the days every recording has, worked out from the project when the preset opens.",
		{
			"measure_as": "rate",
			"kind": "line",
			"channels": {
				"x": ["day"],
				"y": ["value"],
				"color": ["genotype"],
				"facet_col": ["sex"],
			},
			"filters": {"metric": {"mode": "pick", "values": ["time_together"]}},
		},
		compute_filters=shared_days,
	),
	Preset(
		"light-dark-metrics",
		"Light vs dark, four metrics",
		"Metric on Facet row gives every metric its own axis and unit, so Value never pools units.",
		{
			"measure_as": "rate",
			"kind": "box",
			"channels": {
				"x": ["phase"],
				"y": ["value"],
				"color": ["genotype"],
				"facet_row": ["metric"],
				"detail": ["recording", "animal_id"],
			},
			"filters": {
				"metric": {
					"mode": "pick",
					"values": ["activity", "time_alone", "time_together", "n_chasing"],
				}
			},
		},
	),
	Preset(
		"event-activity",
		"Activity around an event",
		"Asks which event when it opens: hours a bout touches against the same clock hours on other days.",
		{
			"measure_as": "rate",
			"kind": "box",
			"channels": {
				"x": [EVENT_SLOT],
				"y": ["value"],
				"color": ["genotype"],
				"detail": ["recording", "animal_id"],
			},
			"filters": {"metric": {"mode": "pick", "values": ["activity"]}},
		},
		slot_key=EVENT_SLOT,
		slot_label="Which event?",
	),
	Preset(
		"chasing-cohort-size",
		"Chasing against cohort size",
		"One point per recording: are larger cohorts more aggressive per available partner?",
		{
			"measure_as": "rate",
			"kind": "scatter",
			"channels": {
				"x": ["n_mice"],
				"y": ["value"],
				"color": ["genotype"],
				"symbol": ["sex"],
				"detail": ["recording"],
			},
			"filters": {"metric": {"mode": "pick", "values": ["n_chasing"]}},
		},
	),
)

BY_ID: dict[str, Preset] = {preset.id: preset for preset in BUILTINS}


def resolve(preset: Preset, project: "Project", choice: str | None = None) -> dict[str, Any]:
	"""The preset's state ready to load into the builder.

	Args:
		preset: the preset to resolve.
		project: the open project, for its computed filters.
		choice: the value to substitute for ``preset.slot_key``, when it has one.

	Returns:
		A fresh builder state; the preset itself is never mutated.
	"""
	state = copy.deepcopy(preset.state)

	if preset.slot_key and choice:
		text = json.dumps(state).replace(json.dumps(preset.slot_key), json.dumps(choice))
		state = json.loads(text)

	if preset.compute_filters is not None:
		state["filters"] = {**state["filters"], **preset.compute_filters(project)}

	return state
