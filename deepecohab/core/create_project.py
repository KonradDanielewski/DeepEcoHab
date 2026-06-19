import datetime as dt
from pathlib import Path
from typing import Any

import toml

from deepecohab.utils import auxfun, config_templates


def create_ecohab_project(
	project_location: str | Path,
	data_path: str | Path,
	start_datetime: str | None = None,
	finish_datetime: str | None = None,
	timezone: str | None = None,
	experiment_name: str = "ecohab_project",
	dark_phase_start: str = "12:00:00",
	light_phase_start: str = "00:00:00",
	animal_ids: list | None = None,
	custom_layout: bool = False,
	field_ecohab: bool = False,
	interpolate_positions: bool = False,
	antenna_rename_scheme: dict | None = None,
	overwrite: bool = False,
) -> tuple[Path, str | None]:
	"""Create an EcoHab project directory and write its ``config.toml``.

	The project directory is named ``<experiment_name>_<creation date>`` under
	``project_location`` and is given a ``results`` subdirectory. The layout flags
	select which config template is used: a custom antenna layout, a field EcoHab
	setup, or the default cage/tunnel layout.

	If the project already exists and ``overwrite`` is False the existing config is
	returned untouched.

	Args:
		project_location: Parent directory the project folder is created in.
		data_path: Directory holding the raw ``.txt`` registration files; must
			contain at least one ``.txt`` file.
		start_datetime: Experiment start as ``"%Y-%m-%d %H:%M:%S"``. When both start
			and finish are given the day range is derived from them; otherwise it is
			inferred from the data later.
		finish_datetime: Experiment finish in the same format as ``start_datetime``.
		timezone: IANA timezone (e.g. ``"Europe/Warsaw"``). Defaults to the local
			machine timezone when ``None``.
		experiment_name: Base name used for the project directory.
		dark_phase_start: Wall-clock time the dark phase begins.
		light_phase_start: Wall-clock time the light phase begins.
		animal_ids: Explicit list of animal ids; inferred from the data when ``None``.
		custom_layout: Use a custom antenna layout (requires ``antenna_rename_scheme``).
		field_ecohab: Use the field EcoHab config template.
		interpolate_positions: Persist the position-interpolation preference in config.
		antenna_rename_scheme: Per-board ``{old_antenna: new_antenna}`` mapping;
			required when ``custom_layout`` is True and not a field setup.
		overwrite: Overwrite an existing project config instead of loading it.

	Raises:
		FileNotFoundError: No ``.txt`` files found in ``data_path``.
		ValueError: Finish date precedes start date, or a custom layout is requested
			without an ``antenna_rename_scheme``.

	Returns:
		Tuple of the config file path and a status string: ``"created"`` for a new
		project or ``"exists"`` when an existing one was loaded.
	"""
	project_root = Path(project_location)
	data_dir = Path(data_path)

	full_project_path = auxfun.make_project_path(project_root, experiment_name)
	config_path = full_project_path / "config.toml"

	if config_path.exists() and not overwrite:
		print(f"Project already exists! Loading: {config_path}")
		return config_path, "exists"

	if not any(data_dir.glob("*.txt")):
		raise FileNotFoundError(f"No .txt files found in {data_dir}")

	days_range: list[int] | None = None
	if start_datetime and finish_datetime:
		dt_format = "%Y-%m-%d %H:%M:%S"
		start = dt.datetime.strptime(start_datetime, dt_format)
		finish = dt.datetime.strptime(finish_datetime, dt_format)

		delta_days = (finish - start).days

		if delta_days < 0:
			raise ValueError("Finish date before start date!")

		days_range = [1, delta_days + 1]

	config_kwargs = {
		"project_location": str(full_project_path),
		"experiment_name": experiment_name,
		"data_path": str(data_dir),
		"animal_ids": sorted(animal_ids) if isinstance(animal_ids, list) else None,
		"light_phase_start": light_phase_start,
		"dark_phase_start": dark_phase_start,
		"start_datetime": start_datetime,
		"finish_datetime": finish_datetime,
		"timezone": timezone,
		"days_range": days_range,
		"interpolate_positions": interpolate_positions,
	}

	if custom_layout and not field_ecohab:
		if not isinstance(antenna_rename_scheme, dict):
			raise ValueError("Custom layout requires an antenna_rename_scheme dict.")

		config_kwargs["antenna_rename_scheme"] = antenna_rename_scheme
		config_cls = config_templates.CustomConfig
	elif field_ecohab:
		config_cls = config_templates.FieldConfig
	else:
		config_cls = config_templates.DefaultConfig

	# ty cannot check **dict unpacking against a union of dataclass constructors.
	config_data: dict[str, Any] = config_cls(**config_kwargs).to_dict()  # ty: ignore[invalid-argument-type]

	full_project_path.mkdir(parents=True, exist_ok=True)
	(full_project_path / "results").mkdir(exist_ok=True)

	with open(config_path, "w") as toml_file:
		toml.dump(config_data, toml_file)

	return config_path, "created"
