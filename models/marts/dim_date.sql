-- A calendar: one row per day, with weekday, weekend flag and holiday/event info.
with days as (
    select cast(day as date) as date_day
    from generate_series(date '2024-11-01', date '2026-11-05', interval 1 day) as t(day)
)
select
    d.date_day,
    dayname(d.date_day)                          as weekday_name,
    isodow(d.date_day)                           as weekday_num,        -- 1 = Monday ... 7 = Sunday
    isodow(d.date_day) >= 6                      as is_weekend,
    month(d.date_day)                            as month_num,
    e.event_name,
    e.event_type,
    coalesce(e.event_type = 'public_holiday', false) as is_public_holiday,
    coalesce(e.event_type = 'major_event', false)    as is_major_event
from days d
left join {{ ref('calendar_events') }} e
       on e.event_date = d.date_day
