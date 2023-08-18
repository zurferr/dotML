import os
from typing import Dict, List

import yaml


def load_cubes(file_path: str) -> Dict:
    with open(file_path, 'r') as f:
        cubes = yaml.safe_load(f)
    return cubes


def load_cube_configs(dir_path: str = "cubes") -> List[Dict]:
    cube_configs = []
    for file in os.listdir(dir_path):
        if file.endswith(".yaml"):
            cube_config = load_cubes(os.path.join(dir_path, file))
            cube_configs.append(cube_config)
    return cube_configs
