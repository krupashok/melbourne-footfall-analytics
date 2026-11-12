-- Fails (returns rows) if any hourly count is negative.
select * from {{ ref('fct_footfall_hourly') }} where pedestrian_count < 0
