"""_Measures table for the Nestle report. Every measure has a description (///) and a display folder."""
import uuid, sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "/home/claude/nb")
tag = lambda *k: str(uuid.uuid5(uuid.NAMESPACE_URL, "nestle-measures/" + "/".join(k)))
M = []   # (folder, name, expr, fmt, description)
GREEN, RED, GREY, ORANGE = "#2E7D4F", "#C2402E", "#5B6B7B", "#D08A2E"
PCT = "+0.0%;-0.0%;0.0%"
EURM = "€#,0.0\\m"


def add(folder, name, expr, fmt=None, desc=""):
    M.append((folder, name, expr, fmt, desc))


def colour(name, measure, higher_better=True):
    good, bad = (GREEN, RED) if higher_better else (RED, GREEN)
    add("99 Formatting", name, f'IF ( [{measure}] >= 0, "{good}", "{bad}" )', None, f"Font colour for {measure}.")


PY = "VAR last = [Last Data Date] RETURN CALCULATE ( {e}, SAMEPERIODLASTYEAR ( FILTER ( VALUES ( dim_date[date] ), dim_date[date] <= last ) ) )"


def py(folder, base, fmt=None, kind="pct", higher_better=True):
    """prior year (comparable months only) + change + colour"""
    add(folder, f"{base} PY", PY.format(e=f"[{base}]"), fmt, f"{base} in the same months of the prior year (only months with data in the current year).")
    if kind == "pct":
        chg = f"{base} YoY %"
        add(folder, chg, f"IF ( ISBLANK ( [{base} PY] ), BLANK (), DIVIDE ( [{base}] - [{base} PY], [{base} PY] ) )", PCT, f"Change of {base} vs prior year.")
    else:
        chg = f"{base} vs PY"
        add(folder, chg, f"IF ( ISBLANK ( [{base} PY] ), BLANK (), ( [{base}] - [{base} PY] ) * {100 if kind == 'pp' else 1} )",
            "+0.0\\ \\p\\p;-0.0\\ \\p\\p;0.0\\ \\p\\p" if kind == "pp" else "+#,0;-#,0;0",
            f"Change of {base} vs prior year" + (" (percentage points)." if kind == "pp" else "."))
    colour(f"{chg} Colour", chg, higher_better)


# ---------------------------------------------------------------- 00 Base
add("00 Base", "Last Data Date", "CALCULATE ( EOMONTH ( MAX ( mart_sales_monthly[month_start] ), 0 ), REMOVEFILTERS () )", "dd mmm yyyy",
    "Last day of the last month with sell-in data. Prior-year comparisons use the same months.")
add("00 Base", "Data As Of", 'FORMAT ( CALCULATE ( MAX ( run_log[ended_at] ), REMOVEFILTERS () ), "dd mmm yyyy", "en-US" )', None,
    "Last pipeline step logged in ops.run_log.")
add("99 Formatting", "Neutral Colour", f'"{GREY}"', None, "Neutral font colour.")

# ---------------------------------------------------------------- 01 Commercial
S = "mart_sales_monthly"
add("01 Commercial", "Net Sales", f"SUM ( {S}[net_sales_eur] )", "€#,0", "Net sales in EUR at daily ECB rates (reportable orders only).")
add("01 Commercial", "Net Sales (€m)", "DIVIDE ( [Net Sales], 1e6 )", EURM, "Net sales in EUR million.")
py("01 Commercial", "Net Sales", "€#,0")
add("01 Commercial", "Net Sales (€m) PY", "DIVIDE ( [Net Sales PY], 1e6 )", EURM, "Net sales of the prior year in EUR million.")
add("01 Commercial", "Net Sales CFX", f"SUM ( {S}[net_sales_cfx_eur] )", "€#,0", "Net sales at constant FX (local currency at the 2022 average ECB rate).")
add("01 Commercial", "Net Sales CFX PY", PY.format(e="[Net Sales CFX]"), "€#,0", "Net sales at constant FX, prior year.")
add("01 Commercial", "Volume (t)", f"SUM ( {S}[volume_t] )", "#,0", "Volume in tonnes (pack size valid on the order date).")
add("01 Commercial", "Volume (kt)", "DIVIDE ( [Volume (t)], 1000 )", "#,0.0\\ \\k\\t", "Volume in thousand tonnes.")
py("01 Commercial", "Volume (kt)", "#,0.0\\ \\k\\t")
add("01 Commercial", "Volume (t) PY", PY.format(e="[Volume (t)]"), "#,0", "Volume in tonnes, prior year.")
add("01 Commercial", "Reported Growth", "IF ( ISBLANK ( [Net Sales PY] ), BLANK (), DIVIDE ( [Net Sales], [Net Sales PY] ) - 1 )", PCT,
    "Net sales growth in EUR, including currency effects.")
