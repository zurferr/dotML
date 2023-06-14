![DotCube](assets/dotcube.png)

# Cuby
⚠️ still in alpha ⚠️
Cuby is a lightweight semantic layer with minimal abstractions.
It enables fetching metrics, filtered by dimensions, by parsing metric queries based on a data model.
The data model defines dimensions and metrics similar to LookML and supports joins on primary keys.
The data model is defined in YAML files.
The package generates a SQL query that you can use to fetch your results.

## Installation

```bash
pip install cuby
```

## Usage

Cuby can be used both as a Python package and through its command line interface.

### As a Python Library

You can import the `load_cubes`, and `generate_sql_query` functions from their respective modules to use in your Python
code.

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

## Is this for me?

Cuby is for you if are a tool builder and want to:

1. query metrics and dimensions consistently and correctly
2. want to support highly flexible analytics without writing complex SQL

We build Cuby for [Dot](https://getdot.ai), but believe it can be useful for other tool builders as well.

In the future, Cuby might also be for you if you are a data analyst and want to:

1. have consistent metrics across all your tools
2. implement a semantic layer for your data warehouse

## Why Cuby?

OLAP cubes, hypercubes, metric stores and semantic layers are all different names for the same thing: a data model that
defines dimensions and metrics, and a query engine that can parse metric queries and generate SQL queries to fetch the
results.
All the existing solutions we found are tightly coupled with a specific tool or database, and are not easy to use with
other tools.

*What about dbt Metricflow?*

There is a chance that dbt's [metricflow](https://github.com/dbt-labs/metricflow) could take this place, but today (
15.06.2023):

1. it does not have a permissive license for tool builders,
2. is still in beta and,
3. is pretty complex: 1359 files vs 12 files of cuby
4. seems harder to learn, because of more abstractions in the data model

However, Cuby only produces sql queries based on the defined data model.
There is no UI, no caching, and no permissions.

today it does:

1. support joins on primary keys
2. nested metrics and dimensions
3. post-processing of metrics with window function (e.g. average over 7 days, cumulative sum, etc.)

## Defining Cubes

Cubes are defined in YAML files with the following structure:

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

Basically all SQL databases are supported: PostgreSQL, Snowflake, Redshift, BigQuery, Databricks SQL, Trino, Druid,
Oracle, MSSQL ...

## Full Example

Let's say we have an online store with the following tables.

```sql
CREATE TABLE orders (
  id INT PRIMARY KEY,
  booking_date DATE,
  country_id INT,
  status VARCHAR(255),
  total INT
);
```

```sql
CREATE TABLE order_items (
    id INT PRIMARY KEY,
    order_id INT,
    product_id INT,
    quantity INT,
    price INT
    );
```

Our data model would look like this.

```yaml
cubes:
  - name: orders
    table: my_db.prod.orders
    always_filter:
      - "${table}.booking_date >= '2019-01-01'"
      - "${table}.status = 'confirmed'"
    dimensions:
      - name: id
        sql: ${table}.id
        primary_key: true
      - name: booking_date
        sql: date_trunc(${time_frame},${table}.booking_date)
        variants:
          - time_frame: [day, week, month, quarter, year]
      - name: country_id
        sql: ${table}.country_id
    metrics:
      - name: revenue
        sql: sum(${table}.total)
      - name: average_order_value
        sql: avg(${table}.total)
      - name: revenue_big_orders
        sql: sum( iff(${table}.total > 100, ${table}.total, 0) )
    window_metrics:
      - name: average_order_value_rolling_30_days
        sql: sum(${revenue}) over (order by ${booking_date_day} rows between 30 preceding and current row)

  - name: orders_items
    table: my_db.prod.orders_line_items
    dimensions:
      - name: id
        sql: ${table}.id
        primary_key: true
      - name: order_id
        sql: ${table}.order_id
      - name: product
        sql: ${table}.product_id
    metrics:
      - name: quantity
        sql: sum(${table}.quantity)
```

Now, we can query the data model with Cuby.

```python
from cuby import load_cubes, generate_sql_query

cubes = load_cubes("data_model.yaml")
query = {
    "fields": ["orders.booking_date_month", "orders.revenue", "orders_items.quantity"],
    "filters": ["${orders.country_id} = '67'"],
    "sorts": ["orders.booking_date_month"],
    "limit": 100
}
sql_query = generate_sql_query(cubes, query)
print(sql_query)
```

The result:

```sql
```

The generated SQL query looks like this:

```sql
with orders_R5S_dimension as (
    select  orders_R5S.id as pk0
    from demo_db.public.orders as orders_R5S
    where (orders_R5S.booking_date >= '2019-01-01') and (orders_R5S.status = 'confirmed')
    group by 1
), orders_items_0B7_dimension as (
    select  
        orders_items_0B7.id as pk0,
        date_trunc(month,orders_R5S.booking_date) as booking_date_month
    from demo_db.public.orders_line_items as orders_items_0B7
    right join demo_db.public.orders as orders_R5S
          on orders_R5S.id = orders_items_0B7.order_id
    group by 1, 2
), orders_R5S_metrics as (
    select  date_trunc(month,orders_R5S.booking_date) as booking_date_month,
            orders_R5S.country_id,
            sum(orders_R5S.total) as revenue
    from demo_db.public.orders as orders_R5S 
            join orders_R5S_dimension as orders_R5S_dimension 
            on orders_R5S.id = orders_R5S_dimension.pk0
    where (orders_R5S.booking_date >= '2019-01-01') and (orders_R5S.status = 'confirmed')
    group by 1
), orders_items_0B7_metrics as (
    select  orders_items_0B7_dimension.booking_date_month,
            orders_items_0B7_dimension.country_id,
    sum(orders_items_0B7.quantity) as quantity
    from demo_db.public.orders_line_items as orders_items_0B7 
            join orders_items_0B7_dimension as orders_items_0B7_dimension 
            on orders_items_0B7.id = orders_items_0B7_dimension.pk0
    group by 1
)
select 
    orders_R5S_metrics.booking_date_month, 
    orders_R5S_metrics.revenue, 
    orders_items_0B7_metrics.quantity 
from orders_R5S_metrics as orders_R5S_metrics
join orders_items_0B7_metrics as orders_items_0B7_metrics
    on orders_R5S.booking_date_month = orders_items_0B7.booking_date_month 
    and orders_R5S.country_id = orders_items_0B7.country_id
where (orders_R5S_metrics.country_id = '67')
order by 1
limit 100
```

## Contributing

If you have suggestions for how Cuby could be improved, or want to report a bug, open an issue!
We'd love all and any contributions.

One area where we would especially appreciate help is a Tableau compiler, so that Cuby cubes can be used as a data
source in Tableau.
Reach out to: hi@sled.so