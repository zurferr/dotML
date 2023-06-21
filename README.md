![DotCube](assets/dotcube.png)

# dotML
⚠️ still in alpha ⚠️
dotML is a lightweight semantic layer with minimal abstractions.
It enables fetching metrics, filtered by dimensions, by parsing metric queries based on a data model.
The data model defines dimensions and metrics similar to LookML and supports joins on primary keys.
The data model is defined in YAML files.
The package generates a SQL query that you can use to fetch your results.

## Installation

```bash
pip install dotml
```

## Usage

dotML can be used both as a Python package and through its command line interface.

### As a Python Library

You can import the `load_cubes`, and `generate_sql_query` functions from their respective modules to use in your Python
code.

### CLI Commands

```bash
# list all cubes
dotml cubes

# list all metrics for a cube
dotml fields <cube_name>

# query a set of metrics and dimensions
dotml query "<query_json>"
```


The `query` command expects a JSON5 string as its argument. Here's an example:

```bash
dotml query "{
'fields': ['orders.booking_date_month', 'orders.revenue', 'orders_items.quantity'],
'filters': ['${orders.country_id} = 67'],
'sorts': ['orders.booking_date_month'],
'limit': 100
}"
```

## Is this for me?

dotML is for you if are a tool builder and want to:

1. query metrics and dimensions consistently and correctly
2. want to support highly flexible analytics without writing complex SQL

We build dotML for [Dot](https://getdot.ai), but believe it can be useful for other tool builders as well.

In the future, dotML might also be for you if you are a data analyst and want to:

1. have consistent metrics across all your tools
2. implement a semantic layer for your data warehouse

## Why dotML?

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
3. is pretty complex: 1359 files vs 12 files of dotML
4. seems harder to learn, because of more abstractions in the data model

However, dotML only produces sql queries based on the defined data model.
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

### Orders

| id | booking\_date | country\_id | status    | total |
|:---|:--------------|:------------|:----------|:------|
| 1  | 2023-05-12    | 68          | cancelled | 109   |
| 2  | 2023-06-02    | 62          | cancelled | 32    |
| 3  | 2023-04-20    | 67          | confirmed | 213   |
| 4  | 2023-04-30    | 64          | cancelled | 22    |
| 5  | 2023-04-28    | 65          | delivered | 5     |
| 6  | 2023-06-13    | 69          | shipped   | 98    |
| 7  | 2023-04-17    | 62          | delivered | 30    |

### Orders Items

| id | order\_id | product\_id | quantity | price |
|:---|:----------|:------------|:---------|:------|
| 10 | 1         | 8           | 9        | 26    |
| 20 | 2         | 15          | 8        | 91    |
| 21 | 2         | 2           | 3        | 20    |
| 30 | 3         | 19          | 9        | 5     |
| 31 | 3         | 13          | 10       | 71    |
| 32 | 3         | 15          | 4        | 26    |
| 40 | 4         | 17          | 9        | 10    |

Each table gets modeled as a cube in dotML.
A cube encodes the business logic on how data should be aggregated in dimensions and metrics.
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

Now, we can query the data model with dotML.  
*Notice how we are querying metrics across different cubes.  
dotML automatically
prevents [join fanouts](https://www.googlecloudcommunity.com/gc/Technical-Tips-Tricks/The-problem-of-SQL-fanouts/ta-p/587483)*

```python
from dotML import load_cubes, generate_sql_query

cubes = load_cubes("data_model.yaml")
query = {
    "fields": ["orders.booking_date_month", "orders.revenue", "orders_items.quantity"],
    "filters": ["${orders.country_id} = '67'"],
    "sorts": ["orders.booking_date_month"],
    "limit": 100
}
sql_query = generate_sql_query(cubes, query)
# here you can execute the sql query with your favorite database client
```

The result looks like this:

| booking_date_month | revenue | quantity |
|:-------------------|:--------|:---------|
| 2023-04-01         | 802     | 125      |
| 2023-05-01         | 1329    | 212      |
| 2023-06-01         | 1689    | 158      |

---
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
order by 1 limit 100
```

## Contributing

If you have suggestions for how dotML could be improved, or want to report a bug, open an issue!
We'd love all and any contributions.

Two areas where we would especially appreciate help are:

- a Tableau compiler, so that dotML cubes can be used as a data
  source in Tableau (or another BI tool, you care about)
- a dbt_package_wrapper, so that cubes can get materialized by dbt

Reach out to: hi@sled.so
