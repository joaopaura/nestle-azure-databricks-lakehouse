"""Render the Power BI page backgrounds (1920x1080 PNG) for the Nestlé report.
Static text is baked in (page title, navigation labels, KPI labels, chart titles, architecture, footer).
Visuals in Power BI have titles and backgrounds OFF and sit on top of these cards.
Layout grid is the same as the Roche and Shell reports (portfolio consistency).
Logo: save the official logo as nestle_logo.png (transparent PNG) next to this script; a placeholder is used if missing."""
import base64
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
OUT = HERE / "backgrounds"; OUT.mkdir(parents=True, exist_ok=True)
b64 = lambda p: base64.b64encode((HERE / p).read_bytes()).decode()
FONTS = "".join(f"@font-face{{font-family:'Inter';font-weight:{w};src:url(data:font/woff2;base64,{b64(f'inter-latin-{w}-normal.woff2')}) format('woff2')}}"
                for w in (400, 500, 600, 700))

# Nestlé palette: Nestlé Blue #005BA5 (sampled from the logo) primary, Oak secondary, light blue accent, light theme
T = dict(bg="#F6F8FA", panel="#FFFFFF", border="#E1E7EE", ink="#1C2B3A", ink2="#5B6B7B", muted="#8D9AA7",
         blue="#005BA5", blue_dark="#003E73", accent="#7FADD2", blue_soft="#E8F1F9", oak="#64513D", oak_soft="#F3EEE8",
         green="#2E7D4F")

LOGO_FILE = HERE / "nestle_logo.png"
if LOGO_FILE.exists():
    from PIL import Image
    _w, _h = Image.open(LOGO_FILE).size
    LOGO_RATIO = _w / _h
    LOGO_HTML = lambda style, h: f"<img class='abs' src='data:image/png;base64,{b64('nestle_logo.png')}' style='{style};height:{h}px'>"
else:  # placeholder until the real logo is saved
    LOGO_RATIO = 1.25
    LOGO_HTML = lambda style, h: (f"<div class='abs' style='{style};height:{h}px;width:{int(h * LOGO_RATIO)}px;border:2px dashed {T['blue']};"
                                  f"border-radius:8px;color:{T['blue']};font-weight:700;font-size:{max(10, h // 6)}px;display:flex;"
                                  f"align-items:center;justify-content:center;text-align:center'>Nestlé<br>logo</div>")

PAGE_LOGO_H = 58
PAGE_LOGO_W = int(PAGE_LOGO_H * LOGO_RATIO)
KPI_X = [48, 357, 667, 976, 1285, 1595]; KPI_W = 277; KPI_Y = 180; KPI_H = 116
ROW2_Y, ROW2_H = 316, 350
ROW3_Y, ROW3_H = 686, 334
TWO = [(48, 900), (972, 900)]
THREE = [(48, 592), (664, 592), (1280, 592)]
NAV = ["Home", "Commercial", "Demand &amp; Sell-out", "Platform &amp; DQ"]
NAV_W, NAV_H, NAV_GAP, NAV_Y = 168, 40, 8, 30
NAV_X0 = 1920 - 48 - PAGE_LOGO_W - 28 - (len(NAV) * NAV_W + (len(NAV) - 1) * NAV_GAP)
SLICER_X = [48, 290, 532, 774]; SLICER_Y = 124; SLICER_W = 226

FOOTER = ("Developed by <b>João Paúra</b> | Data Engineering &amp; BI portfolio project | "
          "Synthetic company data, real public data (ECB, Eurostat, Open-Meteo), processed on Azure Databricks | "
          "Independent project, not affiliated with or endorsed by Nestlé S.A.")
FOOTER_R = "linkedin.com/in/joaopaura | github.com/joaopaura"

