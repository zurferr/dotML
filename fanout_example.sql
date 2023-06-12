orders:
- id
- country
- total
- booking_date

order_items:
- id
- order_id
- product_category
- quantity

-- revenue, quantity by country, product_category


-- revenue, quantity by country, day
-- 🐞 fanout/overcount problem

select
    date_trunc(day, orders.booking_date) as booking_date,
    orders.country as country,
    sum(orders.total) as revenue, --that would overcount
    sum(order_items.quantity) as quantity
from orders
left join order_items
on orders.id = order_items.order_id
group by 1;


-- late join
-- 🐞 dimension is not accessible

with order_metrics as (
    select
        date_trunc(day, orders.booking_date) as booking_date,
        orders.country as country,
        sum(orders.total) as revenue
    from orders
),
order_items_metrics as (
    select
        date_trunc(day, orders.booking_date) as booking_date,
        orders.country as country,
        sum(order_items.quantity) as quantity
    from orders
    left join order_items
    on orders.id = order_items.order_id
)
select
    a.booking_date,
    a.country,
    a.revenue,
    a.quantity
from order_metrics a
join order_items_metrics b
on a.booking_date = a.booking_date and b.country = b.country


-- revenue, quantity by country, product_category
-- fix with pk
-- 🐞 dimension tables can also get duplicate order id, when multiple product categories are in the same order

with order_dimension as (
    select
        orders.id as pk,
        order_items.product_category as product_category
    left join order_items
    on orders.id = order_items.order_id
    group by 1, 2
)
, order_metrics as (
    select
        order_dimension.product_category as product_category,
        orders.country as country,
        sum(orders.total) as revenue
    from orders
    join order_dimension
    on orders.id = order_dimension.pk
),
order_items_dimension as (
    select
        order_items.id as pk,
        orders.country as country
    left join order_items
    on orders.id = order_items.order_id
    group by 1, 2
),
order_items_metrics as (
    select
        order_items.product_category as product_category,
        order_items_dimension.country as country,
        sum(order_items.quantity) as quantity
    from order_items
    left join order_items_dimension
    on order_items.id = order_items_dimension.pk
)
select
    a.product_category,
    a.country,
    a.revenue,
    b.quantity
from order_metrics a
join order_items_metrics b
on a.booking_date = a.booking_date and b.country = b.country