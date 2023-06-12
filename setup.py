from setuptools import setup, find_packages

setup(
    name='cuby',
    version='0.1',
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'cuby = cuby.cli:app',
        ],
    },
    install_requires=[
        'pyyaml',
        'typer'
    ],
)