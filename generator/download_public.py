"""Download the REAL public datasets used by the project (run on your PC, needs internet).

Outputs (data/raw/public/):
  fx_rates_daily.csv      ECB euro reference rates, EUR base (PLN, GBP, CHF, SEK), daily
  food_inflation_monthly.csv  Food and non-alcoholic beverages price index (Eurostat HICP CP01; UK from ONS D7BU)
  weather_daily.csv       Open-Meteo historical weather for the 12 capitals (mean temperature, precipitation)

Usage:  python generator/download_public.py
"""
import io
import re
import sys
import time

import pandas as pd
import requests

from config import COUNTRIES, END, PUBLIC, START

UA = {"User-Agent": "nestle-lakehouse-portfolio/1.0 (github.com/joaopaura)"}
PUBLIC.mkdir(parents=True, exist_ok=True)


def get(url: str, tries: int = 3) -> requests.Response:
    for i in range(tries):
        try:
            r = requests.get(url, headers=UA, timeout=60)
            if r.status_code == 200:
                return r
            print(f"  HTTP {r.status_code} for {url[:110]}")
        except requests.RequestException as e:
            print(f"  error {e.__class__.__name__} for {url[:110]}")
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"failed: {url}")


def fx() -> pd.DataFrame:
    url = ("https://data-api.ecb.europa.eu/service/data/EXR/D.PLN+GBP+CHF+SEK.EUR.SP00.A"
           f"?format=csvdata&startPeriod={START.replace(day=1)}&endPeriod={END}")
    df = pd.read_csv(io.StringIO(get(url).text))
    out = (df[["TIME_PERIOD", "CURRENCY", "OBS_VALUE"]]
           .rename(columns={"TIME_PERIOD": "rate_date", "CURRENCY": "currency", "OBS_VALUE": "rate_per_eur"}))
    out["source"] = "ECB EXR"
    return out.sort_values(["currency", "rate_date"])


def eurostat_food_index(geos: list[str]) -> pd.DataFrame:
    """HICP CP01 monthly index. Tries several bases because Eurostat rebases over time."""
    last_err = None
    for unit in ("I15", "I25", "I05"):
        url = ("https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/prc_hicp_midx/"
               f"M.{unit}.CP01.{'+'.join(geos)}?format=SDMX-CSV&startPeriod=2021-01")
        try:
            df = pd.read_csv(io.StringIO(get(url).text))
            df = df[["geo", "TIME_PERIOD", "OBS_VALUE"]].dropna()
            if df.empty:
                continue
            df.columns = ["country_code", "month", "index_value"]
            df["base"] = unit
            df["source"] = "Eurostat prc_hicp_midx CP01"
            return df
        except Exception as e:  # noqa: BLE001
            last_err = e
    raise RuntimeError(f"Eurostat HICP download failed: {last_err}")


def ons_uk_food_index() -> pd.DataFrame:
    url = "https://www.ons.gov.uk/generator?format=csv&uri=/economy/inflationandpriceindices/timeseries/d7bu/mm23"
    rows = re.findall(r'^"(\d{4}) ([A-Z]{3})","([\d.]+)"', get(url).text, flags=re.M)
    months = {m: i for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}
    df = pd.DataFrame([(f"{y}-{months[m]:02d}", float(v)) for y, m, v in rows if int(y) >= 2021],
                      columns=["month", "index_value"])
    df["country_code"], df["base"], df["source"] = "GB", "I15", "ONS D7BU (CPI index 01 food, 2015=100)"
    return df


def weather() -> pd.DataFrame:
    frames = []
    for code, (_, _, _, city, lat, lon, _) in COUNTRIES.items():
        url = ("https://archive-api.open-meteo.com/v1/archive"
               f"?latitude={lat}&longitude={lon}&start_date={START}&end_date={END}"
               "&daily=temperature_2m_mean,temperature_2m_max,precipitation_sum&timezone=Europe%2FBerlin")
        js = get(url).json()["daily"]
        df = pd.DataFrame(js).rename(columns={"time": "weather_date"})
        df.insert(0, "city", city)
        df.insert(0, "country_code", code)
        frames.append(df)
        print(f"  weather {city}: {len(df)} days")
        time.sleep(0.5)
    out = pd.concat(frames)
    out["source"] = "Open-Meteo archive API"
    return out


def main() -> int:
    print("ECB FX rates ...")
    f = fx(); f.to_csv(PUBLIC / "fx_rates_daily.csv", index=False); print(f"  {len(f):,} rows")

    print("Food inflation index (Eurostat HICP CP01 + ONS for UK) ...")
    eu = [c for c in COUNTRIES if c != "GB"]
    h = pd.concat([eurostat_food_index(eu), ons_uk_food_index()])
    missing = sorted(set(COUNTRIES) - set(h["country_code"]))
    if missing:
        print(f"  WARNING: no index for {missing}; generator will use the euro area average for them")
    h.sort_values(["country_code", "month"]).to_csv(PUBLIC / "food_inflation_monthly.csv", index=False)
    print(f"  {len(h):,} rows, countries: {sorted(h['country_code'].unique())}")

    print("Open-Meteo weather (12 capitals) ...")
    w = weather(); w.to_csv(PUBLIC / "weather_daily.csv", index=False); print(f"  {len(w):,} rows")
    print("Done. Files in", PUBLIC)
    return 0


if __name__ == "__main__":
    sys.exit(main())
