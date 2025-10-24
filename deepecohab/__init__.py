from deepecohab.version import __version__, VERSION

print(f"Loading DeepEcoHab version: {VERSION}...")

from deepecohab.antenna_analysis.activity import (
    calculate_time_spent_per_position,
    calculate_visits_per_position,
    calculate_cage_occupancy,
    create_binary_df,
)
from deepecohab.antenna_analysis.incohort_sociability import (
    calculate_incohort_sociability,
    calculate_pairwise_meetings,
    calculate_time_alone,
)
from deepecohab.antenna_analysis.chasings import (
    calculate_chasings,
    calculate_ranking,
)
from deepecohab.antenna_analysis import auxiliary_analysis

from deepecohab.core.create_project import create_ecohab_project
from deepecohab.core.create_data_structure import get_ecohab_data_structure

from deepecohab.utils.auxfun import (
    load_ecohab_data,
    run_dashboard,
)

from deepecohab.utils.auxfun_plots import set_default_theme

set_default_theme()
