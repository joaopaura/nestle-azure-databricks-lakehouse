# Databricks notebook source
# MAGIC %md
# MAGIC # 07 | Migration reconciliation: legacy ERP (Azure SQL) vs lakehouse (Delta)
# MAGIC Three levels of evidence that the migration is complete and correct:
# MAGIC 1. **Row counts** per table (source via Lakehouse Federation vs bronze)
# MAGIC 2. **Content hashes**: order-independent checksum of every column of every row (sum of `xxhash64`)
# MAGIC 3. **Business totals**: net sales and volume by year and currency, source vs gold, using the same reporting rule
# MAGIC    (cancelled and soft-deleted orders excluded). A naive total (all orders) is shown to quantify the trap.
# MAGIC Results go to `ops.reconciliation_results` (PASS / FAIL) and feed the Platform page.

# COMMAND ----------

# MAGIC %run ./_utils

# COMMAND ----------

spark.sql("""
CREATE TABLE IF NOT EXISTS nestle_dev.ops.reconciliation_results (
  run_id STRING, check_level STRING, object_name STRING, check_name STRING, source_value DOUBLE, target_value DOUBLE,
  difference DOUBLE, status STRING, checked_at TIMESTAMP)
COMMENT 'Azure SQL (legacy ERP) vs Delta lakehouse reconciliation'
""")
results = []


def record(level: str, obj: str, check: str, src: float, tgt: float, tolerance: float = 0.0) -> None:
    diff = float(tgt) - float(src)
    status = "PASS" if abs(diff) <= tolerance else "FAIL"
    results.append((RUN_ID, level, obj, check, float(src), float(tgt), diff, status, now()))
    print(f"{status:<5} {level:<9} {obj:<28} {check:<32} source {src:>20,.2f}  target {tgt:>20,.2f}  diff {diff:,.2f}")

# COMMAND ----------

TABLES = ["countries", "products", "customers", "price_list", "standard_cost", "customer_changes", "product_changes",
          "promotions", "sales_orders", "sales_order_lines", "returns"]
for t in TABLES:
    src = spark.table(f"erp_legacy_catalog.erp.{t}")
    tgt = spark.table(f"nestle_dev.bronze.erp_{t}").drop("_ingested_at", "_source")
    record("1_counts", t, "row_count", src.count(), tgt.count())
    cols = sorted(src.columns)
    h = lambda df: df.select(F.sum(F.xxhash64(*[F.col(c).cast("string") for c in cols]).cast("decimal(38,0)")).alias("h")).first()["h"] or 0
    record("2_hash", t, "content_checksum", h(src), h(tgt.select(*cols)))

# COMMAND ----------

# Business totals: source computed with the reporting rule vs gold
src_orders = spark.table("erp_legacy_catalog.erp.sales_orders")
src_lines = spark.table("erp_legacy_catalog.erp.sales_order_lines")
src = (src_lines.join(src_orders, "order_id")
       .withColumn("year", F.year("order_date"))
       .withColumn("reportable", (~F.col("is_deleted").cast("boolean")) & (F.col("order_status") != "Cancelled")))
src_rep = src.filter("reportable").groupBy("year", "currency").agg(F.sum("net_amount").alias("net_lc"), F.sum("qty_cases").alias("cases"))
src_all = src.groupBy("year", "currency").agg(F.sum("net_amount").alias("net_lc"))
gold = (spark.table("nestle_dev.gold.fact_sales").withColumn("year", F.year("order_date"))
        .groupBy("year", "currency").agg(F.sum("net_amount_lc").alias("net_lc"), F.sum("qty_cases").alias("cases")))


# COMMAND ----------

# Compare by year and currency (net sales in local currency + cases), then quantify the naive-total trap
s_tot = {(r["year"], r["currency"]): r for r in src_rep.collect()}
g_tot = {(r["year"], r["currency"]): r for r in gold.collect()}
a_tot = {(r["year"], r["currency"]): r for r in src_all.collect()}
for k in sorted(set(s_tot) | set(g_tot)):
    s, g = s_tot.get(k), g_tot.get(k)
    record("3_business", f"{k[0]} {k[1]}", "net_sales_local_currency", s["net_lc"] if s else 0, g["net_lc"] if g else 0, tolerance=0.01)
    record("3_business", f"{k[0]} {k[1]}", "cases", s["cases"] if s else 0, g["cases"] if g else 0)
naive = sum(float(r["net_lc"]) for r in a_tot.values() if r["currency"] == "EUR")
correct = sum(float(r["net_lc"]) for r in s_tot.values() if r["currency"] == "EUR")
print(f"\nTrap quantified (EUR markets): a naive sum of all orders overstates net sales by "
      f"{naive - correct:,.0f} EUR ({100 * (naive / correct - 1):.2f}%) because of cancelled and soft-deleted orders.")

# COMMAND ----------

spark.createDataFrame(results, "run_id string, check_level string, object_name string, check_name string, source_value double, "
                               "target_value double, difference double, status string, checked_at timestamp") \
     .write.mode("append").saveAsTable("nestle_dev.ops.reconciliation_results")
log_step("ops", "reconciliation", "nestle_dev.ops.reconciliation_results", len(results), now())

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT check_level, count(*) AS checks, sum(CASE WHEN status = 'PASS' THEN 1 ELSE 0 END) AS passed,
# MAGIC        round(100 * avg(CASE WHEN status = 'PASS' THEN 1 ELSE 0 END), 1) AS pass_rate_pct
# MAGIC FROM nestle_dev.ops.reconciliation_results
# MAGIC WHERE run_id = (SELECT run_id FROM nestle_dev.ops.reconciliation_results ORDER BY checked_at DESC LIMIT 1)
# MAGIC GROUP BY check_level ORDER BY check_level
