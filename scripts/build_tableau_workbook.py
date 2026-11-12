"""Step 6 - TABLEAU: write the Tableau workbook (.twb) with five sheets and one dashboard.

A .twb file is just XML text that describes data sources, worksheets and a dashboard.
This script writes that XML for us, so the whole dashboard is reproducible from code.
The structure follows the sample workbook that ships inside Tableau Public itself.
"""
import re
from pathlib import Path
from xml.sax.saxutils import escape
import datetime
import xml.etree.ElementTree as ET
import zipfile

from tableauhyperapi import (Connection, CreateMode, HyperProcess, SqlType, TableDefinition, TableName, Telemetry,
                             escape_string_literal)

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "tableau_data"
OUT = ROOT / "tableau" / "Melbourne_Footfall.twb"

BLUE_LIGHT, BLUE, BLUE_DARK, ORANGE, GRAY = "#eaf1fb", "#2a78d6", "#0b3a7a", "#eb6834", "#b9b8b2"
INK, INK2 = "#0b0b0b", "#52514e"


def q(text):
    """Escape text for use inside an XML attribute written with single quotes."""
    return escape(text, {"'": "&apos;", '"': "&quot;"})


# ----------------------------------------------------------------------------------------------
# 1) DATA SOURCES: each CSV becomes one data source. (name, type) pairs follow the CSV column order.
# ----------------------------------------------------------------------------------------------
TYPES = {  # datatype -> (remote-type, aggregation)
    "integer": (20, "Sum"), "real": (5, "Sum"), "string": (129, "Count"),
    "boolean": (11, "Count"), "date": (133, "Year"),
}
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

SOURCES = {
    "city_daily": {
        "caption": "City daily footfall",
        "columns": [("sensing_date", "date"), ("weekday_name", "string"), ("weekday_num", "integer"),
                    ("is_weekend", "boolean"), ("month_num", "integer"), ("is_public_holiday", "boolean"),
                    ("is_major_event", "boolean"), ("event_name", "string"), ("total_pedestrians", "integer"),
                    ("data_coverage", "real"), ("max_temp_c", "real"), ("min_temp_c", "real"), ("rain_mm", "real"),
                    ("is_rainy_day", "boolean"), ("weather_bucket", "string"), ("day_type", "string"),
                    ("max_wind_kmh", "real")],
        "dimensions": {"weekday_num": "ordinal", "month_num": "ordinal"},
    },
    "weekday_hour": {
        "caption": "Weekday and hour averages",
        "columns": [("weekday_name", "string"), ("weekday_num", "integer"), ("hour_of_day", "integer"),
                    ("avg_pedestrians_per_sensor", "real")],
        "dimensions": {"weekday_num": "ordinal", "hour_of_day": "ordinal"},
    },
    "effects": {
        "caption": "Weather and event effects",
        "columns": [("factor", "string"), ("pct_change", "real"), ("ci_low", "real"), ("ci_high", "real"),
                    ("is_clear", "integer")],
        "dimensions": {"is_clear": "ordinal"},
    },
    "sensors_top10": {
        "caption": "Busiest sensors",
        "columns": [("sensor_label", "string"), ("total_pedestrians", "integer")],
        "dimensions": {},
    },
}
# Calculated fields (name, caption, datasource, datatype, role, type, formula)
CALCS = {
    "effects": [("Calculation_Shown", "Effect (clear ones only)", "real", "measure", "quantitative",
                 "SUM([pct_change]) * MAX([is_clear])")],
}


CAPTIONS = {  # friendly names shown in tooltips instead of raw column names
    "hour_of_day": "Hour of day", "weekday_num": "Weekday", "avg_pedestrians_per_sensor": "Avg people per sensor per hour",
    "total_pedestrians": "People counted", "pct_change": "Change in footfall (%)", "sensor_label": "Street sensor",
    "weather_bucket": "Weather", "factor": "Factor", "sensing_date": "Date", "day_type": "Day type",
}


