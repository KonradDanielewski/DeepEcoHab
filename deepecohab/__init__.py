from deepecohab.version import __version__, VERSION

from deepecohab.src.activity import (
    calculate_time_spent_per_position,
    calculate_visits_per_position,
    create_binary_df,
)
from deepecohab.src.in_cohort_sociability import (
    calculate_in_cohort_sociability,
    calculate_time_together,
)
from deepecohab.src.chasings import (
    calculate_chasings,
    calculate_ranking,
)
from deepecohab.src.auxiliary_analysis import calculate_approach_to_social_odor
from deepecohab.src.create_project import create_ecohab_project
from deepecohab.src.create_data_structure import get_ecohab_data_structure
from deepecohab.plots.plotting import (
    plot_network_graph,
    plot_ranking_in_time,
    social_dominance_evaluation,
)