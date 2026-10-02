# Databricks notebook source
# MAGIC %md
# MAGIC # 03 | Silver: reference data, SCD2 dimensions, public data
# MAGIC * `silver.dim_country` and `silver.ref_country_alias` (spellings found in distributor files)
# MAGIC * `silver.customers_scd2` and `silver.products_scd2`: **history rebuilt from the legacy ERP audit logs**.
# MAGIC   The ERP only keeps current values; `customer_changes` / `product_changes` record old and new values, so each
# MAGIC   version can be reconstructed with `valid_from`, `valid_to` and `is_current` (SCD type 2).
# MAGIC * `silver.fx_rates_daily` (ECB, forward-filled to every calendar day), `silver.food_inflation_monthly`, `silver.weather_daily`

# COMMAND ----------

# MAGIC %run ./_utils

# COMMAND ----------

import pandas as pd

REGION = {"DE": "Central Europe", "AT": "Central Europe", "CH": "Central Europe", "PL": "Central Europe",
          "FR": "Western Europe", "BE": "Western Europe", "NL": "Western Europe", "GB": "Western Europe",
          "IT": "Southern Europe", "ES": "Southern Europe", "PT": "Southern Europe", "SE": "Northern Europe"}
ALIASES = {"DE": ["Germany", "Deutschland", "DE", "GER"], "FR": ["France", "FR", "FRA"],
           "GB": ["United Kingdom", "UK", "GB", "Great Britain"], "IT": ["Italy", "Italia", "IT"],
           "ES": ["Spain", "España", "ES", "Espana"], "PL": ["Poland", "Polska", "PL", "POL"],
           "NL": ["Netherlands", "Nederland", "NL", "Holland"], "CH": ["Switzerland", "Schweiz", "CH", "Suisse"],
           "BE": ["Belgium", "Belgique", "BE"], "PT": ["Portugal", "PT"], "AT": ["Austria", "Österreich", "AT"],
           "SE": ["Sweden", "Sverige", "SE"]}

started = now()
countries = spark.table("nestle_dev.bronze.erp_countries").drop("_ingested_at", "_source")
region = spark.createDataFrame(list(REGION.items()), "country_code string, region string")
countries.join(region, "country_code").write.mode("overwrite").option("overwriteSchema", "true") \
         .saveAsTable("nestle_dev.silver.dim_country")
log_step("silver", "reference", "nestle_dev.silver.dim_country", table_rows("nestle_dev.silver.dim_country"), started)

started = now()
spark.createDataFrame([(a.upper(), c) for c, names in ALIASES.items() for a in names], "alias string, country_code string") \
     .write.mode("overwrite").saveAsTable("nestle_dev.silver.ref_country_alias")
log_step("silver", "reference", "nestle_dev.silver.ref_country_alias", table_rows("nestle_dev.silver.ref_country_alias"), started)

# COMMAND ----------

# MAGIC %md
# MAGIC ### SCD2 from the audit log
# MAGIC For a version starting at time `t`, a field takes: the `new_value` of the last change at or before `t`;
# MAGIC otherwise the `old_value` of the first change after `t`; otherwise the current ERP value.

# COMMAND ----------

def rebuild_history(cur: pd.DataFrame, log: pd.DataFrame, key: str, start_col: str, fields: list[str], derive=None) -> pd.DataFrame:
    rows = []
    log = log.sort_values("changed_at")
    by_key = {k: g for k, g in log.groupby(key)}
    for rec in cur.to_dict("records"):
        changes = by_key.get(rec[key])
        starts = [rec[start_col]] + ([] if changes is None else sorted(changes["changed_at"].unique()))
        for i, s in enumerate(starts):
            v = dict(rec)
            if changes is not None:
                for f in fields:
                    fc = changes[changes["field_name"] == f]
                    past, future = fc[fc["changed_at"] <= s], fc[fc["changed_at"] > s]
                    if len(past):
                        v[f] = past.iloc[-1]["new_value"]
                    elif len(future):
                        v[f] = future.iloc[0]["old_value"]
                if derive:
                    v = derive(v, rec)
            v["valid_from"] = pd.Timestamp(s)
            v["valid_to"] = pd.Timestamp(starts[i + 1]) if i + 1 < len(starts) else pd.Timestamp("9999-12-31")
            v["is_current"] = i + 1 == len(starts)
            v["version"] = i + 1
            rows.append(v)
    return pd.DataFrame(rows)

# COMMAND ----------

started = now()
cur = spark.table("nestle_dev.bronze.erp_customers").drop("_ingested_at", "_source").toPandas()
log = spark.table("nestle_dev.bronze.erp_customer_changes").drop("_ingested_at", "_source").toPandas()
TYPE_OF_CHANNEL = {"Modern trade": "Retail chain", "Traditional trade": "Wholesaler"}


def derive_customer(v: dict, current: dict) -> dict:
    if v["channel"] != current["channel"]:                       # channel reclassification also changes the type
        v["customer_type"] = TYPE_OF_CHANNEL.get(v["channel"], v["customer_type"])
    v["credit_limit_eur"] = int(float(v["credit_limit_eur"]))
    return v


hist = rebuild_history(cur, log, "customer_id", "created_at",
                       ["customer_name", "channel", "key_account_manager", "credit_limit_eur"], derive_customer)
(spark.createDataFrame(hist)
      .withColumn("customer_sk", F.xxhash64("customer_id", "valid_from"))
      .write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("nestle_dev.silver.customers_scd2"))
