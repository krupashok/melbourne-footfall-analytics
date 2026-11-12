-- One row per sensor, plus how reliable it has been.
-- A "core" sensor reported on at least 95% of days, so city totals stay
-- comparable across time and are not shaken by sensors switching on or off.
with usage as (
    select
        sensor_id,
        count(distinct sensing_date)  as days_reported,
        sum(pedestrian_count)         as total_pedestrians
    from {{ ref('stg_footfall_hourly') }}
    group by sensor_id
),
span as (
    select count(distinct sensing_date) as total_days
    from {{ ref('stg_footfall_hourly') }}
)
select
    u.sensor_id,
    coalesce(s.sensor_name, 'Unregistered sensor ' || u.sensor_id) as sensor_name,
    coalesce(s.sensor_label, 'Unregistered sensor ' || u.sensor_id) as sensor_label,
    s.location_type,
    s.latitude,
    s.longitude,
    s.sensor_id is null                                           as is_unregistered,
    u.days_reported,
    u.total_pedestrians,
    u.total_pedestrians * 1.0 / u.days_reported                    as avg_daily_pedestrians,
    u.days_reported >= 0.95 * span.total_days                     as is_core_sensor
-- Start from the sensors that actually sent data, so none are silently dropped.
-- (Two sensors, IDs 28 and 78, sent data but are missing from the city's sensor list.)
from usage u
left join {{ ref('stg_sensors') }} s using (sensor_id)
cross join span
