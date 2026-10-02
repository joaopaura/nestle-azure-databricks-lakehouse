"""Distributor sell-out files (dirty on purpose): one file per distributor per month, three different layouts."""
import json

import numpy as np
import pandas as pd

from config import OVERSTOCK_FACTOR, OVERSTOCK_WEEKS, SELLOUT
from public_data import N_WEEKS, WEEKS

SPELLINGS = {"DE": ["Germany", "Deutschland", "DE", "GER"], "FR": ["France", "FR", "FRA"], "GB": ["United Kingdom", "UK", "GB", "Great Britain"],
             "IT": ["Italy", "Italia", "IT"], "ES": ["Spain", "España", "ES", "Espana"], "PL": ["Poland", "Polska", "PL", "POL"],
             "NL": ["Netherlands", "Nederland", "NL", "Holland"], "CH": ["Switzerland", "Schweiz", "CH", "Suisse"],
             "BE": ["Belgium", "Belgique", "BE"], "PT": ["Portugal", "PT"], "AT": ["Austria", "Österreich", "AT"], "SE": ["Sweden", "Sverige", "SE"]}


def build(rng, custs: pd.DataFrame, prods: pd.DataFrame, dist_sellin: pd.DataFrame, promos: pd.DataFrame) -> pd.DataFrame:
    """Clean weekly sell-out + closing stock per distributor x product (the 'truth' before dirt is added)."""
    d = dist_sellin.copy()
    over_ci = custs[(custs["is_distributor"]) & (custs["country_code"] == "PL")]["size_factor"].idxmax()
    ow0, ow1 = np.searchsorted(WEEKS, pd.Timestamp(OVERSTOCK_WEEKS[0])), np.searchsorted(WEEKS, pd.Timestamp(OVERSTOCK_WEEKS[1]))
    pairs = d[["cust_idx", "p"]].drop_duplicates().reset_index(drop=True)
    pairs["k"] = np.arange(len(pairs))
    d = d.merge(pairs, on=["cust_idx", "p"])
    G = np.zeros((len(pairs), N_WEEKS)); G[d["k"], d["week"]] = d["qty"]
    base = G.copy()
    ov = (pairs["cust_idx"] == over_ci).to_numpy()
    base[np.ix_(ov, np.arange(ow0, ow1))] /= OVERSTOCK_FACTOR                       # consumer demand did not change
    kern = np.ones(6) / 6
    smooth = np.apply_along_axis(lambda x: np.convolve(x, kern, mode="same"), 1, base)
    sell = np.roll(smooth, 1, axis=1) * rng.normal(0.97, 0.08, smooth.shape)
    pw = np.searchsorted(WEEKS, pd.Timestamp("2025-12-01"))
    sell[np.ix_(ov, np.arange(pw, pw + 3))] *= 1.6                                  # promotion lifts consumer sales
    sell = np.maximum(np.round(sell), 0)
    stock = np.maximum(4 * smooth[:, :1] + np.cumsum(G - sell, axis=1), 0)
    cell = np.nonzero(sell + G)
    out = pd.DataFrame({"cust_idx": pairs["cust_idx"].to_numpy()[cell[0]], "p": pairs["p"].to_numpy()[cell[0]],
                        "week": cell[1], "qty_cases": sell[cell], "stock_cases": np.round(stock[cell])})
    out["week_ending"] = (WEEKS[out["week"]] + pd.Timedelta(days=6)).date
    return out


