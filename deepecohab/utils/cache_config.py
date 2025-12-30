from pathlib import Path

import diskcache
import polars as pl
from dash import DiskcacheManager

cache_dir = Path(r"C:\Repositories\cache")
cache_dir.mkdir(exist_ok=True)

launch_cache = diskcache.Cache(cache_dir)
background_manager = DiskcacheManager(launch_cache)


@launch_cache.memoize(expire=3600, tag="project_data")
def get_project_data(config: dict):
	results_path = Path(config["project_location"]) / "results"
	if not results_path.exists():
		return {}

	return {
		file.stem: pl.read_parquet(file)
		for file in results_path.glob("*.parquet")
		if "binary" not in str(file)
	}
