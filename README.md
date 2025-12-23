## DeepEcoHab: fast and intuitive data analysis platform for your EcoHab experiments

DeepEcoHab is an analytics platform build for preprocessing, analysis and visualization of data acquired in the DeepEcoHab.

Our backend is built on [Polars](https://pola.rs/) - Extremely fast Query Engine for DataFrames, written in Rust and frontend utilizes [Plotly Dash](https://plotly.com/) which allows for system independent operation - running the app in your Chromium based browser - providing an interactive, high quality and responsive visualization of experiments regardless of their length.

## Installation

We suggest usage of [uv](https://docs.astral.sh/uv/). Installation instructions for both Windows and Linux/MacOS can be found [here](https://realpython.com/python-uv/#using-the-standalone-installer)

To install DeepEcoHab please run the following commands line by line in the terminal:

Turn slashes the other way for Linux and MacOS
```
cd where\you\want\to_clone_to
git clone https://github.com/KonradDanielewski/DeepEcoHab.git
cd DeepEcoHab
uv venv
.venv\Scripts\activate
uv pip install .
```
We recommend using [VSCode](https://code.visualstudio.com/download) with the Jupter extension to run the example notebooks provided in the repository.

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
  <img src="docs/dashboard_image.png" alt="Dashboard Preview" width="600">
</p>

## Data structure:

The data is stored in parquet format - an open-source, column-oriented data storage format which allows extremely fast read/write operations of large dataframes.

To get the list of available keys simply call: `deepecohab.df_registry.list_available()` similarily `deepecohab.plot_registry.list_available()` can be called to obtain the list of currently available visualizations.

## Roadmap

1. Full web-app style GUI, deployable via a docker container - no need coding at all
2. Group analysis - combined analysis of multiple cohort, comparing different groups of cohorts.
3. Pose estimation based analysis of animal interactions and more detailed social structure analysis.