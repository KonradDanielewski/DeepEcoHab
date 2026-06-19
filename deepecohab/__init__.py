from importlib.metadata import version

from deepecohab.analysis.antenna_analysis import (
	calculate_activity as calculate_activity,
)
from deepecohab.analysis.antenna_analysis import (
	calculate_chasings as calculate_chasings,
)
from deepecohab.analysis.antenna_analysis import (
	calculate_features as calculate_features,
)
from deepecohab.analysis.antenna_analysis import (
	calculate_incohort_sociability as calculate_incohort_sociability,
)
from deepecohab.analysis.antenna_analysis import (
	calculate_matches as calculate_matches,
)
from deepecohab.analysis.antenna_analysis import (
	calculate_pairwise_meetings as calculate_pairwise_meetings,
)
from deepecohab.analysis.antenna_analysis import (
	calculate_ranking as calculate_ranking,
)
from deepecohab.analysis.antenna_analysis import (
	calculate_tube_test as calculate_tube_test,
)
from deepecohab.core.create_data_structure import (
	get_ecohab_data_structure as get_ecohab_data_structure,
)
from deepecohab.core.create_project import (
	create_ecohab_project as create_ecohab_project,
)
from deepecohab.core.registries import (
	df_registry as df_registry,
)
from deepecohab.core.registries import (
	plot_registry as plot_registry,
)
from deepecohab.plotting import plot_catalog as plot_catalog
from deepecohab.utils.auxfun import (
	load_ecohab_data as load_ecohab_data,
)
from deepecohab.utils.auxfun import (
	read_config as read_config,
)
from deepecohab.utils.auxfun_plots import (
	PlotConfig as PlotConfig,
)
from deepecohab.utils.auxfun_plots import (
	set_default_theme as set_default_theme,
)

__version__ = version("deepecohab")

set_default_theme()
