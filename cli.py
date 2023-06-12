import typer
from cube import load_cubes
from compiler import generate_sql_query

app = typer.Typer()

@app.command()
def list_models():
    cubes = load_cubes()
    typer.echo(f"Cubes: {', '.join(cubes.keys())}")

@app.command()
def list_metrics(cube_name: str):
    cubes = load_cubes()
    cube = cubes.get(cube_name)
    if cube:
        typer.echo(f"Metrics for {cube_name}: {', '.join([metric['name'] for metric in cube['metrics']])}")
    else:
        typer.echo(f"Cube {cube_name} not found")

@app.command()
def query(query: str):
    cubes = load_cubes()
    if len(cubes) > 1:
        sql = generate_sql_query(cubes, query)
        typer.echo(sql)
    else:
        typer.echo(f"Cubes not found")

if __name__ == "__main__":
    app()
