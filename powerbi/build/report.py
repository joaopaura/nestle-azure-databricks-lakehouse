"""Builds the Nestle report pages (PBIR): backgrounds, navigation, slicers, KPI cards, charts and tables.
Same visual framework as the Shell and Roche reports (portfolio consistency)."""
import hashlib, json, shutil, sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "/home/claude/nb")
NAME = "Nestle_FMCG_Lakehouse"
TPL = ROOT / "tpl" / f"{NAME}.Report"
OUT = ROOT / "out" / f"{NAME}.Report"
BG = ROOT / "tpl" / "design" / "backgrounds"
THEME = ROOT / "tpl" / "design" / "nestle_theme.json"
SCHEMA_V = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.12.0/schema.json"
BLUE, BLUE_D, ACCENT, OAK, GREEN, RED, ORANGE, GREY, INK2 = "#005BA5", "#003E73", "#7FADD2", "#64513D", "#2E7D4F", "#C2402E", "#D08A2E", "#A9B4BF", "#5B6B7B"

hid = lambda *k: hashlib.sha1("|".join(map(str, k)).encode()).hexdigest()[:20]
lit = lambda v: {"expr": {"Literal": {"Value": v}}}
col_ = lambda c: {"solid": {"color": lit(f"'{c}'")}}
colm = lambda m: {"solid": {"color": {"expr": {"Measure": {"Expression": {"SourceRef": {"Entity": "_Measures"}}, "Property": m}}}}}
C = lambda e, p: {"Column": {"Expression": {"SourceRef": {"Entity": e}}, "Property": p}}
Me = lambda p: {"Measure": {"Expression": {"SourceRef": {"Entity": "_Measures"}}, "Property": p}}
F = lambda f: C(*f.split(".", 1)) if not f.startswith("[") else Me(f[1:-1])


def qref(f):
    return f"_Measures.{f[1:-1]}" if f.startswith("[") else f


def proj(f, active=False):
    p = {"field": F(f), "queryRef": qref(f), "nativeQueryRef": qref(f).split(".", 1)[1]}
    if active:
        p["active"] = True
    return p


def scope_sel(f, value):
    e, p = f.split(".", 1)
    return {"data": [{"scopeId": {"Comparison": {"ComparisonKind": 0, "Left": C(e, p), "Right": {"Literal": {"Value": value}}}}}]}


def cat_filter(name, e, c, values):
    return {"name": name, "field": C(e, c), "type": "Categorical",
            "filter": {"Version": 2, "From": [{"Name": "t", "Entity": e, "Type": 0}],
                       "Where": [{"Condition": {"In": {"Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": c}}],
                                                       "Values": [[{"Literal": {"Value": v}}] for v in values]}}}]}}


class Page:
    def __init__(self, key, name, bg):
        self.key, self.name, self.bg, self.visuals, self.inter, self.z = key, name, bg, [], [], 1000
        self.id = hid("page", key)

    def add(self, kind, x, y, w, h, visual):
        self.z += 100
        vid = hid(self.key, kind, x, y, len(self.visuals))
        visual.setdefault("visualContainerObjects", {}).setdefault("title", [{"properties": {"show": lit("false"), "text": lit(f"'{kind}'")}}])
        visual["drillFilterOtherVisuals"] = True
        fc = visual.pop("filterConfig", None)
        c = {"$schema": SCHEMA_V, "name": vid,
             "position": {"x": x, "y": y, "z": self.z, "height": h, "width": w, "tabOrder": len(self.visuals)}, "visual": visual}
        if fc:
            c["filterConfig"] = fc
        self.visuals.append(c)
        return vid


