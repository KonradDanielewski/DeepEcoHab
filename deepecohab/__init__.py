from deepecohab.antenna_analysis.activity import (
    calculate_activity,
    calculate_cage_occupancy,
)
from deepecohab.antenna_analysis.chasings import (
    calculate_chasings,
    calculate_ranking,
)
from deepecohab.antenna_analysis.incohort_sociability import (
    calculate_incohort_sociability,
    calculate_pairwise_meetings,
    calculate_time_alone,
)
from deepecohab.core.create_data_structure import get_ecohab_data_structure
from deepecohab.core.create_project import create_ecohab_project
from deepecohab.utils.auxfun import (
    load_ecohab_data,
    run_dashboard,
)
from deepecohab.utils.auxfun_plots import set_default_theme
from deepecohab.version import VERSION, __version__

set_default_theme()
