![DotCube](assets/dotcube.png)
# Cuby
⚠️ work in progress ⚠️

Cuby is a lightweight metric store with minimal abstractions. 
It enables fetching metrics, filtered by dimensions, by parsing metric queries based on a data model. 
The data model defines dimensions and metrics similar to Looker and supports joins on primary keys. 
The data model is defined in YAML files. 
The package generates a SQL query that you can use to fetch your results.

## Installation

```bash
pip install cuby
```

## Usage

Cuby can be used both as a Python library and through its command line interface (CLI).

### As a Python Library

You can import the `load_cubes`, and `generate_sql_query` functions from their respective modules to use in your Python code.

### CLI Commands

To list all cubes:

```bash
cuby list_cubes
```

To list all metrics for a cube:

```bash
cuby list_metrics <cube_name>
```

To execute a query on a model:

```bash
cuby query "<query_json>"
```

The `query` command expects a JSON string as its argument. Here's an example:

```bash
cuby query "{'fields': ['orders.booking_date', 'annual_recurring_revenue', 'churned_revenue'], 'filter': {'country_id': '45', 'product_brand': 'BIG'}, 'sorts': ['booking_date'], 'limit': 300}"
```

## Defining Models

Models are defined in YAML files with the following structure:

```yaml
name: <cube_name>
table: <table_path>
dimensions:
  - name: <dimension_name>
    sql: <sql_expression>
  ...
metrics:
  - name: <measure_name>
    sql: <sql_expression>
  ...
```

Basically all SQL databases are supported: PostgreSQL, Snowflake, Redshift, BigQuery, Databricks SQL, Druid, ...

## Contributing

If you have suggestions for how Cuby could be improved, or want to report a bug, open an issue! 
We'd love all and any contributions.
