"""Builds the Nestle semantic model (TMDL) from the Power BI Desktop template:
date table, helper dimensions, calculated columns, relationships, formats and the _Measures table."""
import re, uuid, shutil, sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "/home/claude/nb")
NAME = "Nestle_FMCG_Lakehouse"
SRC = ROOT / "tpl" / f"{NAME}.SemanticModel"
OUT = ROOT / "out" / f"{NAME}.SemanticModel"
tag = lambda *k: str(uuid.uuid5(uuid.NAMESPACE_URL, "nestle-model/" + "/".join(k)))

shutil.rmtree(OUT, ignore_errors=True)
shutil.copytree(SRC, OUT, ignore=shutil.ignore_patterns("cache.abf"))
D = OUT / "definition"
T = D / "tables"


def edit_col(s, col, add=None, replace=None):
    pat = re.compile(rf"(\tcolumn {re.escape(col)}\n)(.*?)(?=\n\t(?:column|partition|measure|annotation)|\Z)", re.S)
    mm = pat.search(s)
    assert mm, col
    block = mm.group(2)
    if replace:
        block = block.replace(*replace)
    if add:
        block = re.sub(r"(\t\tdataType: [^\n]+\n)", lambda x: x.group(1) + "".join(f"\t\t{a}\n" for a in add), block, count=1)
    return s[:mm.start(2)] + block + s[mm.end(2):]


def rw(name, fn):
    f = T / f"{name}.tmdl"
    f.write_text(fn(f.read_text(encoding="utf-8")), encoding="utf-8")


# ---------------------------------------------------------------- 1. no implicit sums on dimensions and ops tables
for n in ["dim_date", "dim_country", "dim_product", "dim_customer", "run_log", "dq_results", "reconciliation_results",
          "platform_table_counts", "forecast_accuracy"]:
    rw(n, lambda s: s.replace("summarizeBy: sum", "summarizeBy: none"))


# ---------------------------------------------------------------- 2. date table
def date_tbl(s):
    s = s.replace("table dim_date\n\tlineageTag:", "table dim_date\n\tdataCategory: Time\n\tlineageTag:", 1)
    s = edit_col(s, "date", add=["isKey"], replace=("formatString: Long Date", "formatString: dd mmm yyyy"))
    s = edit_col(s, "month_start", replace=("formatString: Long Date", "formatString: mmm yyyy"))
    s = edit_col(s, "week_start", replace=("formatString: Long Date", "formatString: dd mmm yyyy"))
    s = edit_col(s, "month_name", add=["sortByColumn: month"])
    return s


rw("dim_date", date_tbl)
for n, cols in {"forecast_weekly": ["week_start"], "mart_sellin_sellout_weekly": ["week_ending"], "mart_sales_monthly": ["month_start"]}.items():
    for c in cols:
        rw(n, lambda s, c=c: edit_col(s, c, replace=("formatString: Long Date", "formatString: dd mmm yyyy")))

# ---------------------------------------------------------------- 3. hide keys on facts
HIDE = {"mart_sales_monthly": ["country_code", "sku", "category", "channel", "month_start"],
        "mart_sellin_sellout_weekly": ["country_code", "category", "week_ending"],
        "mart_promo_performance": ["country_code", "category", "channel", "customer_id", "start_date"],
        "mart_demand_weekly": ["country_code", "category", "week_start"],
        "forecast_weekly": ["country_code", "category"],
        "mart_pos_daily": ["country", "category", "event_date"]}
for n, cols in HIDE.items():
    for c in cols:
        rw(n, lambda s, c=c: edit_col(s, c, add=["isHidden"]))


# ---------------------------------------------------------------- 4. calculated columns
def calc_col(table, name, expr, dtype="boolean", fmt=None, hidden=False):
    def f(s):
        block = f"\tcolumn {name} = {expr}\n\t\tdataType: {dtype}\n" + (f"\t\tformatString: {fmt}\n" if fmt else "") + \
                ("\t\tisHidden\n" if hidden else "") + \
                f"\t\tlineageTag: {tag(table, name)}\n\t\tsummarizeBy: none\n\n\t\tannotation SummarizationSetBy = Automatic\n\n"
        return s.replace("\tpartition ", block + "\tpartition ", 1)
    rw(table, f)


BOOL = '"""TRUE"";""TRUE"";""FALSE"""'
BATCH = ('VAR lastBronze = MAXX ( FILTER ( ALL ( run_log[layer], run_log[started_at] ), run_log[layer] = "bronze" ), run_log[started_at] ) '
         'VAR batchStart = MINX ( FILTER ( ALL ( run_log[layer], run_log[started_at] ), run_log[layer] = "bronze" && run_log[started_at] >= lastBronze - 15 / 1440 ), run_log[started_at] ) ')