add("01 Commercial", "Organic Growth", "IF ( ISBLANK ( [Net Sales CFX PY] ), BLANK (), DIVIDE ( [Net Sales CFX], [Net Sales CFX PY] ) - 1 )", PCT,
    "Growth at constant FX: real internal growth (volume) plus pricing.")
add("01 Commercial", "RIG", "IF ( ISBLANK ( [Volume (t) PY] ), BLANK (), DIVIDE ( [Volume (t)], [Volume (t) PY] ) - 1 )", PCT,
    "Real internal growth: volume growth in tonnes.")
add("01 Commercial", "Pricing", "IF ( ISBLANK ( [RIG] ), BLANK (), [Organic Growth] - [RIG] )", PCT, "Pricing contribution = organic growth - RIG.")
add("01 Commercial", "FX Effect", "IF ( ISBLANK ( [Organic Growth] ), BLANK (), [Reported Growth] - [Organic Growth] )", PCT,
    "Currency effect = reported growth - organic growth.")
for b in ["Organic Growth", "RIG", "Pricing"]:
    add("01 Commercial", f"{b} PY", PY.format(e=f"[{b}]"), PCT, f"{b} of the prior year.")
    colour(f"{b} Colour", b)
colour("Reported Growth Colour", "Reported Growth")
add("01 Commercial", "Gross Margin", f"DIVIDE ( [Net Sales] - SUM ( {S}[cogs_eur] ), [Net Sales] )", "0.0%", "Net sales minus standard cost, as a share of net sales.")
py("01 Commercial", "Gross Margin", "0.0%", kind="pp")
add("01 Commercial", "Bridge Value (€m)",
    "VAR s = SELECTEDVALUE ( bridge_step[step] ) VAR p = [Net Sales PY] RETURN IF ( ISBLANK ( p ), BLANK (), DIVIDE ( SWITCH ( s, "
    '"Net sales PY", p, "Volume (RIG)", p * [RIG], "Pricing", p * [Pricing], "FX", [Net Sales] - p * ( 1 + [Organic Growth] ) ), 1e6 ) )',
    EURM, "Organic growth bridge: prior-year net sales + volume + pricing + FX = current net sales (total bar).")
add("01 Commercial", "Net Sales Share", "DIVIDE ( [Net Sales], CALCULATE ( [Net Sales], ALLSELECTED ( dim_channel ) ) )", "0.0%",
    "Share of net sales among the selected channels.")

# ---------------------------------------------------------------- 02 Demand: forecast (test period, independent of the Year slicer)
FW = "forecast_weekly"
TEST = f"FILTER ( {FW}, NOT {FW}[is_future] )"
RD = "REMOVEFILTERS ( dim_date )"
add("02 Forecast", "Actual (t)", f"CALCULATE ( SUM ( {FW}[actual_t] ), NOT {FW}[is_future], {RD} )", "#,0", "Actual volume in tonnes, test period.")
add("02 Forecast", "Forecast (t)", f"CALCULATE ( SUM ( {FW}[forecast_t] ), {RD} )", "#,0", "Model forecast (HistGradientBoosting, MLflow), tonnes.")
add("02 Forecast", "Seasonal Naive (t)", f"CALCULATE ( SUM ( {FW}[baseline_t] ), {RD} )", "#,0", "Baseline: same week of the prior year, tonnes.")
add("02 Forecast", "Forecast Accuracy",
    f"VAR err = CALCULATE ( SUMX ( {TEST}, ABS ( {FW}[actual_t] - {FW}[forecast_t] ) ), {RD} ) RETURN IF ( ISBLANK ( [Actual (t)] ), BLANK (), 1 - DIVIDE ( err, [Actual (t)] ) )",
    "0.0%", "1 - WAPE on the test period (12 weeks), country x category x week.")
