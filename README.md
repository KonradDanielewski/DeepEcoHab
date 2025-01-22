### Installation

To install DeepEcoHab you can use the provided yaml file and then pip install:

```
git clone https://github.com/KonradDanielewski/DeepEcoHab.git
cd where/you/cloned/repo
conda env create -f conda_env/env.yaml
conda activate deepecohab
pip install -e .
```


TODO:
1. Static plot export - kaleido issues, check if version dependent (python, plotly, kaleido)
2. Activity plots - time spent in cages, visits etc.
3. Streamline antenna_pair creation for positions (product of adjacent antennas for cages and tunnels (is it necessary?)

Data structure:

experiment_name_data.h5 contains all the data under different keys in a hierarchical data format. 

Keys:

"main_df" is the ecohab data structure - each antenna read assigned to an animal, position of the animal, time spent in it etc.
"chasings" is the chasings matrix. In the future probably will be chasing matrices per phase
"end_ranking" contains the end ranking as an ordinal calculated from the final ranking with Plackett-Luce 
