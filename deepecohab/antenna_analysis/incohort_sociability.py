from pathlib import Path

import polars as pl
import polars.selectors as cs

from deepecohab.antenna_analysis import activity
from deepecohab.utils import auxfun

def calculate_time_alone(
    cfp: Path | str | dict,
    save_data: bool = True, 
    overwrite: bool = False,
):
    """Calculates time spent alone by animal per phase/day/cage

    Args:
        cfp: path to project config file.
        save_data: toogles whether to save data.
        overwrite: toggles whether to overwrite the data.
        
    Returns:
        DataFrame containing time spent alone in seconds.
    """
    cfg = auxfun.read_config(cfp)
    results_path = Path(cfg['project_location']) / 'results'
    key='time_alone'

    time_alone = None if overwrite else auxfun.load_ecohab_data(cfp, key)
    if isinstance(time_alone, pl.LazyFrame):
        return time_alone

    #TODO categorical?
    cages = cfg['cages']

    binary_df = auxfun.load_ecohab_data(cfp, 'binary_df')

    binary_filtered = binary_df.filter(
        pl.col('is_in')
    )

    group_cols = ['datetime','cage', 'phase', 'day', 'phase_count']
    result_cols = ['phase', 'day', 'phase_count', 'animal_id', 'cage']

    time_alone = binary_filtered.group_by(
            group_cols
        ).agg(
            'animal_id'
        ).filter(
            pl.col('animal_id').list.len()==1
        ).with_columns(
            pl.col('animal_id').list.get(0)
        ).group_by(
            result_cols
        ).agg(
            pl.col('datetime').count()
        ).sort(result_cols)
        
    if save_data:
        time_alone.sink_parquet(results_path / f"{key}.parquet", compression='lz4')
        
    return time_alone

def calculate_pairwise_meetings(
    cfp: str | Path | dict, 
    minimum_time: int | float | None = 2, 
    save_data: bool = True, 
    overwrite: bool = False,
    ) -> pl.LazyFrame:
    """Calculates time spent together and number of meetings by animals on a per phase, day and cage basis. Slow due to the nature of datetime overlap calculation.

    Args:
        cfg: dictionary with the project config.
        minimum_time: sets minimum time together to be considered an interaction - in seconds i.e., if set to 2 any time spent in the cage together
                   that is shorter than 2 seconds will be omited. 
        save_data: toogles whether to save data.
        overwrite: toggles whether to overwrite the data.
        
    Returns:
        Multiindex DataFrame of time spent together per phase, per cage.
    """    
    cfg = auxfun.read_config(cfp)
    results_path = Path(cfg['project_location']) / 'results' / 'pairwise_meetings.parquet'
    padded_path = Path(cfg['project_location']) / 'results' / 'padded_df.parquet'

    cages = cfg['cages']

    pairwise_meetings = None if overwrite else auxfun.load_ecohab_data(cfp, 'pairwise_meetings')
    
    if isinstance(pairwise_meetings, pl.DataFrame):
        return pairwise_meetings
    
    lf = (
        pl.scan_parquet(padded_path)
        .filter(pl.col("position").is_in(cages))
        .with_columns([
            (pl.col("datetime") - pl.duration(seconds=pl.col("timedelta"))).alias("event_start"),
            pl.col("datetime").alias("event_end"),
        ])
    )

    joined = (
        lf.join(
            lf,
            on=["position", "phase", "day", "phase_count"],
            how="inner",
            suffix="_2",
        )
        .filter(pl.col("animal_id") < pl.col("animal_id_2"))
        .with_columns([
            (
                pl.min_horizontal(["event_end", "event_end_2"]) - 
                pl.max_horizontal(["event_start", "event_start_2"])
            ).dt.total_seconds(fractional=True).round(3).alias("overlap_duration")
            ,
        ])
        .filter(pl.col("overlap_duration") > minimum_time)
    )

    pairwise_meetings = (
        joined.group_by([
            "phase", "day", "phase_count", "position", "animal_id", "animal_id_2"
        ])
        .agg([
            pl.sum("overlap_duration").alias("time_together"),
            pl.len().alias("pairwise_encounters"),
        ])
        
    ).sort(['phase', 'day', 'phase_count', 'position', 'animal_id', 'animal_id_2'])
    
    if save_data:
        pairwise_meetings.sink_parquet(results_path, compression='lz4')
    
    return pairwise_meetings

