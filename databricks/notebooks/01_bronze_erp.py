# Databricks notebook source
# MAGIC %md
# MAGIC # 01 | Bronze: legacy ERP (Azure SQL) via Lakehouse Federation
# MAGIC The legacy ERP lives in Azure SQL (`sqldb-nestle-erp`). Unity Catalog reaches it through the connection
# MAGIC `conn_nestle_erp` and the foreign catalog `erp_legacy` (read-only login `dbx_reader`, password kept in Unity Catalog).
# MAGIC Each table is copied as-is into `nestle_dev.bronze.erp_<table>` with ingestion metadata. Full reload (snapshot);
# MAGIC the source counts are compared again later in the reconciliation notebook.

# COMMAND ----------

# MAGIC %run ./_utils

# COMMAND ----------

TABLES = ["countries", "products", "customers", "price_list", "standard_cost", "customer_changes", "product_changes",
          "promotions", "sales_orders", "sales_order_lines", "returns"]

for t in TABLES:
    started = now()
    target = f"nestle_dev.bronze.erp_{t}"
    try:
        (spark.table(f"erp_legacy.erp.{t}")
              .withColumn("_ingested_at", F.current_timestamp())
              .withColumn("_source", F.lit(f"azure_sql/sqldb-nestle-erp/erp.{t}"))
              .write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(target))
        log_step("bronze", "erp_snapshot", target, table_rows(target), started)
    except Exception as e:  # keep going, the run log shows the failure
        log_step("bronze", "erp_snapshot", target, 0, started, "FAILED", str(e)[:500])

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT target_table, rows_written, duration_s, status
# MAGIC FROM nestle_dev.ops.run_log
# MAGIC WHERE step = 'erp_snapshot'
# MAGIC QUALIFY row_number() OVER (PARTITION BY target_table ORDER BY ended_at DESC) = 1
# MAGIC ORDER BY target_table
