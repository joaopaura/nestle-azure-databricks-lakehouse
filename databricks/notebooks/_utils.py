# Databricks notebook source
# MAGIC %md
# MAGIC # _utils | shared helpers (run with `%run ./_utils`)
# MAGIC Run log in `nestle_dev.ops.run_log`: one row per step, used by the Platform & Data Quality page.

# COMMAND ----------

import datetime as dt
import uuid

from pyspark.sql import functions as F

CATALOG = "nestle_dev"
LANDING = "/Volumes/nestle_dev/bronze/landing"
CHECKPOINTS = "/Volumes/nestle_dev/ops/checkpoints"
RUN_ID = str(uuid.uuid4())

spark.sql(f"USE CATALOG {CATALOG}")
spark.sql("CREATE VOLUME IF NOT EXISTS nestle_dev.ops.checkpoints COMMENT 'Auto Loader schemas and checkpoints'")
spark.sql("""
CREATE TABLE IF NOT EXISTS nestle_dev.ops.run_log (
  run_id STRING, layer STRING, step STRING, target_table STRING, rows_written BIGINT,
  started_at TIMESTAMP, ended_at TIMESTAMP, duration_s DOUBLE, status STRING, message STRING)
COMMENT 'One row per pipeline step (bronze, silver, gold, ops)'
""")


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def table_rows(table: str) -> int:
    return spark.table(table).count()


def log_step(layer: str, step: str, target: str, rows: int, started: dt.datetime,
             status: str = "SUCCESS", message: str | None = None) -> None:
    ended = now()
    row = [(RUN_ID, layer, step, target, int(rows), started, ended, (ended - started).total_seconds(), status, message)]
    spark.createDataFrame(row, "run_id string, layer string, step string, target_table string, rows_written bigint, "
                               "started_at timestamp, ended_at timestamp, duration_s double, status string, message string") \
         .write.mode("append").saveAsTable("nestle_dev.ops.run_log")
    print(f"{status:<8} {layer:<7} {target:<45} {rows:>12,} rows  {(ended - started).total_seconds():6.1f} s")
