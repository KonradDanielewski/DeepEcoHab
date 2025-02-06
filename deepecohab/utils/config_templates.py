def generate_default_config(
    project_location: str,
    experiment_name: str,
    results_path: str,
    data_path: str,
    animal_ids: list,
    dark_phase_start: str,
    light_phase_start: str,
    start_datetime: str | None = None,
    finish_datetime: str | None = None,
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
            "1_2" : "c1_c2",
            "2_1" : "c2_c1",
            "3_4" : "c2_c3",
            "4_3" : "c3_c2",
            "5_6" : "c3_c4",
            "6_5" : "c4_c3",
            "7_8" : "c4_c1",
            "8_7" : "c1_c4",
            "1_8" : "cage_1",
            "8_1" : "cage_1",
            "1_1" : "cage_1",
            "8_8" : "cage_1",
            "2_3" : "cage_2",
            "3_2" : "cage_2",
            "2_2" : "cage_2",
            "3_3" : "cage_2",
            "4_5" : "cage_3",
            "5_4" : "cage_3",
            "4_4" : "cage_3",
            "5_5" : "cage_3",
            "6_7" : "cage_4",
            "7_6" : "cage_4",
            "6_6" : "cage_4",
            "7_7" : "cage_4",
            "8_2" : "cage_1", # Assumes that position is cage when only one antenna is skipped
            "2_8" : "cage_1",
            "1_7" : "cage_1",
            "7_1" : "cage_1",
            "2_4" : "cage_2",
            "4_2" : "cage_2",
            "3_1" : "cage_2",
            "1_3" : "cage_2",
            "4_6" : "cage_3",
            "6_4" : "cage_3",
            "3_5" : "cage_3",
            "5_3" : "cage_3",
            "5_7" : "cage_4",
            "7_5" : "cage_4",
            "6_8" : "cage_4",
            "8_6" : "cage_4",
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
    antenna_rename_scheme: dict[dict],
    start_datetime: str | None = None,
    finish_datetime: str | None = None,
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
            "1_2" : "c1_c2",
            "2_1" : "c2_c1",
            "3_4" : "c2_c3",
            "4_3" : "c3_c2",
            "5_6" : "c3_c4",
            "6_5" : "c4_c3",
            "7_8" : "c4_c1",
            "8_7" : "c1_c4",
            "1_8" : "cage_1",
            "8_1" : "cage_1",
            "1_1" : "cage_1",
            "8_8" : "cage_1",
            "2_3" : "cage_2",
            "3_2" : "cage_2",
            "2_2" : "cage_2",
            "3_3" : "cage_2",
            "4_5" : "cage_3",
            "5_4" : "cage_3",
            "4_4" : "cage_3",
            "5_5" : "cage_3",
            "6_7" : "cage_4",
            "7_6" : "cage_4",
            "6_6" : "cage_4",
            "7_7" : "cage_4",
            "8_2" : "cage_1", # Assumes that position is cage when only one antenna is skipped
            "2_8" : "cage_1",
            "1_7" : "cage_1",
            "7_1" : "cage_1",
            "2_4" : "cage_2",
            "4_2" : "cage_2",
            "3_1" : "cage_2",
            "1_3" : "cage_2",
            "4_6" : "cage_3",
            "6_4" : "cage_3",
            "3_5" : "cage_3",
            "5_3" : "cage_3",
            "5_7" : "cage_4",
            "7_5" : "cage_4",
            "6_8" : "cage_4",
            "8_6" : "cage_4",
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
    antenna_rename_scheme: dict[dict],
    start_datetime: str | None = None,
    finish_datetime: str | None = None,
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
        "1_2"   : "cA_cB",
        "2_1"   : "cB_cA",
        "3_4"   : "cB_cC",
        "4_3"   : "cC_cB",
        "5_6"   : "cC_cD",
        "6_5"   : "cD_cC",
        "7_8"   : "cD_cE",
        "8_7"   : "cE_cD",
        "9_10"  : "cE_cF",
        "10_9"  : "cF_cE",
        "11_12" : "cF_cG",
        "12_11" : "cG_cF",
        "13_14" : "cG_cH",
        "14_13" : "cH_cG",
        "15_16" : "cH_cA",
        "16_15" : "cA_cH",
        "1_16"  : "cage_A",
        "16_1"  : "cage_A",
        "1_1"   : "cage_A",
        "16_16" : "cage_A",
        "2_16"  : "cage_A",
        "16_2"  : "cage_A",
        "1_15"  : "cage_A",
        "15_1"  : "cage_A",
        "2_3"   : "cage_B",
        "3_2"   : "cage_B",
        "2_2"   : "cage_B",
        "3_3"   : "cage_B",
        "1_3"   : "cage_B",
        "3_1"   : "cage_B",
        "2_4"   : "cage_B",
        "4_2"   : "cage_B",
        "4_5"   : "cage_C",
        "5_4"   : "cage_C",
        "4_4"   : "cage_C",
        "5_5"   : "cage_C",
        "3_5"   : "cage_C",
        "5_3"   : "cage_C",
        "4_6"   : "cage_C",
        "6_4"   : "cage_C",
        "6_7"   : "cage_D",
        "7_6"   : "cage_D",
        "6_6"   : "cage_D",
        "7_7"   : "cage_D",
        "5_7"   : "cage_D",
        "7_5"   : "cage_D",
        "6_8"   : "cage_D",
        "8_6"   : "cage_D",
        "8_9"   : "cage_E",
        "9_8"   : "cage_E",
        "8_8"   : "cage_E",
        "9_9"   : "cage_E",
        "7_9"   : "cage_E",
        "9_7"   : "cage_E",
        "8_10"  : "cage_E",
        "10_8"  : "cage_E",
        "10_11" : "cage_F",
        "11_10" : "cage_F",
        "10_10" : "cage_F",
        "11_11" : "cage_F",
        "9_11"  : "cage_F",
        "11_9"  : "cage_F",
        "10_12" : "cage_F",
        "12_10" : "cage_F",
        "12_13" : "cage_G",
        "13_12" : "cage_G",
        "12_12" : "cage_G",
        "13_13" : "cage_G",
        "11_13" : "cage_G",
        "13_11" : "cage_G",
        "12_14" : "cage_G",
        "14_12" : "cage_G",
        "14_15" : "cage_H",
        "15_14" : "cage_H",
        "14_14" : "cage_H",
        "15_15" : "cage_H",
        "13_15"  : "cage_H",
        "15_13"  : "cage_H",
        "14_16"  : "cage_H",
        "16_14"  : "cage_H",
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