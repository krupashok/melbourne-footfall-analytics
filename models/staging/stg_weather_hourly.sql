-- One clean row per hour of Melbourne weather.
select
    cast(time as timestamp)   as hour_start,
    temperature_2m            as temperature_c,
    precipitation             as rain_mm,
    wind_speed_10m            as wind_kmh
from {{ source('raw', 'weather_hourly') }}
