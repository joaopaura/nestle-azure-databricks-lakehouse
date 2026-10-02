"""Sell-in transactions for the legacy ERP: promotions, sales orders, order lines, returns.
Fully vectorised with numpy and written year by year (Parquet) to keep memory low."""
import datetime as dt

import numpy as np
import pandas as pd

from config import (CATEGORIES, COUNTRIES, END, LINES_PER_ORDER, ORDERS_PER_WEEK, OVERSTOCK_FACTOR, OVERSTOCK_WEEKS,
                    RIG_CATEGORY, RIG_COUNTRY, RIG_YEAR)
from public_data import N_WEEKS, WEEKS, price_rounds, weekly_temperature

CC = list(COUNTRIES)
CATS = list(CATEGORIES)
EASTER = {2022: "2022-04-17", 2023: "2023-04-09", 2024: "2024-03-31", 2025: "2025-04-20", 2026: "2026-04-05"}
TRADE_DISC = {"Modern trade": (0.08, 0.15), "Traditional trade": (0.05, 0.10), "E-commerce": (0.05, 0.08), "Out-of-home": (0.0, 0.05)}
MECHANICS = np.array(["Temporary price reduction", "Multibuy", "Display + feature", "Loyalty coupon"])
BASE_QTY = 3.0


def demand_factors() -> np.ndarray:
    """F[country, category, week]: trend (RIG) x seasonality x weather."""
    temp = weekly_temperature()                                   # (country, week)
    years = WEEKS.year.to_numpy(); woy = WEEKS.isocalendar().week.to_numpy().astype(int)
    F = np.ones((len(CC), len(CATS), N_WEEKS))
    for ci, c in enumerate(CC):
        for ki, k in enumerate(CATS):
            g = np.array([RIG_YEAR[y] + RIG_CATEGORY[k] + RIG_COUNTRY[c] for y in years]) / 100
            trend = np.cumprod((1 + g) ** (1 / 52))
            s = np.ones(N_WEEKS)
            if k == "Water":
                s = np.exp(0.035 * (temp[ci] - 12))
            elif k == "Dairy":
                s = np.exp(0.006 * (temp[ci] - 12)) * np.where(woy >= 50, 1.15, 1.0)
            elif k == "Confectionery":
                s = np.where(woy >= 48, 1.6, np.where((woy >= 26) & (woy <= 34), 0.85, 1.0))
                for y, e in EASTER.items():
                    d = (WEEKS - pd.Timestamp(e)).days.to_numpy()
                    s = np.where((years == y) & (d > -28) & (d <= 0), s * 1.3, s)
            elif k == "Coffee":
                s = 1 + 0.08 * np.cos(2 * np.pi * (woy - 2) / 52)
            elif k == "Culinary":
                s = 1 + 0.20 * np.cos(2 * np.pi * (woy - 3) / 52)
            F[ci, ki] = trend * s
    return F


def seasonal_sku_mask(prods: pd.DataFrame) -> np.ndarray:
    """M[product, week] = 0 outside the selling window of seasonal SKUs (Easter eggs, Advent calendars)."""
    M = np.ones((len(prods), N_WEEKS), dtype=np.float32)
    years = WEEKS.year.to_numpy()
    for i, s in enumerate(prods["seasonal"]):
        if s == "easter":
            ok = np.zeros(N_WEEKS, bool)
            for y, e in EASTER.items():
                d = (WEEKS - pd.Timestamp(e)).days.to_numpy()
                ok |= (years == y) & (d > -56) & (d <= 0)
            M[i] = np.where(ok, 3.0, 0.0)
        elif s == "advent":
            M[i] = np.where(WEEKS.month.isin([9, 10, 11]), 3.0, 0.0)
    launch = ((prods["launch_date"].to_numpy()[:, None]) <= WEEKS.to_numpy()[None, :])
    disc = prods["discontinued_date"].to_numpy()[:, None]
    alive = launch & (pd.isna(disc) | (WEEKS.to_numpy()[None, :] <= disc))
    return M * alive