calc_col("run_log", "is_latest_run", BATCH + "RETURN run_log[started_at] >= batchStart", fmt=BOOL)
calc_col("dq_results", "is_latest_run", BATCH + "RETURN dq_results[checked_at] >= batchStart", fmt=BOOL)
calc_col("reconciliation_results", "is_latest_run",
         "VAR lastRun = CONCATENATEX ( TOPN ( 1, ALL ( reconciliation_results[run_id], reconciliation_results[checked_at] ), "
         "reconciliation_results[checked_at], DESC ), reconciliation_results[run_id] ) RETURN reconciliation_results[run_id] = lastRun", fmt=BOOL)
calc_col("platform_table_counts", "table_label", 'platform_table_counts[layer] & "." & platform_table_counts[table_name]', dtype="string")
calc_col("dq_results", "failed_share", "DIVIDE ( dq_results[failed_pct], 100 )", dtype="double", fmt="0.00%")


# ---------------------------------------------------------------- 5. calculated tables
def calc_table(name, source, cols, sort=None, hidden=()):
    s = f"table {name}\n\tlineageTag: {tag(name)}\n\n"
    for c, dt in cols:
        s += f"\tcolumn {c}\n\t\tdataType: {dt}\n" + ("\t\tisHidden\n" if c in hidden else "") + \
             f"\t\tlineageTag: {tag(name, c)}\n\t\tsummarizeBy: none\n\t\tsourceColumn: [{c}]\n" + \
             (f"\t\tsortByColumn: {sort[1]}\n" if sort and sort[0] == c else "") + "\n\t\tannotation SummarizationSetBy = Automatic\n\n"
    s += f"\tpartition {name} = calculated\n\t\tmode: import\n\t\tsource = {source}\n\n\tannotation PBI_Id = {uuid.uuid5(uuid.NAMESPACE_URL, name).hex}\n\n"
    (T / f"{name}.tmdl").write_text(s, encoding="utf-8")


calc_table("dim_category", 'DISTINCT ( SELECTCOLUMNS ( dim_product, "category", dim_product[category] ) )', [("category", "string")])
calc_table("dim_channel", 'DISTINCT ( SELECTCOLUMNS ( dim_customer, "channel", dim_customer[channel] ) )', [("channel", "string")])
calc_table("bridge_step", 'DATATABLE ( "step", STRING, "step_order", INTEGER, { { "Net sales PY", 1 }, { "Volume (RIG)", 2 }, { "Pricing", 3 }, { "FX", 4 } } )',
           [("step", "string"), ("step_order", "int64")], sort=("step", "step_order"), hidden=("step_order",))

# ---------------------------------------------------------------- 6. relationships
REL = [("mart_sales_monthly", "month_start", "dim_date", "date"), ("mart_sales_monthly", "country_code", "dim_country", "country_code"),
       ("mart_sales_monthly", "sku", "dim_product", "sku"), ("mart_sales_monthly", "category", "dim_category", "category"),
       ("mart_sales_monthly", "channel", "dim_channel", "channel"),
       ("mart_sellin_sellout_weekly", "week_ending", "dim_date", "date"), ("mart_sellin_sellout_weekly", "country_code", "dim_country", "country_code"),
       ("mart_sellin_sellout_weekly", "category", "dim_category", "category"),
       ("mart_promo_performance", "start_date", "dim_date", "date"), ("mart_promo_performance", "country_code", "dim_country", "country_code"),
       ("mart_promo_performance", "category", "dim_category", "category"), ("mart_promo_performance", "channel", "dim_channel", "channel"),
       ("mart_demand_weekly", "week_start", "dim_date", "date"), ("mart_demand_weekly", "country_code", "dim_country", "country_code"),
       ("mart_demand_weekly", "category", "dim_category", "category"),
       ("forecast_weekly", "week_start", "dim_date", "date"), ("forecast_weekly", "country_code", "dim_country", "country_code"),
       ("forecast_weekly", "category", "dim_category", "category"),
       ("mart_pos_daily", "event_date", "dim_date", "date"), ("mart_pos_daily", "country", "dim_country", "country_code"),
       ("mart_pos_daily", "category", "dim_category", "category"),
       ("dim_customer", "country_code", "dim_country", "country_code")]
r = ""
for ft, fc, tt, tc in REL:
    r += f"relationship {tag('rel', ft, fc)}\n\tfromColumn: {ft}.{fc}\n\ttoColumn: {tt}.{tc}\n\n"
(D / "relationships.tmdl").write_text(r, encoding="utf-8")

# ---------------------------------------------------------------- 7. model refs
m = (D / "model.tmdl").read_text(encoding="utf-8")
new = ["dim_category", "dim_channel", "bridge_step", "_Measures"]
m = m.replace("ref table reconciliation_results", "ref table reconciliation_results\n" + "\n".join(f"ref table {t}" for t in new))
m = m.replace('"reconciliation_results"]', '"reconciliation_results","_Measures"]')
(D / "model.tmdl").write_text(m, encoding="utf-8")
print("model ok")
