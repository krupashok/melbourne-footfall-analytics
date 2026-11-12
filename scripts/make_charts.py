"""Step 4 - CHARTS: four clear, LinkedIn-sized pictures of the findings.

Design rules used (from the dataviz skill): one message per chart, one axis,
one hue for magnitude, gray for "not clearly different", labels on the bars so
nobody has to hunt for numbers, and a light calm background.
"""
import json
from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "charts"
BLUE, ORANGE, GRAY = "#2a78d6", "#eb6834", "#b9b8b2"
INK, INK2, SURFACE = "#0b0b0b", "#52514e", "#fcfcfb"
plt.rcParams.update({
    "font.family": "Helvetica", "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "axes.edgecolor": "#d9d8d2", "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.spines.top": False, "axes.spines.right": False,
})
SIZE = (12, 6.27)   # LinkedIn image ratio

def finish(fig, title, subtitle, name):
    fig.text(0.045, 0.945, title, fontsize=20, fontweight="bold", color=INK, va="top")
    fig.text(0.045, 0.885, subtitle, fontsize=12, color=INK2, va="top")
    fig.text(0.045, 0.025, "Source: City of Melbourne Pedestrian Counting System, Open-Meteo weather | Nov 2024 - Nov 2026",
             fontsize=9, color=INK2)
    fig.savefig(OUT / name, dpi=160, facecolor=SURFACE)
    plt.close(fig)

con = duckdb.connect(str(ROOT / "warehouse" / "footfall.duckdb"), read_only=True)
metrics = json.loads((ROOT / "results" / "metrics.json").read_text())

# ---- Chart 1: when is the city busiest? (weekday x hour heatmap) ----
h = con.sql("""
    select f.weekday_name, f.hour_of_day, avg(f.pedestrian_count) as avg_count
    from fct_footfall_hourly f join dim_sensor s using (sensor_id)
    where s.is_core_sensor and not f.is_public_holiday
    group by 1, 2
""").df()
order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
grid = h.pivot(index="weekday_name", columns="hour_of_day", values="avg_count").reindex(order)
cmap = LinearSegmentedColormap.from_list("blues", ["#eaf1fb", "#2a78d6", "#0b3a7a"])
fig, ax = plt.subplots(figsize=SIZE)
fig.subplots_adjust(left=0.1, right=0.9, top=0.78, bottom=0.14)
im = ax.imshow(grid.values, aspect="auto", cmap=cmap)
ax.set_yticks(range(7)); ax.set_yticklabels(order)
ax.set_xticks(range(0, 24, 2)); ax.set_xticklabels([f"{i}:00" for i in range(0, 24, 2)])
for s in ax.spines.values(): s.set_visible(False)
ax.tick_params(length=0)
cb = fig.colorbar(im, ax=ax, pad=0.01, fraction=0.025)
cb.set_label("Average people per sensor per hour", color=INK2); cb.outline.set_visible(False)
finish(fig, "When is Melbourne's city centre busiest?",
       "Weekdays peak around lunchtime and after work. Saturdays run from late morning into the evening.",
       "1_busiest_times_heatmap.png")

# ---- Chart 2: what moves footfall? ----
e = metrics["effects_pct"]
rain_total = round(((1 + e["is_rainy"]["pct_change"] / 100) * (1 + e["heavy_rain"]["pct_change"] / 100) - 1) * 100, 1)
rows = [
    ("Heavy rain (10 mm+), total", rain_total, None, None, True),
    ("Hot day (30°C+)", e["hot_day"]["pct_change"], e["hot_day"]["ci_low"], e["hot_day"]["ci_high"], True),
    ("Rainy day (1 mm+)", e["is_rainy"]["pct_change"], e["is_rainy"]["ci_low"], e["is_rainy"]["ci_high"], True),
    ("Public holiday", e["holiday"]["pct_change"], e["holiday"]["ci_low"], e["holiday"]["ci_high"], False),
    ("Windy day (30 km/h+)", e["windy_day"]["pct_change"], e["windy_day"]["ci_low"], e["windy_day"]["ci_high"], False),
    ("Cold day (12°C or less)", e["cold_day"]["pct_change"], e["cold_day"]["ci_low"], e["cold_day"]["ci_high"], False),
    ("New Year's Eve", e["nye"]["pct_change"], e["nye"]["ci_low"], e["nye"]["ci_high"], True),
]
rows.sort(key=lambda r: r[1])
fig, ax = plt.subplots(figsize=SIZE)
fig.subplots_adjust(left=0.24, right=0.93, top=0.78, bottom=0.14)
for i, (name, v, lo, hi, clear) in enumerate(rows):
    colour = (BLUE if v > 0 else ORANGE) if clear else GRAY
    ax.barh(i, v, color=colour, height=0.6)
    if lo is not None:
        ax.plot([lo, hi], [i, i], color=INK2, lw=1.2)
    # put the label just beyond the end of the bar (and beyond its range line)
    edge = (max(v, hi) if v >= 0 else min(v, lo)) if lo is not None else v
    ax.text(edge + (1.2 if v >= 0 else -1.2), i, f"{v:+.0f}%",
            ha="left" if v >= 0 else "right", va="center", fontsize=12, color=INK, fontweight="bold")
