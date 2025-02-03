def generate_default_config(
    project_location: str,
    experiment_name: str,
    results_path: str,
    data_path: str,
    animal_ids: list,
    dark_phase_start: str,
    light_phase_start: str,
    start_datetime: str,
    finish_datetime: str,
) -> dict:
    """Generates a default config template

    Args:
        project_location: location of the project
        experiment_name: name of the experiment
        data_path: directory containing the antenna reads
        animal_ids: RFID tag hex codes for animals
        dark_phase_start: start time of the dark phase (light off)
        light_phase_start: start time of the light phase (light on)
        start_datetime: date and time of the experiment start - data will be pruned to match
        finish_datetime: date and time of the experiment end - data will be pruned to match
        
    Returns:
        config: dictionary that will be used to create a toml config
    """    
    
    config = dict(
        project_location = project_location,
        experiment_name = experiment_name,
        results_path = results_path,
        data_path = data_path,
        animal_ids = animal_ids,
        
        antenna_combinations = {
            "12" : "c1_c2",
            "21" : "c2_c1",
            "34" : "c2_c3",
            "43" : "c3_c2",
            "56" : "c3_c4",
            "65" : "c4_c3",
            "78" : "c4_c1",
            "87" : "c1_c4",
            "18" : "cage_1",
            "81" : "cage_1",
            "11" : "cage_1",
            "88" : "cage_1",
            "23" : "cage_2",
            "32" : "cage_2",
            "22" : "cage_2",
            "33" : "cage_2",
            "45" : "cage_3",
            "54" : "cage_3",
            "44" : "cage_3",
            "55" : "cage_3",
            "67" : "cage_4",
            "76" : "cage_4",
            "66" : "cage_4",
            "77" : "cage_4",
        },
        
        tunnels = dict(
            c1_c2 = "tunnel_1",
            c2_c1 = "tunnel_1",
            c2_c3 = "tunnel_2",
            c3_c2 = "tunnel_2",
            c3_c4 = "tunnel_3",
            c4_c3 = "tunnel_3",
            c4_c1 = "tunnel_4",
            c1_c4 = "tunnel_4",
        ),
        
        phase = dict(
            light_phase = light_phase_start,
            dark_phase = dark_phase_start,
        ),
        
        experiment_timeline = dict(
            start_date = start_datetime,
            finish_date = finish_datetime,
        ),
    )

    return config

def generate_custom_config(
    project_location: str,
    experiment_name: str,
    results_path: str,
    data_path: str,
    animal_ids: list,
    dark_phase_start: str,
    light_phase_start: str,
    start_datetime: str,
    finish_datetime: str,
    antenna_rename_scheme: dict[dict],
) -> dict:
    """Generates a custm config template

    Args:
        project_location: location of the project
        experiment_name: name of the experiment
        data_path: directory containing the antenna reads
        animal_ids: RFID tag hex codes for animals
        dark_phase_start: start time of the dark phase (light off)
        light_phase_start: start time of the light phase (light on)
        start_datetime: date and time of the experiment start - data will be pruned to match
        finish_datetime: date and time of the experiment end - data will be pruned to match
        antenna_rename_scheme: a dictionary that contains per comport renaming scheme - used when using multiple boards in one setup
        
    Returns:
        config: dictionary that will be used to create a toml config
    """

    config = dict(
        project_location = project_location,
        experiment_name = experiment_name,
        results_path = results_path,
        data_path = data_path,
        animal_ids = animal_ids, 
                
        antenna_rename_scheme = antenna_rename_scheme,
        
        antenna_combinations = {
            "12" : "c1_c2",
            "21" : "c2_c1",
            "34" : "c2_c3",
            "43" : "c3_c2",
            "56" : "c3_c4",
            "65" : "c4_c3",
            "78" : "c4_c1",
            "87" : "c1_c4",
            "18" : "cage_1",
            "81" : "cage_1",
            "11" : "cage_1",
            "88" : "cage_1",
            "23" : "cage_2",
            "32" : "cage_2",
            "22" : "cage_2",
            "33" : "cage_2",
            "45" : "cage_3",
            "54" : "cage_3",
            "44" : "cage_3",
            "55" : "cage_3",
            "67" : "cage_4",
            "76" : "cage_4",
            "66" : "cage_4",
            "77" : "cage_4",
        },
        
        tunnels = dict(
            c1_c2 = "tunnel_1",
            c2_c1 = "tunnel_1",
            c2_c3 = "tunnel_2",
            c3_c2 = "tunnel_2",
            c3_c4 = "tunnel_3",
            c4_c3 = "tunnel_3",
            c4_c1 = "tunnel_4",
            c1_c4 = "tunnel_4",
        ),
        
        phase = dict(
            light_phase = light_phase_start,
            dark_phase = dark_phase_start,
        ),
        
        experiment_timeline = dict(
            start_date = start_datetime,
            finish_date = finish_datetime,
        ),
    )
    
    print("Please update the geometry information in the config according to your antenna layout!")
    print("Antennas will be automatically renamed following your naming scheme on a per COM name basis.")
    
    return config

