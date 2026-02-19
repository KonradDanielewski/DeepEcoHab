from deepecohab.analysis.antenna_analysis import (
	calculate_activity as calculate_activity,
	calculate_cage_occupancy as calculate_cage_occupancy,
	calculate_chasings as calculate_chasings,
	calculate_ranking as calculate_ranking,
	calculate_incohort_sociability as calculate_incohort_sociability,
	calculate_pairwise_meetings as calculate_pairwise_meetings,
	calculate_time_alone as calculate_time_alone,
	calculate_tube_test as calculate_tube_test,
	calculate_features as calculate_features,
)

from deepecohab.core.create_data_structure import (
	get_ecohab_data_structure as get_ecohab_data_structure,
)
from deepecohab.core.create_project import (
	create_ecohab_project as create_ecohab_project,
)
from deepecohab.core.registries import (
	df_registry as df_registry,
	plot_registry as plot_registry,
)
from deepecohab.utils.auxfun import (
	load_ecohab_data as load_ecohab_data,
	read_config as read_config,
)
from deepecohab.utils.auxfun_plots import (
    set_default_theme as set_default_theme, 
    PlotConfig as PlotConfig,
)
from deepecohab.version import __version__ as __version__

set_default_theme()
