-- One clean row per sensor, with friendly names.
select
    cast(location_id as integer)  as sensor_id,
    sensor_name,
    sensor_description            as sensor_label,
    location_type,
    status                        as sensor_status,
    cast(installation_date as date) as installation_date,
    latitude,
    longitude
from {{ source('raw', 'sensor_locations') }}