log_step("silver", "scd2", "nestle_dev.silver.customers_scd2", table_rows("nestle_dev.silver.customers_scd2"), started)

# COMMAND ----------

started = now()
cur = spark.table("nestle_dev.bronze.erp_products").drop("_ingested_at", "_source").toPandas()
log = spark.table("nestle_dev.bronze.erp_product_changes").drop("_ingested_at", "_source").toPandas()
cur["valid_start"] = pd.Timestamp("2015-01-01")
cur["case_weight_kg"] = cur["case_weight_kg"].astype(float)      # DECIMAL from Azure SQL arrives as decimal.Decimal


def grams(size: str) -> float:
    return float(str(size).split()[0])


def derive_product(v: dict, current: dict) -> dict:
    """Shrinkflation: older versions had a bigger pack; name and case weight follow the pack size."""
    if v["pack_size"] != current["pack_size"]:
        v["product_name"] = current["product_name"].replace(current["pack_size"], v["pack_size"])
        v["case_weight_kg"] = round(current["case_weight_kg"] * grams(v["pack_size"]) / grams(current["pack_size"]), 2)
    return v


hist = rebuild_history(cur, log, "sku", "valid_start", ["pack_size"], derive_product).drop(columns=["valid_start"])
(spark.createDataFrame(hist)
      .withColumn("product_sk", F.xxhash64("sku", "valid_from"))
      .write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("nestle_dev.silver.products_scd2"))
log_step("silver", "scd2", "nestle_dev.silver.products_scd2", table_rows("nestle_dev.silver.products_scd2"), started)

# COMMAND ----------

# Expectations on the SCD2 dimensions
for t, k in [("customers_scd2", "customer_id"), ("products_scd2", "sku")]:
    d = spark.table(f"nestle_dev.silver.{t}")
    keys = d.select(k).distinct().count()
    bad_current = d.groupBy(k).agg(F.sum(F.col("is_current").cast("int")).alias("n")).filter("n <> 1").count()
    overlaps = (d.alias("a").join(d.alias("b"), (F.col(f"a.{k}") == F.col(f"b.{k}")) & (F.col("a.version") < F.col("b.version"))
                                  & (F.col("a.valid_to") > F.col("b.valid_from"))).count())
    dq_check("silver", t, "exactly_one_current_row", bad_current, keys)
    dq_check("silver", t, "no_overlapping_versions", overlaps, keys)

# COMMAND ----------

# Public data
started = now()
fx = spark.table("nestle_dev.bronze.public_fx_rates_daily").select(
    F.to_date("rate_date").alias("rate_date"), "currency", F.col("rate_per_eur").cast("double").alias("rate_per_eur"))
cal = (spark.sql("SELECT explode(sequence(DATE'2021-12-01', DATE'2026-09-30', INTERVAL 1 DAY)) AS rate_date")
            .crossJoin(fx.select("currency").distinct()))
w = Window.partitionBy("currency").orderBy("rate_date").rowsBetween(Window.unboundedPreceding, 0)
filled = (cal.join(fx, ["rate_date", "currency"], "left")
             .withColumn("is_filled", F.col("rate_per_eur").isNull())
             .withColumn("rate_per_eur", F.last("rate_per_eur", ignorenulls=True).over(w)))
eur = spark.sql("SELECT explode(sequence(DATE'2021-12-01', DATE'2026-09-30', INTERVAL 1 DAY)) AS rate_date") \
           .select("rate_date", F.lit("EUR").alias("currency"), F.lit(1.0).alias("rate_per_eur"), F.lit(False).alias("is_filled"))
filled.unionByName(eur).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("nestle_dev.silver.fx_rates_daily")
log_step("silver", "public_data", "nestle_dev.silver.fx_rates_daily", table_rows("nestle_dev.silver.fx_rates_daily"), started)

started = now()
w12 = Window.partitionBy("country_code").orderBy("month")
(spark.table("nestle_dev.bronze.public_food_inflation_monthly")
      .select("country_code", F.to_date(F.concat("month", F.lit("-01"))).alias("month"),
              F.col("index_value").cast("double").alias("food_index_2015"), "source")
      .withColumn("food_inflation_yoy_pct", F.round((F.col("food_index_2015") / F.lag("food_index_2015", 12).over(w12) - 1) * 100, 2))
      .write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("nestle_dev.silver.food_inflation_monthly"))
log_step("silver", "public_data", "nestle_dev.silver.food_inflation_monthly", table_rows("nestle_dev.silver.food_inflation_monthly"), started)

started = now()
(spark.table("nestle_dev.bronze.public_weather_daily")
      .select("country_code", "city", F.to_date("weather_date").alias("weather_date"),
              F.col("temperature_2m_mean").cast("double").alias("temp_mean_c"),
              F.col("temperature_2m_max").cast("double").alias("temp_max_c"),
              F.col("precipitation_sum").cast("double").alias("precipitation_mm"))
      .write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("nestle_dev.silver.weather_daily"))
log_step("silver", "public_data", "nestle_dev.silver.weather_daily", table_rows("nestle_dev.silver.weather_daily"), started)

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Example: a customer reclassified from Traditional trade to Modern trade keeps both versions
# MAGIC SELECT customer_id, version, customer_name, channel, customer_type, key_account_manager, valid_from, valid_to, is_current
# MAGIC FROM nestle_dev.silver.customers_scd2
# MAGIC WHERE customer_id IN (SELECT customer_id FROM nestle_dev.silver.customers_scd2 WHERE version > 1 LIMIT 3)
# MAGIC ORDER BY customer_id, version
