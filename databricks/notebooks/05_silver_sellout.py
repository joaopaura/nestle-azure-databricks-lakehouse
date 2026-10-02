# Databricks notebook source
# MAGIC %md
# MAGIC # 05 | Silver: distributor sell-out (cleaning the dirty files)
# MAGIC Three layouts are mapped to one schema, then each row is validated. Rejected rows are **kept with a reason**
# MAGIC in `ops.sellout_rejected` (nothing is silently dropped); exact duplicates (files resent) are removed.
# MAGIC | Problem in the files | Rule |
# MAGIC |---|---|
# MAGIC | Dates `dd.MM.yyyy`, `yyyy-MM-dd`, `MM/dd/yyyy`, empty | parse per layout, empty -> `INVALID_DATE` |
# MAGIC | Quantities `1.234` (thousand dots), `384,0` (decimal comma), `n/a` | layout-aware parsing, `n/a` -> `INVALID_QUANTITY` |
# MAGIC | EAN `7.60901E+12` (Excel), `7609 01...` (spaces), foreign EANs | strip spaces; scientific -> `EAN_SCIENTIFIC_NOTATION`; unknown -> `UNKNOWN_EAN` |
# MAGIC | Units vs cases (`EA`, `pcs`, `units`, `CS`, `cases`, `CSE`) | convert units to cases with `units_per_case` |
# MAGIC | Country spellings (`Polska`, `Deutschland`, `UK`...) | `silver.ref_country_alias` |
# MAGIC | Distributor id `c-000751` | upper case, remove `-` |
# MAGIC | Negative quantities | `NEGATIVE_QUANTITY` |

# COMMAND ----------

# MAGIC %run ./_utils

# COMMAND ----------

B = "nestle_dev.bronze"
cols = ["layout", "distributor_raw", "week_raw", "ean_raw", "qty_raw", "uom_raw", "stock_raw", "country_raw", "_source_file"]
a = spark.table(f"{B}.sellout_layout_a").select(
    F.lit("A"), "Distributor", "Week_Ending", "EAN", "Qty_Sold", "UoM", "Closing_Stock", "Country", "_source_file").toDF(*cols)
b = spark.table(f"{B}.sellout_layout_b").select(
    F.lit("B"), "distributor_id", "week_end_date", "gtin", "units_sold", "unit", "stock_on_hand", "country", "_source_file").toDF(*cols)
j = spark.table(f"{B}.sellout_layout_json").select(
    F.lit("JSON"), "dist", "period_end", "barcode", "sold", "uom", "stock", "market", "_source_file").toDF(*cols)
raw = a.unionByName(b).unionByName(j)

week_fmt = F.when(F.col("layout") == "A", "dd.MM.yyyy").when(F.col("layout") == "B", "yyyy-MM-dd").otherwise("MM/dd/yyyy")
parsed = (raw
  .withColumn("distributor_id", F.upper(F.regexp_replace(F.trim("distributor_raw"), "-", "")))
  .withColumn("week_ending", F.expr("""CASE layout WHEN 'A' THEN try_to_timestamp(week_raw, 'dd.MM.yyyy')
                                                   WHEN 'B' THEN try_to_timestamp(week_raw, 'yyyy-MM-dd')
                                                   ELSE try_to_timestamp(week_raw, 'MM/dd/yyyy') END""").cast("date"))
  .withColumn("ean", F.regexp_replace(F.trim("ean_raw"), " ", ""))
  .withColumn("ean_scientific", F.upper("ean").contains("E+"))
  .withColumn("qty", F.expr("CASE layout WHEN 'A' THEN try_cast(replace(qty_raw, '.', '') AS DOUBLE) ELSE try_cast(qty_raw AS DOUBLE) END"))
  .withColumn("stock", F.expr("CASE layout WHEN 'A' THEN try_cast(replace(stock_raw, ',', '.') AS DOUBLE) ELSE try_cast(stock_raw AS DOUBLE) END"))
  .withColumn("uom", F.expr("""CASE WHEN upper(trim(uom_raw)) IN ('EA', 'PCS', 'UNITS') THEN 'units'
                                    WHEN upper(trim(uom_raw)) IN ('CS', 'CASES', 'CSE') THEN 'cases' END"""))
  .withColumn("alias", F.upper(F.trim("country_raw"))))

