### Installation

To install DeepEcoHab you can use the provided yaml file:

```
cd location/to_clone_to
git clone https://github.com/KonradDanielewski/DeepEcoHab.git
cd DeepEcoHab
conda env create -f environment/env.yaml
conda activate deepecohab
python -m ipykernel install --user --name=deepecohab
```

To check out the package please run the example_notebook provided in the examples directory of this repository.

### Data structure:

experiment_name_data.h5 contains all the data under different keys in a hierarchical data format. 

Data keys are listed [here.](./docs/data_keys.md)
