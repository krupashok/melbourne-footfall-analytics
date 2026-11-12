-- Fails if more than 2% of footfall rows have no matching weather.
select 1
from (
    select avg(case when temperature_c is null then 1.0 else 0.0 end) as missing_share
    from {{ ref('fct_footfall_hourly') }}
)
where missing_share > 0.02