def column_def(src, name, datatype):
    spec = SOURCES[src]
    if name in spec["dimensions"]:
        role, ctype = "dimension", spec["dimensions"][name]
    elif datatype in ("integer", "real"):
        role, ctype = "measure", "quantitative"
    elif datatype == "date":
        role, ctype = "dimension", "ordinal"
    else:
        role, ctype = "dimension", "nominal"
    aliases = ""
    if name == "weekday_num":
        aliases = "<aliases>" + "".join(f"<alias key='{i + 1}' value='{d}' />" for i, d in enumerate(WEEKDAYS)) + "</aliases>"
    agg = f" aggregation='Sum'" if role == "dimension" and datatype in ("integer", "real") else ""
    cap = f" caption='{q(CAPTIONS[name])}'" if name in CAPTIONS else ""
    body = f"<column{cap} datatype='{datatype}'{agg} name='[{name}]' role='{role}' type='{ctype}'>{aliases}</column>" if aliases \
        else f"<column{cap} datatype='{datatype}'{agg} name='[{name}]' role='{role}' type='{ctype}' />"
    return body


# ----------------------------------------------------------------------------------------------
# 1b) EXTRACTS: Tableau Public only opens workbooks whose data is stored as a Tableau extract (.hyper).
#     So each CSV is converted into a .hyper file that travels inside the packaged workbook (.twbx).
# ----------------------------------------------------------------------------------------------
EXTRACT_DIR = ROOT / "tableau" / "Data" / "Extracts"
HYPER_TYPES = {"integer": SqlType.big_int(), "real": SqlType.double(), "string": SqlType.text(),
               "boolean": SqlType.bool(), "date": SqlType.date()}
ROWS, STAMP = {}, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.000")


