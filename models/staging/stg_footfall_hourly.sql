-- One clean row per sensor per hour.
select
    cast(location_id as integer)                       as sensor_id,
    sensor_name,
    cast(sensing_date as date)                         as sensing_date,
    cast(hourday as integer)                           as hour_of_day,
    cast(sensing_date as timestamp)
        + cast(hourday as integer) * interval 1 hour   as hour_start,
    cast(pedestriancount as integer)                   as pedestrian_count
from {{ source('raw', 'pedestrian_hourly') }}
where pedestriancount is not null
  and pedestriancount >= 0
-- The raw file can repeat the same sensor-hour. Keep exactly one row for each.
qualify row_number() over (
    partition by location_id, sensing_date, hourday
    order by pedestriancount desc
) = 1