def promotions(rng, custs: pd.DataFrame) -> pd.DataFrame:
    rows, pid = [], 1
    elig = custs.index[custs["channel"].isin(["Modern trade", "E-commerce"]) | custs["is_distributor"]]
    for i in elig:
        n = rng.poisson(8 * N_WEEKS / 52)
        starts = rng.integers(0, N_WEEKS - 3, n)
        for s in starts:
            dur = int(rng.choice([1, 2, 2, 3]))
            disc = float(rng.choice([0.10, 0.15, 0.20, 0.25, 0.30], p=[0.2, 0.3, 0.25, 0.15, 0.10]))
            rows.append((f"P{pid:06d}", custs.at[i, "customer_id"], i, rng.choice(CATS), s, dur, disc, rng.choice(MECHANICS)))
            pid += 1
    # Story 4: big December 2025 promotion at the overstocking Polish distributor
    pl = custs[(custs["is_distributor"]) & (custs["country_code"] == "PL")]
    if len(pl):
        i = pl["size_factor"].idxmax()
        w = int(np.searchsorted(WEEKS, pd.Timestamp("2025-12-01")))
        for cat in ["Confectionery", "Coffee"]:
            rows.append((f"P{pid:06d}", custs.at[i, "customer_id"], i, cat, w, 3, 0.25, "Display + feature")); pid += 1
    df = pd.DataFrame(rows, columns=["promo_id", "customer_id", "cust_idx", "category", "start_week", "duration_weeks",
                                     "discount_pct", "mechanic"])
    df["start_date"] = WEEKS[df["start_week"]].date
    df["end_date"] = [d + dt.timedelta(days=7 * k - 1) for d, k in zip(df["start_date"], df["duration_weeks"])]
    df["planned_uplift_pct"] = np.round(df["discount_pct"] * 400 * rng.uniform(0.8, 1.2, len(df)), 0)
    return df