CSS = f"""{FONTS}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{width:1920px;height:1080px;background:{T['bg']};font-family:'Inter',sans-serif;color:{T['ink']};position:relative;overflow:hidden}}
.abs{{position:absolute}}
.title{{left:48px;top:24px;font-size:30px;font-weight:700;letter-spacing:-0.3px}}
.title span{{color:{T['blue']}}}
.sub{{left:48px;top:68px;font-size:15px;color:{T['ink2']};width:880px;line-height:1.35;white-space:nowrap}}
.nav{{height:{NAV_H}px;width:{NAV_W}px;border-radius:8px;border:1px solid {T['border']};background:#fff;
      font-size:14px;font-weight:600;display:flex;align-items:center;justify-content:center;color:{T['ink']}}}
.nav.on{{background:{T['blue']};border-color:{T['blue']};color:#fff}}
.slabel{{font-size:12px;font-weight:600;color:{T['ink2']};text-transform:uppercase;letter-spacing:.6px}}
.card{{background:{T['panel']};border:1px solid {T['border']};border-radius:12px;box-shadow:0 1px 2px rgba(28,43,58,.05)}}
.kpi .l{{position:absolute;left:20px;top:16px;font-size:13px;font-weight:600;color:{T['ink2']}}}
.kpi .bar{{position:absolute;left:0;top:16px;width:4px;height:20px;border-radius:0 3px 3px 0;background:{T['accent']}}}
.panel .h{{position:absolute;left:24px;top:18px;font-size:17px;font-weight:700}}
.panel .s{{position:absolute;left:24px;top:44px;font-size:12.5px;color:{T['ink2']}}}
.footer{{left:48px;top:1044px;font-size:12px;color:{T['muted']}}}
.footer b{{color:{T['ink2']};font-weight:700}}
.footr{{right:48px;top:1044px;font-size:12px;color:{T['ink2']};font-weight:600}}
.fline{{left:48px;top:1032px;width:1824px;height:1px;background:{T['border']}}}
.stripe{{left:0;top:0;width:1920px;height:6px;background:linear-gradient(90deg,{T['blue']} 0 50%,{T['accent']} 50% 100%)}}
"""


def base(inner: str) -> str:
    return (f"<html><head><style>{CSS}</style></head><body><div class='abs stripe'></div>{inner}"
            f"<div class='abs fline'></div><div class='abs footer'>{FOOTER}</div>"
            f"<div class='abs footr'>{FOOTER_R}</div></body></html>")


def nav(active: int) -> str:
    html = ""
    for i, name in enumerate(NAV):
        x = NAV_X0 + i * (NAV_W + NAV_GAP)
        html += f"<div class='abs nav{' on' if i == active else ''}' style='left:{x}px;top:{NAV_Y}px'>{name}</div>"
    return html + LOGO_HTML("right:48px;top:20px", PAGE_LOGO_H)


def page(p: dict) -> str:
    h = f"<div class='abs title'>{p['title']}</div><div class='abs sub'>{p['sub']}</div>" + nav(p["nav"])
    for x, label in zip(SLICER_X, p["slicers"]):
        h += f"<div class='abs slabel' style='left:{x}px;top:{SLICER_Y - 18}px'>{label}</div>"
    h += f"<div class='abs slabel' style='left:1622px;top:{SLICER_Y - 18}px'>Data as of</div>"
    for x, label in zip(KPI_X, p["kpis"]):
        h += (f"<div class='abs card kpi' style='left:{x}px;top:{KPI_Y}px;width:{KPI_W}px;height:{KPI_H}px'>"
              f"<div class='bar'></div><div class='l'>{label}</div></div>")
    for (x, y, w, hh, title, sub, extra) in p["panels"]:
        h += (f"<div class='abs card panel' style='left:{x}px;top:{y}px;width:{w}px;height:{hh}px'>"
              f"<div class='h'>{title}</div><div class='s'>{sub}</div>{extra}</div>")
    return base(h)


def arch() -> str:
    box = ("display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center;"
           "border-radius:10px;font-size:13px;font-weight:600;padding:8px;line-height:1.3")

    def b(x, y, w, hh, t, s, fill, color=T["ink"]):
        return (f"<div class='abs' style='left:{x}px;top:{y}px;width:{w}px;height:{hh}px;{box};background:{fill};color:{color}'>"
                f"{t}<span style='font-size:11px;font-weight:500;opacity:.85;margin-top:3px'>{s}</span></div>")

    def arrow(x, y, w):
        return (f"<div class='abs' style='left:{x}px;top:{y}px;width:{w}px;height:2px;background:#ABA196'></div>"
                f"<div class='abs' style='left:{x + w - 7}px;top:{y - 4}px;width:0;height:0;border-left:8px solid #ABA196;"
                f"border-top:5px solid transparent;border-bottom:5px solid transparent'></div>")
    W, G = 146, 26
    X = [24 + i * (W + G) for i in range(7)]
    s = ""
    s += b(X[0], 84, W, 172, "Sources", "Legacy ERP (Azure SQL)<br>distributor files<br>ECB, Eurostat, weather", "#EEF2F6")
    s += b(X[1], 84, W, 172, "ADLS Gen2", "landing zone<br>CSV, JSON<br>POS events", T["oak_soft"])
    s += b(X[2], 84, W, 172, "Bronze", "Auto Loader<br>raw Delta<br>+ metadata", T["blue_soft"])
    s += b(X[3], 84, W, 172, "Silver", "PySpark, DLT<br>expectations<br>SCD2, MERGE", T["blue_soft"])
    s += b(X[4], 84, W, 172, "Gold", "Star schema<br>KPI marts<br>Unity Catalog", T["blue_soft"])
    s += b(X[5], 84, W, 172, "ML", "Weekly forecast<br>MLflow<br>UC model registry", T["oak_soft"])
    s += b(X[6], 84, 106, 172, "Power BI", "Import mode<br>4 pages", T["blue"], "#FFFFFF")
    for i in range(6):
        s += arrow(X[i] + W, 170, G)
    s += b(24, 272, 1160, 44, "Reconciliation Azure SQL vs Delta | DQ expectations | Workflow + ADF | Asset Bundle + GitHub Actions", "", T["bg"])
    return s


