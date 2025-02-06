### Installation

To install DeepEcoHab you can use the provided yaml file and then pip install:

```
git clone https://github.com/KonradDanielewski/DeepEcoHab.git
cd where/you/cloned/repo
conda env create -f conda_env/env.yaml
conda activate deepecohab
pip install -e .
```


TODO:
1. Static plot export - kaleido issues, check if version dependent (python, plotly, kaleido)
2. Activity plots - time spent in cages, visits etc.
3. Streamline antenna_pair creation for positions (product of adjacent antennas for cages and tunnels (is it necessary?)

### Data structure:

experiment_name_data.h5 contains all the data under different keys in a hierarchical data format. 

### Keys:

`main_df` is the ecohab data structure - each antenna read assigned to an animal, position of the animal, time spent in it etc.

`chasings` is the chasings matrix. In the future probably will be chasing matrices per phase.

`end_ranking` contains the end ranking as an ordinal calculated from the final ranking with Plackett-Luce. 

`padded_df` same as `main_df` but padded in such way that detections that happen across multiple phases are split to end with the end of the ongoing phase and start as a new detection in the new phase.

`time_per_position` MultiIndex DataFrame with time spent per each positions. Directional tunnel detections are transformed into undirected, i.e. `c1_c2` and `c2_c1` becomes `tunnel_1`

`visits_per_position` MultiIndex DataFrame with the number of visits to each position. Directional tunnel detections are transformed into undirected, i.e. `c1_c2` and `c2_c1` becomes `tunnel_1`

`time_together` MultiIndex DataFrame with time spent together per cage for all possible mouse pair combinations. Measured in seconds.

`in_cohort_sociability` MultiIndex DataFrame with in-cohort sociability measure. More info in the methods section: https://doi.org/10.7554/eLife.19532

`phase_durations` MultiIndex Series per phase with estimated duration of each phase. Measured in seconds and rounded to the closest full hour. Used as total time for division in in-cohort sociability.

`ranking_ordinal` Series, ordinal of the ranking calculated with the Plackett Luce algorithm. Higher value == more dominant animal, based on chasing data

`ranking_in_time` DataFrame, per row update of the ordinal ranking happening at each match, columns are animals

`matches_datetimes` Series containig datetimes of each chasing event for all animals. Can be matched to animals based on ranking in time (or used a index for it)



`_ranking_data` pickle file contains a dictionary with the raw ranking containing mu and sigma values. Can be used between projects when the same mice are used. Allows to start ranking from the last state instead of zero-state