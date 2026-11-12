"""Step 5 - EXPORT: write small, ready-to-use CSV files for Tableau into tableau_data/."""
from pathlib import Path
import shutil
import duckdb

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "tableau_data"
OUT.mkdir(exist_ok=True)
con = duckdb.connect(str(ROOT / "warehouse" / "footfall.duckdb"), read_only=True)

exports = {
    "city_daily": "select * from fct_city_daily order by sensing_date",
    "weekday_hour": "select * from rpt_weekday_hour order by weekday_num, hour_of_day",
    "sensors_top10": """select sensor_label, total_pedestrians from dim_sensor
                        where not is_unregistered and is_core_sensor order by total_pedestrians desc limit 10""",
    "sensors": """select sensor_id, sensor_label, latitude, longitude, days_reported, total_pedestrians,
                         round(avg_daily_pedestrians) as avg_daily_pedestrians
                  from dim_sensor where not is_unregistered and is_core_sensor order by total_pedestrians desc""",
}
for name, sql in exports.items():
    con.execute(f"copy ({sql}) to '{OUT / (name + '.csv')}' (header, delimiter ',')")
# Tableau shows one clear "heavy rain" bar: the total effect (rainy-day effect plus the extra heavy-rain effect)
import pandas as pd
eff = pd.read_csv(ROOT / "results" / "effects.csv")
eff = eff[eff["factor"] != "Heavy rain (10 mm+), extra effect"]
eff["factor"] = eff["factor"].replace({"Heavy rain (10 mm+), total": "Heavy rain (10 mm+)"})
eff.to_csv(OUT / "effects.csv", index=False)
print(sorted(p.name for p in OUT.iterdir()))