def generate(rng, custs, prods, assort, alen, prices, writer) -> pd.DataFrame:
    """Writes sales_orders / sales_order_lines / returns per year through `writer`. Returns distributor weekly sell-in."""
    F = demand_factors(); M = seasonal_sku_mask(prods)
    promos = promotions(rng, custs)
    pmap = np.full((len(custs), len(CATS), N_WEEKS), -1, dtype=np.int32)
    pcat = promos["category"].map({k: i for i, k in enumerate(CATS)}).to_numpy()
    for j, (ci, k, s, d) in enumerate(zip(promos["cust_idx"], pcat, promos["start_week"], promos["duration_weeks"])):
        pmap[ci, k, s:s + d] = j
    writer("promotions", promos.drop(columns=["cust_idx", "start_week"]), None)

    rounds = np.array(price_rounds(), dtype="datetime64[D]")
    sku_pos = {s: i for i, s in enumerate(prods["sku"])}
    P = np.zeros((len(rounds), len(CC), len(prods)))
    pr = prices.assign(r=np.searchsorted(rounds, prices["valid_from"].to_numpy().astype("datetime64[D]")),
                       c=prices["country_code"].map({c: i for i, c in enumerate(CC)}), p=prices["sku"].map(sku_pos))
    P[pr["r"], pr["c"], pr["p"]] = pr["list_price_case"]

    ch = custs["channel"].to_numpy(); cidx_country = custs["country_code"].map({c: i for i, c in enumerate(CC)}).to_numpy()
    size = custs["size_factor"].to_numpy()
    tdisc = np.array([rng.uniform(*TRADE_DISC[x]) for x in ch])
    pcat_of = prods["category"].map({k: i for i, k in enumerate(CATS)}).to_numpy()
    pop = prods["popularity"].to_numpy(); pop = pop / pop.mean()
    week_days = np.where(ch == "E-commerce", 7, 5)
    pl_dist = custs[(custs["is_distributor"]) & (custs["country_code"] == "PL")]["size_factor"]
    over_ci = pl_dist.idxmax() if len(pl_dist) else -1
    ow0, ow1 = np.searchsorted(WEEKS, pd.Timestamp(OVERSTOCK_WEEKS[0])), np.searchsorted(WEEKS, pd.Timestamp(OVERSTOCK_WEEKS[1]))

    is_dist = custs["is_distributor"].to_numpy()
    tickets = np.zeros((len(custs), 1000), dtype=np.int32)
    for i in range(len(custs)):
        a = assort[i, :alen[i]]; w = pop[a] / pop[a].sum()
        tickets[i] = np.repeat(a, np.diff(np.round(np.concatenate([[0], np.cumsum(w)]) * 1000).astype(int)))[:1000] \
            if len(a) else 0
    order_seq, dist_parts = 1, []
    for year in sorted(set(WEEKS.year)):
        wk = np.where(WEEKS.year == year)[0]
        rate = np.where(is_dist, 2.0, [ORDERS_PER_WEEK[x] for x in ch])[:, None] * np.ones((1, len(wk)))
        counts = np.floor(rate + rng.random(rate.shape)).astype(int)    # regular ordering rhythm (low noise)
        ci, wi = np.nonzero(counts); rep = counts[ci, wi]
        o_c = np.repeat(ci, rep); o_w = np.repeat(wk[wi], rep)
        day = (rng.random(len(o_c)) * week_days[o_c]).astype(int)
        o_date = (WEEKS.to_numpy()[o_w].astype("datetime64[D]") + day)
        keep = o_date <= np.datetime64(END)
        o_c, o_w, o_date = o_c[keep], o_w[keep], o_date[keep]
        n_o = len(o_c)
        o_id = np.arange(order_seq, order_seq + n_o); order_seq += n_o

        # lines
        nl = np.clip(rng.poisson(np.where(is_dist, 40, [LINES_PER_ORDER[x] for x in ch])[o_c]), 1, alen[o_c])
        l_o = np.repeat(np.arange(n_o), nl)
        # popular SKUs are ordered almost every time (ticket sampling), quantities depend less on popularity
        l_p = tickets[o_c[l_o], rng.integers(0, tickets.shape[1], len(l_o))]
        df = pd.DataFrame({"o": l_o, "p": l_p}).drop_duplicates()
        l_o, l_p = df["o"].to_numpy(), df["p"].to_numpy()
        lc, lw = o_c[l_o], o_w[l_o]
        k = pcat_of[l_p]
        mean = BASE_QTY * size[lc] * pop[l_p] ** 0.3 * F[cidx_country[lc], k, lw] * M[l_p, lw]
        promo = pmap[lc, k, lw]
        disc = tdisc[lc].copy()
        has_p = promo >= 0
        pdisc = promos["discount_pct"].to_numpy()
        uplift = np.where(has_p, 1 + 4 * pdisc[np.maximum(promo, 0)], 1.0)
        mean = mean * uplift
        if over_ci >= 0:
            mean = np.where((lc == over_ci) & (lw >= ow0) & (lw < ow1), mean * OVERSTOCK_FACTOR, mean)
        qty = np.ceil(rng.gamma(2.0, np.maximum(mean, 1e-9) / 2.0)).astype(np.int32)
        ok = (mean > 0) & (qty > 0)
        l_o, l_p, lc, lw, k, qty, promo, disc = l_o[ok], l_p[ok], lc[ok], lw[ok], k[ok], qty[ok], promo[ok], disc[ok]
        disc = np.where(promo >= 0, disc + pdisc[np.maximum(promo, 0)], disc)
        r = np.searchsorted(rounds, o_date[l_o], side="right") - 1
        lp = P[r, cidx_country[lc], l_p]
        net = np.round(qty * lp * (1 - disc), 2)

        # orders header
        status = np.where(rng.random(n_o) < 0.008, "Cancelled", "Invoiced")
        status = np.where(o_date > np.datetime64(END) - 5, "Open", status)
        orders = pd.DataFrame({"order_id": o_id, "customer_id": custs["customer_id"].to_numpy()[o_c],
                               "order_date": o_date, "requested_delivery_date": o_date + rng.integers(1, 6, n_o),
                               "currency": [COUNTRIES[CC[x]][1] for x in cidx_country[o_c]],
                               "order_status": status, "sales_channel": ch[o_c],
                               "is_deleted": rng.random(n_o) < 0.002,
                               "created_at": o_date.astype("datetime64[s]") + rng.integers(6 * 3600, 20 * 3600, n_o)})
        lines = pd.DataFrame({"order_id": o_id[l_o], "sku": prods["sku"].to_numpy()[l_p], "qty_cases": qty,
                              "list_price_case": np.round(lp, 2), "discount_pct": np.round(disc, 4), "net_amount": net,
                              "promo_id": np.where(promo >= 0, promos["promo_id"].to_numpy()[np.maximum(promo, 0)], None)})
        lines.insert(1, "line_no", lines.groupby("order_id").cumcount() + 1)

        # returns (about 1.2% of invoiced lines)
        inv = (status[l_o] == "Invoiced")
        ridx = np.where(inv & (rng.random(len(l_o)) < 0.012))[0]
        rdate = o_date[l_o[ridx]] + rng.integers(3, 31, len(ridx))
        rk = rdate <= np.datetime64(END)
        ridx, rdate = ridx[rk], rdate[rk]
        rq = np.maximum(1, (qty[ridx] * rng.uniform(0.05, 0.6, len(ridx))).astype(int))
        returns = pd.DataFrame({"order_id": o_id[l_o[ridx]], "line_no": lines["line_no"].to_numpy()[ridx], "return_date": rdate,
                                "qty_cases": rq, "reason_code": rng.choice(["DAMAGED", "EXPIRED", "WRONG_ITEM", "QUALITY", "OVERSTOCK"],
                                                                           len(ridx), p=[0.35, 0.25, 0.15, 0.10, 0.15]),
                                "credit_amount": np.round(rq * lp[ridx] * (1 - disc[ridx]), 2)})
        writer("sales_orders", orders, year); writer("sales_order_lines", lines, year); writer("returns", returns, year)
        print(f"  {year}: {n_o:,} orders, {len(lines):,} lines, {len(returns):,} returns")

        dm = custs["is_distributor"].to_numpy()[lc] & (status[l_o] != "Cancelled")
        dist_parts.append(pd.DataFrame({"cust_idx": lc[dm], "p": l_p[dm], "week": lw[dm], "qty": qty[dm]})
                          .groupby(["cust_idx", "p", "week"], as_index=False)["qty"].sum())
    return pd.concat(dist_parts, ignore_index=True)