PAGES = {
    "02_commercial": dict(
        nav=1, title="Commercial Performance <span>|</span> Sell-in",
        sub="Net sales, organic growth, volume and margin across 12 European markets, 7 categories and 4 channels | EUR",
        slicers=["Year", "Country", "Category", "Channel"],
        kpis=["Net sales", "Organic growth", "Real internal growth (RIG)", "Pricing", "Gross margin", "Volume (tonnes)"],
        panels=[(TWO[0][0], ROW2_Y, TWO[0][1], ROW2_H, "Net sales trend", "EUR m per month, current vs prior year", ""),
                (TWO[1][0], ROW2_Y, TWO[1][1], ROW2_H, "Organic growth bridge", "Prior year to current year: volume (RIG), pricing and FX, EUR m", ""),
                (THREE[0][0], ROW3_Y, THREE[0][1], ROW3_H, "Net sales by category", "EUR m and organic growth, selected period", ""),
                (THREE[1][0], ROW3_Y, THREE[1][1], ROW3_H, "Net sales by country", "EUR m, top 12 markets", ""),
                (THREE[2][0], ROW3_Y, THREE[2][1], ROW3_H, "Channel mix", "Share of net sales by channel", "")]),
    "03_demand": dict(
        nav=2, title="Demand &amp; Sell-out <span>|</span> Forecast and promotions",
        sub="Weekly demand forecast (MLflow), distributor sell-out vs sell-in and promotion performance | tonnes, EUR",
        slicers=["Year", "Country", "Category", "Channel"],
        kpis=["Forecast accuracy", "MAPE", "Bias", "Sell-out", "Sell-through", "Promo uplift"],
        panels=[(TWO[0][0], ROW2_Y, TWO[0][1], ROW2_H, "Actual vs forecast", "Volume per week, tonnes | test period and next 12 weeks", ""),
                (TWO[1][0], ROW2_Y, TWO[1][1], ROW2_H, "Sell-in vs sell-out", "Thousand cases per month, distributors | gap = stock building", ""),
                (THREE[0][0], ROW3_Y, THREE[0][1], ROW3_H, "Forecast error by category", "MAPE on the test period, lower is better", ""),
                (THREE[1][0], ROW3_Y, THREE[1][1], ROW3_H, "Stock cover by distributor", "Top 12 distributors, weeks of stock at period end | red = 30% above network", ""),
                (THREE[2][0], ROW3_Y, THREE[2][1], ROW3_H, "Promo uplift by category", "Incremental volume vs baseline, %", "")]),
    "04_platform_dq": dict(
        nav=3, title="Platform &amp; Data Quality <span>|</span> Azure Databricks",
        sub="Legacy ERP migrated to a governed lakehouse: medallion layers, expectations, reconciliation and orchestration",
        slicers=["", "", "", ""],
        kpis=["Pipeline runs", "Rows processed", "DQ expectations passed", "Reconciliation pass rate", "Last run duration", "Delta tables"],
        panels=[(TWO[0][0], ROW2_Y, TWO[0][1], ROW2_H, "Rows by layer", "Top 12 Delta tables by row count, colour = medallion layer", ""),
                (TWO[1][0], ROW2_Y, TWO[1][1], ROW2_H, "Reconciliation Azure SQL vs Delta", "Row counts, content hashes and business totals, latest run", ""),
                (48, ROW3_Y, 1208, ROW3_H, "Architecture", "End-to-end flow on Azure Databricks", arch()),
                (THREE[2][0], ROW3_Y, THREE[2][1], ROW3_H, "Data quality expectations", "Passed and failed records per expectation, latest run", "")]),
}


