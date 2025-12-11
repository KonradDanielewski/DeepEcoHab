from pathlib import Path

import polars as pl
from openskill.models import PlackettLuce

from deepecohab.utils import auxfun


def _combine_matches(cfg: dict) -> tuple[list, pl.Series]:
    """Auxfun to combine all the chasing events into one data structure"""
    match_lf = auxfun.load_ecohab_data(cfg, "match_df")
    match_df = match_lf.collect()

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

    if not isinstance(ranking, dict):
        ranking = {}

    for player in animal_ids:
        ranking[player] = model.rating()

    ranking_update = []

    for loser_name, winner_name in match_list:
        new_ratings = model.rate(
            [[ranking[loser_name]], [ranking[winner_name]]], ranks=[1, 0]
        )

        ranking[loser_name] = new_ratings[0][0]
        ranking[winner_name] = new_ratings[1][0]

        temp = {
            key: round(ranking[key].ordinal(), 3) for key in ranking.keys()
        }  # alpha=200/ranking[key].sigma, target=1000 for ordinal if ELO like values
        ranking_update.append(temp)

    ranking_in_time = pl.LazyFrame(ranking_update)

    ranking_in_time = ranking_in_time.with_columns(datetimes.alias("datetime"))

    return ranking, ranking_in_time


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
    key = "chasings"

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
    key = "ranking_ordinal"

    ranking_ordinal = None if overwrite else auxfun.load_ecohab_data(config_path, key)

    if isinstance(ranking_ordinal, pl.LazyFrame):
        return ranking_ordinal

    animals = cfg["animal_ids"]
    df = auxfun.load_ecohab_data(config_path, "main_df")

    ranking, ranking_in_time = _rank_mice_openskill(cfg, animals, ranking)

    ranking_df = pl.LazyFrame(
        {
            "animal_id": list(ranking.keys()),
            "mu": [v.mu for v in ranking.values()],
            "sigma": [v.sigma for v in ranking.values()],
        }
    ).with_columns(pl.col("animal_id").cast(pl.Enum(animals)))

    ranking_in_time = ranking_in_time.group_by("datetime", maintain_order=True).tail(1)

    rit_datetimes = ranking_in_time.select("datetime").unique()

    phase_end_marks = (
        df.join(rit_datetimes, on="datetime", how="semi")
        .group_by(["phase", "day", "phase_count"])
        .agg(pl.col("datetime").max().alias("datetime"))
    )

    ranking_ordinal = phase_end_marks.join(ranking_in_time, on="datetime", how="left")

    if save_data:
        ranking_ordinal.sink_parquet(
            results_path / "ranking_ordinal.parquet", compression="lz4"
        )
        ranking_in_time.sink_parquet(
            results_path / "ranking_in_time.parquet", compression="lz4"
        )
        ranking_df.sink_parquet(results_path / "ranking.parquet", compression="lz4")

    return ranking_ordinal
