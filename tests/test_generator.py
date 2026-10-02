"""Unit tests for the synthetic data generator (pure Python, no Spark, no cloud)."""
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "generator"))

import gen_master as gm  # noqa: E402
from config import CUSTOMERS_BY_CHANNEL, N_DISTRIBUTORS, N_PRODUCTS  # noqa: E402


def check_digit_ok(code: str) -> bool:
    d = [int(c) for c in code]
    return (sum(d[0:12:2]) + 3 * sum(d[1:12:2]) + d[12]) % 10 == 0


def test_ean13_check_digits_are_valid():
    codes = gm.ean13(np.arange(1000001, 1000101))
    assert all(len(c) == 13 and check_digit_ok(c) for c in codes)


def test_products_unique_keys_and_size():
    p = gm.products(np.random.default_rng(1))
    assert len(p) == N_PRODUCTS
    assert p["sku"].is_unique and p["ean"].is_unique
    assert (p["case_weight_kg"] > 0).all()


def test_customers_and_distributors():
    c = gm.customers(np.random.default_rng(1))
    assert len(c) == sum(CUSTOMERS_BY_CHANNEL.values())
    assert c["customer_id"].is_unique
    assert c["is_distributor"].sum() == N_DISTRIBUTORS
    assert (c.loc[c["is_distributor"], "channel"] == "Traditional trade").all()


def test_audit_log_matches_current_values():
    rng = np.random.default_rng(1)
    c = gm.customers(rng)
    cur, log = gm.customer_changes(rng, c)
    no_op = (log["old_value"] == log["new_value"]).mean()
    assert no_op < 0.05            # legacy ERPs log a few no-op updates; SCD2 must tolerate them
    last = log.sort_values("changed_at").groupby(["customer_id", "field_name"]).tail(1)
    cur = cur.set_index("customer_id")
    for r in last.itertuples():
        assert str(cur.at[r.customer_id, r.field_name]) == r.new_value


def test_price_list_is_contiguous_and_positive():
    rng = np.random.default_rng(1)
    p = gm.products(rng).head(10)
    prices = gm.price_list(rng, p)
    assert (prices["list_price_case"] > 0).all()
    for _, g in prices.sort_values("valid_from").groupby(["sku", "country_code"]):
        nxt = g["valid_from"].shift(-1).dropna()
        assert ((g["valid_to"].iloc[:-1] + np.timedelta64(1, "D")).values == nxt.values).all()
