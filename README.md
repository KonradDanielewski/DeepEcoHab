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
