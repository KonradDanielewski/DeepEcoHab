### Installation

To install DeepEcoHab in editable mode you can use the provided yaml file and then pip install:

```
cd location/to_clone_to
git clone https://github.com/KonradDanielewski/DeepEcoHab.git
cd DeepEcoHab
conda env create -f environment/env.yaml
conda activate deepecohab
pip install -e .
```


TODO:
1. Static plot export - kaleido issues, check if version dependent (python, plotly, kaleido) - This may be a chromium not on PATH in the current env issue
2. Activity plots - time spent in cages, visits etc.
3. Streamline antenna_pair creation for positions (product of adjacent antennas for cages and tunnels (is it necessary?)

### Data structure:

experiment_name_data.h5 contains all the data under different keys in a hierarchical data format. 

Data keys are listed [here.](./docs/data_keys.md)
