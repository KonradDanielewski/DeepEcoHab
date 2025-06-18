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

This is the main data structure of our experiment. All other analyses are derived from this one way or another. For the ease of use and to avoid potential issues with user input the from this point on the config file controls all of the data loading, saving and principles of analysis. Hence, the user only needs to provide:

```python
df = deepecohab.get_ecohab_data_structure(config_path)
```

## Chasings and ranking - social hierarchy analysis

Social hierarchy analysis is based on how mice chase eachother through the tunnel where the one chasing others is considered to be more dominant. In the created data structures the value corresponds to the number of chasings done by the animal from the column index i.e. how many times it chased the animal from the row index.
```python
chasings = deepecohab.calculate_chasings(config_path)
```

Ranking is a feature implemented based on a Plackett Luce algorithm used in multiplayer video games for the purposes of ranking the players. It allows for a more robust calculation of the actual place in the social hierarchy by rewarding chasing individuals that are higher in the hierarchy while lowering the value of chasing those that are lower in the hierarchy

```python
ranking = deepecohab.calculate_ranking(config_path)
```

## Acitvity and sociability measures

Additional users can analyze time spent in each possible location and number of visits to that location as well as pairwise time spent together. Those are also then used to calculate in-cohort sociability - a metric of pairwise social prefernce between mice.

```python
time_per_position = deepecohab.calculate_time_spent_per_position(config_path)
visits_per_position = deepecohab.calculate_visits_per_position(config_path)
time_together = deepecohab.calculate_time_together(config_path, minimum_time=2)
in_cohort_sociability = deepecohab.calculate_in_cohort_sociability(config_path)
```

In calculating time together a user can also specify minimum time of the interaction. Interactions shorter than that will be discarded.

## Additional analysis

Not part of the main analysis pipeline additional analysis are provided for experiments commonly conducted within the EcoHab system, e.g. approach to social odor:

Approach to social odor calculates time spent in the stimulation cage and time spent in the control cage normalized by the total stimulation time (or bin length if analyzed in bins). The same is done for this period of time in the previous day. Data is then MutliIndexed per bin and stored in four columns corresponding to the normalized time spent in each of the cages. 

```python
deepecohab.auxiliary_analysis.calculate_approach_to_social_odor(
  config_path = config_path,
  stimulation_start = '2023-05-24 12:00:00', #datetime str of YYYY-MM-DD HH:MM:SS format
  stimulation_end = '2023-05-24 14:00:00',
  stimulation_cage = 'cage_1',
  control_cage = 'cage_3',
  N_time_bins = 10, # Number of time bins into which the data should be divided
)
```
The provided code would analyzed the data in 10 time bins, each 12 minutes long starting from 12:00 ending at 14:00 on May 24th and calculating the same for May 25th.