products = spark.table("nestle_dev.silver.products_scd2").filter("is_current").select("ean", "sku", "units_per_case", "category")
aliases = spark.table("nestle_dev.silver.ref_country_alias")
dists = spark.table("nestle_dev.silver.customers_scd2").filter("is_current AND is_distributor") \
             .select(F.col("customer_id").alias("distributor_id"), F.col("country_code").alias("distributor_country"))

df = (parsed.join(F.broadcast(products), "ean", "left")
            .join(F.broadcast(aliases), "alias", "left")
            .join(F.broadcast(dists), "distributor_id", "left")
            .withColumn("reject_reason", F.expr("""CASE
                WHEN distributor_country IS NULL THEN 'UNKNOWN_DISTRIBUTOR'
                WHEN week_ending IS NULL THEN 'INVALID_DATE'
                WHEN ean_scientific THEN 'EAN_SCIENTIFIC_NOTATION'
                WHEN sku IS NULL THEN 'UNKNOWN_EAN'
                WHEN qty IS NULL THEN 'INVALID_QUANTITY'
                WHEN qty < 0 THEN 'NEGATIVE_QUANTITY'
                WHEN uom IS NULL THEN 'UNKNOWN_UOM'
                WHEN country_code IS NULL THEN 'UNKNOWN_COUNTRY'
                END""")))

# COMMAND ----------

started = now()
total = df.count()
(df.filter("reject_reason IS NOT NULL")
   .select("layout", "reject_reason", "distributor_raw", "week_raw", "ean_raw", "qty_raw", "uom_raw", "country_raw", "_source_file",
           F.current_timestamp().alias("_rejected_at"))
   .write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("nestle_dev.ops.sellout_rejected"))
rejected = spark.table("nestle_dev.ops.sellout_rejected").count()
log_step("silver", "sellout", "nestle_dev.ops.sellout_rejected", rejected, started)

started = now()
valid = (df.filter("reject_reason IS NULL")
           .withColumn("qty_cases", F.round(F.when(F.col("uom") == "units", F.col("qty") / F.col("units_per_case")).otherwise(F.col("qty")), 3))
           .withColumn("stock_cases", F.round(F.when(F.col("uom") == "units", F.col("stock") / F.col("units_per_case")).otherwise(F.col("stock")), 3))
           .select("distributor_id", "country_code", "week_ending", "sku", "ean", "category", "qty_cases", "stock_cases",
                   F.col("uom").alias("reported_uom"), "layout", "_source_file"))
before_dedup = valid.count()
(valid.dropDuplicates(["distributor_id", "week_ending", "sku", "qty_cases", "stock_cases"])
      .withColumn("_processed_at", F.current_timestamp())
      .write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("nestle_dev.silver.sellout_weekly"))
spark.sql("ALTER TABLE nestle_dev.silver.sellout_weekly CLUSTER BY (week_ending)")
clean = table_rows("nestle_dev.silver.sellout_weekly")
log_step("silver", "sellout", "nestle_dev.silver.sellout_weekly", clean, started)

# COMMAND ----------

dq_check("silver", "sellout_weekly", "rows_rejected_with_reason", rejected, total, threshold_pct=2.0)
dq_check("silver", "sellout_weekly", "duplicate_rows_removed", before_dedup - clean, before_dedup, threshold_pct=2.0)
dq_check("silver", "sellout_weekly", "unique_distributor_week_sku",
         clean - spark.table("nestle_dev.silver.sellout_weekly").select("distributor_id", "week_ending", "sku").distinct().count(), clean)

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT reject_reason, layout, count(*) AS rows
# MAGIC FROM nestle_dev.ops.sellout_rejected
# MAGIC GROUP BY ALL ORDER BY rows DESC
