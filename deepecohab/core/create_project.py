from datetime import datetime
from pathlib import Path

import toml

from deepecohab.utils import config_templates
from deepecohab.utils import auxfun

def create_ecohab_project(
    project_location: str | Path,
    data_path: str | Path,
    start_datetime: str | None = None,
    finish_datetime: str | None = None,
    experiment_name: str = 'ecohab_project',
    dark_phase_start: str = '12:00:00',
    light_phase_start: str = '23:59:59.999',
    animal_ids: list | None = None,
    custom_layout: bool = False,
    field_ecohab: bool = False,
    antenna_rename_scheme: dict | None = None,
    ) -> str:
    """Creates the ecohab project directory and config

    Args:
        project_location: path to where the project should be created.
        data_path: path to directory that contains raw data (COMxxxxx.txt files).
        start_datetime: full date and time of the proper start of the experiment. Defaults to 'yyyy-mm-dd HH:MM:SS.ffffff'. If not provided data is taken as is
        finish_datetime: full date and time of the proper end of the experiment. Defaults to 'yyyy-mm-dd HH:MM:SS.ffffff'. If not provided data is taken as is
        experiment_name: name of the experiment. Defaults to 'ecohab_project'.
        dark_phase_start: hour, minute, second, milisecond of the dark phase start. Defaults to '23:59:59:999'.
        light_phase_start: hour, minute and second of the light phase start. Defaults to '12:00:00'.
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
        print('Project location not provided')
        return
    if not isinstance(data_path, (str, Path)):
        print('Data location not provided')
        return
    if len(list(Path(data_path).glob('*.txt'))) == 0:
        print(f'{data_path} is empty, please check if you provided the correct directory')
        return
    dt_format = '%Y-%m-%d %H:%M:%S'
    check_date = (datetime.strptime(finish_datetime, dt_format) - 
                  datetime.strptime(start_datetime, dt_format)).days < 0
    
    if check_date:
        raise ValueError('Finish date before start date! Please check provided dates.')
    
    if not isinstance(project_location, str): # Has to be a string for config purposes
        data_path = str(data_path)

    project_location = auxfun.make_project_path(project_location, experiment_name)
    
    if not isinstance(animal_ids, list):
        animal_ids = sorted(auxfun.get_animal_ids(data_path))
    else:
        animal_ids = sorted(animal_ids)

    if field_ecohab and isinstance(antenna_rename_scheme, dict):
        config = config_templates.FieldConfig(
            project_location=project_location,
            experiment_name=experiment_name,
            data_path=data_path,
            animal_ids=animal_ids,
            light_phase_start=light_phase_start,
            dark_phase_start=dark_phase_start,
            start_datetime=start_datetime,
            finish_datetime=finish_datetime,
            antenna_rename_scheme=antenna_rename_scheme,
            ).to_dict()

    elif custom_layout and isinstance(antenna_rename_scheme, dict):
        config = config_templates.CustomConfig(
            project_location=project_location,
            experiment_name=experiment_name,
            data_path=data_path,
            animal_ids=animal_ids,
            light_phase_start=light_phase_start,
            dark_phase_start=dark_phase_start,
            start_datetime=start_datetime,
            finish_datetime=finish_datetime,
            antenna_rename_scheme=antenna_rename_scheme,
            ).to_dict()
    
    elif custom_layout or field_ecohab and not isinstance(antenna_rename_scheme, dict):
        raise TypeError('Chosen custom layout/field layout but antenna renaming graph not provided!')
    
    else:
        config = config_templates.DefaultConfig(
            project_location=project_location,
            experiment_name=experiment_name,
            data_path=data_path,
            animal_ids=animal_ids,
            light_phase_start=light_phase_start,
            dark_phase_start=dark_phase_start,
            start_datetime=start_datetime,
            finish_datetime=finish_datetime,
            ).to_dict()
    
    # Remake into Path here for safety
    project_location = Path(project_location) 
    
    # Check/make the project directory
    if Path(project_location).is_dir():
        print('Project already exists! Loading existing project config.')
        config_path = project_location / 'config.toml'
        if config_path.is_file():
            return config_path
        else:
            raise FileNotFoundError(f'Config file not found in {project_location}!')
    else:
        Path.mkdir(project_location)
        Path.mkdir(project_location / 'plots')
        Path.mkdir(project_location / 'plots' / 'fig_source')
        Path.mkdir(project_location / 'results')
    
    # Create the toml
    config_path = project_location / 'config.toml'
    with open(config_path, 'w') as toml_file:
        toml.dump(config, toml_file)

    return config_path