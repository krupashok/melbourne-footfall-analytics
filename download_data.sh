#!/bin/bash
# Downloads the three raw datasets used in Week 1 into data/raw/
set -e
cd "$(dirname "$0")"
mkdir -p data/raw
B=https://data.melbourne.vic.gov.au/api/explore/v2.1/catalog/datasets
curl -s -o data/raw/sensor_locations.csv "$B/pedestrian-counting-system-sensor-locations/exports/csv?select=location_id,sensor_description,sensor_name,installation_date,location_type,status,direction_1,direction_2,latitude,longitude&delimiter=%2C"
curl -s -o data/raw/weather.json "https://archive-api.open-meteo.com/v1/archive?latitude=-37.8136&longitude=144.9631&start_date=2024-11-01&end_date=2026-11-05&hourly=temperature_2m,precipitation,wind_speed_10m&timezone=Australia%2FMelbourne"
curl -s -o data/raw/pedestrian_hourly.csv "$B/pedestrian-counting-system-monthly-counts-per-hour/exports/csv?select=location_id,sensing_date,hourday,direction_1,direction_2,pedestriancount,sensor_name&delimiter=%2C"
echo DONE
