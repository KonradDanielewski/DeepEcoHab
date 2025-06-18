from deepecohab.version import __version__, VERSION

from deepecohab.antenna_analysis.activity import (
    calculate_time_spent_per_position,
    calculate_visits_per_position,
    create_binary_df,
)
from deepecohab.antenna_analysis.incohort_sociability import (
    calculate_incohort_sociability,
    calculate_time_together,
    calculate_pairwise_encounters,
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
    plot_cage_position_time,
    plot_cage_position_visits,
    plot_time_together,
    plot_incohort_sociability,
    plot_pairwise_encounters,
    plot_chasings,
)
from deepecohab.utils.auxfun import (
    load_ecohab_data,
    run_dashboard,
)