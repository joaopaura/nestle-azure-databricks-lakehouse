"""Load the real public data into the shapes the generator needs (with synthetic fallbacks for offline tests)."""
import datetime as dt

import numpy as np
import pandas as pd

from config import COUNTRIES, END, FALLBACK_FOOD_INFLATION, PRICE_PASS_THROUGH, PUBLIC, START

CC = list(COUNTRIES)
WEEKS = pd.date_range(START, END, freq="W-MON")          # week start dates (Monday)
N_WEEKS = len(WEEKS)
USED_FALLBACK = []


def price_rounds() -> list[dt.date]:
    """List price changes happen twice a year: 1 Jan and 1 Jul."""
    return [dt.date(y, m, 1) for y in range(2022, END.year + 1) for m in (1, 7) if dt.date(y, m, 1) <= END]


def food_price_factors() -> pd.DataFrame:
    """Price factor per country and price round, driven by the REAL food inflation index.
    factor = 1 + pass_through * (index[month before round] / index[Dec 2021] - 1)."""
    f = PUBLIC / "food_inflation_monthly.csv"
    rows = []
    if f.exists():
        h = pd.read_csv(f)
        piv = h.pivot_table(index="month", columns="country_code", values="index_value")
        ea = piv.mean(axis=1)                                    # simple average as proxy for missing countries
        for c in CC:
            s = piv[c] if c in piv else ea
            s = s.ffill()
            base = s.loc["2021-12"]
            for r in price_rounds():
                prev = (pd.Timestamp(r) - pd.DateOffset(months=1)).strftime("%Y-%m")
                idx = s.loc[:prev].iloc[-1]
                rows.append((c, r, 1 + PRICE_PASS_THROUGH * (idx / base - 1)))
    else:
        USED_FALLBACK.append("food inflation")
        for c in CC:
            lvl = 1.0
            for r in price_rounds():
                infl = FALLBACK_FOOD_INFLATION[r.year] / 100 / 2           # half-year step
                lvl *= 1 + PRICE_PASS_THROUGH * infl
                rows.append((c, r, lvl))
    return pd.DataFrame(rows, columns=["country_code", "valid_from", "price_factor"])


def weekly_temperature() -> np.ndarray:
    """Mean temperature per country (rows, CC order) and week (cols, WEEKS order)."""
    f = PUBLIC / "weather_daily.csv"
    if f.exists():
        w = pd.read_csv(f, parse_dates=["weather_date"])
        w["week"] = w["weather_date"] - pd.to_timedelta(w["weather_date"].dt.weekday, unit="D")
        piv = w.pivot_table(index="country_code", columns="week", values="temperature_2m_mean")
        piv = piv.reindex(index=CC, columns=WEEKS).ffill(axis=1).bfill(axis=1)
        return piv.to_numpy()
    USED_FALLBACK.append("weather")
    rng = np.random.default_rng(7)
    lat = np.array([COUNTRIES[c][4] for c in CC])[:, None]
    doy = WEEKS.dayofyear.to_numpy()[None, :]
    mean = 24 - 0.35 * lat
    return mean - 9 * np.cos(2 * np.pi * (doy - 15) / 365) + rng.normal(0, 2.2, (len(CC), N_WEEKS))