def cover() -> str:
    logo_h = 270  # cover logo: big and prominent, centred over the right column (x 1180 to 1872)
    h = LOGO_HTML(f"left:{1526 - int(logo_h * LOGO_RATIO / 2)}px;top:34px", logo_h)
    h += (f"<div class='abs' style='left:48px;top:180px;font-size:14px;font-weight:700;color:{T['blue']};letter-spacing:1.4px'>"
          "PORTFOLIO PROJECT | FMCG DATA ENGINEERING</div>")
    h += "<div class='abs' style='left:48px;top:212px;font-size:60px;font-weight:700;letter-spacing:-1.2px;line-height:1.05'>Nestlé European<br>FMCG Lakehouse</div>"
    h += (f"<div class='abs' style='left:48px;top:360px;width:1040px;font-size:19px;color:{T['ink2']};line-height:1.5'>"
          "End-to-end Azure Databricks project: a legacy ERP is migrated into a governed Delta lakehouse, "
          "reconciled, enriched with real public data and used to forecast demand across 12 European markets.</div>")
    for i, label in enumerate(["Rows processed", "Reconciliation checks passed", "Forecast accuracy"]):
        x = 48 + i * 364
        h += (f"<div class='abs card kpi' style='left:{x}px;top:500px;width:340px;height:140px'>"
              f"<div class='bar'></div><div class='l'>{label}</div></div>")
    chips = ["Azure Databricks", "Unity Catalog", "Delta Lake", "PySpark", "MLflow", "Data Factory", "Azure SQL", "Power BI"]
    x = 48
    for c in chips:
        w = 28 + len(c) * 9
        h += (f"<div class='abs' style='left:{x}px;top:690px;height:36px;width:{w}px;border-radius:18px;background:{T['blue_soft']};"
              f"color:{T['blue_dark']};font-size:14px;font-weight:600;display:flex;align-items:center;justify-content:center'>{c}</div>")
        x += w + 10
    facts = [("", "rows in bronze (ERP, files, stream)"), ("", "Delta tables in Unity Catalog"),
             ("", "difference Azure SQL vs Delta"), ("", "end-to-end pipeline run, 10 tasks")]
    for i, (big, small) in enumerate(facts):
        x = 48 + i * 262
        h += (f"<div class='abs' style='left:{x}px;top:770px;width:240px;text-align:center'><div style='height:36px'></div>"
              f"<div style='font-size:13.5px;color:{T['ink2']};margin-top:4px'>{small}</div></div>")
    cards = [("Commercial", "Net sales, organic growth, RIG, pricing and margin"),
             ("Demand &amp; Sell-out", "Forecast vs actual, sell-in vs sell-out and promo uplift"),
             ("Platform &amp; DQ", "Reconciliation, expectations, lineage and orchestration")]
    for i, (name, desc) in enumerate(cards):
        x = 1180 + (i % 2) * 358; y = 336 + (i // 2) * 170
        h += (f"<div class='abs card' style='left:{x}px;top:{y}px;width:334px;height:150px'>"
              f"<div class='abs' style='left:24px;top:20px;width:36px;height:4px;border-radius:2px;background:{T['accent']}'></div>"
              f"<div class='abs' style='left:24px;top:36px;font-size:21px;font-weight:700'>{name}</div>"
              f"<div class='abs' style='left:24px;top:70px;width:286px;font-size:13.5px;color:{T['ink2']};line-height:1.45'>{desc}</div>"
              f"<div class='abs' style='left:24px;top:116px;font-size:14px;font-weight:700;color:{T['blue']}'>Open page &#8594;</div></div>")
    h += (f"<div class='abs' style='left:1538px;top:516px;width:334px;font-size:12.5px;color:{T['muted']};line-height:1.5'>"
          "Company figures are synthetic and generated for portfolio purposes. They do not represent Nestlé S.A. reporting. "
          "FX, inflation and weather data are real public data. The Nestlé logo is used only to identify the case study.</div>")
    return base(h)


if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page(viewport={"width": 1920, "height": 1080})
        docs = {"01_home": cover(), **{k: page(v) for k, v in PAGES.items()}}
        for name, html in docs.items():
            pg.set_content(html); pg.wait_for_timeout(400)
            pg.screenshot(path=str(OUT / f"{name}.png"))
            print("rendered", name)
        browser.close()
