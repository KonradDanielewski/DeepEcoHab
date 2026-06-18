"""Tests for the config dataclasses in deepecohab.utils.config_templates.

These build phase/timeline dicts and load antenna/tunnel layouts from the
packaged deepecohab/config/*.toml (via _load_config).
"""

import strategies as strat
from hypothesis import given

from deepecohab.utils.config_templates import CustomConfig, DefaultConfig, FieldConfig

BASE = {
	"project_location": "proj",
	"experiment_name": "exp",
	"data_path": "data",
	"animal_ids": ["A", "B"],
	"dark_phase_start": "20:00:00",
	"light_phase_start": "07:00:00",
}

REQUIRED_KEYS = {
	"project_location",
	"experiment_name",
	"data_path",
	"animal_ids",
	"phase",
	"experiment_timeline",
	"timezone",
	"days_range",
	"antenna_combinations",
	"tunnels",
}


@given(light=strat.time_strings_hms, dark=strat.time_strings_hms)
def test_phase_mapping_from_times(light, dark):
	"""Phase maps light_phase/dark_phase to the provided start strings."""
	cfg = DefaultConfig(**{**BASE, "light_phase_start": light, "dark_phase_start": dark}).to_dict()
	assert cfg["phase"] == {"light_phase": light, "dark_phase": dark}


def test_to_dict_has_required_keys_and_timeline():
	cfg = DefaultConfig(
		**BASE, start_datetime="2023-05-01 00:00:00", finish_datetime="2023-05-10 00:00:00"
	).to_dict()
	assert set(cfg) >= REQUIRED_KEYS
	assert cfg["experiment_timeline"] == {
		"start_date": "2023-05-01 00:00:00",
		"finish_date": "2023-05-10 00:00:00",
	}


def test_interpolate_positions_selects_different_antenna_combinations():
	"""interpolate_positions toggles which packaged layout is loaded."""
	default = DefaultConfig(**BASE, interpolate_positions=False).to_dict()
	interp = DefaultConfig(**BASE, interpolate_positions=True).to_dict()
	assert default["antenna_combinations"]
	assert interp["antenna_combinations"]
	assert default["antenna_combinations"] != interp["antenna_combinations"]


def test_custom_config_includes_rename_scheme():
	scheme = {"COM1": {"1": 1, "2": 2}}
	cfg = CustomConfig(**BASE, antenna_rename_scheme=scheme).to_dict()
	assert cfg["antenna_rename_scheme"] == scheme


def test_field_config_has_16_antenna_com_scheme():
	cfg = FieldConfig(**BASE).to_dict()
	scheme = cfg["antenna_rename_scheme"]
	assert set(scheme) == {"COM1", "COM2", "COM3", "COM4"}
	assert scheme["COM4"]["4"] == 16
	# Field layout differs from the default antenna_combinations.
	assert cfg["antenna_combinations"] == FieldConfig(**BASE).to_dict()["antenna_combinations"]
