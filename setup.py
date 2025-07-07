import setuptools

with open('README.md', 'r') as f:
    long_description = f.read()

setuptools.setup(
    name='deepecohab',
    version='0.2',
    author='Konrad Danielewski',
    author_email='kdanielewski@gmail.com',
    description='EcoHab with some machine learning',
    include_package_data=True,
    packages=setuptools.find_packages(),
    classifiers=[
        'Programming Language :: Python :: 3',
        'Operating System :: OS Independent'
    ],
    python_requires='>=3.10',
    install_requires=[
        'numpy',
        'plotly',
        'matplotlib',
        'scipy',
        'pandas',
        'tables',
        'toml',
        'openskill',
        'networkx',
        'nbformat',
        'kaleido==1.0.0rc13',
        'joblib',
        'tqdm',
        'tzlocal',
    ], 
    url='https://github.com/KonradDanielewski/DeepEcoHab'
)