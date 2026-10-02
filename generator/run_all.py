"""Generate the full synthetic dataset.

    python generator/download_public.py   # real public data first (FX, food inflation, weather)
    python generator/run_all.py           # synthetic ERP, distributor files, POS stream

Outputs under data/raw/ (git-ignored):
    erp/<table>.parquet  and  erp/<table>/year=YYYY/part-0.parquet  (legacy ERP, loaded into Azure SQL later)
    sellout/<distributor>/*.csv|*.json                                (dirty distributor files)
    pos_stream/date=YYYY-MM-DD/*.jsonl                                (simulated event stream)
    manifest.json                                                     (row counts, used by the reconciliation)
"""
import json
import shutil
import time

import numpy as np
import pandas as pd

import gen_master as gm
import gen_pos
import gen_sales
import gen_sellout
from config import ERP, POS, RAW, SEED, SELLOUT
from public_data import USED_FALLBACK

MANIFEST: dict[str, int] = {}


def writer(table: str, df: pd.DataFrame, year: int | None) -> None:
    if year is None:
        df.to_parquet(ERP / f"{table}.parquet", index=False)
    else:
        folder = ERP / table / f"year={year}"; folder.mkdir(parents=True, exist_ok=True)
        df.to_parquet(folder / "part-0.parquet", index=False)
    MANIFEST[table] = MANIFEST.get(table, 0) + len(df)


def main() -> None:
    t0 = time.time()
    for d in (ERP, SELLOUT, POS):
        shutil.rmtree(d, ignore_errors=True); d.mkdir(parents=True)
    rng = np.random.default_rng(SEED)

    print("Master data ...")
    prods = gm.products(rng)
    custs = gm.customers(rng)
    assort, alen = gm.assortments(rng, prods, custs)
    prices = gm.price_list(rng, prods)
    custs_cur, cust_log = gm.customer_changes(rng, custs)
    prods_cur, prod_log = gm.product_changes(rng, prods)
    writer("countries", gm.countries(), None)
    writer("products", prods_cur.drop(columns=["popularity", "seasonal", "cost_ratio", "base_price_eur"]), None)
    writer("customers", custs_cur.drop(columns=["size_factor"]), None)
    writer("price_list", prices, None)
    writer("standard_cost", gm.standard_cost(prods), None)
    writer("customer_changes", cust_log, None)
    writer("product_changes", prod_log, None)

    print("Sell-in (orders, lines, promotions, returns) ...")
    dist = gen_sales.generate(rng, custs, prods, assort, alen, prices, writer)

    print("Distributor sell-out files ...")
    promos = pd.read_parquet(ERP / "promotions.parquet")
    so = gen_sellout.build(rng, custs, prods, dist, promos)
    MANIFEST["sellout_rows_clean"] = len(so)
    MANIFEST["sellout_files"] = gen_sellout.write_files(rng, custs, prods, so)

    print("POS event stream ...")
    MANIFEST["pos_events"] = gen_pos.write(rng, custs, prods, assort, alen, prices)

    MANIFEST["fallback_used"] = USED_FALLBACK
    (RAW / "manifest.json").write_text(json.dumps(MANIFEST, indent=2))
    print(json.dumps(MANIFEST, indent=2))
    if USED_FALLBACK:
        print(f"WARNING: synthetic fallback used for {USED_FALLBACK}. Run download_public.py first for real data.")
    print(f"Done in {time.time() - t0:,.0f} s")


if __name__ == "__main__":
    main()
