# DeepEcoHab: fast and intuitive data analysis platform for your EcoHab experiments

[![PyPI version](https://img.shields.io/pypi/v/deepecohab.svg)](https://pypi.org/project/deepecohab/)
[![Python versions](https://img.shields.io/pypi/pyversions/deepecohab.svg)](https://pypi.org/project/deepecohab/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/KonradDanielewski/DeepEcoHab/blob/main/LICENSE)

DeepEcoHab is an analytics platform built for preprocessing, analysis and visualization of data acquired in the DeepEcoHab.

Our backend is built on [Polars](https://pola.rs/) - Extremely fast Query Engine for DataFrames, written in Rust and visualization utilizes [Plotly](https://plotly.com/), providing interactive, high quality and responsive plots of experiments regardless of their length.

## Installation

We keep DeepEcoHab lean to ensure easy integration and fast installation. In the
spirit of open-source we build on [uv](https://docs.astral.sh/uv/) — a fast,
self-contained Python package manager.

### Step 1 — Install `uv`

**Windows:**
```
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Linux / macOS:**
```
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Step 2 — Install DeepEcoHab

Install DeepEcoHab into an environment:

```
uv venv
# Windows:        .venv\Scripts\activate
# Linux / macOS:  source .venv/bin/activate
uv pip install deepecohab
```

Already have an environment running `python>=3.12`? Just run `pip install deepecohab`.

We recommend [VSCode](https://code.visualstudio.com/download) with the Jupyter
extension to run the example notebooks provided in the repository.

## Example data

We provide 3 example datasets that reflect 3 main possibilites for an EcoHab layout.

- [example_notebook](./examples/example_notebook.ipynb) for a vanilla 4 cage, 8 antenna setup.
- [example_notebook_custom_layout](./examples/example_notebook_custom_layout.ipynb) for a custom layout that can be user defined in the `config.toml` of the created project.
- [example_notebook_field](./examples/example_notebook_field.ipynb) for a field EcoHab layout.

## Data structure:

The data is stored in parquet format - an open-source, column-oriented data storage format which allows extremely fast read/write operations of large dataframes. Every recording in a project keeps one parquet file per analysis table, loaded with `recording.load_results(key)`.

To get the list of available keys call `deepecohab.core.data_model.DataFrameRegistry.list_available()`; similarly `deepecohab.PlotRegistry.list_available()` lists the available visualizations. See the [antenna analysis guide](./docs/tutorial_antenna.md) and [plotting guide](./docs/plotting.md).

## Roadmap

1. Full web-app style GUI, deployable via a docker container.
2. Group analysis - combined analysis of multiple cohort, comparing different groups of cohorts.
3. Pose estimation based analysis of animal interactions and more detailed social structure analysis.