add("02 Forecast", "Baseline Accuracy",
    f"VAR err = CALCULATE ( SUMX ( {TEST}, ABS ( {FW}[actual_t] - {FW}[baseline_t] ) ), {RD} ) RETURN IF ( ISBLANK ( [Actual (t)] ), BLANK (), 1 - DIVIDE ( err, [Actual (t)] ) )",
    "0.0%", "1 - WAPE of the seasonal naive baseline.")
add("02 Forecast", "MAPE",
    f"CALCULATE ( AVERAGEX ( FILTER ( {FW}, NOT {FW}[is_future] && {FW}[actual_t] > 0 ), ABS ( {FW}[actual_t] - {FW}[forecast_t] ) / {FW}[actual_t] ), {RD} )",
    "0.0%", "Mean absolute percentage error, test period.")
add("02 Forecast", "Baseline MAPE",
    f"CALCULATE ( AVERAGEX ( FILTER ( {FW}, NOT {FW}[is_future] && {FW}[actual_t] > 0 ), ABS ( {FW}[actual_t] - {FW}[baseline_t] ) / {FW}[actual_t] ), {RD} )",
    "0.0%", "MAPE of the seasonal naive baseline.")
add("02 Forecast", "Bias",
    f"DIVIDE ( CALCULATE ( SUMX ( {TEST}, {FW}[forecast_t] - {FW}[actual_t] ), {RD} ), [Actual (t)] )", PCT,
    "Forecast minus actual as a share of actual (negative = under-forecast).")
add("02 Forecast", "Baseline Bias",
    f"DIVIDE ( CALCULATE ( SUMX ( {TEST}, {FW}[baseline_t] - {FW}[actual_t] ), {RD} ), [Actual (t)] )", PCT, "Bias of the seasonal naive baseline.")
add("99 Formatting", "Bias Colour", f'IF ( ABS ( [Bias] ) <= 0.05, "{GREEN}", "{ORANGE}" )', None, "Green when bias is within +/-5%.")

# ---------------------------------------------------------------- 03 Sell-out and promotions
SS = "mart_sellin_sellout_weekly"
UPTO = "VAR last = [Last Data Date] RETURN CALCULATE ( {e}, KEEPFILTERS ( dim_date[date] <= last ) )"
add("03 Sell-out", "Sell-out (k cases)", UPTO.format(e=f"DIVIDE ( SUM ( {SS}[sell_out_cases] ), 1000 )"), "#,0\\k", "Distributor sell-out in thousand cases (distributor files).")
py("03 Sell-out", "Sell-out (k cases)", "#,0\\k")
add("03 Sell-out", "Sell-in (k cases)", UPTO.format(e=f"DIVIDE ( SUM ( {SS}[sell_in_cases] ), 1000 )"), "#,0\\k", "Sell-in to distributors in thousand cases (ERP).")
add("03 Sell-out", "Sell-through", "DIVIDE ( [Sell-out (k cases)], [Sell-in (k cases)] )", "0.0%", "Sell-out as a share of sell-in.")
py("03 Sell-out", "Sell-through", "0.0%", kind="pp")
add("03 Sell-out", "Stock Cover (weeks)",
    f"VAR lastW = CALCULATE ( MAX ( {SS}[week_ending] ), NOT ISBLANK ( {SS}[stock_cases] ) ) "
    f"RETURN DIVIDE ( CALCULATE ( SUM ( {SS}[stock_cases] ), {SS}[week_ending] = lastW ), CALCULATE ( SUM ( {SS}[sell_out_4w_avg] ), {SS}[week_ending] = lastW ) )",
    "0.0", "Distributor stock at the last week of the period / average weekly sell-out of the last 4 weeks.")
add("03 Sell-out", "Stock Cover Top 12",
    f"IF ( RANKX ( ALLSELECTED ( {SS}[distributor_name] ), [Stock Cover (weeks)],, DESC ) <= 12, [Stock Cover (weeks)] )", "0.0",
    "Stock cover of the 12 distributors with the highest cover.")
