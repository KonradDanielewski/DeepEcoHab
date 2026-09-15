# What is DeepEcoHab?

DeepEcoHab is a package for analysis of data acquired in the EcoHab system - a semi-naturalistic cage design for long-term recording of a group of up to 12 mice.
The package provides three modules:

### 1. Antenna analysis
`deepecohab.core` - a set of optimized, fast functions to analyze your experiments purely on information obtained from animals crossing the antennas: time spent in cages and tunnels, number of visits, time alone, chasings and dominance ranking, pairwise meetings, in-cohort sociability, and a feature table that compares animals across recordings. Provides an approximate picture of the social structure and social hierarchy type.

### 2. Auxiliary analyses
`deepecohab.auxiliary_analysis` - analyses kept outside the routine pipeline, which you run yourself when you need them, such as the spontaneous tube test.

### 3. Plotting
`deepecohab.plotting` - interactive Plotly figures of the most important results, built straight from an analysed recording.

Analysis of pose estimation data is planned.

Organise your recordings into a project, then analyze them step by step or run the whole pipeline over every recording with one call.

## Installation

DeepEcoHab requires Python 3.12 or newer. In the spirit of open-source we recommend the [uv](https://docs.astral.sh/uv/) package and project manager to work with deepecohab.

```
uv pip install deepecohab
```

To install from source:

```
cd location_to_clone_to
git clone https://github.com/KonradDanielewski/DeepEcoHab.git
cd DeepEcoHab
pip install .
```

## Data structure of DeepEcoHab

A project is a directory. Each recording in it keeps its validated metadata, a copy of its antenna registrations, and the results of its analysis - one [Parquet](https://parquet.apache.org/) file per table, read with [Polars](https://pola.rs/):

```
my_project/
  project.json
  project.log
  recording_name/
    config.json
    raw/data.parquet
    results/
      main_df.parquet
      activity_df.parquet
      ...
```

To load a table, open the project and ask the recording for it by name:

```python
import deepecohab as deh

project = deh.Project.load("path/to/my_project")
activity = project["recording_name"].load_results("activity_df")
```

Every table, and what it holds, is described in the [antenna analysis guide](./tutorial_antenna.md#the-analysis-tables).

## Data Visualization

Plots are built from an analysed recording by name:

```python
figure = deh.plot("activity-bar", project["recording_name"])
figure.show()
```

Every figure is a Plotly figure, so it can be modified further, saved as an interactive `.html` file with `figure.write_html()`, exported as an image in a preferred format and resolution for publication with `figure.write_image()`, or saved as JSON with `figure.write_json()` and reopened with `plotly.io.read_json()`. See [Plotting](./plotting.md) for every available plot and its options.

## DeepEcoHab team


## Citations

```{bibliography}
```

