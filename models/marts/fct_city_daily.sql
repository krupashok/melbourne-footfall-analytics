-- One row per day for the whole city (core sensors only), with daily weather.
-- This is the table the prediction model and the dashboard use.
with core as (
    select sensor_id from {{ ref('dim_sensor') }} where is_core_sensor
),
daily_footfall as (
    select
        f.sensing_date,
        sum(f.pedestrian_count) as total_pedestrians,
        count(*)                as sensor_hours_reported
    from {{ ref('stg_footfall_hourly') }} f
    join core using (sensor_id)
    group by f.sensing_date
),
expected as (
    -- A full day should have 24 readings from every core sensor.
    select count(*) * 24 as sensor_hours_expected from core
),
daily_weather as (
    -- Weather during daytime hours (7am to 8pm), when most people are out.
    select
        cast(hour_start as date)  as sensing_date,
        max(temperature_c)        as max_temp_c,
        min(temperature_c)        as min_temp_c,
        sum(rain_mm)              as rain_mm,
        max(wind_kmh)             as max_wind_kmh
    from {{ ref('stg_weather_hourly') }}
    where hour(hour_start) between 7 and 20
    group by 1
)
select
    d.date_day                    as sensing_date,
    d.weekday_name,
    d.weekday_num,
    d.is_weekend,
    d.month_num,
    d.is_public_holiday,
    d.is_major_event,
    d.event_name,
    f.total_pedestrians,
    f.sensor_hours_reported * 1.0 / e.sensor_hours_expected as data_coverage,
    w.max_temp_c,
    w.min_temp_c,
    w.rain_mm,
    w.rain_mm >= 1.0              as is_rainy_day,
    case when w.rain_mm >= 10 then 'Heavy rain (10 mm+)'
         when w.rain_mm >= 1  then 'Rainy (1-10 mm)'
         else 'Dry' end           as weather_bucket,
    case when d.is_public_holiday then 'Public holiday'
         when d.is_weekend        then 'Weekend'
         else 'Weekday' end       as day_type,
    w.max_wind_kmh
from {{ ref('dim_date') }} d
join daily_footfall f on f.sensing_date = d.date_day
cross join expected e
left join daily_weather w on w.sensing_date = d.date_day
-- Keep only complete days. A half-recorded day (for example today, which is still
-- in progress) would look like a crash in footfall when it is really missing data.
where f.sensor_hours_reported * 1.0 / e.sensor_hours_expected >= 0.90
