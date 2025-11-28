from pathlib import Path

import pandas as pd

from deepecohab.utils import auxfun

def calculate_approach_to_social_odor(
    cfp: str | Path | dict, 
    stim_start: str, 
    stim_end: str, 
    stim_cage: str, 
    control_cage: str,
    time_bins: int = 1,
    save_data: bool = True, 
    overwrite: bool = False,
    ) -> pd.DataFrame:
    """Calulates cage preference in approach to social odor.

    Args:
        cfp: path to project config file.
        stim_start: datetime of the stimulus placement, in format '2021-07-14 20:56:01.473'.
        stim_end: datetime to mark the end of analyzed period, in format '2021-07-14 20:56:01.473'.
        stim_cage: name of the cage where the stimulus was placed.
        control_cage: name of the cage where the control stimulus was placed.
        time_bins: number of time bins into which the stimulation period should be divided
        save_data: toogles whether to save data.
        overwrite: toggles whether to overwrite the data.

    Returns:
        DataFrame indexed (MultiIndex per bin if time_bins > 1) by animals columns correspond to preference:
        1. Stimulation cage on the day of the experiment
        2. Stimulation cage the day before
        3. control stimulus cage on the day of the experiment
        4. control stimulus cage the day before
    """    
    cfg = auxfun.read_config(cfp)
    results_path = Path(cfg['project_location']) / 'results' / 'results.h5'
    key='social_odor'
    
    social_odor = None if overwrite else auxfun.load_ecohab_data(cfp, key)
    if isinstance(social_odor, pd.DataFrame):
        return social_odor
    
    animals = cfg['animal_ids']
    
    stim_start = pd.to_datetime(stim_start)
    stim_end = pd.to_datetime(stim_end)
    normalization_start = stim_start - pd.Timedelta(1, 'd')
    bin_len = (stim_end - stim_start) / time_bins
    
    binary_df = auxfun.load_ecohab_data(cfg, key='binary_df').loc[normalization_start:stim_end]
    
    idx = pd.MultiIndex.from_product([range(1, time_bins+1), animals])
    cols = ['stim_cage', 'stim_cage_prev_day', 'control_cage', 'control_cage_prev_day']
    social_odor = pd.DataFrame(index=idx, columns=cols)
    
    for i in range(time_bins): 
        if i == 0:
            pass
        else:
            stim_start+=bin_len
            normalization_start+=bin_len
            
        end = stim_start + bin_len
        prev_end = normalization_start + bin_len
        
        stim_place = binary_df.loc[stim_start:end, stim_cage]
        control_place = binary_df.loc[stim_start:end, control_cage]
        stim_place_norm = binary_df.loc[normalization_start:prev_end, stim_cage]
        control_place_norm = binary_df.loc[normalization_start:prev_end, control_cage]

        total_time = (end - stim_start).total_seconds()
        # Assumes binary_df was made with defualt 100ms step. Can be automated to check diff between binary df and get divisor from that
        pref_stim = stim_place.sum() / 10 / total_time 
        pref_control = control_place.sum() / 10 / total_time

        prev_pref_stim = stim_place_norm.sum() / 10 / total_time
        prev_pref_control = control_place_norm.sum() / 10 / total_time
        
        bin_social_odor = pd.concat([pref_stim, prev_pref_stim, pref_control, prev_pref_control], axis=1)
        social_odor.loc[(i+1, animals), :] = bin_social_odor.values
    
    if len((social_odor.index.levels[0])) == 1:
        social_odor = social_odor.droplevel(0, axis=0)
            
    if save_data:
        social_odor.to_hdf(results_path, key='social_odor', mode='a', format='table')
        
    return social_odor   
    
    