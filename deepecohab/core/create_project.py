import datetime as dt
from pathlib import Path
import toml
from deepecohab.utils import auxfun, config_templates

def create_ecohab_project(
    project_location: str | Path,
    data_path: str | Path,
    start_datetime: str | None = None,
    finish_datetime: str | None = None,
    experiment_name: str = "ecohab_project",
    dark_phase_start: str = "12:00:00",
    light_phase_start: str = "00:00:00",
    animal_ids: list | None = None,
    custom_layout: bool = False,
    field_ecohab: bool = False,
    antenna_rename_scheme: dict | None = None,
) -> Path:
    """Creates the ecohab project directory and config."""
    project_root = Path(project_location)
    data_dir = Path(data_path)
    
    full_project_path = auxfun.make_project_path(project_root, experiment_name)
    config_path = full_project_path / "config.toml"

    if config_path.exists():
        print(f"Project already exists! Loading: {config_path}")
        return config_path
    
    if not any(data_dir.glob("*.txt")):
        raise FileNotFoundError(f"No .txt files found in {data_dir}")

    days_range = None
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
        "days_range": days_range,
    }

    if (field_ecohab or custom_layout):
        if not isinstance(antenna_rename_scheme, dict):
            raise ValueError("Custom or field layout requires an antenna_rename_scheme dict.")
        
        config_kwargs["antenna_rename_scheme"] = antenna_rename_scheme
        config_cls = config_templates.FieldConfig if field_ecohab else config_templates.CustomConfig
    else:
        config_cls = config_templates.DefaultConfig

    config_data = config_cls(**config_kwargs).to_dict()

    full_project_path.mkdir(parents=True, exist_ok=True)
    (full_project_path / "results").mkdir(exist_ok=True)

    with open(config_path, "w") as toml_file:
        toml.dump(config_data, toml_file)

    return config_path