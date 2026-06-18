from abc import ABC
from dataclasses import dataclass, field
from importlib import resources

import toml


@dataclass
class ExperimentConfig(ABC):
	"""Template for an experiment configuration.

	Attributes:
		project_location: location of the project
		experiment_name: name of the experiment
		data_path: directory containing the antenna reads
		animal_ids: RFID tag hex codes for animals
		dark_phase_start: start time of the dark phase (light off)
		light_phase_start: start time of the light phase (light on)
		start_datetime: date and time of the experiment start - data will be
			pruned to match
		finish_datetime: date and time of the experiment end - data will be
			pruned to match
		antenna_combinations: per-comport renaming scheme, used when combining
			reads from multiple boards in one setup
	"""

	project_location: str
	experiment_name: str
	data_path: str
	animal_ids: list[str]
	dark_phase_start: str
	light_phase_start: str
	days_range: list[int] | None = None
	start_datetime: str | None = None
	finish_datetime: str | None = None
	timezone: str = None
	antenna_combinations: dict[str, str] = field(default_factory=dict)
	tunnels: dict[str, str] = field(default_factory=dict)
	phase: dict[str, str] = field(init=False)
	experiment_timeline: dict[str, str | None] = field(init=False)
	interpolate_positions: bool = False

	def __post_init__(self):
		self.phase = {
			"light_phase": self.light_phase_start,
			"dark_phase": self.dark_phase_start,
		}
		self.experiment_timeline = {
			"start_date": self.start_datetime,
			"finish_date": self.finish_datetime,
		}

	def _load_config(self, config_name: str, interp_key: str, default_key: str) -> dict:
		with resources.open_text("deepecohab.config", f"{config_name}.toml") as f:
			cfg = toml.load(f)
		return cfg[interp_key] if self.interpolate_positions else cfg[default_key]

	def to_dict(self) -> dict:
		"""Serialize the config to a plain dict ready to write to TOML."""
		data = {}
		data["project_location"] = self.project_location
		data["experiment_name"] = self.experiment_name
		data["data_path"] = self.data_path
		data["animal_ids"] = self.animal_ids
		data["phase"] = self.phase
		data["experiment_timeline"] = self.experiment_timeline
		data["timezone"] = self.timezone
		data["days_range"] = self.days_range
		data["antenna_combinations"] = self.antenna_combinations
		data["tunnels"] = self.tunnels

		scheme = getattr(self, "antenna_rename_scheme", None)
		if scheme is not None:
			data["antenna_rename_scheme"] = scheme
		return data


@dataclass
class DefaultConfig(ExperimentConfig):
	"""Generates default config."""

	def __post_init__(self):
		super().__post_init__()
		self.antenna_combinations = self._load_config(
			"antenna_combinations", "default_interp", "default"
		)
		self.tunnels = self._load_config("tunnels", "default_interp", "default")


@dataclass
class CustomConfig(DefaultConfig):
	"""Generates custom config for arbitrary."""

	antenna_rename_scheme: dict[str, dict[str, int]] = field(default_factory=dict)

	def __post_init__(self):
		super().__post_init__()
		print(
			"Please update the geometry information in the config according to your antenna layout!"
		)
		print(
			"Antennas will be automatically renamed following your naming scheme on a per COM name basis."
		)


@dataclass
class FieldConfig(CustomConfig):
	"""Generates config for field ecohab."""

	def __post_init__(self):
		super().__post_init__()
		self.antenna_combinations = self._load_config(
			"antenna_combinations", "field_interp", "field"
		)
		self.tunnels = self._load_config("tunnels", "field_interp", "field")
		self.antenna_rename_scheme = {
			"COM1": {
				"1": 1,
				"2": 2,
				"3": 3,
				"4": 4,
			},
			"COM2": {
				"1": 5,
				"2": 6,
				"3": 7,
				"4": 8,
			},
			"COM3": {
				"1": 9,
				"2": 10,
				"3": 11,
				"4": 12,
			},
			"COM4": {
				"1": 13,
				"2": 14,
				"3": 15,
				"4": 16,
			},
		}
