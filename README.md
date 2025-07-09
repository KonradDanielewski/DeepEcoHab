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

To check out the package please run the example_notebook provided in the examples directory of this repository.

<b><u>BIG TODO:</b></u>
1. Pose estimation model training
2. Animal reid with antenna reads
3. Custom tracklet stitching based on more features (our own simplified fork of DLC?)

### Data structure:

experiment_name_data.h5 contains all the data under different keys in a hierarchical data format. 

Data keys are listed [here.](./docs/data_keys.md)
