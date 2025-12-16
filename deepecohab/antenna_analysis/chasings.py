from pathlib import Path

import polars as pl
from openskill.models import PlackettLuce

from deepecohab.utils import auxfun


def _combine_matches(cfg: dict) -> tuple[list, pl.Series]:
    """Auxfun to combine all the chasing events into one data structure"""
    match_lf = auxfun.load_ecohab_data(cfg, "match_df")
    match_df = match_lf.collect().sort('datetime')

    datetimes = match_df["datetime"]

    match_df = match_df.drop("datetime")

    matches = [tuple(row) for row in match_df.iter_rows()]

    return matches, datetimes


def _rank_mice_openskill(
    cfg: dict,
    animal_ids: list[str],
    ranking: dict | None = None,
) -> tuple[dict, pl.DataFrame]:
    """Rank mice using PlackettLuce algorithm from openskill. More info: https://arxiv.org/pdf/2401.05451

    Args:
        cfg: config dict
        matches: list of all matches structured
        animal_ids: list of animal IDs
        ranking: dictionary that contains ranking of animals - if provided the ranking will start from this state. Defaults to None.

    Returns:
        ranking: dictionary of the ranking per animal
        ranking_in_time: pd.DataFrame of the ranking where each row is another match, sorted in time
        datetimes: pd.Series of all matches datetimes for sorting or axis setting purposes
    """
    model = PlackettLuce(limit_sigma=True, balance=True)
    match_list, datetimes = _combine_matches(cfg)

    ranking = {}

    for player in animal_ids:
        ranking[player] = model.rating()

    ranking_df = []

    for (loser_name, winner_name), datetime in zip(match_list, datetimes):
        new_ratings = model.rate(
            [[ranking[loser_name]], [ranking[winner_name]]], ranks=[1, 0]
        )

        ranking[loser_name] = new_ratings[0][0]
        ranking[winner_name] = new_ratings[1][0]

        intermediate = {
                'mu': [],
                'sigma': [],
                'ordinal': [],
                'animal_id': [],
                'datetime': [],
            }
        
        for animal in ranking.keys():
            intermediate['mu'].append(ranking[animal].mu)
            intermediate['sigma'].append(ranking[animal].sigma)
            intermediate['ordinal'].append(round(ranking[animal].ordinal(), 3))
            intermediate['animal_id'].append(animal)
            intermediate['datetime'].append(datetime)

        ranking_df.append(pl.LazyFrame(intermediate))
    ranking_df = pl.concat(ranking_df).with_columns(pl.col('datetime').dt.hour().alias('hour'))
    ranking_df = auxfun.get_phase(cfg, ranking_df)
    ranking_df = auxfun.get_day(ranking_df)

    return ranking_df


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

    matches = intermediate.select(
        "animal_id", "animal_id_chasing", "datetime_chasing"
    ).rename(
        {
            "animal_id": "loser",
            "animal_id_chasing": "winner",
            "datetime_chasing": "datetime",
        }
    )

    chasings = (
        intermediate.group_by(
            ["phase", "day", "phase_count", "hour", "animal_id_chasing", "animal_id"]
        )
        .len(name="chasings")
        .rename({"animal_id": "chased", "animal_id_chasing": "chaser"})
    )

    if save_data:
        chasings.sink_parquet(results_path / f"{key}.parquet", compression="lz4")
        matches.sink_parquet(results_path / "match_df.parquet", compression="lz4")

    return chasings


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

    animals = cfg["animal_ids"]

    ranking = _rank_mice_openskill(cfg, animals, ranking)

    if save_data:
        ranking.sink_parquet(
            results_path / "ranking.parquet", compression="lz4"
        )

    return ranking
