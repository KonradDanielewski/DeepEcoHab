from deepecohab.version import __version__, VERSION

from deepecohab.antenna_analysis.activity import (
    calculate_time_spent_per_position,
    calculate_visits_per_position,
    create_binary_df,
)
from deepecohab.antenna_analysis.in_cohort_sociability import (
    calculate_in_cohort_sociability,
    calculate_time_together,
)
from deepecohab.antenna_analysis.chasings import (
    calculate_chasings,
    calculate_ranking,
)
from deepecohab.antenna_analysis import auxiliary_analysis
from deepecohab.core.create_project import create_ecohab_project
from deepecohab.core.create_data_structure import get_ecohab_data_structure
from deepecohab.plots.plotting import (
    plot_network_graph,
    plot_ranking_in_time,
    social_dominance_evaluation,
    plot_cage_position_time,
    plot_cage_position_visits,
    plot_time_together
)