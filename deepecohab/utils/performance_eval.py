import time, resource, multiprocessing as mp
from datetime import datetime

from pathlib import Path

import pandas as pd
import polars as pl
import statistics as stats
import traceback

import deepecohab
from deepecohab.utils import auxfun

def _run_and_measure(target, args, kwargs, conn):
    try:
        t0 = time.perf_counter()
        out = target(*args, **kwargs)
        t1 = time.perf_counter()
        peak_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        peak_mb = peak_kb / 1024

        try:
            rows = len(out); cols = out.shape[1]
        except Exception:
            rows = cols = None

        bytes_out = None
        df_type = None
        try:
            import pandas as pd
            if isinstance(out, pd.DataFrame):
                bytes_out = int(out.memory_usage(deep=True).sum())
                df_type = "pandas"
        except Exception:
            pass
        try:
            import polars as pl
            if bytes_out is None and isinstance(out, pl.DataFrame):
                bytes_out = int(out.rechunk().estimated_size())
                df_type = "polars"
        except Exception:
            pass

        kb_out = bytes_out / (1024*2)
        conn.send({"ok": True, "wall_s": t1 - t0, "peak_mb": peak_mb,
                   "rows": rows, "cols": cols, "kb_out": kb_out, "df_type": df_type})
    except Exception:
        conn.send({"ok": False, "error": traceback.format_exc()})
    finally:
        conn.close()

def measure_call(func, *args, **kwargs):
    """
    Run func(*args, **kwargs) in a fresh process.
    Returns: dict(wall_s, peak_mb, rows, cols, kb_out)
    """
    parent, child = mp.Pipe(duplex=False)
    p = mp.Process(target=_run_and_measure, args=(func, args, kwargs, child))
    p.start()
    result = parent.recv()
    p.join()
    if not result.get("ok"):
        raise RuntimeError(f"Child failed:\n{result.get('error')}")

    return {k: v for k, v in result.items() if k != "ok"}

def measure_many(func, *args, repeats=5, **kwargs):
    results = [measure_call(func, *args, **kwargs) for _ in range(repeats)]
    return {
        "wall_s_median": stats.median(r["wall_s"] for r in results),
        "peak_mb_median": stats.median(r["peak_mb"] for r in results),
        "kb_out_median": stats.median(
            r["kb_out"] for r in results if r.get("kb_out") is not None
        ) if any(r.get("kb_out") is not None for r in results) else None,
        "df_type": results[0]["df_type"],
        "runs": results,
    }

def save_results(results, save_dir):
    rows = []
    for r in results:
        rows.append({
            "name": r.get("name"),
            "wall_s_median": r.get("wall_s_median"),
            "peak_mb_median": r.get("peak_mb_median"),
            "kb_out_median": r.get("kb_out_median"),
            "n_runs": len(r.get("runs", [])),
            "df_type": r.get("df_type"),
        })
    df = pd.DataFrame(rows)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    df.to_csv(save_dir / f"perofrmance_results_{ts}.csv")


if __name__ == "__main__":
    mp.set_start_method("spawn", force=True)

    example_dir = Path.cwd() / "examples"

    cfg = deepecohab.create_ecohab_project(
        project_location=example_dir,
        experiment_name='performance_eval',
        data_path=example_dir / 'test_data',
        start_datetime='2023-05-24 12:00:00',
        finish_datetime='2023-05-29 23:00:00',
        light_phase_start='00:00:00',
        dark_phase_start='12:00:00',
    )
    
    save_dir = Path(example_dir / "performance")
    save_dir.mkdir(exist_ok=True)

    funcs = [
        ("main_df", deepecohab.get_ecohab_data_structure, {"cfp": cfg, "overwrite":True}),
        #("binary_df", deepecohab.create_binary_df, {"cfp": cfg, "return_df":True, "overwrite":True}),
        # ("chasings", deepecohab.calculate_chasings, {"cfp": cfg}),
        # ("ranking", deepecohab.calculate_ranking, {"cfp": cfg}),
        # ("time_per_position", deepecohab.calculate_time_spent_per_position, {"cfp": cfg}),
        # ("cage_occupancy", deepecohab.calculate_cage_occupancy, {"cfp": cfg}),
        # ("visits_per_position", deepecohab.calculate_visits_per_position, {"cfp": cfg}),
        # ("time_alone", deepecohab.calculate_time_alone, {"cfp": cfg}),
        # ("incohort_sociability", deepecohab.calculate_incohort_sociability, {"cfp": cfg}),
    ]

    results = []
    for name, fn, kw in funcs:
        fn_stats = measure_many(fn, repeats=1, **kw)
        fn_stats["name"] = name
        results.append(fn_stats)
        print(name, fn_stats)

    save_results(results, save_dir)

