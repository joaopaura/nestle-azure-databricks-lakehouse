"""Master data for the legacy ERP: countries, products, customers, price list, standard cost, audit logs."""
import datetime as dt

import numpy as np
import pandas as pd

from config import (ASSORTMENT_SIZE, CATEGORIES, COUNTRIES, CUSTOMERS_BY_CHANNEL, END, EXTRA_PRICING, N_DISTRIBUTORS,
                    N_PRODUCTS, PRICE_LEVEL)
from public_data import food_price_factors, price_rounds

CC = list(COUNTRIES)

LINES = {
    "Coffee": ("Brava Coffee", [("Instant", "Classic", ["100 g", "200 g", "300 g"]), ("Instant", "Gold", ["100 g", "200 g"]),
                                ("Capsules", "Espresso", ["10 caps", "30 caps"]), ("Capsules", "Lungo", ["10 caps", "30 caps"]),
                                ("Ground", "Roast & Ground", ["250 g", "500 g"]), ("Beans", "Crema", ["500 g", "1 kg"]),
                                ("Mixes", "Cappuccino Sachets", ["8 x 14 g", "20 x 14 g"]), ("Instant", "Decaf", ["100 g"])]),
    "Confectionery": ("Alpina", [("Tablets", "Milk Chocolate", ["100 g", "200 g"]), ("Tablets", "Dark 70%", ["100 g"]),
                                 ("Wafers", "Choco Wafer", ["4 finger", "multipack 9"]), ("Boxes", "Pralines", ["200 g", "400 g"]),
                                 ("Seasonal", "Easter Egg", ["150 g", "300 g"]), ("Seasonal", "Advent Calendar", ["240 g"]),
                                 ("Bites", "Mini Bites", ["150 g", "350 g"])]),
    "Water": ("Sorgente", [("Still", "Mineral Still", ["1.5 L x 6", "0.5 L x 12"]), ("Sparkling", "Sparkling", ["1 L x 6", "0.5 L x 12"]),
                           ("Flavoured", "Lemon Flavoured", ["0.5 L x 12"])]),
    "Pet Care": ("NutriPaws", [("Cat dry", "Adult Cat Dry", ["800 g", "2 kg", "7 kg"]), ("Cat wet", "Cat Pouch", ["12 x 85 g", "40 x 85 g"]),
                               ("Dog dry", "Adult Dog Dry", ["3 kg", "10 kg", "14 kg"]), ("Dog wet", "Dog Tray", ["8 x 300 g"]),
                               ("Treats", "Dental Treats", ["7 sticks", "28 sticks"]), ("Cat dry", "Senior Cat", ["1.5 kg"])]),
    "Dairy": ("Lattea", [("Milk", "Condensed Milk", ["397 g", "1 kg"]), ("Creamer", "Coffee Creamer", ["200 g", "400 g"]),
                         ("Drinks", "Yogurt Drink", ["6 x 100 g"]), ("Powder", "Milk Powder", ["400 g", "900 g"])]),
    "Culinary": ("Herbal Kitchen", [("Bouillon", "Chicken Stock Cubes", ["8 cubes", "24 cubes"]), ("Soups", "Tomato Soup", ["3 servings", "5 servings"]),
                                    ("Sauces", "Sauce Mix", ["35 g", "70 g"]), ("Noodles", "Instant Noodles", ["5 x 70 g"]),
                                    ("Seasoning", "All-Purpose Seasoning", ["90 g", "200 g"])]),
    "Infant Nutrition": ("Little Steps", [("Formula", "Infant Formula Stage 1", ["800 g"]), ("Formula", "Follow-on Stage 2", ["800 g"]),
                                          ("Formula", "Growing-up Stage 3", ["800 g", "1.2 kg"]), ("Cereals", "Baby Cereal", ["250 g"]),
                                          ("Purees", "Baby Puree", ["4 x 100 g"])]),
}
NAME_A = ["Nova", "Sol", "Linden", "Aurora", "Vista", "Polar", "Tera", "Orbis", "Luma", "Vela", "Kestrel", "Brio", "Cedar", "Marla",
          "Oaken", "Pico", "Riva", "Sora", "Talia", "Umbra"]
