### Installation

If you do not have anaconda/miniconda installed please follow the instructions [here](https://www.anaconda.com/docs/getting-started/miniconda/install).

After it's installed open the Anaconda Prompt and run `conda install git`. Then follow the instructions below by copy-pasting them into the terminal. 
The provided instructions create a new directory on your `C` drive where the downloaded repository will be stored.

To install DeepEcoHab you can use the provided yaml file. Please run the following commands line by line in the terminal:

```
cd C:\
mkdir Repositories
cd Repositories 
git clone https://github.com/KonradDanielewski/DeepEcoHab.git
cd DeepEcoHab
conda env create -f environment/env.yaml
conda activate deepecohab
python -m ipykernel install --user --name=deepecohab
```

After that you can open the `example_notebook.ipynb` located here (if you followed our installation guide) `C:\Repositories\DeepEcoHab\examples`.
We recommend using [VSCode](https://code.visualstudio.com/download) with the Jupter extension to run the notebook. 

### Dashboard

The last function run in the notebook opens the dashboard with visualization of the data from the experiment. It requires a Chromium based browser and opens in it.

### Data structure:

results.h5 contains all the data under different keys in a hierarchical data format. 

Data keys are listed [here.](./docs/data_keys.md)