add("03 Sell-out", "Network Stock Cover", f"CALCULATE ( [Stock Cover (weeks)], ALLSELECTED ( {SS}[distributor_name] ) )", "0.0",
    "Stock cover of all selected distributors together.")
add("99 Formatting", "Stock Cover Colour", f'IF ( [Stock Cover (weeks)] > 1.3 * [Network Stock Cover], "{RED}", "#005BA5" )', None,
    "Red when a distributor holds 30% more weeks of stock than the network (overstock risk).")
PP = "mart_promo_performance"
add("03 Sell-out", "Promo Uplift", f"DIVIDE ( SUM ( {PP}[promo_cases] ), SUM ( {PP}[baseline_cases] ) ) - 1", PCT,
    "Promotion volume vs baseline (average of the 8 weeks before the promotion).")
add("03 Sell-out", "Planned Uplift", f"DIVIDE ( AVERAGE ( {PP}[planned_uplift_pct] ), 100 )", PCT, "Average uplift planned by the key account managers.")
add("99 Formatting", "Promo Uplift Colour", f'IF ( [Promo Uplift] >= [Planned Uplift], "{GREEN}", "{ORANGE}" )', None, "Green when the uplift beats the plan.")

# ---------------------------------------------------------------- 04 Platform
RL, DQ, RC, PT = "run_log", "dq_results", "reconciliation_results", "platform_table_counts"
LAT = f"{RL}[is_latest_run] = TRUE ()"
add("04 Platform", "Pipeline Runs", f'CALCULATE ( DISTINCTCOUNT ( {RL}[run_id] ), {RL}[step] = "erp_snapshot", REMOVEFILTERS () )', "#,0",
    "Executions of the ingestion notebook (manual development run + Workflow job + ADF-triggered job).")
add("04 Platform", "Orchestration", '"Workflow + ADF"', None, "How the pipeline is orchestrated.")
add("04 Platform", "Rows Processed (M)", f'DIVIDE ( CALCULATE ( SUM ( {PT}[row_count] ), {PT}[layer] = "bronze", REMOVEFILTERS () ), 1e6 )', "#,0.0\\M",
    "Rows in the bronze layer (ERP extract, distributor files, public data, POS events), million.")
add("04 Platform", "Silver Rows (M)", f'DIVIDE ( CALCULATE ( SUM ( {PT}[row_count] ), {PT}[layer] = "silver", REMOVEFILTERS () ), 1e6 )', "#,0.0\\M",
    "Rows in the silver layer, million.")
add("04 Platform", "Delta Tables", f"CALCULATE ( COUNTROWS ( {PT} ), REMOVEFILTERS () )", "#,0", "Delta tables in bronze, silver and gold (Unity Catalog).")
add("04 Platform", "Gold Tables", f'CALCULATE ( COUNTROWS ( {PT} ), {PT}[layer] = "gold", REMOVEFILTERS () )', "#,0", "Tables in the gold layer.")
add("04 Platform", "Table Rows", f"SUM ( {PT}[row_count] )", "#,0", "Rows per Delta table.")
add("04 Platform", "Rows Top 12",
    f"IF ( RANKX ( ALL ( {PT}[table_label] ), CALCULATE ( [Table Rows], REMOVEFILTERS ( {PT}[layer] ) ),, DESC ) <= 12, [Table Rows] )", "#,0",
    "Row count of the 12 largest Delta tables.")
add("04 Platform", "Rows Top 12 (M)", "DIVIDE ( [Rows Top 12], 1e6 )", "#,0.00\\M", "Row count of the 12 largest Delta tables, million.")
add("04 Platform", "DQ Checks Total", f"CALCULATE ( COUNTROWS ( {DQ} ), {DQ}[is_latest_run] = TRUE (), REMOVEFILTERS () )", "#,0",
    "Data quality expectations evaluated in the latest pipeline run.")
add("04 Platform", "DQ Checks Failed", f'CALCULATE ( COUNTROWS ( {DQ} ), {DQ}[is_latest_run] = TRUE (), {DQ}[status] <> "PASS", REMOVEFILTERS () ) + 0', "#,0",
    "Failed expectations in the latest run.")
add("04 Platform", "DQ Checks Passed", 'FORMAT ( [DQ Checks Total] - [DQ Checks Failed], "0" ) & " / " & FORMAT ( [DQ Checks Total], "0" )', None,
    "Passed vs total expectations in the latest run.")