def generate_field_config(
    project_location: str,
    experiment_name: str,
    results_path: str,
    data_path: str,
    animal_ids: list,
    dark_phase_start: str,
    light_phase_start: str,
    start_datetime: str,
    finish_datetime: str,
    antenna_rename_scheme: dict[dict],
) -> dict:
    """Generates a custm config template

    Args:
        project_location: location of the project
        experiment_name: name of the experiment
        data_path: directory containing the antenna reads
        animal_ids: RFID tag hex codes for animals
        dark_phase_start: start time of the dark phase (light off)
        light_phase_start: start time of the light phase (light on)
        start_datetime: date and time of the experiment start - data will be pruned to match
        finish_datetime: date and time of the experiment end - data will be pruned to match
        antenna_rename_scheme: a dictionary that contains per comport renaming scheme - used when using multiple boards in one setup
        
    Returns:
        config: dictionary that will be used to create a toml config
    """
    
    config = dict(
        project_location = project_location,
        experiment_name = experiment_name,
        results_path = results_path,
        data_path = data_path,
        animal_ids = animal_ids, 
                
        antenna_rename_scheme = antenna_rename_scheme,
        
        antenna_combinations = {
        "12" : "cA_cB",
        "21" : "cB_cA",
        "34" : "cB_cC",
        "43" : "cC_cB",
        "56" : "cC_cD",
        "65" : "cD_cC",
        "78" : "cD_cE",
        "87" : "cE_cD",
        "910" : "cE_cF",
        "109" : "cF_cE",
        "1112" : "cF_cG",
        "1211" : "cG_cF",
        "1314" : "cG_cH",
        "1413" : "cH_cG",
        "1516" : "cH_cA",
        "1615" : "cA_cH",
        "116" : "cage_A",
        "161" : "cage_A",
        "11" : "cage_A",
        "1616" : "cage_A",
        "23" : "cage_B",
        "32" : "cage_B",
        "22" : "cage_B",
        "33" : "cage_B",
        "45" : "cage_C",
        "54" : "cage_C",
        "44" : "cage_C",
        "55" : "cage_C",
        "67" : "cage_D",
        "76" : "cage_D",
        "66" : "cage_D",
        "77" : "cage_D",
        "89" : "cage_E",
        "98" : "cage_E",
        "88" : "cage_E",
        "99" : "cage_E",
        "1011" : "cage_F",
        "1110" : "cage_F",
        "1010" : "cage_F",
        "1111" : "cage_F",
        "1213" : "cage_G",
        "1312" : "cage_G",
        "1212" : "cage_G",
        "1313" : "cage_G",
        "1415" : "cage_H",
        "1514" : "cage_H",
        "1414" : "cage_H",
        "1515" : "cage_H",
        },
        
        tunnels = dict(
            cA_cB = "tunnel1",
            cB_cA = "tunnel1",
            cB_cC = "tunnel2",
            cC_cB = "tunnel2",
            cC_cD = "tunnel3",
            cD_cC = "tunnel3",
            cD_cE = "tunnel4",
            cE_cD = "tunnel4",
            cE_cF = "tunnel5",
            cF_cE = "tunnel5",
            cF_cG = "tunnel6",
            cG_cF = "tunnel6",
            cG_cH = "tunnel7",
            cH_cG = "tunnel7",
            cH_cA = "tunnel8",
            cA_cH = "tunnel8",
        ),
        
        phase = dict(
            light_phase = light_phase_start,
            dark_phase = dark_phase_start,
        ),
        
        experiment_timeline = dict(
            start_date = start_datetime,
            finish_date = finish_datetime,
        ),
    )
    
    return config