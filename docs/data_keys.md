# List of available data keys:

## Antenna data keys:

`main_df` is the ecohab data structure - each antenna read assigned to an animal, position of the animal, time spent in it etc.

`chasings` is the chasings matrix. In the future probably will be chasing matrices per phase.

`padded_df` same as main_df but padded in such way that detections that happen across multiple phases are split to end with the end of the ongoing phase and start as a new detection in the new phase.

`time_per_position` MultiIndex DataFrame with time spent per each positions. Directional tunnel detections are transformed into undirected, i.e. c1_c2 and c2_c1 becomes tunnel_1

`visits_per_position` MultiIndex DataFrame with the number of visits to each position. Directional tunnel detections are transformed into undirected, i.e. c1_c2 and c2_c1 becomes tunnel_1

`time_together` MultiIndex DataFrame with time spent together per cage for all possible mouse pair combinations. Measured in seconds.

`in_cohort_sociability` MultiIndex DataFrame with in-cohort sociability measure. More info in the methods section: https://doi.org/10.7554/eLife.19532

`phase_durations` MultiIndex Series per phase with estimated duration of each phase. Measured in seconds and rounded to the closest full hour. Used as total time for division in in-cohort sociability.

`ranking_ordinal` Series, ordinal of the ranking calculated with the Plackett Luce algorithm. Higher value == more dominant animal, based on chasing data

`ranking_in_time` DataFrame, per row update of the ordinal ranking happening at each match, columns are animals

`matches_datetimes` Series containig datetimes of each chasing event for all animals. Can be matched to animals based on ranking in time (or used a index for it)

`binary_df` dataframe of position of each animal in a binary format, by default per every 100ms.

`social_odor` optional analysis, DataFrame contains proportion of time spent in compartments with and without a social stimulus on the day of the experiment and same day before

`_ranking_data` pickle file contains a dictionary with the raw ranking containing mu and sigma values. Can be used between projects when the same mice are used. Allows to start ranking from the last state instead of zero-state