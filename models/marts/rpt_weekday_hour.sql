-- Average footfall for every weekday and hour (core sensors, non-holidays).
-- A small, ready-made table so the dashboard heatmap needs no heavy calculation.
select
    f.weekday_name,
    isodow(f.sensing_date)           as weekday_num,
    f.hour_of_day,
    avg(f.pedestrian_count)          as avg_pedestrians_per_sensor
from {{ ref('fct_footfall_hourly') }} f
join {{ ref('dim_sensor') }} s using (sensor_id)
where s.is_core_sensor and not f.is_public_holiday
group by 1, 2, 3