NAME_B = {"Modern trade": ["Markt", "Retail", "Supermarkets", "Hypermarkets", "Stores", "Foods"],
          "Traditional trade": ["Wholesale", "Cash & Carry", "Trading", "Distribution"],
          "E-commerce": ["Online", "Direct", "Delivery", "eGrocer"],
          "Out-of-home": ["Cafe", "Hotels", "Catering", "Canteens", "Vending"]}
CTYPE = {"Modern trade": "Retail chain", "Traditional trade": "Wholesaler", "E-commerce": "E-retailer", "Out-of-home": "Foodservice"}
FIRST = ["Anna", "Marek", "Julia", "Lukas", "Sofia", "Pierre", "Elena", "Tomasz", "Laura", "Marco", "Ines", "Jan", "Clara", "David",
         "Eva", "Hugo", "Lea", "Nils", "Olga", "Paulo", "Rita", "Sven", "Tess", "Victor", "Zofia", "Emma", "Luca", "Maja", "Noah", "Ida"]
LAST = ["Nowak", "Muller", "Rossi", "Garcia", "Dubois", "Smith", "Kowalski", "Silva", "Jansen", "Peeters", "Gruber", "Lindberg",
        "Bauer", "Moretti", "Lopez", "Martin", "Brown", "Wisniewski", "Costa", "Visser", "Huber", "Svensson", "Fischer", "Bianchi"]
KAMS = [f"{f} {l}" for f, l in zip(FIRST * 2, LAST[::-1] * 3)][:40]


def ean13(n: np.ndarray) -> np.ndarray:
    """Valid EAN-13 codes from a fictitious '7609' prefix + running number."""
    body = np.array([f"7609{x:08d}" for x in n])
    digits = np.array([[int(ch) for ch in b] for b in body])
    s = (digits[:, ::2].sum(1) + 3 * digits[:, 1::2].sum(1)) % 10
    return np.array([b + str((10 - c) % 10) for b, c in zip(body, s)])


def countries() -> pd.DataFrame:
    return pd.DataFrame([(c, v[0], v[1], v[3]) for c, v in COUNTRIES.items()],
                        columns=["country_code", "country_name", "currency", "capital"])


