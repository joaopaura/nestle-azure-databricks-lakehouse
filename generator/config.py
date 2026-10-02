"""Central configuration for the Nestlé synthetic data generator.

All company data is synthetic. Public data (ECB FX, Eurostat / ONS food inflation, Open-Meteo weather) is real
and is downloaded by download_public.py. Seeded: the same seed always produces the same data.
"""
from pathlib import Path
import datetime as dt

SEED = 2026
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PUBLIC = RAW / "public"
ERP = RAW / "erp"
SELLOUT = RAW / "sellout"
POS = RAW / "pos_stream"

START = dt.date(2022, 1, 3)          # first Monday of 2022
END = dt.date(2026, 9, 30)           # last actual day
POS_START = dt.date(2026, 8, 1)      # POS event stream window (simulated stream)

# Scale knobs (about 10M order lines, about 15M rows in total)
N_PRODUCTS = 350
CUSTOMERS_BY_CHANNEL = {"Modern trade": 600, "Traditional trade": 900, "E-commerce": 100, "Out-of-home": 900}
ORDERS_PER_WEEK = {"Modern trade": 1.5, "Traditional trade": 1.0, "E-commerce": 3.0, "Out-of-home": 0.5}
LINES_PER_ORDER = {"Modern trade": 26, "Traditional trade": 16, "E-commerce": 12, "Out-of-home": 8}
ASSORTMENT_SIZE = {"Modern trade": 220, "Traditional trade": 140, "E-commerce": 260, "Out-of-home": 60}
N_DISTRIBUTORS = 60                  # traditional-trade customers that send sell-out files

# 12 markets: name, currency, size weight, capital (lat, lon), 2022 reference FX (local per EUR, list price setting)
COUNTRIES = {
    "DE": ("Germany", "EUR", 18, "Berlin", 52.52, 13.40, 1.0),
    "FR": ("France", "EUR", 15, "Paris", 48.86, 2.35, 1.0),
    "GB": ("United Kingdom", "GBP", 14, "London", 51.51, -0.13, 0.85),
    "IT": ("Italy", "EUR", 11, "Rome", 41.90, 12.50, 1.0),
    "ES": ("Spain", "EUR", 10, "Madrid", 40.42, -3.70, 1.0),
    "PL": ("Poland", "PLN", 8, "Warsaw", 52.23, 21.01, 4.60),
    "NL": ("Netherlands", "EUR", 5, "Amsterdam", 52.37, 4.90, 1.0),
    "CH": ("Switzerland", "CHF", 5, "Bern", 46.95, 7.45, 1.03),
    "BE": ("Belgium", "EUR", 4, "Brussels", 50.85, 4.35, 1.0),
    "PT": ("Portugal", "EUR", 4, "Lisbon", 38.72, -9.14, 1.0),
    "AT": ("Austria", "EUR", 3, "Vienna", 48.21, 16.37, 1.0),
    "SE": ("Sweden", "SEK", 3, "Stockholm", 59.33, 18.07, 10.6),
}
PRICE_LEVEL = {"DE": 1.00, "FR": 1.04, "GB": 1.06, "IT": 0.98, "ES": 0.92, "PL": 0.72, "NL": 1.02,
               "CH": 1.45, "BE": 1.03, "PT": 0.88, "AT": 1.05, "SE": 1.12}

# Categories: share of SKUs, base EUR price per case, case weight kg, cost ratio 2022
CATEGORIES = {
    "Coffee": (0.18, 38.0, 4.8, 0.52),
    "Confectionery": (0.20, 24.0, 3.6, 0.50),
    "Water": (0.10, 6.5, 9.0, 0.55),
    "Pet Care": (0.16, 29.0, 8.0, 0.50),
    "Dairy": (0.12, 18.0, 6.0, 0.60),
    "Culinary": (0.14, 15.0, 4.0, 0.48),
    "Infant Nutrition": (0.10, 46.0, 3.2, 0.42),
}

# Volume growth (RIG) targets: year effect + category + country, in % per year
RIG_YEAR = {2022: -1.5, 2023: -3.0, 2024: 0.0, 2025: 1.5, 2026: 2.0}   # compounding weekly, y/y effect ~ average of 2 years
RIG_CATEGORY = {"Coffee": 3.0, "Pet Care": 3.5, "Confectionery": -1.0, "Water": 0.0, "Dairy": -2.0,
                "Culinary": -0.5, "Infant Nutrition": -3.0}
RIG_COUNTRY = {"PL": 5.5, "ES": 5.0, "PT": 1.5, "GB": -1.5, "IT": 0.0, "DE": -0.5, "FR": -0.5,
               "NL": 0.5, "CH": 0.0, "BE": 0.0, "AT": 0.5, "SE": 1.0}
PRICE_PASS_THROUGH = 0.9      # share of food inflation passed into list prices (Jan and Jul price rounds)
# Extra category pricing on top of food inflation (real commodity spikes: cocoa 2024, arabica coffee 2024 to 2025)
EXTRA_PRICING = {("Confectionery", "2024-07-01"): 0.03, ("Coffee", "2025-01-01"): 0.07, ("Coffee", "2025-07-01"): 0.03}

# Story 4: one Polish distributor overstocks ahead of a promotion (sell-in spike, flat sell-out)
OVERSTOCK_WEEKS = (dt.date(2025, 10, 27), dt.date(2025, 11, 23))
OVERSTOCK_FACTOR = 3.2

# Fallback curves (used only when public files are missing, e.g. in tests). Food inflation y/y %.
FALLBACK_FOOD_INFLATION = {2022: 11.0, 2023: 9.0, 2024: 2.0, 2025: 2.6, 2026: 2.4}
