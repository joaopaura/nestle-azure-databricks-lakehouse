# Databricks notebook source
# MAGIC %md
# MAGIC # 10 | POS / e-commerce event stream: Auto Loader + MERGE (incremental, exactly-once)
# MAGIC Simulated stream of JSON-lines files (4 micro-batch files per day). Run with `trigger(availableNow=True)`:
# MAGIC each run processes **only new files**, then stops (no always-on cluster, cost-friendly).
# MAGIC * **Schema drift**: from 15 Sep the events carry a new field `device`. v1 used `addNewColumns`, which stops the stream
# MAGIC   on purpose and needs a restart (fine in a Job with retries, noisy in a notebook). v2 uses `rescue` mode: unknown
# MAGIC   fields land in `_rescued_data` and silver promotes `device` to a column, so the stream never stops
# MAGIC * **Duplicates** (same `event_id` sent twice) -> `MERGE` on `event_id` inserts each event once (idempotent)
# MAGIC * **Late events** (arrive in the next day's file) -> kept, flagged with `is_late`
# MAGIC Demo: run 1 with August files, upload September (`infra/upload_landing.ps1 -PosSeptember`), run 2 picks up only September.

# COMMAND ----------

# MAGIC %run ./_utils

# COMMAND ----------

CP = f"{CHECKPOINTS}/pos_events_v2"
SILVER_COLS = ["event_id", "event_type", "event_ts", "event_date", "retailer_id", "country", "ean", "quantity",
               "unit_price", "currency", "device", "file_date", "is_late", "_source_file", "_ingested_at"]


def path_exists(p: str) -> bool:
    try:
        dbutils.fs.ls(p)
        return True
    except Exception:
        return False


if not path_exists(CP):                 # first run of v2: start clean (v1 stopped on the schema change, see markdown)
    spark.sql("DROP TABLE IF EXISTS nestle_dev.bronze.pos_events")
    spark.sql("DROP TABLE IF EXISTS nestle_dev.silver.pos_events")


def upsert_batch(batch_df, batch_id):
    s = batch_df.sparkSession
    batch_df.write.mode("append").option("mergeSchema", "true").saveAsTable("nestle_dev.bronze.pos_events")
    # schema drift: `device` is a real column when inferred, otherwise it arrives in _rescued_data -> promote it
    device = F.col("device") if "device" in batch_df.columns else F.lit(None).cast("string")
    if "_rescued_data" in batch_df.columns:
        device = F.coalesce(device, F.get_json_object("_rescued_data", "$.device"))
    events = (batch_df.dropDuplicates(["event_id"])
                      .withColumn("device", device)
                      .withColumn("event_ts", F.to_timestamp("event_ts"))
                      .withColumn("event_date", F.to_date("event_ts"))
                      .withColumn("file_date", F.to_date(F.regexp_extract("_source_file", r"date=(\d{4}-\d{2}-\d{2})", 1)))
                      .withColumn("is_late", F.col("event_date") < F.col("file_date"))
                      .select(*SILVER_COLS))
    if not s.catalog.tableExists("nestle_dev.silver.pos_events"):
        events.write.saveAsTable("nestle_dev.silver.pos_events")
        return
    events.createOrReplaceTempView("pos_batch")
    s.sql("""MERGE INTO nestle_dev.silver.pos_events t
             USING pos_batch b ON t.event_id = b.event_id
             WHEN NOT MATCHED THEN INSERT *""")


started = now()
before = spark.table("nestle_dev.silver.pos_events").count() if spark.catalog.tableExists("nestle_dev.silver.pos_events") else 0
(spark.readStream.format("cloudFiles")
      .option("cloudFiles.format", "json")
      .option("cloudFiles.schemaLocation", f"{CP}/schema")
      .option("cloudFiles.schemaEvolutionMode", "rescue")     # new fields never stop the stream: they land in _rescued_data
      .option("cloudFiles.inferColumnTypes", "true")
      .load(f"{LANDING}/pos_stream/")
      .withColumn("_source_file", F.col("_metadata.file_path"))
      .withColumn("_ingested_at", F.current_timestamp())
      .writeStream.foreachBatch(upsert_batch)
      .option("checkpointLocation", f"{CP}/cp")
      .trigger(availableNow=True).start().awaitTermination())
log_step("silver", "pos_stream", "nestle_dev.silver.pos_events", table_rows("nestle_dev.silver.pos_events") - before, started)

# COMMAND ----------

bronze, silver = spark.table("nestle_dev.bronze.pos_events"), spark.table("nestle_dev.silver.pos_events")
nb, ns = bronze.count(), silver.count()
dq_check("silver", "pos_events", "duplicate_events_removed", nb - ns, nb, threshold_pct=1.0)
dq_check("silver", "pos_events", "late_events_flagged", silver.filter("is_late").count(), ns, threshold_pct=2.0)
dq_check("silver", "pos_events", "unique_event_id", ns - silver.select("event_id").distinct().count(), ns)

# COMMAND ----------

started = now()
spark.sql("""
CREATE OR REPLACE TABLE nestle_dev.gold.mart_pos_daily AS
SELECT e.event_date, e.country, e.retailer_id, p.category,
       sum(CASE WHEN e.event_type = 'purchase' THEN e.quantity ELSE -e.quantity END) AS net_units,
       round(sum(CASE WHEN e.event_type = 'purchase' THEN 1 ELSE -1 END * e.quantity * e.unit_price / fx.rate_per_eur), 2) AS net_revenue_eur,
       count(*) AS events,
       sum(CASE WHEN e.device IS NOT NULL THEN 1 ELSE 0 END) AS events_with_device
FROM nestle_dev.silver.pos_events e
LEFT JOIN nestle_dev.gold.dim_product p ON p.ean = e.ean
LEFT JOIN nestle_dev.silver.fx_rates_daily fx ON fx.currency = e.currency AND fx.rate_date = e.event_date
GROUP BY ALL""")
log_step("gold", "pos_stream", "nestle_dev.gold.mart_pos_daily", table_rows("nestle_dev.gold.mart_pos_daily"), started)

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT date_format(file_date, 'yyyy-MM') AS month, count(DISTINCT _source_file) AS files, count(*) AS events,
# MAGIC        sum(CASE WHEN is_late THEN 1 ELSE 0 END) AS late_events,
# MAGIC        sum(CASE WHEN device IS NOT NULL THEN 1 ELSE 0 END) AS events_with_new_field_device
# MAGIC FROM nestle_dev.silver.pos_events GROUP BY 1 ORDER BY 1
