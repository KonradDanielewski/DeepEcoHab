# DeepEcoHab: fast and intuitive data analysis platform for your EcoHab experiments

[![PyPI version](https://img.shields.io/pypi/v/deepecohab.svg)](https://pypi.org/project/deepecohab/)
[![Python versions](https://img.shields.io/pypi/pyversions/deepecohab.svg)](https://pypi.org/project/deepecohab/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/KonradDanielewski/DeepEcoHab/blob/main/LICENSE)

DeepEcoHab is an analytics platform built for preprocessing, analysis and visualization of data acquired in the DeepEcoHab.

Our backend is built on [Polars](https://pola.rs/) - Extremely fast Query Engine for DataFrames, written in Rust and frontend utilizes [Plotly Dash](https://plotly.com/) which allows for system independent operation - running the app in your Chromium based browser - providing an interactive, high quality and responsive visualization of experiments regardless of their length.

## Quick start

On Windows, three steps get you from nothing to a running dashboard:

```
uv tool install deepecohab   # install as a standalone app
deepecohab-shortcut          # create a desktop icon
```

Then double-click the **DeepEcoHab** icon on your desktop. See
[Installation](#installation) for `uv` setup and other platforms.

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

For most users the simplest path is to install DeepEcoHab as a standalone
application. This puts the `deepecohab` and `deepecohab-shortcut` commands on
your PATH in an isolated environment — no virtual environment to create or
activate:

```
uv tool install deepecohab
```

That's it. Run `deepecohab` to launch the dashboard, which opens automatically
in your browser.

> If the commands aren't found afterwards, run `uv tool update-shell` and reopen
> your terminal.

### Desktop shortcut (Windows)

After `uv tool install deepecohab`, create a clickable desktop icon with:

```
deepecohab-shortcut
```

This places a **DeepEcoHab** shortcut on your desktop. Double-clicking it starts
the dashboard and opens it in your browser — no terminal required. This is the
recommended way to launch DeepEcoHab on Windows.

> On Linux / macOS there is no desktop shortcut — simply run `deepecohab` from
> the terminal to launch the dashboard.

### Using DeepEcoHab as a library

If you want to run the example notebooks or call DeepEcoHab from your own Python
code, install it into an environment instead of as a tool:

```
uv venv
# Windows:        .venv\Scripts\activate
# Linux / macOS:  source .venv/bin/activate
uv pip install deepecohab
```

Already have an environment running `python>=3.12`? Just run `pip install deepecohab`.

We recommend [VSCode](https://code.visualstudio.com/download) with the Jupyter
extension to run the example notebooks provided in the repository.

## How it works

A DeepEcoHab analysis follows three stages. The first two run from Python (the
[example notebooks](#example-data) walk through them end to end); the third is
the interactive dashboard.

1. **Create a project** from your raw EcoHab `.txt` files with
   `deepecohab.create_ecohab_project(...)`. This builds a project folder with a
   `config.toml` describing your layout, light/dark phases, timezone and animal
   IDs.
2. **Run the analysis pipeline** with `deepecohab.df_registry.run_pipeline(config_path)`.
   Results (chasings, activity, sociability, social hierarchy, …) are written to
   the project as fast parquet files.
3. **Explore the results** by launching the dashboard — run `deepecohab` (or
   double-click the desktop shortcut), select your project in the app, and
   browse and compare plots interactively.

## Example data

We provide 3 example datasets that reflect 3 main possibilites for an EcoHab layout.

- [example_notebook](./examples/example_notebook.ipynb) for a vanilla 4 cage, 8 antenna setup.
- [example_notebook_custom_layout](./examples/example_notebook_custom_layout.ipynb) for a custom layout that can be user defined in the `config.toml` of the created project.
- [example_notebook_field](./examples/example_notebook_field.ipynb) for a field EcoHab layout.

## Dashboard

The dashboard contains visualization of the experiment analysis results. It is divided into two tabs: main dashboard tab and a tab for comparisons (when the user wants to compare same plot in different days/phases etc.) and 3 sections:

1. Social hierarchy
2. Activity
3. Sociability

All providing multiple plots controlled via the settings block located on top.

<p align="center">
  <img src="https://raw.githubusercontent.com/KonradDanielewski/DeepEcoHab/main/docs/dash_images/Readme_image.png" alt="Dashboard Preview" width="800">
</p>

## Data structure:

The data is stored in parquet format - an open-source, column-oriented data storage format which allows extremely fast read/write operations of large dataframes.

To get the list of available keys simply call: `deepecohab.df_registry.list_available()` similarily `deepecohab.plot_registry.list_available()` can be called to obtain the list of currently available visualizations.

## Roadmap

1. Full web-app style GUI, deployable via a docker container.
2. Group analysis - combined analysis of multiple cohort, comparing different groups of cohorts.
3. Pose estimation based analysis of animal interactions and more detailed social structure analysis.