add("99 Formatting", "DQ Failed Colour", f'IF ( [DQ Checks Failed] > 0, "{ORANGE}", "{GREEN}" )', None, "Font colour.")
add("04 Platform", "Recon Checks", f"CALCULATE ( COUNTROWS ( {RC} ), {RC}[is_latest_run] = TRUE (), REMOVEFILTERS () )", "#,0",
    "Reconciliation checks Azure SQL vs Delta in the latest run (counts, hashes, business totals).")
add("04 Platform", "Recon Checks Passed (n)", f'CALCULATE ( COUNTROWS ( {RC} ), {RC}[is_latest_run] = TRUE (), {RC}[status] = "PASS", REMOVEFILTERS () ) + 0', "#,0",
    "Passed reconciliation checks in the latest run.")
add("04 Platform", "Recon Checks Passed", 'FORMAT ( [Recon Checks Passed (n)], "0" ) & " / " & FORMAT ( [Recon Checks], "0" )', None,
    "Passed vs total reconciliation checks.")
add("04 Platform", "Recon Pass Rate", "DIVIDE ( [Recon Checks Passed (n)], [Recon Checks] )", "0.0%", "Share of reconciliation checks that passed.")
add("99 Formatting", "Recon Colour", f'IF ( [Recon Pass Rate] = 1, "{GREEN}", "{RED}" )', None, "Font colour.")
add("04 Platform", "Recon Difference", f"CALCULATE ( SUMX ( {RC}, ABS ( {RC}[difference] ) ), {RC}[is_latest_run] = TRUE (), REMOVEFILTERS () ) + 0", "#,0",
    "Sum of absolute differences between Azure SQL and Delta in the latest reconciliation.")
add("04 Platform", "Last Run Start", f'FORMAT ( CALCULATE ( MIN ( {RL}[started_at] ), {LAT}, REMOVEFILTERS () ), "dd mmm, hh:nn", "en-US" ) & " UTC"', None,
    "Start of the latest pipeline run.")
add("04 Platform", "Last Run Duration",
    f"VAR s = CALCULATE ( MIN ( {RL}[started_at] ), {LAT}, REMOVEFILTERS () ) VAR e = CALCULATE ( MAX ( {RL}[ended_at] ), {LAT}, REMOVEFILTERS () ) "
    'VAR sec = DATEDIFF ( s, e, SECOND ) RETURN INT ( sec / 60 ) & " min " & FORMAT ( MOD ( sec, 60 ), "00" ) & " s"', None,
    "Time from the first to the last logged step of the latest run (10 serverless tasks).")


def write(path: Path):
    s = f"table _Measures\n\tlineageTag: {tag('table')}\n\n"
    for folder, name, expr, fmt, desc in M:
        s += f"\t/// {desc}\n\tmeasure '{name}' = {expr}\n"
        if fmt:
            s += f"\t\tformatString: {fmt}\n"
        s += f"\t\tdisplayFolder: {folder}\n\t\tlineageTag: {tag(name)}\n\n"
    s += ('\tpartition _Measures = m\n\t\tmode: import\n\t\tsource =\n\t\t\t\tlet\n'
          '\t\t\t\t  Source = Table.FromRows(Json.Document(Binary.Decompress(Binary.FromText("i44FAA==", BinaryEncoding.Base64), Compression.Deflate)), let _t = ((type nullable text) meta [Serialized.Text = true]) in type table [Column1 = _t]),\n'
          '\t\t\t\t    #"Removed Columns" = Table.RemoveColumns(Source,{"Column1"})\n\t\t\t\tin\n\t\t\t\t  #"Removed Columns"\n\n'
          '\tannotation PBI_NavigationStepName = Navigation\n\n\tannotation PBI_ResultType = Table\n\n')
    path.write_text(s, encoding="utf-8")
    names = [x[1] for x in M]
    assert len(names) == len(set(names)), "duplicate measure"
    return names


if __name__ == "__main__":
    names = write(ROOT / "out" / "Nestle_FMCG_Lakehouse.SemanticModel" / "definition" / "tables" / "_Measures.tmdl")
    print(len(names), "measures")
