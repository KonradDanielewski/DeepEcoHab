from pathlib import Path

import diskcache
from dash import DiskcacheManager

from deepecohab.core.registries import df_registry
from deepecohab.utils import auxfun

cache_dir = Path(r"\cache")
cache_dir.mkdir(exist_ok=True)

launch_cache = diskcache.Cache(cache_dir)
launch_cache.clear()
background_manager = DiskcacheManager(launch_cache)


@launch_cache.memoize()
def get_project_data(config_tuple):
	"""Load and cache all available analysis tables for a project config.

	Args:
		config_tuple: project config as a hashable tuple of items (so the
			result can be memoized).

	Returns:
		Mapping of data key to loaded DataFrame, or an empty dict if the
		project has no results directory yet.
	"""
	config = dict(config_tuple)
	results_path = Path(config["project_location"]) / "results"
	if not results_path.exists():
		return {}

	return {
		name: auxfun.load_ecohab_data(config, name, return_df=True)
		for name in df_registry.list_available()
	}
