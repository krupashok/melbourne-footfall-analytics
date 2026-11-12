"""Step 3 - MODEL: (a) measure what moves footfall, (b) predict tomorrow's footfall.

(a) uses a simple, explainable regression so we can say things like
    "rain cuts footfall by about X% once we account for weekday and season".
(b) uses a gradient-boosting model and checks it honestly against a simple
    "average for that weekday" guess, on days the model has never seen.
"""
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from sklearn.ensemble import HistGradientBoostingRegressor

ROOT = Path(__file__).resolve().parent.parent
con = duckdb.connect(str(ROOT / "warehouse" / "footfall.duckdb"), read_only=True)
df = con.sql("select * from fct_city_daily order by sensing_date").df()
df["sensing_date"] = pd.to_datetime(df["sensing_date"])
df["log_footfall"] = np.log(df["total_pedestrians"])
df["is_rainy"] = df["is_rainy_day"].astype(int)
df["heavy_rain"] = (df["rain_mm"] >= 10).astype(int)
df["hot_day"] = (df["max_temp_c"] >= 30).astype(int)
df["cold_day"] = (df["max_temp_c"] <= 12).astype(int)
df["windy_day"] = (df["max_wind_kmh"] >= 30).astype(int)
df["holiday"] = df["is_public_holiday"].astype(int)
df["nye"] = df["is_major_event"].astype(int)

# ---------- (a) What moves footfall? Explainable regression ----------
formula = ("log_footfall ~ C(weekday_name) + C(month_num) + holiday + nye "
           "+ is_rainy + heavy_rain + hot_day + cold_day + windy_day")
ols = smf.ols(formula, data=df).fit(cov_type="HC3")
effects = {}
for name in ["is_rainy", "heavy_rain", "hot_day", "cold_day", "windy_day", "holiday", "nye"]:
    coef, lo, hi = ols.params[name], *ols.conf_int().loc[name]
    effects[name] = {
        "pct_change": round((np.exp(coef) - 1) * 100, 1),
        "ci_low": round((np.exp(lo) - 1) * 100, 1),
        "ci_high": round((np.exp(hi) - 1) * 100, 1),
        "p_value": round(float(ols.pvalues[name]), 4),
    }

# ---------- (b) Prediction, tested on the most recent 120 days ----------
features = ["weekday_num", "month_num", "holiday", "nye", "rain_mm", "max_temp_c",
            "min_temp_c", "max_wind_kmh"]
cut = df["sensing_date"].max() - pd.Timedelta(days=120)
train, test = df[df["sensing_date"] <= cut], df[df["sensing_date"] > cut]

model = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05,
                                      max_depth=4, random_state=42)
model.fit(train[features], train["total_pedestrians"])
test = test.assign(pred=model.predict(test[features]))

# Baseline: "just guess the usual number for that weekday"
base = train.groupby("weekday_num")["total_pedestrians"].mean()
test["baseline"] = test["weekday_num"].map(base)

def mape(y, p): return float(np.mean(np.abs(y - p) / y) * 100)
metrics = {
    "train_days": int(len(train)), "test_days": int(len(test)),
    "test_period": [str(test.sensing_date.min().date()), str(test.sensing_date.max().date())],
    "model_mape_pct": round(mape(test.total_pedestrians, test.pred), 1),
    "baseline_mape_pct": round(mape(test.total_pedestrians, test.baseline), 1),
    "model_mae": round(float(np.mean(np.abs(test.total_pedestrians - test.pred)))),
    "baseline_mae": round(float(np.mean(np.abs(test.total_pedestrians - test.baseline)))),
    "ols_r2": round(float(ols.rsquared), 3),
    "effects_pct": effects,
}
(ROOT / "results" / "metrics.json").write_text(json.dumps(metrics, indent=2))

# A tidy table of the effects, ready for Tableau
labels = {"is_rainy": "Rainy day (1 mm+)", "heavy_rain": "Heavy rain (10 mm+), extra effect", "hot_day": "Hot day (30C+)",
          "cold_day": "Cold day (12C or less)", "windy_day": "Windy day (30 km/h+)", "holiday": "Public holiday",
          "nye": "New Year's Eve"}
rows = [{"factor": labels[k], "pct_change": v["pct_change"], "ci_low": v["ci_low"], "ci_high": v["ci_high"],
         "is_clear": int(v["ci_low"] > 0 or v["ci_high"] < 0)} for k, v in effects.items()]
combined = round(((1 + effects["is_rainy"]["pct_change"] / 100) * (1 + effects["heavy_rain"]["pct_change"] / 100) - 1) * 100, 1)
rows.append({"factor": "Heavy rain (10 mm+), total", "pct_change": combined, "ci_low": None, "ci_high": None, "is_clear": 1})
pd.DataFrame(rows).sort_values("pct_change").to_csv(ROOT / "results" / "effects.csv", index=False)
test[["sensing_date", "total_pedestrians", "pred", "baseline"]].to_csv(
    ROOT / "results" / "test_predictions.csv", index=False)
print(json.dumps(metrics, indent=2))
