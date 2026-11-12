-- Fails if any day in the city table has less than 90% of its expected readings.
select * from {{ ref('fct_city_daily') }} where data_coverage < 0.90