# ------------------------------------------------------------------ visual builders
def card(pg, x, y, w, h, m, ref=None, ref_title="vs PY", ref_colour=None, value_colour=None, size=None):
    mm = f"_Measures.{m}"
    obj = {"label": [{"properties": {"show": lit("false")}, "selector": {"id": "default"}}],
           "outline": [{"properties": {"show": lit("false")}, "selector": {"id": "default"}}],
           "divider": [{"properties": {"show": lit("false")}, "selector": {"id": "default"}}],
           "fillCustom": [{"properties": {"show": lit("false")}}],
           "value": [{"properties": {"labelDisplayUnits": lit("1D")}, "selector": {"metadata": mm}}]}
    if size:
        obj["value"].append({"properties": {"fontSize": lit(f"{size}D")}, "selector": {"id": "default"}})
    if value_colour:
        obj["value"].append({"properties": {"fontColor": colm(value_colour)},
                             "selector": {"data": [{"dataViewWildcard": {"matchingOption": 0}}], "metadata": mm}})
    if ref:
        rid = "field-" + hid("ref", pg.key, m)[:8] + "-0000-0000-0000-" + hid("ref2", pg.key, m)[:12]
        obj["referenceLabel"] = [{"properties": {"value": {"expr": Me(ref)}},
                                  "selector": {"data": [{"dataViewWildcard": {"matchingOption": 0}}], "metadata": mm, "id": rid, "order": 0}}]
        obj["referenceLabelTitle"] = [{"properties": {"titleContentType": lit("'custom'"), "titleText": lit(f"'{ref_title}'")},
                                       "selector": {"metadata": mm, "id": rid}}]
        obj["referenceLabelValue"] = [{"properties": {"valueFontSize": lit("10D"), "valueFontColor": col_(INK2)}, "selector": {"id": "default"}},
                                      {"properties": {"valueDisplayUnits": lit("1D")}, "selector": {"metadata": mm, "id": rid}}]
        if ref_colour:
            obj["referenceLabelValue"].insert(0, {"properties": {"valueFontColor": colm(ref_colour)},
                                                  "selector": {"data": [{"dataViewWildcard": {"matchingOption": 0}}], "metadata": mm, "id": rid}})
    v = {"visualType": "cardVisual", "query": {"queryState": {"Data": {"projections": [proj(f"[{m}]")]}}}, "objects": obj,
         "visualContainerObjects": {"padding": [{"properties": {"right": lit("0D"), "left": lit("4D"), "top": lit("0D")}}]}}
    return pg.add(f"Card {m}", x, y, w, h, v)


def slicer(pg, x, y, f, default=None):
    v = {"visualType": "slicer", "query": {"queryState": {"Values": {"projections": [proj(f, True)]}}},
         "objects": {"data": [{"properties": {"mode": lit("'Dropdown'")}}],
                     "selection": [{"properties": {"selectAllCheckboxEnabled": lit("true")}}],
                     "items": [{"properties": {"textSize": lit("11D")}}]},
         "visualContainerObjects": {"background": [{"properties": {"show": lit("true")}}],
                                    "border": [{"properties": {"show": lit("true"), "color": col_("#E1E7EE"), "radius": lit("8D")}}]}}
    e, p = f.split(".", 1)
    if default is not None:
        v["objects"]["general"] = [{"properties": {"filter": {"filter": {"Version": 2, "From": [{"Name": "d", "Entity": e, "Type": 0}],
            "Where": [{"Condition": {"In": {"Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "d"}}, "Property": p}}],
                                            "Values": [[{"Literal": {"Value": default}}]]}}}]}}}}]
    return pg.add(f"Slicer {p}", x, y, 226, 36, v)


def nav_button(pg, x, y, w, h, target_id, label):
    fill = [{"properties": {"show": lit("true")}},
            {"properties": {"fillColor": col_(BLUE), "transparency": lit("90D")}, "selector": {"id": "hover"}},
            {"properties": {"transparency": lit("100D")}, "selector": {"id": "default"}},
            {"properties": {"transparency": lit("85D")}, "selector": {"id": "selected"}}]
    v = {"visualType": "actionButton",
         "objects": {"icon": [{"properties": {"shapeType": lit("'blank'")}, "selector": {"id": "default"}}, {"properties": {"show": lit("false")}}],
                     "fill": fill, "outline": [{"properties": {"show": lit("false")}}]},
         "visualContainerObjects": {"visualLink": [{"properties": {"show": lit("true"), "type": lit("'PageNavigation'"),
                                                                   "navigationSection": lit(f"'{target_id}'"), "tooltip": lit(f"'Go to {label}'")}}],
                                    "title": [{"properties": {"show": lit("false"), "text": lit(f"'Nav {label}'")}}],
                                    "background": [{"properties": {"show": lit("false")}}],
                                    "padding": [{"properties": {k: lit("0D") for k in ("top", "bottom", "left", "right")}}],
                                    "visualHeader": [{"properties": {"show": lit("false")}}]}}
    return pg.add(f"Nav {label}", x, y, w, h, v)