ax.set_yticks(range(len(rows))); ax.set_yticklabels([r[0] for r in rows], fontsize=12)
ax.axvline(0, color=INK2, lw=1)
ax.set_xlim(-34, 28); ax.set_xlabel("Change in city-wide daily footfall vs a comparable day (%)")
ax.grid(axis="x", color="#ecebe6"); ax.set_axisbelow(True)
for s in ["left"]: ax.spines[s].set_visible(False)
ax.tick_params(axis="y", length=0)
fig.text(0.93, 0.80, "Gray = could be chance (confidence range crosses zero). Lines show the 95% range.",
         ha="right", fontsize=10, color=INK2)
finish(fig, "What moves foot traffic in the city centre?",
       "Rain and heat keep people home. Heavy rain cuts footfall by about a quarter.",
       "2_what_moves_footfall.png")

# ---- Chart 3: weekday pattern ----
d = con.sql("""select weekday_name, weekday_num, avg(total_pedestrians) as avg_ped
               from fct_city_daily where not is_public_holiday group by 1, 2 order by 2""").df()
fig, ax = plt.subplots(figsize=SIZE)
fig.subplots_adjust(left=0.08, right=0.97, top=0.78, bottom=0.14)
top = d.avg_ped.idxmax()
colours = [BLUE if i == top else "#9dbfeb" for i in range(len(d))]
bars = ax.bar(d.weekday_name.str[:3], d.avg_ped / 1000, color=colours, width=0.62)
for b, v in zip(bars, d.avg_ped / 1000):
    ax.text(b.get_x() + b.get_width() / 2, v + 12, f"{v:,.0f}k", ha="center", fontsize=12, color=INK, fontweight="bold")
ax.set_ylabel("Average people counted per day (thousands)")
ax.set_ylim(0, 960); ax.grid(axis="y", color="#ecebe6"); ax.set_axisbelow(True)
ax.spines["left"].set_visible(False); ax.tick_params(axis="x", length=0, labelsize=12)
finish(fig, "Friday and Saturday are the city's busiest days",
       "Monday and Sunday are the quietest days of the week.", "3_busiest_days.png")

# ---- Chart 4: model vs reality ----
p = pd.read_csv(ROOT / "results" / "test_predictions.csv", parse_dates=["sensing_date"])
fig, ax = plt.subplots(figsize=SIZE)
fig.subplots_adjust(left=0.08, right=0.9, top=0.78, bottom=0.14)
ax.plot(p.sensing_date, p.total_pedestrians / 1000, color=BLUE, lw=2, label="Actual")
ax.plot(p.sensing_date, p.pred / 1000, color=ORANGE, lw=2, label="Model prediction")
ax.text(p.sensing_date.iloc[-1], p.total_pedestrians.iloc[-1] / 1000 + 25, "Actual", color=BLUE, fontsize=12, fontweight="bold")
ax.text(p.sensing_date.iloc[-1], p.pred.iloc[-1] / 1000 - 45, "Model", color=ORANGE, fontsize=12, fontweight="bold")
ax.set_ylabel("People counted per day (thousands)"); ax.set_ylim(0, 1150)
ax.grid(axis="y", color="#ecebe6"); ax.set_axisbelow(True); ax.spines["left"].set_visible(False)
ax.legend(frameon=False, loc="lower left", ncol=2)
m = metrics
finish(fig, "Predicting daily footfall for days the model had never seen",
       f"Average error {m['model_mape_pct']}% vs {m['baseline_mape_pct']}% for the usual-weekday guess "
       f"(last {m['test_days']} days, {m['test_period'][0]} to {m['test_period'][1]}).", "4_model_vs_actual.png")
print("charts saved:", sorted(p.name for p in OUT.glob("*.png")))
