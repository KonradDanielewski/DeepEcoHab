from pathlib import Path

import polars as pl
from openskill.models import PlackettLuce

from deepecohab.utils import auxfun
from deepecohab.utils.auxfun import df_registry


@df_registry.register('ranking')
def calculate_ranking(
    config_path: str | Path | dict,
    overwrite: bool = False,
    save_data: bool = True,
    ranking: dict | None = None,
) -> pl.LazyFrame:
    """Calculate ranking using Plackett Luce algortihm. Each chasing event is a match
        TODO: handling of previous rankings
    Args:
        config_path: path to project config file.
        save_data: toogles whether to save data.
        overwrite: toggles whether to overwrite the data.
        ranking: optionally, user can pass a dictionary from a different recording of same animals
                 to start ranking from a certain point instead of 0

    Returns:
        LazyFrame of ranking
    """
    cfg = auxfun.read_config(config_path)
    results_path = Path(cfg["project_location"]) / "results"
    key = "ranking"

    ranking = None if overwrite else auxfun.load_ecohab_data(config_path, key)

    if isinstance(ranking, pl.LazyFrame):
        return ranking
    
    match_df = auxfun.load_ecohab_data(cfg, 'match_df').sort('datetime').collect()
    animal_ids = cfg['animal_ids']

    model = PlackettLuce(limit_sigma=True, balance=True)
    ranking = {player: model.rating() for player in animal_ids}

    rows = []

    for loser_name, winner_name, dtime in match_df.iter_rows():
        new_ratings = model.rate(
            [[ranking[loser_name]], [ranking[winner_name]]],
            ranks=[1, 0],
        )

        ranking[loser_name] = new_ratings[0][0]
        ranking[winner_name] = new_ratings[1][0]

        for animal, rating in ranking.items():
            rows.append({
                "animal_id": animal,
                "mu": rating.mu,
                "sigma": rating.sigma,
                "ordinal": round(rating.ordinal(), 3),
                "datetime": dtime,
            })

    ranking_df = pl.LazyFrame(rows).with_columns(
        auxfun.get_phase(cfg),
        auxfun.get_day(),
        auxfun.get_hour(),
    )

    if save_data:
        ranking_df.sink_parquet(results_path / "ranking.parquet", compression="lz4", engine='streaming')

    return ranking

@df_registry.register('match_df')
def get_matches(lf: pl.LazyFrame, results_path: Path, save_data: bool) -> None:
    """Creates a lazyframe of matches"""
    matches = lf.select(
        "animal_id", "animal_id_chasing", "datetime_chasing"
    ).rename(
        {
            "animal_id": "loser",
            "animal_id_chasing": "winner",
            "datetime_chasing": "datetime",
        }
    )
    if save_data:
        matches.sink_parquet(results_path / "match_df.parquet", compression="lz4", engine='streaming')
    
    
@df_registry.register('chasings_df')
def calculate_chasings(
    config_path: str | Path | dict,
    overwrite: bool = False,
    save_data: bool = True,
) -> pl.LazyFrame:
    """Calculates chasing events per pair of mice for each phase

    Args:
        config_path: path to project config file.
        save_data: toogles whether to save data.
        overwrite: toggles whether to overwrite the data.

    Returns:
        LazyFrame of chasings
    """
    cfg = auxfun.read_config(config_path)
    results_path = Path(cfg["project_location"]) / "results"
    key = "chasings_df"

    chasings = None if overwrite else auxfun.load_ecohab_data(config_path, key)

    if isinstance(chasings, pl.LazyFrame):
        return chasings

    lf = auxfun.load_ecohab_data(cfg, key="main_df")

    cages = cfg["cages"]
    tunnels = cfg["tunnels"]

    chased = lf.filter(
        pl.col("position").is_in(tunnels),
    )
    chasing = lf.with_columns(
        pl.col("datetime").shift(1).over("animal_id").alias("tunnel_entry"),
        pl.col("position").shift(1).over("animal_id").alias("prev_position"),
    )

    intermediate = chased.join(
        chasing, on=["phase", "day", "hour", "phase_count"], suffix="_chasing"
    ).filter(
        pl.col("animal_id") != pl.col("animal_id_chasing"),
        pl.col("position") == pl.col("position_chasing"),
        pl.col("prev_position").is_in(cages),
        (pl.col("datetime") - pl.col("tunnel_entry"))
        .dt.total_seconds(fractional=True)
        .is_between(0.1, 1.2, "none"),
        (pl.col("datetime") < pl.col("datetime_chasing")),
    )
    
    get_matches(intermediate, results_path, save_data)
    
    chasings = (
        intermediate.group_by(
            ["phase", "day", "phase_count", "hour", "animal_id_chasing", "animal_id"]
        )
        .len(name="chasings")
        .rename({"animal_id": "chased", "animal_id_chasing": "chaser"})
    )

    if save_data:
        chasings.sink_parquet(results_path / f"{key}.parquet", compression="lz4", engine='streaming')

    return chasings