def chart(pg, vtype, x, y, w, h, cat, ys, series=None, tooltips=None, colours=None, sort=None, labels=True, value_axis=False,
          legend=True, label_units=None, extra=None, hide_labels=(), precision=None, fill_measure=None, label_style=None):
    qs = {"Category": {"projections": [proj(cat, True)]}, "Y": {"projections": [proj(f) for f in ys]}}
    if series:
        qs["Series"] = {"projections": [proj(series)]}
    if tooltips:
        qs["Tooltips"] = {"projections": [proj(f) for f in tooltips]}
    q = {"queryState": qs}
    if sort == "desc":
        q["sortDefinition"] = {"sort": [{"field": F(ys[0]), "direction": "Descending"}], "isDefaultSort": True}
    elif sort == "cat":
        q["sortDefinition"] = {"sort": [{"field": F(cat), "direction": "Ascending"}]}
    obj = {"labels": [{"properties": {"show": lit("true" if labels else "false")}}],
           "legend": [{"properties": {"show": lit("true" if legend else "false"), "position": lit("'Top'")}}]}
    if vtype not in ("donutChart",):
        obj["valueAxis"] = [{"properties": {"show": lit("true" if value_axis else "false")}}]
    for hl in hide_labels:
        obj["labels"].append({"properties": {"showSeries": lit("false")}, "selector": {"metadata": qref(hl)}})
    if precision is not None:
        obj["labels"][0]["properties"]["labelPrecision"] = lit(f"{precision}L")
    if label_units:
        obj["labels"][0]["properties"]["labelDisplayUnits"] = lit(label_units)
    if label_style:
        obj["labels"][0]["properties"]["labelStyle"] = lit(f"'{label_style}'")
    obj["dataPoint"] = []
    for key, c in (colours or {}).items():
        if key.startswith("["):
            obj["dataPoint"].append({"properties": {"fill": col_(c)}, "selector": {"metadata": qref(key)}})
        else:
            f, val = key.split("=", 1)
            obj["dataPoint"].append({"properties": {"fill": col_(c)}, "selector": scope_sel(f, val)})
    if fill_measure:
        obj["dataPoint"].append({"properties": {"fill": colm(fill_measure)}, "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}]}})
    if not obj["dataPoint"]:
        del obj["dataPoint"]
    for k, v in (extra or {}).items():
        obj.setdefault(k, []).extend(v)
    return pg.add(f"{vtype} {cat}", x, y, w, h, {"visualType": vtype, "query": q, "objects": obj})


def table(pg, x, y, w, h, fields, headers, latest_entity=None, font=10, sort=None):
    projs = []
    for f, hdr in zip(fields, headers):
        p = proj(f)
        p["displayName"] = hdr
        projs.append(p)
    q = {"queryState": {"Values": {"projections": projs}}}
    if sort:
        q["sortDefinition"] = {"sort": [{"field": F(sort[0]), "direction": sort[1]}]}
    v = {"visualType": "tableEx", "query": q,
         "objects": {"columnHeaders": [{"properties": {"fontSize": lit(f"{font}D")}}], "values": [{"properties": {"fontSize": lit(f"{font}D")}}],
                     "total": [{"properties": {"totals": lit("false")}}]}}
    if latest_entity:
        v["filterConfig"] = {"filters": [cat_filter(hid("latest", pg.key, latest_entity), latest_entity, "is_latest_run", ["true"])]}
    return pg.add("Table", x, y, w, h, v)


# ------------------------------------------------------------------ layout (same grid as design/backgrounds.py)
KPI_X = [48, 357, 667, 976, 1285, 1595]; KPI_Y, KPI_W = 180, 277
ROW2_Y, ROW2_H, ROW3_Y, ROW3_H = 316, 350, 686, 334
TWO = [(48, 900), (972, 900)]; THREE = [(48, 592), (664, 592), (1280, 592)]
SLICER_X, SLICER_Y = [48, 290, 532, 774], 124
LOGO_W = int(58 * 1038 / 624)
NAV_W, NAV_GAP, NAV_Y = 168, 8, 30
NAV_X0 = 1920 - 48 - LOGO_W - 28 - (4 * NAV_W + 3 * NAV_GAP)

PAGES = [Page("home", "Home", "01_home"), Page("commercial", "Commercial Performance", "02_commercial"),
         Page("demand", "Demand & Sell-out", "03_demand"), Page("platform", "Platform & Data Quality", "04_platform_dq")]
P = {p.key: p for p in PAGES}


def inner(x, y, w, h):
    return x + 12, y + 64, w - 24, h - 74


def kpis(pg, specs):
    for x, s in zip(KPI_X, specs):
        m, ref, title, rc, vc = (list(s) + [None] * 5)[:5]
        card(pg, x + 12, KPI_Y + 34, KPI_W - 24, 76, m, ref, title or "vs PY", rc, vc)


def header(pg, active, slicers):
    for i, p in enumerate(PAGES):
        if i != active:
            nav_button(pg, NAV_X0 + i * (NAV_W + NAV_GAP), NAV_Y, NAV_W, 40, p.id, p.name)
    ids = [slicer(pg, x, SLICER_Y, *s) for x, s in zip(SLICER_X, slicers)]
    card(pg, 1614, SLICER_Y - 6, 258, 44, "Data As Of", size=16)
    return ids


SLICERS = [("dim_date.year", "2026L"), ("dim_country.country_name",), ("dim_category.category",), ("dim_channel.channel",)]

# ------------------------------------------------------------------ Home
pg = P["home"]
for i, (m, ref, title, rc) in enumerate([("Rows Processed (M)", "Delta Tables", "Delta tables", None),
                                          ("Recon Checks Passed", "Recon Pass Rate", "pass rate", "Recon Colour"),
                                          ("Forecast Accuracy", "Baseline Accuracy", "seasonal naive", None)]):
    card(pg, 48 + i * 364 + 14, 540, 312, 92, m, ref, title, rc, size=40)
for i, m in enumerate(["Rows Processed (M)", "Delta Tables", "Recon Difference", "Last Run Duration"]):
    card(pg, 48 + i * 262, 764, 240, 46, m, size=26)
for i, p in enumerate(PAGES[1:]):
    nav_button(pg, 1180 + (i % 2) * 358, 336 + (i // 2) * 170, 334, 150, p.id, p.name)

# ------------------------------------------------------------------ Commercial Performance
pg = P["commercial"]
header(pg, 1, SLICERS)
kpis(pg, [("Net Sales (€m)", "Net Sales YoY %", "vs PY", "Net Sales YoY % Colour"),
          ("Organic Growth", "Organic Growth PY", "prior year", "Neutral Colour", "Organic Growth Colour"),
          ("RIG", "RIG PY", "prior year", "Neutral Colour", "RIG Colour"),
          ("Pricing", "Pricing PY", "prior year", "Neutral Colour", "Pricing Colour"),
          ("Gross Margin", "Gross Margin vs PY", "vs PY", "Gross Margin vs PY Colour"),
          ("Volume (kt)", "Volume (kt) YoY %", "vs PY", "Volume (kt) YoY % Colour")])
chart(pg, "lineChart", *inner(TWO[0][0], ROW2_Y, TWO[0][1], ROW2_H), "dim_date.month_name", ["[Net Sales (€m)]", "[Net Sales (€m) PY]"],
      colours={"[Net Sales (€m)]": BLUE, "[Net Sales (€m) PY]": OAK}, sort="cat", hide_labels=["[Net Sales (€m) PY]"], precision=1,
      tooltips=["[Reported Growth]", "[Organic Growth]"])
chart(pg, "waterfallChart", *inner(TWO[1][0], ROW2_Y, TWO[1][1], ROW2_H), "bridge_step.step", ["[Bridge Value (€m)]"], sort="cat",
      legend=False, precision=1,
      extra={"sentimentColors": [{"properties": {"increaseFill": col_(ACCENT), "decreaseFill": col_(RED), "totalFill": col_(BLUE)}}]})
chart(pg, "clusteredBarChart", *inner(THREE[0][0], ROW3_Y, THREE[0][1], ROW3_H), "dim_category.category", ["[Net Sales (€m)]"],
      tooltips=["[Organic Growth]", "[RIG]", "[Pricing]"], sort="desc", legend=False, colours={"[Net Sales (€m)]": BLUE}, precision=1)
chart(pg, "clusteredBarChart", *inner(THREE[1][0], ROW3_Y, THREE[1][1], ROW3_H), "dim_country.country_name", ["[Net Sales (€m)]"],
      tooltips=["[Organic Growth]", "[FX Effect]"], sort="desc", legend=False, colours={"[Net Sales (€m)]": BLUE}, precision=1)
chart(pg, "clusteredBarChart", *inner(THREE[2][0], ROW3_Y, THREE[2][1], ROW3_H), "dim_channel.channel", ["[Net Sales Share]"],
      tooltips=["[Net Sales (€m)]", "[Organic Growth]"], sort="desc", legend=False, colours={"[Net Sales Share]": BLUE}, precision=1)

# ------------------------------------------------------------------ Demand & Sell-out
pg = P["demand"]
header(pg, 2, SLICERS)
kpis(pg, [("Forecast Accuracy", "Baseline Accuracy", "seasonal naive", None),
          ("MAPE", "Baseline MAPE", "seasonal naive", None),
          ("Bias", "Baseline Bias", "seasonal naive", None, "Bias Colour"),
          ("Sell-out (k cases)", "Sell-out (k cases) YoY %", "vs PY", "Sell-out (k cases) YoY % Colour"),
          ("Sell-through", "Sell-through vs PY", "vs PY", "Sell-through vs PY Colour"),
          ("Promo Uplift", "Planned Uplift", "planned", None, "Promo Uplift Colour")])
chart(pg, "lineChart", *inner(TWO[0][0], ROW2_Y, TWO[0][1], ROW2_H), "forecast_weekly.week_start",
      ["[Actual (t)]", "[Forecast (t)]", "[Seasonal Naive (t)]"], sort="cat", value_axis=True, precision=0,
      hide_labels=["[Actual (t)]", "[Seasonal Naive (t)]"],
      colours={"[Actual (t)]": OAK, "[Forecast (t)]": BLUE, "[Seasonal Naive (t)]": GREY},
      extra={"lineStyles": [{"properties": {"lineStyle": lit("'dashed'")}, "selector": {"metadata": "_Measures.Seasonal Naive (t)"}}]})
chart(pg, "lineChart", *inner(TWO[1][0], ROW2_Y, TWO[1][1], ROW2_H), "dim_date.month_name", ["[Sell-in (k cases)]", "[Sell-out (k cases)]"],
      sort="cat", colours={"[Sell-in (k cases)]": OAK, "[Sell-out (k cases)]": BLUE}, tooltips=["[Sell-through]"], hide_labels=["[Sell-in (k cases)]"])
chart(pg, "clusteredBarChart", *inner(THREE[0][0], ROW3_Y, THREE[0][1], ROW3_H), "dim_category.category", ["[MAPE]"],
      tooltips=["[Forecast Accuracy]", "[Baseline MAPE]", "[Bias]"], sort="desc", legend=False, colours={"[MAPE]": BLUE}, precision=1)
chart(pg, "clusteredBarChart", *inner(THREE[1][0], ROW3_Y, THREE[1][1], ROW3_H), "mart_sellin_sellout_weekly.distributor_name",
      ["[Stock Cover Top 12]"], tooltips=["[Network Stock Cover]", "[Sell-out (k cases)]", "[Sell-through]"], sort="desc", legend=False,
      fill_measure="Stock Cover Colour", precision=1)
chart(pg, "clusteredBarChart", *inner(THREE[2][0], ROW3_Y, THREE[2][1], ROW3_H), "dim_category.category", ["[Promo Uplift]"],
      tooltips=["[Planned Uplift]"], sort="desc", legend=False, colours={"[Promo Uplift]": BLUE}, precision=1)

# ------------------------------------------------------------------ Platform & Data Quality
pg = P["platform"]
header(pg, 3, [])
kpis(pg, [("Pipeline Runs", "Orchestration", "via", None),
          ("Rows Processed (M)", "Silver Rows (M)", "silver", None),
          ("DQ Checks Passed", "DQ Checks Failed", "failed", "DQ Failed Colour"),
          ("Recon Pass Rate", "Recon Checks", "checks", None, "Recon Colour"),
          ("Last Run Duration", "Last Run Start", "started", None),
          ("Delta Tables", "Gold Tables", "gold", None)])
chart(pg, "barChart", *inner(TWO[0][0], ROW2_Y, TWO[0][1], ROW2_H), "platform_table_counts.table_label", ["[Rows Top 12 (M)]"],
      series="platform_table_counts.layer", sort="desc", labels=False,
      extra={"totals": [{"properties": {"show": lit("true")}}]},
      colours={"platform_table_counts.layer='bronze'": OAK, "platform_table_counts.layer='silver'": ACCENT,
               "platform_table_counts.layer='gold'": BLUE})
table(pg, *inner(TWO[1][0], ROW2_Y, TWO[1][1], ROW2_H),
      ["reconciliation_results.check_level", "reconciliation_results.object_name", "reconciliation_results.check_name",
       "reconciliation_results.source_value", "reconciliation_results.target_value", "reconciliation_results.status"],
      ["Level", "Object", "Check", "Azure SQL", "Delta", "Status"], latest_entity="reconciliation_results",
      sort=("reconciliation_results.check_level", "Ascending"))
table(pg, *inner(THREE[2][0], ROW3_Y, THREE[2][1], ROW3_H),
      ["dq_results.table_name", "dq_results.check_name", "dq_results.failed_rows", "dq_results.failed_share", "dq_results.status"],
      ["Table", "Expectation", "Failed rows", "Failed %", "Status"], latest_entity="dq_results", font=9)

# ------------------------------------------------------------------ write
shutil.rmtree(OUT, ignore_errors=True)
shutil.copytree(TPL, OUT, ignore=shutil.ignore_patterns("pages"))
defn = OUT / "definition"
res = OUT / "StaticResources" / "RegisteredResources"
res.mkdir(parents=True)
shutil.copy(THEME, res / "nestle_theme.json")
items = [{"name": "nestle_theme.json", "path": "nestle_theme.json", "type": "CustomTheme"}]
for p in PAGES:
    shutil.copy(BG / f"{p.bg}.png", res / f"{p.bg}.png")
    items.append({"name": f"{p.bg}.png", "path": f"{p.bg}.png", "type": "Image"})
    pdir = defn / "pages" / p.id
    (pdir / "visuals").mkdir(parents=True)
    page = {"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json",
            "name": p.id, "displayName": p.name, "displayOption": "FitToPage", "height": 1080, "width": 1920,
            "objects": {"background": [{"properties": {"image": {"image": {
                "name": lit(f"'{p.bg}.png'"),
                "url": {"expr": {"ResourcePackageItem": {"PackageName": "RegisteredResources", "PackageType": 1, "ItemName": f"{p.bg}.png"}}},
                "scaling": lit("'Normal'")}}, "transparency": lit("0D")}}]}}
    if p.inter:
        page["visualInteractions"] = p.inter
    (pdir / "page.json").write_text(json.dumps(page, indent=2, ensure_ascii=False), encoding="utf-8")
    for v in p.visuals:
        (pdir / "visuals" / v["name"]).mkdir()
        (pdir / "visuals" / v["name"] / "visual.json").write_text(json.dumps(v, indent=2, ensure_ascii=False), encoding="utf-8")
(defn / "pages" / "pages.json").write_text(json.dumps({
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.1.0/schema.json",
    "pageOrder": [p.id for p in PAGES], "activePageName": PAGES[0].id}, indent=2), encoding="utf-8")

rep = json.loads((TPL / "definition" / "report.json").read_text(encoding="utf-8"))
rep["themeCollection"]["customTheme"] = {"name": "nestle_theme.json", "reportVersionAtImport": rep["themeCollection"]["baseTheme"]["reportVersionAtImport"],
                                         "type": "RegisteredResources"}
rep["resourcePackages"] = [r for r in rep["resourcePackages"] if r["type"] != "RegisteredResources"] + \
                          [{"name": "RegisteredResources", "type": "RegisteredResources", "items": items}]
rep.setdefault("objects", {})["outspacePane"] = [{"properties": {"expanded": lit("false")}}]
(defn / "report.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
print({p.name: len(p.visuals) for p in PAGES})
