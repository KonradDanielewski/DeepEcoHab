# What is DeepEcoHab?

DeepEcoHab is a package for analysis of data acquired in the EcoHab system - a semi-naturalistic cage design for long-term recording of a group of up to 12 mice.
The package provides three main modules:

### 1. Antenna module
used for analysis of data from the antennas only - a set of optimized, fast functions to analyze your experiments purely on information obtained from animals crossing the antennas, such as chasings, time spent in cages, number of visits, in-cohort sociability etc. Provides an approximate information about the social structure and social hierarchy type.
   
### 2. Pose module
used for analysis of pose estimation data - provides a detailed behavior analysis as well as it's effects on the social structure. Can be used for phenotyping, social behavior analysis, studies of social hierarchy formation etc. Analysis is performed on multiple levels - heuristics based on kinematics, unsupervised and supervised behavior segmentation. 

### 3. Visualization module
you can quicky and easily visualize the most important results of your analysis thanks to our dashboard with interactive plots and summary of the analysis results.

Analyze your data in steps, curating the analysis for your goals or take advantage of our 'one-step-approach' and just analyze all your data seamlessly with a click of button!

## Installation

In the spirit of open-source we recommend the [uv](https://docs.astral.sh/uv/) package and project manager to work with deepecohab. 

```
cd location_to_clone_to
git clone https://github.com/KonradDanielewski/DeepEcoHab.git
cd DeepEcoHab
pip install .
```

## Data structure of DeepEcoHab

By defualt all the results of your analysis are stored in a Hierarchical Data Format in the form of MultiIndexed Pandas DataFrames. The goal here was simplicity - the multiple tables are similarily indexed allowing easy slicing and quick access to the parts of data that interest you! Results are always stored within your project directory under `results` in an `.h5` file.

To load the data, simply provide the path to the projects' config and a key of the table you want to access:
```python
deepecohab.load_ecohab_data(config_path, table_key)
```

Full list of available keys can be found [here](./data_keys.md).

## Data Visualization

Preferable way to visualize the results is with the use of our [Dashboard](./dashboard.md) but plots can also be opened invidually from within the `plots` directory inside your project folder. 

Additionally, for the users convenience every plot can be saved as a json file and then opened with `plotly.io.read_json()`. This allows further modification and beautification as well as saving into a prefered format and resolution for publication purposes.

## DeepEcoHab team


## Citations

```{bibliography}
```