def products(rng: np.random.Generator) -> pd.DataFrame:
    rows, sku = [], 1000001
    for cat, (share, price, weight, cost) in CATEGORIES.items():
        brand, lines = LINES[cat]
        n = round(N_PRODUCTS * share)
        variants = [(sub, name, size) for sub, name, sizes in lines for size in sizes]
        for i in range(n):
            sub, name, size = variants[i % len(variants)]
            flav = ["", " Original", " Intense", " Mild", " Family", " Organic", " Light", " Premium"][(i // len(variants)) % 8]
            rows.append(dict(sku=sku, product_name=f"{brand} {name}{flav} {size}", brand=brand, category=cat, subcategory=sub,
                             pack_size=size, units_per_case=int(rng.choice([6, 8, 10, 12, 16, 24])),
                             case_weight_kg=round(weight * rng.uniform(0.6, 1.5), 2),
                             base_price_eur=round(price * rng.uniform(0.6, 1.6), 2), cost_ratio=cost,
                             popularity=float(rng.lognormal(0, 0.8)),
                             seasonal=("easter" if "Easter" in name else "advent" if "Advent" in name else "")))
            sku += 1
    df = pd.DataFrame(rows).iloc[:N_PRODUCTS].copy()
    df["ean"] = ean13(df["sku"].to_numpy())
    launch = np.full(len(df), "2015-01-01", dtype=object)
    low = np.argsort(df["popularity"].to_numpy())[: int(len(df) * 0.45)]       # launches and delistings are small SKUs
    new = rng.choice(low, int(len(df) * 0.08), replace=False)
    launch[new] = [str(dt.date(2023, 1, 1) + dt.timedelta(days=int(d))) for d in rng.integers(0, 900, len(new))]
    df["launch_date"] = pd.to_datetime(launch)
    disc = rng.choice(np.setdiff1d(low, new), int(len(df) * 0.05), replace=False)
    df["discontinued_date"] = pd.NaT
    df.loc[df.index[disc], "discontinued_date"] = pd.Timestamp("2024-12-31")
    df["status"] = np.where(df["discontinued_date"].notna(), "Discontinued", "Active")
    return df


def customers(rng: np.random.Generator) -> pd.DataFrame:
    weights = np.array([COUNTRIES[c][2] for c in CC], float); weights /= weights.sum()
    rows, cid = [], 1
    for ch, n in CUSTOMERS_BY_CHANNEL.items():
        ctry = rng.choice(CC, n, p=weights)
        size = rng.lognormal({"Modern trade": 1.2, "Traditional trade": 0.4, "E-commerce": 0.8, "Out-of-home": -0.6}[ch], 0.7, n)
        for k in range(n):
            c = ctry[k]
            first, last = rng.choice(FIRST), rng.choice(LAST)
            name = f"{rng.choice(NAME_A)} {rng.choice(NAME_B[ch])} {c}-{cid:04d}"
            rows.append(dict(customer_id=f"C{cid:06d}", customer_name=name, country_code=c, channel=ch,
                             customer_type=CTYPE[ch], size_factor=float(size[k]),
                             key_account_manager=rng.choice(KAMS), credit_limit_eur=int(round(size[k] * 50000, -3)) + 5000,
                             contact_name=f"{first} {last}", contact_email=f"{first}.{last}{cid}@example.com".lower(),
                             contact_phone=f"+{rng.integers(30, 49)} {rng.integers(100, 999)} {rng.integers(100, 999)} {rng.integers(100, 999)}",
                             vat_number=f"{c}{rng.integers(10**8, 10**9)}",
                             created_at=pd.Timestamp("2008-01-01") + pd.Timedelta(days=int(rng.integers(0, 5000)))))
            cid += 1
    df = pd.DataFrame(rows)
    tt = df.index[df["channel"] == "Traditional trade"]
    dist = rng.choice(tt, N_DISTRIBUTORS, replace=False)
    df["is_distributor"] = False
    df.loc[dist, "is_distributor"] = True
    df.loc[dist, "customer_type"] = "Distributor"
    df.loc[dist, "customer_name"] = [n.replace("Wholesale", "Distribution").replace("Cash & Carry", "Distribution")
                                     for n in df.loc[dist, "customer_name"]]
    # Story 4: the overstocking distributor is the largest Polish distributor
    pl = df[(df["is_distributor"]) & (df["country_code"] == "PL")]
    if len(pl):
        df.loc[pl["size_factor"].idxmax(), "size_factor"] *= 2.5
    return df


def assortments(rng, prods: pd.DataFrame, custs: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Per customer, a list of product row indexes (padded 2D array + lengths)."""
    pop = prods["popularity"].to_numpy(); pop = pop / pop.sum()
    kmax = max(ASSORTMENT_SIZE.values())
    arr = np.zeros((len(custs), kmax), dtype=np.int32); lens = np.zeros(len(custs), dtype=np.int32)
    for i, ch in enumerate(custs["channel"]):
        base = 220 if custs["is_distributor"].iat[i] else ASSORTMENT_SIZE[ch]
        k = min(int(base * rng.uniform(0.7, 1.15)), kmax, len(prods))
        arr[i, :k] = rng.choice(len(prods), k, replace=False, p=pop); lens[i] = k
    return arr, lens


def price_list(rng, prods: pd.DataFrame) -> pd.DataFrame:
    pf = food_price_factors()
    rounds = price_rounds()
    rows = []
    for c in CC:
        fx_ref, cur = COUNTRIES[c][6], COUNTRIES[c][1]
        f = pf[pf["country_code"] == c].set_index("valid_from")["price_factor"]
        drift = np.ones(len(prods))
        for j, r in enumerate(rounds):
            drift *= rng.normal(1.0, 0.012, len(prods))
            for (cat, when), pct in EXTRA_PRICING.items():
                if str(r) == when:
                    drift *= np.where(prods["category"].to_numpy() == cat, 1 + pct, 1.0)
            price = prods["base_price_eur"].to_numpy() * PRICE_LEVEL[c] * fx_ref * f.loc[r] * drift
            vt = (rounds[j + 1] - dt.timedelta(days=1)) if j + 1 < len(rounds) else dt.date(9999, 12, 31)
            rows.append(pd.DataFrame({"sku": prods["sku"], "country_code": c, "currency": cur,
                                      "list_price_case": np.round(price, 2), "valid_from": pd.Timestamp(r), "valid_to": pd.Timestamp(vt)}))
    return pd.concat(rows, ignore_index=True)


def cost_index(cat: str, q: pd.Period) -> float:
    t = q.year + (q.quarter - 1) / 4
    base = 1 + 0.12 * min(max((t - 2022.0) / 0.75, 0), 1) + 0.05 * min(max(t - 2023.0, 0), 1) + 0.02 * max(t - 2024.0, 0)
    if cat == "Coffee":           # arabica price spike 2024 to 2025
        base *= 1 + 0.35 * max(0, 1 - abs(t - 2025.0) / 0.9)
    if cat == "Confectionery":    # cocoa price spike 2024
        base *= 1 + 0.40 * max(0, 1 - abs(t - 2024.6) / 0.8)
    return base


def standard_cost(prods: pd.DataFrame) -> pd.DataFrame:
    qs = pd.period_range("2022Q1", pd.Period(END, "Q"), freq="Q")
    rows = [pd.DataFrame({"sku": prods["sku"], "fiscal_quarter": str(q),
                          "std_cost_eur_case": np.round(prods["base_price_eur"] * prods["cost_ratio"]
                                                        * prods["category"].map(lambda c: cost_index(c, q)), 2)})
            for q in qs]
    return pd.concat(rows, ignore_index=True)


def customer_changes(rng, custs: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Legacy ERP audit log. customers table keeps the CURRENT values; the log has old -> new (source for SCD2)."""
    custs = custs.copy(); logs = []
    idx = rng.choice(len(custs), 320, replace=False)
    for k, i in enumerate(idx):
        when = pd.Timestamp("2023-01-01") + pd.Timedelta(days=int(rng.integers(0, 1350)), hours=int(rng.integers(7, 19)))
        field = ["key_account_manager", "key_account_manager", "credit_limit_eur", "customer_name", "channel"][k % 5]
        old = custs.at[i, field]
        if field == "key_account_manager":
            new = rng.choice([x for x in KAMS if x != old])
        elif field == "credit_limit_eur":
            new = int(old * rng.choice([0.5, 1.5, 2.0]))
        elif field == "customer_name":
            new = f"{rng.choice(NAME_A)} {old.split(' ', 1)[1]}"
        else:
            if custs.at[i, "channel"] != "Traditional trade" or custs.at[i, "is_distributor"]:
                continue
            new = "Modern trade"
        custs.at[i, field] = new
        if field == "channel":
            custs.at[i, "customer_type"] = "Retail chain"
        logs.append((custs.at[i, "customer_id"], field, str(old), str(new), when))
    log = pd.DataFrame(logs, columns=["customer_id", "field_name", "old_value", "new_value", "changed_at"])
    log.insert(0, "change_id", np.arange(1, len(log) + 1))
    return custs, log.sort_values("changed_at")


def product_changes(rng, prods: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Shrinkflation: some Coffee / Confectionery packs get smaller in 2023 (price per case unchanged)."""
    prods = prods.copy(); logs = []
    cand = prods.index[prods["category"].isin(["Coffee", "Confectionery"]) & prods["pack_size"].str.endswith(" g")]
    for i in rng.choice(cand, min(24, len(cand)), replace=False):
        old = prods.at[i, "pack_size"]; g = int(old.split()[0]); new = f"{int(round(g * 0.9, -1))} g"
        when = pd.Timestamp(str(rng.choice(["2023-03-01", "2023-09-01", "2024-03-01"])))
        prods.at[i, "pack_size"] = new
        prods.at[i, "product_name"] = prods.at[i, "product_name"].replace(old, new)
        prods.at[i, "case_weight_kg"] = round(prods.at[i, "case_weight_kg"] * 0.9, 2)
        logs.append((prods.at[i, "sku"], "pack_size", old, new, when))
    log = pd.DataFrame(logs, columns=["sku", "field_name", "old_value", "new_value", "changed_at"])
    log.insert(0, "change_id", np.arange(1, len(log) + 1))
    return prods, log.sort_values("changed_at")
