"""Sanity checks and business-story checks on the generated data.   python generator/validate.py"""
import json

import numpy as np
import pandas as pd

from config import COUNTRIES, ERP, PUBLIC, RAW, SELLOUT

pd.set_option("display.width", 160); pd.set_option("display.max_columns", 20)
ok = lambda cond, msg: print(("  PASS " if cond else "  FAIL ") + msg)

m = json.loads((RAW / "manifest.json").read_text())
print(f"Rows: {sum(v for v in m.values() if isinstance(v, int)):,} | fallback used: {m['fallback_used'] or 'none (real public data)'}")

prods = pd.read_parquet(ERP / "products.parquet")
custs = pd.read_parquet(ERP / "customers.parquet")
orders = pd.read_parquet(ERP / "sales_orders", columns=["order_id", "customer_id", "order_date", "currency", "order_status", "is_deleted"])
lines = pd.read_parquet(ERP / "sales_order_lines", columns=["order_id", "sku", "qty_cases", "net_amount", "promo_id"])
log = pd.read_parquet(ERP / "product_changes.parquet")

# weight per case with shrinkflation history (SCD2 style)
w = prods.set_index("sku")["case_weight_kg"]
df = lines.merge(orders[(orders["order_status"] != "Cancelled") & (~orders["is_deleted"])], on="order_id")
df = df.merge(custs[["customer_id", "country_code"]], on="customer_id").merge(prods[["sku", "category"]], on="sku")
df["kg"] = df["qty_cases"] * df["sku"].map(w)
for _, r in log.iterrows():                                       # before the change the pack was ~11% heavier
    mask = (df["sku"] == r["sku"]) & (df["order_date"] < r["changed_at"])
    df.loc[mask, "kg"] /= 0.9
ref = {c: v[6] for c, v in COUNTRIES.items()}
df["sales_const_eur"] = df["net_amount"] / df["country_code"].map(ref)
df["year"] = df["order_date"].dt.year
df["ytd"] = df["order_date"].dt.dayofyear <= pd.Timestamp("2026-09-30").dayofyear

fx_file = PUBLIC / "fx_rates_daily.csv"
if fx_file.exists():
    fx = pd.read_csv(fx_file, parse_dates=["rate_date"])
    fxm = fx.assign(y=fx["rate_date"].dt.year).groupby(["currency", "y"])["rate_per_eur"].mean()
    rate = [1.0 if cur == "EUR" else fxm.get((cur, y), np.nan) for cur, y in zip(df["currency"], df["year"])]
    df["sales_eur"] = df["net_amount"] / np.array(rate)
else:
    df["sales_eur"] = df["sales_const_eur"]

print("\n1) Group P&L, YTD Jan to Sep (constant FX = organic)")
y = df[df["ytd"]].groupby("year").agg(sales_eur=("sales_eur", "sum"), sales_const=("sales_const_eur", "sum"), tonnes=("kg", "sum"))
y["tonnes"] /= 1000
y["OG %"] = y["sales_const"].pct_change() * 100
y["RIG %"] = y["tonnes"].pct_change() * 100
y["Pricing %"] = y["OG %"] - y["RIG %"]
y["Reported %"] = y["sales_eur"].pct_change() * 100
print((y / [1e6, 1e6, 1, 1, 1, 1, 1]).round(1).to_string())
ok(y.loc[2023, "Pricing %"] > 4 and y.loc[2023, "RIG %"] < 0, "story 1: pricing drives 2023, volume negative")
ok(y.loc[2026, "RIG %"] > 0, "story 1: volume recovers in 2026")

print("\n2) Organic growth 2025 vs 2024 by category and country (%)")
a = df.groupby(["year", "category"])["sales_const_eur"].sum().unstack(0)
cat = (a[2025] / a[2024] - 1) * 100
print(cat.round(1).sort_values(ascending=False).to_string())
ok(set(cat.sort_values(ascending=False).index[:2]) == {"Coffee", "Pet Care"}, "story 2: Coffee and Pet Care lead growth")
b = df.groupby(["year", "country_code"])["kg"].sum().unstack(0)
ctry = (b[2025] / b[2024] - 1) * 100
print("  RIG by country:", ctry.round(1).sort_values(ascending=False).to_dict())
ok(set(ctry.sort_values(ascending=False).index[:2]) == {"PL", "ES"}, "story 3: Poland and Spain grow fastest")

print("\n3) Water vs temperature")
wf = PUBLIC / "weather_daily.csv"
if wf.exists():
    wd = pd.read_csv(wf, parse_dates=["weather_date"])
    wd["week"] = wd["weather_date"].dt.to_period("W")
    t = wd.groupby(["country_code", "week"])["temperature_2m_mean"].mean()
    wa = df[df["category"] == "Water"].assign(week=lambda x: x["order_date"].dt.to_period("W")).groupby(["country_code", "week"])["kg"].sum()
    j = pd.concat([t, wa], axis=1, join="inner")
    corr = j.groupby(level=0).corr().xs("kg", level=1)["temperature_2m_mean"]
    print("  correlation per country:", corr.round(2).to_dict())
    ok(corr.mean() > 0.4, "story 2: water sales follow temperature")
else:
    print("  (weather file missing, skipped)")

print("\n4) Data quality traps in the ERP")
print(f"  cancelled orders {(orders['order_status'] == 'Cancelled').sum():,} | soft-deleted {orders['is_deleted'].sum():,} | "
      f"promo lines {lines['promo_id'].notna().mean():.1%}")
files = list(SELLOUT.rglob("*.*"))
print(f"  sell-out files {len(files):,} ({sum(f.suffix == '.csv' for f in files):,} csv, {sum(f.suffix == '.json' for f in files):,} json)")
ok(len(files) > 1000, "dirty distributor files written")

print("\n5) Story 4: Polish distributor overstock before the December 2025 promotion")
pl = custs[custs["is_distributor"] & (custs["country_code"] == "PL")]["customer_id"]
s = df[df["customer_id"].isin(pl)].groupby(["customer_id", df["order_date"].dt.to_period("M")])["qty_cases"].sum()
top = s.groupby(level=0).sum().idxmax()
t = s.loc[top]; t.index = t.index.astype(str)
spike = t[["2025-10", "2025-11"]].mean() / t[[f"2025-0{m}" for m in range(1, 10)]].mean()
print(f"  {top}: Oct to Nov 2025 sell-in = {spike:.1f}x the Jan to Sep 2025 monthly average")
ok(spike > 2, "story 4: sell-in spike at the overstocking distributor")