def write_files(rng, custs: pd.DataFrame, prods: pd.DataFrame, so: pd.DataFrame) -> int:
    SELLOUT.mkdir(parents=True, exist_ok=True)
    so = so.copy()
    so["customer_id"] = custs["customer_id"].to_numpy()[so["cust_idx"]]
    so["country_code"] = custs["country_code"].to_numpy()[so["cust_idx"]]
    so["ean"] = prods["ean"].to_numpy()[so["p"]]
    so["desc"] = prods["product_name"].to_numpy()[so["p"]]
    upc = prods["units_per_case"].to_numpy()[so["p"]]
    dists = sorted(so["customer_id"].unique())
    layout = {c: ("A" if i % 10 < 7 else "B" if i % 10 < 9 else "J") for i, c in enumerate(dists)}
    reports_units = {c: (i % 3 == 0) for i, c in enumerate(dists)}                 # a third of distributors report units
    so["month"] = pd.to_datetime(so["week_ending"]).dt.strftime("%Y-%m")
    n_files = 0
    for (cid, month), g in so.groupby(["customer_id", "month"], sort=False):
        g = g.copy()
        units = reports_units[cid]
        qty = g["qty_cases"].to_numpy() * (upc[g.index] if units else 1)
        stock = g["stock_cases"].to_numpy() * (upc[g.index] if units else 1)
        uom = np.where(units, rng.choice(["EA", "pcs", "units"]), rng.choice(["CS", "cases", "CSE"]))
        ctry = rng.choice(SPELLINGS[g["country_code"].iloc[0]], len(g))
        ean = g["ean"].astype(str).to_numpy().copy()
        r = rng.random(len(g))
        ean = np.where(r < 0.004, [f"{float(e):.5E}" for e in ean], ean)            # Excel scientific notation
        ean = np.where((r >= 0.004) & (r < 0.008), [e[:4] + " " + e[4:] for e in ean], ean)
        ean = np.where((r >= 0.008) & (r < 0.010), "4000000" + rng.integers(100000, 999999, len(g)).astype(str), ean)  # not ours
        qty = np.where(rng.random(len(g)) < 0.003, -qty, qty)                       # corrections
        wk = pd.to_datetime(g["week_ending"])
        lay = layout[cid]
        if lay == "A":
            dates = wk.dt.strftime("%d.%m.%Y").to_numpy()
            q = np.array([f"{x:,.0f}".replace(",", ".") for x in qty], dtype=object)
            q = np.where(rng.random(len(g)) < 0.002, "n/a", q)
            df = pd.DataFrame({"Distributor": cid, "Week_Ending": dates, "EAN": ean, "Product_Desc": g["desc"].to_numpy(),
                               "Qty_Sold": q, "UoM": uom, "Closing_Stock": [f"{x:.1f}".replace(".", ",") for x in stock], "Country": ctry})
        elif lay == "B":
            dates = wk.dt.strftime("%Y-%m-%d").to_numpy()
            dates = np.where(rng.random(len(g)) < 0.002, "", dates)
            df = pd.DataFrame({"distributor_id": cid.lower().replace("c", "c-"), "week_end_date": dates, "gtin": ean,
                               "description": g["desc"].to_numpy(), "units_sold": qty, "unit": uom, "stock_on_hand": stock,
                               "country": ctry})
        else:
            dates = wk.dt.strftime("%m/%d/%Y").to_numpy()
            df = pd.DataFrame({"dist": cid, "period_end": dates, "barcode": ean, "sold": qty, "uom": uom, "stock": stock, "market": ctry})
        dup = rng.random(len(df)) < 0.01
        df = pd.concat([df, df[dup]], ignore_index=True)                            # duplicates (resent rows)
        folder = SELLOUT / cid; folder.mkdir(exist_ok=True)
        if lay == "A":
            df.to_csv(folder / f"sellout_{cid}_{month}.csv", sep=";", index=False, encoding="utf-8")
        elif lay == "B":
            df.to_csv(folder / f"{cid.lower()}_{month.replace('-', '')}.csv", index=False)
        else:
            (folder / f"sellout_{month}.json").write_text(json.dumps(
                {"distributor": cid, "generated_at": f"{month}-28T23:00:00Z", "records": df.to_dict(orient="records")},
                default=float, ensure_ascii=False), encoding="utf-8")
        n_files += 1
    return n_files
