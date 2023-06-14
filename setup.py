import os

from setuptools import setup, find_packages

# Get the long description from the README file
with open(os.path.join(os.path.dirname(__file__), 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

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
    long_description=long_description,
    long_description_content_type='text/markdown',
)
