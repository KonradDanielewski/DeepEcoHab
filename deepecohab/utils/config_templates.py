from dataclasses import dataclass, field

@dataclass
class ExperimentConfig:
    project_location: str
    experiment_name: str
    results_path: str
    data_path: str
    animal_ids: list[str]
    dark_phase_start: str
    light_phase_start: str
    start_datetime: str = None
    finish_datetime: str = None
    antenna_combinations: dict[str, str] = field(default_factory=dict)
    tunnels: dict[str, str] = field(default_factory=dict)
    phase: dict[str, str] = field(init=False)
    experiment_timeline: dict[str, str] = field(init=False)
    """Generates a config template

    Attributes:
        project_location: location of the project
        experiment_name: name of the experiment
        data_path: directory containing the antenna reads
        animal_ids: RFID tag hex codes for animals
        dark_phase_start: start time of the dark phase (light off)
        light_phase_start: start time of the light phase (light on)
        start_datetime: date and time of the experiment start - data will be pruned to match
        finish_datetime: date and time of the experiment end - data will be pruned to match
        antenna_rename_scheme: a dictionary that contains per comport renaming scheme - used when using multiple boards in one setup   
    """
    def __post_init__(self):
        self.phase = {
            "light_phase": self.light_phase_start,
            "dark_phase": self.dark_phase_start,
        }
        self.experiment_timeline = {
            "start_date": self.start_datetime,
            "finish_date": self.finish_datetime,
        }
        
    def to_dict(self) -> dict:
        data = {}
        data["project_location"] = self.project_location
        data["experiment_name"] = self.experiment_name
        data["results_path"] = self.results_path
        data["data_path"] = self.data_path
        data["animal_ids"] = self.animal_ids
        data["phase"] = self.phase
        data["experiment_timeline"] = self.experiment_timeline
        data["antenna_combinations"] = self.antenna_combinations
        data["tunnels"] = self.tunnels
        try:
            data["antenna_rename_scheme"] = self.antenna_rename_scheme
        except:
            pass
        return data

@dataclass
class DefaultConfig(ExperimentConfig):
    """Generates default config
    """    
    def __post_init__(self):
        super().__post_init__()
        self.antenna_combinations = {
            "1_2": "c1_c2", "2_1": "c2_c1", "3_4": "c2_c3", "4_3": "c3_c2",
            "5_6": "c3_c4", "6_5": "c4_c3", "7_8": "c4_c1", "8_7": "c1_c4",
            "1_8": "cage_1", "8_1": "cage_1", "1_1": "cage_1", "8_8": "cage_1",
            "2_3": "cage_2", "3_2": "cage_2", "2_2": "cage_2", "3_3": "cage_2",
            "4_5": "cage_3", "5_4": "cage_3", "4_4": "cage_3", "5_5": "cage_3",
            "6_7": "cage_4", "7_6": "cage_4", "6_6": "cage_4", "7_7": "cage_4",
        }
        self.tunnels = {
            "c1_c2": "tunnel_1", "c2_c1": "tunnel_1", "c2_c3": "tunnel_2", "c3_c2": "tunnel_2",
            "c3_c4": "tunnel_3", "c4_c3": "tunnel_3", "c4_c1": "tunnel_4", "c1_c4": "tunnel_4",
        }

@dataclass
class CustomConfig(DefaultConfig):
    """Generates custom config for arbitrary 
    """    
    antenna_rename_scheme: dict[str, dict[str, str]] = field(default_factory=dict)

    def __post_init__(self):
        super().__post_init__()
        print("Please update the geometry information in the config according to your antenna layout!")
        print("Antennas will be automatically renamed following your naming scheme on a per COM name basis.")

@dataclass
class FieldConfig(CustomConfig):
    """Generates config for field ecohab. 
    """    
    def __post_init__(self):
        super().__post_init__()
        self.antenna_combinations = {
            "1_2": "cA_cB", "2_1": "cB_cA", "3_4": "cB_cC", "4_3": "cC_cB",
            "5_6": "cC_cD", "6_5": "cD_cC", "7_8": "cD_cE", "8_7": "cE_cD",
            "9_10": "cE_cF", "10_9": "cF_cE", "11_12": "cF_cG", "12_11": "cG_cF",
            "13_14": "cG_cH", "14_13": "cH_cG", "15_16": "cH_cA", "16_15": "cA_cH",
        }
        self.tunnels = {
            "cA_cB": "tunnel1", "cB_cA": "tunnel1", "cC_cB": "tunnel2", "cB_cC": "tunnel2",
            "cC_cD": "tunnel3", "cD_cC": "tunnel3", "cD_cE": "tunnel4", "cE_cD": "tunnel4",
            "cE_cF": "tunnel5", "cF_cE": "tunnel5", "cF_cG": "tunnel6", "cG_cF": "tunnel6",
            "cG_cH": "tunnel7", "cH_cG": "tunnel7", "cH_cA": "tunnel8", "cA_cH": "tunnel8",
        }