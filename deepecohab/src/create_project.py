import datetime as dt
import os
from pathlib import Path

import pandas as pd
import toml

from deepecohab.src import config_templates
from deepecohab.utils.auxfun import get_data_paths

def get_animal_ids(data_path: str) -> list:
    """Auxfun to read animal IDs from the data if not provided
    """    
    data_files = get_data_paths(data_path)
    
    dfs = [pd.read_csv(file, delimiter="\t", names=["ind", "date", "time", "antenna", "time_under", "animal_id"]) for file in data_files[:10]]
    animal_ids = pd.concat(dfs).animal_id.unique()
    return animal_ids

def make_project_path(project_location: str, project_name: str):
    """Auxfun to make a name of the project directory using its name and time of creation
    """    
    project_name = project_name + "_" + dt.datetime.today().strftime('%Y-%m-%d')
    project_location = Path(project_location) / project_name

    return str(project_location)

def create_ecohab_project(
    project_location: str | Path,
    data_path: str | Path,
    start_datetime: str,
    finish_datetime: str,
    experiment_name: str = "ecohab_project",
    dark_phase_start: str = "12:00:00",
    light_phase_start: str = "23:59:59.999",
    animal_ids: list | None = None,
    custom_layout: bool = False,
    field_ecohab: bool = False,
    antenna_rename_scheme: dict | None = None,
    ) -> str:
    """Creates the ecohab project directory and config

    Args:
        project_location: path to where the project should be created.
        data_path: path to directory that contains raw data (COMxxxxx.txt files).
        start_datetime: full date and time of the proper start of the experiment. Defaults to "yyyy-mm-dd HH:MM:SS.ffffff". If not provided data is taken as is
        finish_datetime: full date and time of the proper end of the experiment. Defaults to "yyyy-mm-dd HH:MM:SS.ffffff". If not provided data is taken as is
        experiment_name: name of the experiment. Defaults to "ecohab_project".
        dark_phase_start: hour, minute, second, milisecond of the dark phase start. Defaults to "23:59:59:999".
        light_phase_start: hour, minute and second of the light phase start. Defaults to "12:00:00".
        animal_ids: if not provided reads animal ids from the first file with data. Defaults to [].
        custom_layout: change to True if using multiple boards at the same time during one recordig with a custom arena geometry. Defaults to False.
        field_ecohab: change to True if the data is from a field ecohab. Defaults to False.
        antenna_rename_scheme: a dictionary that contains per comport renaming scheme - used when using multiple boards in one setup. Defaults to None.

    Raises:
        TypeError: When custom or field layout but renaming scheme not provided
        FileNotFoundError: When the project config not found in location

    Returns:
        config_path: path to config file 
    """

    if not isinstance(project_location, (str, Path)):
        print("Project location not provided")
        return
    if not isinstance(data_path, (str, Path)):
        print("Project location not provided")
        return
    if len(os.listdir(data_path)) == 0:
        print(f"{data_path} is empty, please check if you provided the correct directory")
        return
    
    if not isinstance(project_location, str): # Has to be a string for config purposes
        data_path = str(data_path)

    project_location = make_project_path(project_location, experiment_name)
    
    if not isinstance(animal_ids, list):
        animal_ids = get_animal_ids(data_path)

    if field_ecohab and isinstance(antenna_rename_scheme, dict):
        config = config_templates.generate_field_config(
            project_location=project_location,
            experiment_name=experiment_name,
            data_path=data_path,
            animal_ids=animal_ids,
            light_phase_start=light_phase_start,
            dark_phase_start=dark_phase_start,
            start_datetime=start_datetime,
            finish_datetime=finish_datetime,
            antenna_rename_scheme=antenna_rename_scheme,
            )

    elif custom_layout and isinstance(antenna_rename_scheme, dict):
        config = config_templates.generate_custom_config(
            project_location=project_location,
            experiment_name=experiment_name,
            data_path=data_path,
            animal_ids=animal_ids,
            light_phase_start=light_phase_start,
            dark_phase_start=dark_phase_start,
            start_datetime=start_datetime,
            finish_datetime=finish_datetime,
            antenna_rename_scheme=antenna_rename_scheme,
            )
    
    elif custom_layout or field_ecohab and not isinstance(antenna_rename_scheme, dict):
        raise TypeError("Chosen custom layout/field layout but antenna renaming graph not provided!")
    
    else:
        config = config_templates.generate_default_config(
            project_location=project_location,
            experiment_name=experiment_name,
            data_path=data_path,
            animal_ids=animal_ids,
            light_phase_start=light_phase_start,
            dark_phase_start=dark_phase_start,
            start_datetime=start_datetime,
            finish_datetime=finish_datetime,
            )
    
    # Remake into Path here for safety
    project_location = Path(project_location) 
    data_path = Path(data_path)
    
    # Check/make the project directory
    if os.path.exists(project_location):
        print("Project already exists! Loading existing project config.")
        config_path = project_location / "config.toml"
        if config_path.exists():
            return config_path
        else:
            raise FileNotFoundError(f"Config file not found in {project_location}!")
    else:
        os.mkdir(project_location)
        os.mkdir(project_location / "plots")
        os.mkdir(project_location / "data")
    
    # Create the toml
    config_path = project_location / "config.toml"
    with open(config_path, "w") as toml_file:
        toml.dump(config, toml_file)

    return config_path