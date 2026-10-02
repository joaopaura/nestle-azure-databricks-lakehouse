"""Simulated POS / e-commerce event stream (JSON lines), 1 Aug to 30 Sep 2026, 4 micro-batch files per day.
Includes duplicates, late-arriving events and a schema change on 15 Sep (new field `device`) for Auto Loader demos."""
import datetime as dt
import json
import uuid

import numpy as np
import pandas as pd

from config import COUNTRIES, END, POS, POS_START


def write(rng, custs: pd.DataFrame, prods: pd.DataFrame, assort: np.ndarray, alen: np.ndarray, prices: pd.DataFrame) -> int:
    POS.mkdir(parents=True, exist_ok=True)
    ecom = custs.index[custs["channel"] == "E-commerce"].to_numpy()
    last = prices[prices["valid_from"] <= pd.Timestamp(POS_START)].sort_values("valid_from").groupby(["sku", "country_code"]).tail(1)
    price = last.set_index(["sku", "country_code"])["list_price_case"]
    upc = prods.set_index("sku")["units_per_case"]
    late, total, day = [], 0, POS_START
    while day <= END:
        n = rng.poisson(custs.loc[ecom, "size_factor"].to_numpy() * 35)
        ev = []
        for ci, k in zip(ecom, n):
            c = custs.at[ci, "country_code"]
            pos = (rng.random(k) * alen[ci]).astype(int)
            for p in assort[ci, pos]:
                sku = int(prods.at[p, "sku"])
                unit = price.get((sku, c), 10.0) / upc[sku] * 1.3
                ts = dt.datetime.combine(day, dt.time()) + dt.timedelta(seconds=int(rng.integers(0, 86400)))
                e = {"event_id": str(uuid.UUID(int=int(rng.integers(0, 2**63)) << 64 | int(rng.integers(0, 2**63)))),
                     "event_type": "return" if rng.random() < 0.05 else "purchase",
                     "event_ts": ts.isoformat() + "Z", "retailer_id": custs.at[ci, "customer_id"], "country": c,
                     "ean": prods.at[p, "ean"], "quantity": int(rng.choice([1, 1, 1, 2, 2, 3, 4])),
                     "unit_price": round(float(unit), 2), "currency": COUNTRIES[c][1]}
                if day >= dt.date(2026, 9, 15):
                    e["device"] = rng.choice(["web", "ios", "android"])
                ev.append(e)
        ev.sort(key=lambda e: e["event_ts"])
        dups = [ev[i] for i in np.where(rng.random(len(ev)) < 0.005)[0]]
        is_late = rng.random(len(ev)) < 0.01
        today = [e for e, l in zip(ev, is_late) if not l] + late + dups
        late = [e for e, l in zip(ev, is_late) if l]
        folder = POS / f"date={day}"; folder.mkdir(exist_ok=True)
        for b, chunk in enumerate(np.array_split(np.array(today, dtype=object), 4)):
            (folder / f"events_{day:%Y%m%d}_{b + 1:02d}.jsonl").write_text(
                "\n".join(json.dumps(e, ensure_ascii=False) for e in chunk), encoding="utf-8")
        total += len(today); day += dt.timedelta(days=1)
    return total
