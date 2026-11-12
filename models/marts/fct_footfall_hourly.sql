-- The main fact table: footfall per sensor per hour, with weather and calendar attached.
select
    f.sensor_id,
    f.hour_start,
    f.sensing_date,
    f.hour_of_day,
    f.pedestrian_count,
    w.temperature_c,
    w.rain_mm,
    w.wind_kmh,
    d.weekday_name,
    d.is_weekend,
    d.is_public_holiday,
    d.is_major_event,
    d.event_name
from {{ ref('stg_footfall_hourly') }} f
left join {{ ref('stg_weather_hourly') }} w using (hour_start)
left join {{ ref('dim_date') }} d on d.date_day = f.sensing_date
