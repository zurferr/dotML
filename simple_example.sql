orders:
- id
- country
- total
- booking_date


-- user: revenue, average order value in France, by day
-- formatted query { fields: ['orders.booking_date_day', 'orders.country', 'orders.revenue', 'orders.aov'], filters: { orders.country: 'France' }}

-- generated query
select
    date_trunc(day, orders.booking_date) as booking_date_day,
    orders.country as country,
    sum(orders.total) as revenue,
    avg(orders.total) as aov
from orders
where orders.country = 'France'
group by 1, 2;