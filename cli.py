import typer
import os
import json5 as json
from cube import load_cube_configs
from compiler import generate_sql_query
from typing_extensions import Annotated
from typing import Optional

app = typer.Typer()


def get_first_cubes(path: Optional[str]) -> dict:
    if path is None:
        # get current path
        path = os.getcwd()

    r_cubes = load_cube_configs(dir_path=path)
    if len(r_cubes) > 0:
        return r_cubes[0]
    else:
        typer.echo("No cubes found")
        return {}

@app.command()
def cubes(path: Annotated[Optional[str], typer.Argument()] = None):
    cubes = get_first_cubes(path)
    if len(r_cubes) > 0:
        typer.echo('\n'.join([cube.get('name', '') for cube in cubes.get('cubes', [])]))



@app.command()
def fields(cube_name: str, path: Annotated[Optional[str], typer.Argument()] = None):
    cubes = get_first_cubes(path)
    if len(r_cubes) > 0:
        cube = [cube for cube in cubes.get('cubes', []) if cube.get('name') == cube_name]
        if len(cube) > 0:
            fields = cube[0].get('dimensions', []) + cube[0].get('metrics', []) + cube[0].get('window_metrics', [])
            typer.echo('\n'.join([field.get('name', '') for field in fields]))
        else:
            typer.echo(f"Cube {cube_name} not found")


@app.command()
def query(query: str, path: Annotated[Optional[str], typer.Argument()] = None):
    print(query)
    query_dict = {}
    try:
        query_dict = json.loads(query)
    except Exception as e:
        typer.echo("Invalid query: " + str(e))
        return

    cubes = get_first_cubes(path)
    
    if len(cubes) > 1:
        sql = generate_sql_query(cubes, query_dict)
        typer.echo(sql)


if __name__ == "__main__":
    app()
