"""Step 1 - LOAD: copy the raw downloaded files into DuckDB, untouched.

dbt only transforms data that is already inside the database, so this small
script is the "delivery truck" that puts the raw files in the warehouse.
"""
import json
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
DB = ROOT / "warehouse" / "footfall.duckdb"

con = duckdb.connect(str(DB))
con.execute("create schema if not exists raw")

# 1) Hourly pedestrian counts and sensor list: DuckDB can read CSVs directly.
con.execute(f"""
    create or replace table raw.pedestrian_hourly as
    select * from read_csv_auto('{RAW / "pedestrian_hourly.csv"}')
""")
con.execute(f"""
    create or replace table raw.sensor_locations as
    select * from read_csv_auto('{RAW / "sensor_locations.csv"}')
""")

# 2) Weather arrives as JSON with parallel lists (one list per measure).
#    We reshape it into a normal table: one row per hour.
hourly = json.loads((RAW / "weather.json").read_text())["hourly"]
weather = pd.DataFrame(hourly)
con.execute("create or replace table raw.weather_hourly as select * from weather")

for table in ["pedestrian_hourly", "sensor_locations", "weather_hourly"]:
    n = con.execute(f"select count(*) from raw.{table}").fetchone()[0]
    print(f"raw.{table}: {n:,} rows")
