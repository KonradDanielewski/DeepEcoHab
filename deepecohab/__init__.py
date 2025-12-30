from deepecohab.antenna_analysis.activity import (
	calculate_activity as calculate_activity,
	calculate_cage_occupancy as calculate_cage_occupancy,
)
from deepecohab.antenna_analysis.chasings import (
	calculate_chasings as calculate_chasings,
	calculate_ranking as calculate_ranking,
)
from deepecohab.antenna_analysis.incohort_sociability import (
	calculate_incohort_sociability as calculate_incohort_sociability,
	calculate_pairwise_meetings as calculate_pairwise_meetings,
	calculate_time_alone as calculate_time_alone,
)
from deepecohab.core.create_data_structure import (
	get_ecohab_data_structure as get_ecohab_data_structure,
)
from deepecohab.core.create_project import (
	create_ecohab_project as create_ecohab_project,
)
from deepecohab.utils.auxfun import (
	load_ecohab_data as load_ecohab_data,
	run_dashboard as run_dashboard,
)
from deepecohab.utils.auxfun import df_registry as df_registry
from deepecohab.plotting.dash_plotting import plot_registry as plot_registry
from deepecohab.utils.auxfun_plots import set_default_theme as set_default_theme
from deepecohab.version import __version__ as __version__

set_default_theme()