def make_extracts():
    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
    with HyperProcess(Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hyper:
        for src, spec in SOURCES.items():
            path = EXTRACT_DIR / f"{src}.hyper"
            table = TableName("Extract", "Extract")
            definition = TableDefinition(table, [TableDefinition.Column(n, HYPER_TYPES[t]) for n, t in spec["columns"]])
            with Connection(hyper.endpoint, str(path), CreateMode.CREATE_AND_REPLACE) as conn:
                conn.catalog.create_schema("Extract")
                conn.catalog.create_table(definition)
                csv = escape_string_literal(str(DATA_DIR / f"{src}.csv"))
                conn.execute_command(f"COPY {table} FROM {csv} WITH (FORMAT CSV, HEADER true, NULL '')")
                ROWS[src] = conn.execute_scalar_query(f"SELECT COUNT(*) FROM {table}")


make_extracts()


def datasource_xml(src):
    spec = SOURCES[src]
    table = f"[{src}#csv]"
    cols = "".join(f"<column datatype='{t}' name='{n}' ordinal='{i}' />" for i, (n, t) in enumerate(spec["columns"]))
    meta = ""
    for i, (n, t) in enumerate(spec["columns"]):
        rt, agg = TYPES[t]
        extra = "<scale>1</scale><width>1073741823</width>" if t == "string" else ""
        meta += (f"<metadata-record class='column'><remote-name>{n}</remote-name><remote-type>{rt}</remote-type>"
                 f"<local-name>[{n}]</local-name><parent-name>{table}</parent-name><remote-alias>{n}</remote-alias>"
                 f"<ordinal>{i}</ordinal><local-type>{t}</local-type><aggregation>{agg}</aggregation>{extra}"
                 f"<contains-null>true</contains-null></metadata-record>")
    defs = "".join(column_def(src, n, t) for n, t in spec["columns"])
    calcs = ""
    for name, caption, dt, role, ctype, formula in CALCS.get(src, []):
        calcs += (f"<column caption='{caption}' datatype='{dt}' name='[{name}]' role='{role}' type='{ctype}'>"
                  f"<calculation class='tableau' formula='{q(formula)}' /></column>")
    style = ("<style><style-rule element='mark'>" + "".join(DS_STYLE[src]) + "</style-rule></style>") if DS_STYLE.get(src) else ""
    return f"""
    <datasource caption='{q(spec["caption"])}' inline='true' name='{src}' version='18.1'>
      <connection class='federated'>
        <named-connections>
          <named-connection name='{src}_leaf'>
            <connection class='textscan' character-set='UTF-8' directory='{q(str(DATA_DIR))}' filename='{src}.csv' force-header='no' header='yes' separator=',' text-qualifier='&quot;' />
          </named-connection>
        </named-connections>
        <relation connection='{src}_leaf' name='{src}.csv' table='{table}' type='table'>
          <columns character-set='UTF-8' header='yes' locale='en_AU' separator=',' text-qualifier='&quot;'>{cols}</columns>
        </relation>
        <metadata-records>{meta}</metadata-records>
      </connection>
      <aliases enabled='yes' />
      {defs}
      {calcs}
      <extract count='-1' enabled='true' units='records'>
        <connection authentication='auth-none' class='hyper' db-format='dataengine' default-settings='yes' dbname='Data/Extracts/{src}.hyper' schema='Extract' sslmode='' tablename='Extract' update-time='{STAMP}' username='tableau_internal_user'>
          <relation name='Extract' table='[Extract].[Extract]' type='table' />
          <refresh increment-key='' incremental-updates='false'>
            <refresh-event add-from-file-path='' increment-value='%null%' refresh-type='create' rows-inserted='{ROWS[src]}' timestamp-start='{STAMP}' />
          </refresh>
        </connection>
      </extract>
      <layout dim-ordering='alphabetic' dim-percentage='0.5' measure-ordering='alphabetic' measure-percentage='0.4' show-structure='true' />
      {style}
    </datasource>"""


# ----------------------------------------------------------------------------------------------
# 2) FIELD HELPERS: how a field is "used" in a sheet (None, Avg, Sum, Day-Trunc ...)
# ----------------------------------------------------------------------------------------------
def dtype_of(src, name):
    for n, t in SOURCES[src]["columns"]:
        if n == name:
            return t
    for cname, caption, dt, role, ctype, formula in CALCS.get(src, []):
        if cname == name:
            return dt
    raise KeyError(name)


def inst(src, field, how):
    """Return (instance-name, column-instance xml, type) for a field used in a certain way."""
    prefix = {"none-o": ("None", "none", "ok", "ordinal"), "none-n": ("None", "none", "nk", "nominal"),
              "avg": ("Avg", "avg", "qk", "quantitative"), "sum": ("Sum", "sum", "qk", "quantitative"),
              "day": ("Day-Trunc", "tdy", "qk", "quantitative"), "usr": ("User", "usr", "qk", "quantitative"), "none-q": ("None", "none", "qk", "quantitative")}[how]
    derivation, short, suffix, ctype = prefix
    name = f"[{short}:{field}:{suffix}]"
    xml = f"<column-instance column='[{field}]' derivation='{derivation}' name='{name}' pivot='key' type='{ctype}' />"
    return name, xml


def deps(src, used):
    """datasource-dependencies block. `used` is a list of (field, how) pairs."""
    cols, insts, seen = "", "", set()
    for field, how in used:
        if field not in seen:
            seen.add(field)
            calc = next((c for c in CALCS.get(src, []) if c[0] == field), None)
            if calc:
                cols += (f"<column caption='{calc[1]}' datatype='{calc[2]}' name='[{field}]' role='{calc[3]}' type='{calc[4]}'>"
                         f"<calculation class='tableau' formula='{q(calc[5])}' /></column>")
            else:
                cols += column_def(src, field, dtype_of(src, field))
        insts += inst(src, field, how)[1]
    return f"<datasource-dependencies datasource='{src}'>{cols}{insts}</datasource-dependencies>"


def ref(src, field, how):
    return f"[{src}].{inst(src, field, how)[0]}"


def title_xml(text, size=14):
    return (f"<layout-options><title><formatted-text><run bold='true' fontcolor='{INK}' fontsize='{size}'>{q(text)}</run>"
            f"</formatted-text></title></layout-options>")


DS_STYLE = {}   # data source -> list of colour encodings (Tableau reads these at data-source level)


def _register(field_ref, encoding_xml):
    src = re.match(r"\[(\w+)\]\.", field_ref).group(1)
    DS_STYLE.setdefault(src, []).append(encoding_xml.replace("FIELD", field_ref))
    return ""


def palette_continuous(field_ref, colours):
    cs = "".join(f"<color>{c}</color>" for c in colours)
    return _register(field_ref, f"<encoding attr='color' field='FIELD' type='custom-interpolated'>"
                                f"<color-palette custom='true' name='' type='ordered-sequential'>{cs}</color-palette></encoding>")


def palette_diverging(field_ref, colours, centre, lo, hi):
    cs = "".join(f"<color>{c}</color>" for c in colours)
    return _register(field_ref, f"<encoding attr='color' center='{centre}' field='FIELD' max='{hi}' min='{lo}' type='custom-interpolated'>"
                                f"<color-palette custom='true' name='' type='ordered-diverging'>{cs}</color-palette></encoding>")


def palette_buckets(field_ref, mapping):
    maps = "".join(f"<map to='{c}'><bucket>&quot;{q(b)}&quot;</bucket></map>" for b, c in mapping.items())
    unqualified = re.sub(r"^\[\w+\]\.", "", field_ref)
    return _register(field_ref, f"<encoding attr='color' field='{unqualified}' type='palette'>{maps}</encoding>")


def worksheet(name, title, src, used, rows, cols, mark, encodings="", filters="", slices="", sorts="",
              extra_style="", pane_style="", aggregation="true"):
    cell_rules = "".join(re.findall(r"<style-rule element='label'>.*?</style-rule>", pane_style))
    pane_style = re.sub(r"<style-rule element='label'>.*?</style-rule>", "", pane_style)
    extra_style += cell_rules.replace("element='label'", "element='cell'") + FORMATS.get(name, "")
    extra_style += ("<style-rule element='worksheet'><format attr='display-field-labels' scope='cols' value='false' />"
                    "<format attr='display-field-labels' scope='rows' value='false' /></style-rule>")
    return f"""
    <worksheet name='{q(name)}'>
      {title_xml(title)}
      <table>
        <view>
          <datasources><datasource caption='{q(SOURCES[src]["caption"])}' name='{src}' /></datasources>
          {deps(src, used)}
          {filters}
          {sorts}
          {slices}
          <aggregation value='{aggregation}' />
        </view>
        <style>
          <style-rule element='worksheet'><format attr='font-size' value='11' /></style-rule>
          {extra_style}
        </style>
        <panes>
          <pane>
            <view><breakdown value='auto' /></view>
            <mark class='{mark}' />
            <encodings>{encodings}</encodings>
            <style>{pane_style}</style>
          </pane>
        </panes>
        <rows>{rows}</rows>
        <cols>{cols}</cols>
      </table>
    </worksheet>"""


def member_filter(src, field, member, exclude):
    col = f"[{src}].[{field}]"
    if exclude:
        return (f"<filter class='categorical' column='{col}'><groupfilter function='except' user:ui-domain='database' "
                f"user:ui-enumeration='exclusive' user:ui-marker='enumerate'><groupfilter function='level-members' level='[{field}]' />"
                f"<groupfilter function='member' level='[{field}]' member='&quot;{q(member)}&quot;' /></groupfilter></filter>")
    return (f"<filter class='categorical' column='{col}'><groupfilter function='member' level='[{field}]' "
            f"member='&quot;{q(member)}&quot;' user:ui-domain='database' user:ui-enumeration='inclusive' "
            f"user:ui-marker='enumerate' /></filter>")


# ----------------------------------------------------------------------------------------------
# 3) THE FIVE WORKSHEETS
# ----------------------------------------------------------------------------------------------

def axis_rule(field_ref, scope, title):
    return (f"<style-rule element='axis'><format attr='title' class='0' field='{field_ref}' scope='{scope}' value='{q(title)}' />"
            f"<format attr='subtitle' class='0' field='{field_ref}' scope='{scope}' value='' />"
            f"<format attr='auto-subtitle' class='0' field='{field_ref}' scope='{scope}' value='true' /></style-rule>")


def header_width(field_ref, width):
    return f"<style-rule element='header'><format attr='width' field='{field_ref}' value='{width}' /></style-rule>"


FORMATS = {
    "Busiest times": header_width(ref("weekday_hour", "weekday_num", "none-o"), 48),
    "What moves footfall": axis_rule(ref("effects", "pct_change", "sum"), "cols", "Change in daily footfall vs a comparable day")
                           + header_width(ref("effects", "factor", "none-n"), 170),
    "Busiest days": axis_rule(ref("city_daily", "total_pedestrians", "avg"), "rows", "Average people per day"),
    "Weather buckets": axis_rule(ref("city_daily", "total_pedestrians", "avg"), "rows", "Average people per weekday"),
    "Busiest streets": axis_rule(ref("sensors_top10", "total_pedestrians", "sum"), "cols", "People counted over two years")
                       + header_width(ref("sensors_top10", "sensor_label", "none-n"), 250),
    "Daily footfall": axis_rule(ref("city_daily", "total_pedestrians", "sum"), "rows", "People per day")
                      + axis_rule(ref("city_daily", "sensing_date", "day"), "cols", "Date"),
}

SHEETS = []

# 1. Heatmap: when is the city busiest?
src = "weekday_hour"
used = [("hour_of_day", "none-o"), ("weekday_num", "none-o"), ("avg_pedestrians_per_sensor", "avg")]
c = ref(src, "avg_pedestrians_per_sensor", "avg")
SHEETS.append(worksheet(
    "Busiest times", "When is the city busiest? Darker = more people. Weekdays peak at lunchtime and about 5pm", src, used,
    rows=ref(src, "weekday_num", "none-o"), cols=ref(src, "hour_of_day", "none-o"), mark="Square",
    encodings=f"<color column='{c}' />", extra_style=palette_continuous(c, [BLUE_LIGHT, BLUE, BLUE_DARK]),
    slices=""))

# 2. Busiest days (public holidays left out)
src = "city_daily"
used = [("weekday_num", "none-o"), ("total_pedestrians", "avg"), ("day_type", "none-n")]
c = ref(src, "total_pedestrians", "avg")
SHEETS.append(worksheet(
    "Busiest days", "Friday and Saturday are the busiest days", src, used,
    rows=c, cols=ref(src, "weekday_num", "none-o"), mark="Bar",
    encodings=f"<color column='{c}' /><text column='{c}' />",
    filters=member_filter(src, "day_type", "Public holiday", exclude=True),
    slices=f"<slices><column>[{src}].[day_type]</column></slices>",
    extra_style=palette_continuous(c, ["#9dbfeb", BLUE]),
    pane_style=f"<style-rule element='mark'><format attr='mark-labels-show' value='true' />"
               f"<format attr='mark-labels-cull' value='true' /></style-rule>"
               f"<style-rule element='label'><format attr='text-format' field='{c}' value='n#,##0,K;-#,##0,K' /></style-rule>"))

# 3. What moves footfall? (regression effects)
src = "effects"
used = [("factor", "none-n"), ("pct_change", "sum"), ("Calculation_Shown", "usr")]
x, color = ref(src, "pct_change", "sum"), ref(src, "Calculation_Shown", "usr")
SHEETS.append(worksheet(
    "What moves footfall", "What moves footfall? Heavy rain cuts it by about a quarter (gray = could be chance)", src, used,
    rows=ref(src, "factor", "none-n"), cols=x, mark="Bar",
    encodings=f"<color column='{color}' /><text column='{x}' />",
    sorts=f"<sort class='computed' column='[{src}].[none:factor:nk]' direction='DESC' using='[{src}].[sum:pct_change:qk]' />",
    extra_style=palette_diverging(color, [ORANGE, "#d9d8d2", BLUE], 0.0, -25, 25),
    pane_style=f"<style-rule element='mark'><format attr='mark-labels-show' value='true' />"
               f"<format attr='mark-labels-cull' value='false' /></style-rule>"
               f"<style-rule element='label'><format attr='text-format' field='{x}' value='n+0&quot;%&quot;;-0&quot;%&quot;' /></style-rule>"))

# 4. Weather buckets (weekdays only)
src = "city_daily"
used = [("weather_bucket", "none-n"), ("total_pedestrians", "avg"), ("day_type", "none-n")]
y, color = ref(src, "total_pedestrians", "avg"), ref(src, "weather_bucket", "none-n")
order = ["Dry", "Rainy (1-10 mm)", "Heavy rain (10 mm+)"]
sort_xml = (f"<sort class='manual' column='[{src}].[none:weather_bucket:nk]' direction='ASC'><dictionary>"
            + "".join(f"<bucket>&quot;{q(o)}&quot;</bucket>" for o in order) + "</dictionary></sort>")
SHEETS.append(worksheet(
    "Weather buckets", "Weekdays: footfall drops as the rain gets heavier", src, used,
    rows=y, cols=color, mark="Bar", encodings=f"<text column='{y}' />",
    filters=member_filter(src, "day_type", "Weekday", exclude=False), sorts=sort_xml,
    slices=f"<slices><column>[{src}].[day_type]</column></slices>",
    pane_style=f"<style-rule element='mark'><format attr='mark-color' value='{BLUE}' /><format attr='mark-labels-show' value='true' /></style-rule>"
               f"<style-rule element='label'><format attr='text-format' field='{y}' value='n#,##0,K;-#,##0,K' /></style-rule>"))

# 5. Daily footfall over time
src = "city_daily"
used = [("sensing_date", "day"), ("total_pedestrians", "sum")]
y = ref(src, "total_pedestrians", "sum")
SHEETS.append(worksheet(
    "Daily footfall", "Daily footfall in the city centre, Nov 2024 to Nov 2026", src, used,
    rows=y, cols=ref(src, "sensing_date", "day"), mark="Line", encodings="",
    pane_style=f"<style-rule element='mark'><format attr='mark-color' value='{BLUE}' /></style-rule>"))

# 6. Busiest sensors (top 12)
src = "sensors_top10"
used = [("sensor_label", "none-n"), ("total_pedestrians", "sum")]
x = ref(src, "total_pedestrians", "sum")
SHEETS.append(worksheet(
    "Busiest streets", "The 10 busiest streets: people counted over two years", src, used,
    rows=ref(src, "sensor_label", "none-n"), cols=x, mark="Bar", encodings=f"<text column='{x}' />",
    sorts=f"<sort class='computed' column='[{src}].[none:sensor_label:nk]' direction='DESC' using='[{src}].[sum:total_pedestrians:qk]' />",
    pane_style=f"<style-rule element='mark'><format attr='mark-color' value='{BLUE}' /><format attr='mark-labels-show' value='true' /></style-rule>"
               f"<style-rule element='label'><format attr='text-format' field='{x}' value='n#,##0,,.0M;-#,##0,,.0M' /></style-rule>"))

SHEET_NAMES = ["Busiest times", "What moves footfall", "Busiest days", "Weather buckets", "Busiest streets", "Daily footfall"]

# ----------------------------------------------------------------------------------------------
# 4) THE DASHBOARD: zones are placed on a 100,000 x 100,000 grid.
# ----------------------------------------------------------------------------------------------
DASH = "Does rain empty Melbourne's city centre"
zone_id = [10]
CARD = ("<zone-style><format attr='border-color' value='#e3e2dc' /><format attr='border-style' value='solid' />"
        "<format attr='border-width' value='1' /><format attr='margin' value='12' /></zone-style>")
W_PX, H_PX = 1400, 1900


def sheet_zone(name, x, y, w, h):
    zone_id[0] += 1
    return f"<zone h='{h}' id='{zone_id[0]}' name='{q(name)}' show-title='true' w='{w}' x='{x}' y='{y}'>{CARD}</zone>"


def text_zone(runs, x, y, w, h, card=False):
    """runs: list of (text, size, bold, colour)."""
    zone_id[0] += 1
    inner = "".join(f"<run{' bold=\'true\'' if bold else ''} fontcolor='{colour}' fontsize='{size}'>{q(t)}</run>"
                    for t, size, bold, colour in runs)
    style = CARD if card else ""
    return (f"<zone h='{h}' id='{zone_id[0]}' type='text' w='{w}' x='{x}' y='{y}'>"
            f"<formatted-text>{inner}</formatted-text>{style}</zone>")


def px(v):  # pixels of height -> dashboard units
    return round(v / H_PX * 100000)


y = 0
zones = []
zones.append(text_zone([("Does rain empty Melbourne's city centre?", 28, True, INK)], 0, y, 100000, px(70)))
y += px(70)
zones.append(text_zone([("1.6 million hourly readings from 134 street sensors, Nov 2024 to Nov 2026, combined with weather and public holidays.", 13, False, INK2)],
                       0, y, 100000, px(50)))
y += px(50)
kpis = [("-9%", "Rainy weekday", ORANGE), ("-25%", "Heavy rain (10 mm+)", ORANGE), ("-10%", "Hot day (30C+)", ORANGE),
        ("+19%", "New Year's Eve", BLUE), ("6.6%", "Forecast error on unseen days", BLUE)]
for i, (big, caption, colour) in enumerate(kpis):
    zones.append(text_zone([(big + "\n", 32, True, colour), (caption, 12, False, INK2)], i * 20000, y, 20000, px(120), card=True))
y += px(120) + px(10)
rows = [  # (height px, [(sheet, x, w)])
    (470, [("Busiest times", 0, 58000), ("What moves footfall", 58000, 42000)]),
    (420, [("Busiest days", 0, 50000), ("Weather buckets", 50000, 50000)]),
    (340, [("Daily footfall", 0, 100000)]),
    (440, [("Busiest streets", 0, 100000)]),
]
for height, items in rows:
    for name, x, w in items:
        zones.append(sheet_zone(name, x, y, w, px(height)))
    y += px(height)
zones.append(text_zone([("Data: City of Melbourne Pedestrian Counting System and Open-Meteo weather. Effects come from a regression that holds weekday and month constant; "
                         "gray bars could be chance. These are associations, not proof of cause.", 10, False, INK2)], 0, y, 100000, 100000 - y))
dashboard = f"""
    <dashboard name='{q(DASH)}'>
      <style />
      <size maxheight='{H_PX}' maxwidth='{W_PX}' minheight='{H_PX}' minwidth='{W_PX}' />
      <zones>
        <zone h='100000' id='3' type='layout-basic' w='100000' x='0' y='0'>
          {''.join(zones)}
        </zone>
      </zones>
    </dashboard>"""


def window(name):
    return (f"<window class='worksheet' name='{q(name)}'><cards><edge name='left'><strip size='160'>"
            f"<card type='pages' /><card type='filters' /><card type='marks' /></strip></edge>"
            f"<edge name='top'><strip size='31'><card type='columns' /></strip><strip size='31'><card type='rows' /></strip>"
            f"<strip size='31'><card type='title' /></strip></edge></cards></window>")


windows = (f"<window class='dashboard' maximized='true' name='{q(DASH)}'><viewpoints>"
           + "".join(f"<viewpoint name='{q(n)}'><zoom type='entire-view' /></viewpoint>" for n in SHEET_NAMES) + "</viewpoints><active id='-1' /></window>"
           + "".join(window(n) for n in SHEET_NAMES))

workbook = f"""<?xml version='1.0' encoding='utf-8' ?>

<workbook locale='en_AU' source-build='2026.2.2 (20262.26.0819.2015)' source-platform='mac' version='18.1' xmlns:user='http://www.tableausoftware.com/xml/user'>
  <preferences>
    <preference name='ui.encoding.shelf.height' value='24' />
    <preference name='ui.shelf.height' value='26' />
  </preferences>
  <datasources>{''.join(datasource_xml(s) for s in SOURCES)}
  </datasources>
  <worksheets>{''.join(SHEETS)}
  </worksheets>
  <dashboards>{dashboard}
  </dashboards>
  <windows source-height='30'>{windows}</windows>
</workbook>
"""

OUT.parent.mkdir(exist_ok=True)
OUT.write_text(workbook, encoding="utf-8")
ET.parse(OUT)  # fails loudly if the XML is not well formed
PACKAGE = OUT.with_suffix(".twbx")
with zipfile.ZipFile(PACKAGE, "w", zipfile.ZIP_DEFLATED) as z:
    z.write(OUT, OUT.name)
    for src in SOURCES:
        z.write(EXTRACT_DIR / f"{src}.hyper", f"Data/Extracts/{src}.hyper")
print("packaged", PACKAGE, {k: f"{v:,} rows" for k, v in ROWS.items()})
print("wrote", OUT, f"({len(workbook):,} characters)")