def calculate_incohort_sociability(
    cfp: dict, 
    save_data: bool = True, 
    overwrite: bool = False, 
    minimum_time: int | float | None = None
    ) -> pl.LazyFrame:
    """Calculates in-cohort sociability. For more info: DOI:10.7554/eLife.19532.

    Args:
        cfp: path to project config file.
        save_data: toogles whether to save data.
        overwrite: toggles whether to overwrite the data.
        minimum_time: sets minimum time together to be considered an interaction - in seconds. Passed to calculate_time_together.
        n_workers: number of CPU threads used to paralelize the calculation. Passed to calculate_time_together.

    Returns:
        Multiindex DataFrame of in-cohort sociability per phase for each possible pair of mice.
    """    
    cfg = auxfun.read_config(cfp)
    results_path = Path(cfg['project_location']) / 'results'
    key='incohort_sociability'

    incohort_sociability = None if overwrite else auxfun.load_ecohab_data(cfp, key)

    if isinstance(incohort_sociability, pl.LazyFrame):
        return incohort_sociability

    padded_df = auxfun.load_ecohab_data(cfg, key='padded_df')
    
    cages = cfg['cages']
    animals = cfg['animal_ids']

    phase_durations = auxfun.get_phase_durations(padded_df)

    # Get time spent together in cages
    time_together_df = calculate_pairwise_meetings(cfg, minimum_time, save_data, overwrite)

    # Get time per position
    time_per_position = activity.calculate_time_spent_per_position(cfg, save_data, overwrite)
    time_per_cage = time_per_position.filter(
        pl.col("position").is_in(cages)
    ).unpivot(
        animals,
        index = ['phase', 'day', 'phase_count', 'position'],
        variable_name='animal_id',
        value_name='time_sum',
    ).with_columns(
        pl.col('animal_id').cast(pl.Enum(animals))
    )

    # Normalize times as proportion of the phase duration
    estimated_proportion_together = time_per_cage.join(
        time_per_cage,
        on = ['phase_count', 'phase', 'position'],
        suffix="_right"
    ).rename(
        {'animal_id_right' : 'animal_id_2'}
    ).filter(
        pl.col('animal_id') < pl.col('animal_id_2')
    ).join(
        phase_durations.collect(),
        on = ['phase_count', 'phase']
    ).with_columns(
        (cs.contains('time_sum')/pl.col('duration_seconds')),
    ).with_columns(
        (pl.col('time_sum')*pl.col('time_sum_right')).alias('chance')
    ).group_by(
        ['day', 'phase_count', 'phase', 'animal_id', 'animal_id_2']
    ).agg(
        pl.col('chance').sum()
    )
    
    # sum of time spent together across all cages
    true_proportion_df = time_together_df.join(
        phase_durations.collect(),
        on = ['phase_count', 'phase']
    ).with_columns(
        pl.col('time_together')/pl.col('duration_seconds')
    ).group_by(
        ['day', 'phase_count', 'phase', 'animal_id', 'animal_id_2']
    ).agg(
        pl.col('time_together').sum()
    )

    incohort_sociability = estimated_proportion_together.join(
        true_proportion_df,
        on = ['day', 'phase_count', 'phase', 'animal_id', 'animal_id_2']
    ).with_columns(
        (pl.col('time_together')-pl.col('chance')).alias('sociability')
    ).sort(['day', 'phase_count', 'phase', 'animal_id', 'animal_id_2'])
    
    if save_data:
        incohort_sociability.sink_parquet(results_path / f"{key}.parquet", compression='lz4')

    return incohort_sociability