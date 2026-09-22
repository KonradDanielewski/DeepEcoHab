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

```
uv venv
# Windows:        .venv\Scripts\activate
# Linux / macOS:  source .venv/bin/activate
uv pip install "deepecohab[app]"
```

Already have an environment running `python>=3.12`? Just run `pip install "deepecohab[app]"`.

### Step 3 — Start the app

```
deepecohab-app
```

The app opens in your browser. Create a project, add your recordings, run the analysis and
build plots — no code involved. This is how we expect most people to use DeepEcoHab.

### Working from code instead

The app is an extra because the analysis itself does not need Dash. If you only want the
library, for scripts or notebooks, install it on its own:

```
uv pip install deepecohab
```

We recommend [VSCode](https://code.visualstudio.com/download) with the Jupyter
extension to run the example notebooks provided in the repository.

To install from source:

```
cd location_to_clone_to
git clone https://github.com/KonradDanielewski/DeepEcoHab.git
cd DeepEcoHab
pip install ".[app]"
```

## Example data

[`examples/data`](./examples/data) ships six real recordings, each a metadata JSON beside its
registrations parquet. [`example_notebook.ipynb`](./examples/example_notebook.ipynb)
runs them end to end: create a project, add every recording, tune the analysis parameters, run
the pipeline and aggregate a project table.

## Data structure:

The data is stored in parquet format - an open-source, column-oriented data storage format which allows extremely fast read/write operations of large dataframes. Every recording in a project keeps one parquet file per analysis table, loaded with `recording.load_results(key)`.

To get the list of available keys call `deepecohab.core.data_model.DataFrameRegistry.list_available()`; similarly `deepecohab.PlotRegistry.list_available()` lists the available visualizations. See the [antenna analysis guide](./docs/tutorial_antenna.md) and [plotting guide](./docs/plotting.md).

## Roadmap

1. Full web-app style GUI, deployable via a docker container.
2. Group analysis - combined analysis of multiple cohort, comparing different groups of cohorts.
3. Pose estimation based analysis of animal interactions and more detailed social structure analysis.

## DeepEcoHab team

DeepEcoHab is developed at the Nencki Institute of Experimental Biology in Warsaw:

- **Konrad Danielewski** ([@KonradDanielewski](https://github.com/KonradDanielewski)) - lead developer and maintainer
- **Ula Włodkowska** ([@uwlodkowska](https://github.com/uwlodkowska))
- **Marcin Lipiec** - principal investigator

With contributions from [@Winiarsky](https://github.com/Winiarsky) and
[@Brosnan-neuro](https://github.com/Brosnan-neuro).

Found a bug or missing a feature? Open an issue
[here](https://github.com/KonradDanielewski/DeepEcoHab/issues).

## Citations

DeepEcoHab has no paper of its own yet. If you use it in published work, please cite the
package together with the paper introducing the Eco-HAB system:

```bibtex
@software{deepecohab,
  title     = {{DeepEcoHab}: fast and intuitive data analysis platform for {EcoHab} experiments},
  author    = {Danielewski, Konrad and W{\l}odkowska, Ula and Lipiec, Marcin},
  year      = {2026},
  publisher = {GitHub},
  url       = {https://github.com/KonradDanielewski/DeepEcoHab}
}

@article{puscian2016ecohab,
  title   = {Eco-{HAB} as a fully automated and ecologically relevant assessment of social impairments in mouse models of autism},
  author  = {Pu{\'s}cian, Alicja and {\L}{\k e}ski, Szymon and Kasprowicz, Grzegorz and Winiarski, Maciej and Borowska, Joanna and Nikolaev, Tomasz and Boguszewski, Pawe{\l} M. and Lipp, Hans-Peter and Knapska, Ewelina},
  journal = {eLife},
  volume  = {5},
  pages   = {e19532},
  year    = {2016},
  doi     = {10.7554/eLife.19532}
}
```
