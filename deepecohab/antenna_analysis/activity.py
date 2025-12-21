from pathlib import Path

import polars as pl
from deepecohab.utils import auxfun
from deepecohab.utils.auxfun import df_registry

@df_registry.register('cage_occupancy')
def calculate_cage_occupancy(
    config_path: str | Path | dict,
    save_data: bool = True,
    overwrite: bool = False,
) -> pl.LazyFrame:
    """Calculates time spent per animal per phase in every cage.

    Args:
        config_path: path to projects' config file or dict with the config.
        save_data: toogles whether to save data.
        overwrite: toggles whether to overwrite the data.

    Returns:
        LazyFrame of time spent in each cage with 1s resolution.
    """
    cfg = auxfun.read_config(config_path)

    results_path = Path(cfg["project_location"]) / "results"
    key = "cage_occupancy"

    cage_occupancy = None if overwrite else auxfun.load_ecohab_data(config_path, key)

    if isinstance(cage_occupancy, pl.LazyFrame):
        return cage_occupancy

    binary_lf = auxfun.load_ecohab_data(config_path, "binary_df")

    animal_ids = cfg["animal_ids"]
    cages = cfg["cages"]

    cols = ["day", "hour", "cage", "animal_id"]

    bounds = (
        binary_lf
        .select(
            pl.col("datetime").min().dt.truncate("1h").alias("start"),
            pl.col("datetime").max().dt.truncate("1h").alias("end")
            )
            .collect()
            .row(0)
        )

    start, end = bounds
    time_lf = (
        pl.LazyFrame()
        .select(pl.datetime_range(pl.lit(start), pl.lit(end), "1h").alias("datetime"))
    )

    animals_lf = auxfun.get_lf_from_enum(animal_ids, 'animal_id', sorted = True, col_type=pl.Enum(animal_ids))
    cages_lf = auxfun.get_lf_from_enum(cages, 'cage', col_type=pl.Categorical)

    full_group_list = (
        time_lf
        .join(animals_lf, how='cross')
        .join(cages_lf, how='cross')
        .with_columns(
            auxfun.get_hour(),
            auxfun.get_day()
            )
        .drop('datetime')
    )
    cage_occupancy = (
        binary_lf
        .sort('animal_id', 'datetime')
        .with_columns(
            auxfun.get_hour(),
            auxfun.get_day()
            )
        .group_by(cols)
        .agg(pl.len().alias('time_spent'))
        .join(full_group_list, on=cols, how = 'right').fill_null(0)
        )

    if save_data:
        cage_occupancy.sink_parquet(results_path / f"{key}.parquet", compression="lz4", engine='streaming')

    return cage_occupancy

@df_registry.register('activity_df')
def calculate_activity(
    config_path: str | Path | dict,
    save_data: bool = True,
    overwrite: bool = False,
) -> pl.LazyFrame:
    """Calculates time spent and visits to every possible position per phase for every mouse.

    Args:
        config_path: path to projects' config file or dict with the config.
        save_data: toogles whether to save data.
        overwrite: toggles whether to overwrite the data.

    Returns:
        LazyFrame of time and visits
    """
    cfg = auxfun.read_config(config_path)

    results_path = Path(cfg["project_location"]) / "results"
    key = "activity_df"

    time_per_position_lf = None if overwrite else auxfun.load_ecohab_data(config_path, key)

    if isinstance(time_per_position_lf, pl.LazyFrame):
        return time_per_position_lf

    padded_lf = auxfun.load_ecohab_data(cfg, key="padded_df")
    padded_lf = auxfun.remove_tunnel_directionality(padded_lf, cfg)

    per_position_lf = padded_lf.group_by(
        ["phase", "day", "phase_count", "position", "animal_id"]
    ).agg(
        pl.sum("time_spent").alias("time_in_position"),
        pl.len().alias("visits_to_position"),
    )

    if save_data:
        per_position_lf.sink_parquet(results_path / f"{key}.parquet", compression="lz4", engine='streaming')

    return per_position_lf
