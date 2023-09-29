import os

from setuptools import setup, find_packages

# Get the long description from the README file
with open(os.path.join(os.path.dirname(__file__), 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='dotml',
    version='0.1.8',
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'dotml = dotml.cli:app',
        ],
    },
    install_requires=[
        'pyyaml',
        'typer',
        'json5',
    ],
    long_description=long_description,
    long_description_content_type='text/markdown',
)
