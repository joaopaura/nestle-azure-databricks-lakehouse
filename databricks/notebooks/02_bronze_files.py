# Databricks notebook source
# MAGIC %md
# MAGIC # 02 | Bronze: distributor sell-out files + public data (Auto Loader)
# MAGIC Distributors send monthly files in three layouts. Auto Loader (`cloudFiles`, `availableNow`) ingests only new
# MAGIC files, keeps every column as STRING (cleaning happens in silver) and records the source file of each row.
# MAGIC | Layout | Files | Format |
# MAGIC |---|---|---|
# MAGIC | A | `sellout_C*.csv` | `;` separator, decimal comma, dd.mm.yyyy |
# MAGIC | B | `c0*.csv` | `,` separator, ISO dates, lower-case distributor id |
# MAGIC | J | `sellout_*.json` | JSON document with a `records` array, mm/dd/yyyy |

# COMMAND ----------

# MAGIC %run ./_utils

# COMMAND ----------

def autoload(name: str, fmt: str, glob: str, options: dict, explode_records: bool = False) -> None:
    started = now()
    target = f"nestle_dev.bronze.{name}"
    df = (spark.readStream.format("cloudFiles")
          .option("cloudFiles.format", fmt)
          .option("cloudFiles.schemaLocation", f"{CHECKPOINTS}/{name}/schema")
          .option("cloudFiles.inferColumnTypes", "false")
          .option("pathGlobFilter", glob)
          .options(**options)
          .load(f"{LANDING}/sellout/"))
    if explode_records:
        df = df.select("distributor", F.explode("records").alias("r"), "_metadata").select("distributor", "r.*", "_metadata")
    df = (df.withColumn("_source_file", F.col("_metadata.file_path"))
            .withColumn("_file_modified", F.col("_metadata.file_modification_time"))
            .withColumn("_ingested_at", F.current_timestamp())
            .drop("_metadata"))
    before = spark.table(target).count() if spark.catalog.tableExists(target) else 0
    (df.writeStream.option("checkpointLocation", f"{CHECKPOINTS}/{name}/cp")
       .option("mergeSchema", "true").trigger(availableNow=True).toTable(target).awaitTermination())
    log_step("bronze", "autoloader_sellout", target, table_rows(target) - before, started)


autoload("sellout_layout_a", "csv", "sellout_C*.csv", {"header": "true", "sep": ";"})
autoload("sellout_layout_b", "csv", "c0*.csv", {"header": "true", "sep": ","})
autoload("sellout_layout_json", "json", "sellout_*.json", {"multiLine": "true"}, explode_records=True)

# COMMAND ----------

# Public data (small, full reload): ECB FX, Eurostat / ONS food inflation, Open-Meteo weather
for name, file in [("public_fx_rates_daily", "fx_rates_daily.csv"),
                   ("public_food_inflation_monthly", "food_inflation_monthly.csv"),
                   ("public_weather_daily", "weather_daily.csv")]:
    started = now()
    target = f"nestle_dev.bronze.{name}"
    (spark.read.option("header", "true").csv(f"{LANDING}/public/{file}")
          .withColumn("_source_file", F.col("_metadata.file_path"))
          .withColumn("_ingested_at", F.current_timestamp())
          .write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(target))
    log_step("bronze", "public_data", target, table_rows(target), started)

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT 'A' AS layout, count(*) AS rows, count(DISTINCT _source_file) AS files FROM nestle_dev.bronze.sellout_layout_a
# MAGIC UNION ALL SELECT 'B', count(*), count(DISTINCT _source_file) FROM nestle_dev.bronze.sellout_layout_b
# MAGIC UNION ALL SELECT 'JSON', count(*), count(DISTINCT _source_file) FROM nestle_dev.bronze.sellout_layout_json
