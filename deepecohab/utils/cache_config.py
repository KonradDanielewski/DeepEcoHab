from pathlib import Path

import diskcache
from dash import DiskcacheManager

from deepecohab.utils import auxfun

cache_dir = Path(r"\cache")
cache_dir.mkdir(exist_ok=True)

launch_cache = diskcache.Cache(cache_dir)
launch_cache.clear()
background_manager = DiskcacheManager(launch_cache)


@launch_cache.memoize()
def get_project_data(config_tuple):
	config = dict(config_tuple)
	results_path = Path(config["project_location"]) / "results"
	if not results_path.exists():
		return {}

	return {
		name: auxfun.load_ecohab_data(config, name, return_df=True)
		for name in auxfun.df_registry.list_available()
		if "binary" not in str(name)
	}
