# Step by step guide to antenna data analysis

To start analyzing your data using our API first run:

```python
import deepecohab
```

## Create project

The deepecohab project can be created by passing:

```python
config_path = deepecohab.create_ecohab_project(
    project_location=r'path/where/project/will/be/created',
    experiment_name='experiment1',
    data_path=r'path/to/raw/recording/data',
    start_datetime='2023-05-24 12:00:00', 
    finish_datetime='2023-05-29 23:00:00',
    light_phase_start='00:00:00',
    dark_phase_start='12:00:00',
    )
```

Datetime for both start and finish should be provided in a format: `YYYY-MM-DD HH:MM:SS`

If not provided those will be set to the datetimes of first and last antenna reads respectively.

## Create main data structure

This is the main data structure of our experiment. All other analyses are derived from this one way or another. For the ease of use and to avoid potential issues with user input, from this point on the config file controls all of the data loading, saving and principles of analysis. Hence, the user only needs to provide:

```python
df = deepecohab.get_ecohab_data_structure(config_path)
```

This also builds the supporting structures the analysis steps depend on (`padded_df`, `phase_durations`). Run it once before any of the analyses below.

## Run the analysis pipeline

The recommended way to produce every analysis table is to run the pipeline. It resolves the dependencies between steps automatically and runs them in the correct order, yielding progress as `(step_name, current, total)`:

```python
for step, current, total in deepecohab.df_registry.run_pipeline(config_path):
    print(f"[{current}/{total}] {step}")
```

Useful options:

- `overwrite=True` recomputes every step even if a cached result exists (otherwise existing `results/<step>.parquet` files are reused).
- `targets=["feature_df"]` runs only the named step(s) and their dependencies — e.g. recomputing `feature_df` will also (re)build `activity_df`, `match_df`, `chasings_df`, `tube_test_df` and `pairwise_meetings` if needed, but skip unrelated steps.
- Analysis parameters such as `minimum_time` and `chasing_time_window` (see below) can be passed straight through and are forwarded to the steps that use them.

To see the available data keys:

```python
deepecohab.df_registry.list_available()
```

Each step can also be called on its own (the call signatures are described below); they cache to `results/<key>.parquet` and short-circuit on a cached result unless `overwrite=True`.

## Chasings and ranking - social hierarchy analysis

Social hierarchy analysis is based on how mice chase each other through the tunnels - the one doing the chasing is considered to be more dominant. The results are stored in long format, one row per ordered pair of mice per hour per tunnel, where `winner` is the chaser (dominant) and `loser` is the chased, and `chasings` is the number of times the winner chased the loser.

```python
chasings = deepecohab.calculate_chasings(config_path)
```

Chasings are counted from an event-level table, `match_df`, where each row is a single chasing event. It is produced as its own step and can be inspected directly (it is also the input to ranking):

```python
matches = deepecohab.calculate_matches(config_path, chasing_time_window=[0.1, 1.2])
```

`chasing_time_window` defines the minimum and maximum length of a chasing event in seconds (defaults to `[0.1, 1.2]`).

Ranking is a feature implemented based on a Plackett-Luce algorithm used in multiplayer video games for the purposes of ranking the players. Treating each chasing event as a match, it allows for a more robust estimate of an animal's place in the social hierarchy by rewarding chasing individuals that are higher in the hierarchy while lowering the value of chasing those that are lower.

```python
ranking = deepecohab.calculate_ranking(config_path)
```

## Tube test - head-on tunnel encounters

The tube test measures dominance from head-on tunnel encounters: the loser enters a tunnel and retreats to the cage it came from while the winner enters the same tunnel from the opposite end during an overlapping interval and exits later. Results are long format with `winner`/`loser` per hour, like chasings.

```python
tube_test = deepecohab.calculate_tube_test(
    config_path,
    winner_behavior="BOTH",  # "CHASE", "GUARD" or "BOTH"
    max_dwell=10.0,
)
```

- `winner_behavior` selects which winner outcomes to include: `"CHASE"` (the winner follows the loser into the cage it retreated to), `"GUARD"` (the winner returns to its own origin cage), or `"BOTH"` (the union).
- `max_dwell` is the maximum tunnel dwell time, in seconds, for a segment to count - it drops inflated segments synthesised from repeated antenna reads.

## Activity and sociability measures

Time spent in each location and the number of visits to it are computed together as activity, along with time spent alone in each location:

```python
activity = deepecohab.calculate_activity(config_path)
```

Pairwise time spent together and the number of meetings per pair of mice are computed as pairwise meetings. A user can specify the minimum time of an interaction in seconds; interactions shorter than that are discarded:

```python
pairwise = deepecohab.calculate_pairwise_meetings(config_path, minimum_time=2)
```

These feed in-cohort sociability - a metric of pairwise social preference between mice (see DOI:10.7554/eLife.19532):

```python
in_cohort_sociability = deepecohab.calculate_incohort_sociability(config_path)
```

## Feature table

For downstream machine-learning analysis, the metrics above are combined and z-scored into a single long-format feature table per mouse:

```python
features = deepecohab.calculate_features(config_path)
```

## Loading results

Every step writes a parquet file under the project's `results/` directory. Already-computed results can be loaded by key without recomputing:

```python
chasings = deepecohab.load_ecohab_data(config_path, "chasings_df", return_df=True)
```

`return_df=True` returns an eager `DataFrame`; the default returns a `LazyFrame`. Use `deepecohab.df_registry.list_available()` to list the valid keys.
