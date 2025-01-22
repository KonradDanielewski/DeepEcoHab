def generate_default_config(
    project_location: str,
    experiment_name: str,
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
        data_path = data_path,
        animal_ids = animal_ids,
        
        antenna_combinations = dict(
            c1_c2 = [[1,2]],
            c2_c1 = [[2,1]],
            c2_c3 = [[3,4]],
            c3_c2 = [[4,3]],
            c3_c4 = [[5,6]],
            c4_c3 = [[6,5]],
            c4_c1 = [[7,8]],
            c1_c4 = [[8,7]],
            cage_1 = [[1,8], [8,1], [1,1], [8,8]],
            cage_2 = [[2,3], [3,2], [2,2], [3,3]],
            cage_3 = [[4,5], [5,4], [4,4], [5,5]],
            cage_4 = [[6,7], [7,6], [6,6], [7,7]],
        ),
        
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
        
        possible_first = dict(
            cage_1 = [1, 8],
            cage_2 = [2, 3],
            cage_3 = [4, 5],
            cage_4 = [6, 7],
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
        data_path = data_path,
        animal_ids = animal_ids, 
                
        antenna_rename_scheme = antenna_rename_scheme,
        
        antenna_combinations = dict(
            c1_c2 = [[1,2]],
            c2_c1 = [[2,1]],
            c2_c3 = [[3,4]],
            c3_c2 = [[4,3]],
            c3_c4 = [[5,6]],
            c4_c3 = [[6,5]],
            c4_c1 = [[7,8]],
            c1_c4 = [[8,7]],
            cage_1 = [[1,8], [8,1], [1,1], [8,8]],
            cage_2 = [[2,3], [3,2], [2,2], [3,3]],
            cage_3 = [[4,5], [5,4], [4,4], [5,5]],
            cage_4 = [[6,7], [7,6], [6,6], [7,7]],
        ),
        
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
        
        possible_first = dict(
            cage_1 = [1, 8],
            cage_2 = [2, 3],
            cage_3 = [4, 5],
            cage_4 = [6, 7],
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
        data_path = data_path,
        animal_ids = animal_ids, 
                
        antenna_rename_scheme = antenna_rename_scheme,
        
        antenna_combinations = dict(
            cA_cB = [ [ 1, 2,],],
            cB_cA = [ [ 2, 1,],],
            cB_cC = [ [ 3, 4,],],
            cC_cB = [ [ 4, 3,],],
            cC_cD = [ [ 5, 6,],],
            cD_cC = [ [ 6, 5,],],
            cD_cE = [ [ 7, 8,],],
            cE_cD = [ [ 8, 7,],],
            cE_cF = [ [ 9, 10,],],
            cF_cE = [ [ 10, 9,],],
            cF_cG = [ [ 11, 12,],],
            cG_cF = [ [ 12, 11,],],
            cG_cH = [ [ 13, 14,],],
            cH_cG = [ [ 14, 13,],],
            cH_cA = [ [ 15, 16,],],
            cA_cH = [ [ 16, 15,],],
            cage_A = [ [ 1, 16,], [ 16, 1,], [ 1, 1,], [ 16, 16,],],
            cage_B = [ [ 2, 3,], [ 3, 2,], [ 2, 2,], [ 3, 3,],],
            cage_C = [ [ 4, 5,], [ 5, 4,], [ 4, 4,], [ 5, 5,],],
            cage_D = [ [ 6, 7,], [ 7, 6,], [ 6, 6,], [ 7, 7,],],
            cage_E = [ [ 8, 9,], [ 9, 8,], [ 8, 8,], [ 9, 9,],],
            cage_F = [ [ 10, 11,], [ 11, 10,], [ 10, 10,], [ 11, 11,],],
            cage_G = [ [ 12, 13,], [ 13, 12,], [ 12, 12,], [ 13, 13,],],
            cage_H = [ [ 14, 15,], [ 15, 14,], [ 14, 14,], [ 15, 15,],],
        ),
        
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
        
        possible_first = dict(
            cage_A = [ 1, 16,],
            cage_B = [ 2, 3,],
            cage_C = [ 4, 5,],
            cage_D = [ 6, 7,],
            cage_E = [ 8, 9,],
            cage_F = [ 10, 11,],
            cage_G = [ 12, 13,],
            cage_H = [ 14, 15,],
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