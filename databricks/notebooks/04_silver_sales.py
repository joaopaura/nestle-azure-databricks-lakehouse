# Databricks notebook source
# MAGIC %md
# MAGIC # 04 | Silver: sell-in (orders, lines, returns, promotions)
# MAGIC `silver.sales_order_lines` = ERP lines + order header + customer and product **versions valid on the order date**
# MAGIC (SCD2 point-in-time join) + real ECB FX rate of the day + standard cost of the quarter.
# MAGIC * Amounts in local currency and in EUR; volume in kg uses the pack size valid at the time (shrinkflation-aware)
# MAGIC * Cancelled and soft-deleted orders are **kept and flagged** (gold decides what to report; reconciliation needs them)
# MAGIC * Liquid clustering on `order_date` for date-range queries

# COMMAND ----------

# MAGIC %run ./_utils

# COMMAND ----------

started = now()
spark.sql("""
CREATE OR REPLACE TABLE nestle_dev.silver.sales_order_lines
CLUSTER BY (order_date)
COMMENT 'Sell-in order lines, point-in-time customer/product versions, EUR at ECB daily rate'
AS
WITH o AS (
  SELECT order_id, customer_id, CAST(order_date AS DATE) AS order_date, currency, order_status,
         sales_channel, CAST(is_deleted AS BOOLEAN) AS is_deleted
  FROM nestle_dev.bronze.erp_sales_orders)
SELECT
  l.order_id, l.line_no, o.order_date, o.customer_id, c.customer_sk, c.country_code, o.sales_channel AS channel,
  l.sku, p.product_sk, p.category, p.subcategory, p.brand,
  CAST(l.qty_cases AS INT) AS qty_cases,
  o.currency,
  CAST(l.list_price_case AS DECIMAL(12,2)) AS list_price_case,
  CAST(l.discount_pct AS DECIMAL(6,4)) AS discount_pct,
  CAST(l.qty_cases * l.list_price_case AS DECIMAL(16,2)) AS gross_amount_lc,
  CAST(l.net_amount AS DECIMAL(16,2)) AS net_amount_lc,
  fx.rate_per_eur,
  CAST(l.qty_cases * l.list_price_case / fx.rate_per_eur AS DECIMAL(16,2)) AS gross_amount_eur,
  CAST(l.net_amount / fx.rate_per_eur AS DECIMAL(16,2)) AS net_amount_eur,
  CAST(l.qty_cases * sc.std_cost_eur_case AS DECIMAL(16,2)) AS cogs_eur,
  CAST(l.qty_cases * p.case_weight_kg AS DECIMAL(16,3)) AS volume_kg,
  l.promo_id,
  l.promo_id IS NOT NULL AS is_promo,
  o.order_status,
  o.is_deleted,
  current_timestamp() AS _processed_at
FROM nestle_dev.bronze.erp_sales_order_lines l
JOIN o ON o.order_id = l.order_id
LEFT JOIN nestle_dev.silver.customers_scd2 c
  ON c.customer_id = o.customer_id AND o.order_date >= c.valid_from AND o.order_date < c.valid_to
LEFT JOIN nestle_dev.silver.products_scd2 p
  ON p.sku = l.sku AND o.order_date >= p.valid_from AND o.order_date < p.valid_to
LEFT JOIN nestle_dev.silver.fx_rates_daily fx
  ON fx.currency = o.currency AND fx.rate_date = o.order_date
LEFT JOIN nestle_dev.bronze.erp_standard_cost sc
  ON sc.sku = l.sku AND sc.fiscal_quarter = concat(year(o.order_date), 'Q', quarter(o.order_date))
""")
log_step("silver", "sales", "nestle_dev.silver.sales_order_lines", table_rows("nestle_dev.silver.sales_order_lines"), started)

# COMMAND ----------

started = now()
spark.sql("""
CREATE OR REPLACE TABLE nestle_dev.silver.returns AS
SELECT r.return_id, r.order_id, r.line_no, CAST(r.return_date AS DATE) AS return_date, CAST(r.qty_cases AS INT) AS qty_cases,
       r.reason_code, CAST(r.credit_amount AS DECIMAL(16,2)) AS credit_amount_lc, o.currency,
       CAST(r.credit_amount / fx.rate_per_eur AS DECIMAL(16,2)) AS credit_amount_eur
FROM nestle_dev.bronze.erp_returns r
JOIN nestle_dev.bronze.erp_sales_orders o ON o.order_id = r.order_id
LEFT JOIN nestle_dev.silver.fx_rates_daily fx ON fx.currency = o.currency AND fx.rate_date = CAST(r.return_date AS DATE)
""")
log_step("silver", "sales", "nestle_dev.silver.returns", table_rows("nestle_dev.silver.returns"), started)

started = now()
spark.sql("""
CREATE OR REPLACE TABLE nestle_dev.silver.promotions AS
SELECT promo_id, customer_id, category, mechanic, CAST(discount_pct AS DECIMAL(5,4)) AS discount_pct,
       CAST(start_date AS DATE) AS start_date, CAST(end_date AS DATE) AS end_date, CAST(duration_weeks AS INT) AS duration_weeks,
       CAST(planned_uplift_pct AS DECIMAL(6,1)) AS planned_uplift_pct
FROM nestle_dev.bronze.erp_promotions
""")
log_step("silver", "sales", "nestle_dev.silver.promotions", table_rows("nestle_dev.silver.promotions"), started)

# COMMAND ----------

# Expectations
s = spark.table("nestle_dev.silver.sales_order_lines")
total = s.count()
bronze_lines = spark.table("nestle_dev.bronze.erp_sales_order_lines").count()
checks = s.agg(
    F.sum(F.col("net_amount_eur").isNull().cast("int")).alias("missing_fx"),
    F.sum(F.col("product_sk").isNull().cast("int")).alias("missing_product_version"),
    F.sum(F.col("customer_sk").isNull().cast("int")).alias("missing_customer_version"),
    F.sum(F.col("cogs_eur").isNull().cast("int")).alias("missing_standard_cost"),
    F.sum((F.col("qty_cases") <= 0).cast("int")).alias("non_positive_qty"),
    F.sum(F.col("is_deleted").cast("int")).alias("soft_deleted_orders"),
    F.sum((F.col("order_status") == "Cancelled").cast("int")).alias("cancelled_orders"),
).first().asDict()
dq_check("silver", "sales_order_lines", "orphan_lines_without_header", bronze_lines - total, bronze_lines)
dq_check("silver", "sales_order_lines", "unique_order_line", total - s.select("order_id", "line_no").distinct().count(), total)
for k in ["missing_fx", "missing_product_version", "missing_customer_version", "missing_standard_cost", "non_positive_qty"]:
    dq_check("silver", "sales_order_lines", k, checks[k], total)
dq_check("silver", "sales_order_lines", "soft_deleted_orders_flagged", checks["soft_deleted_orders"], total, threshold_pct=1.0)
dq_check("silver", "sales_order_lines", "cancelled_orders_flagged", checks["cancelled_orders"], total, threshold_pct=2.0)

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT year(order_date) AS year, count(*) AS lines,
# MAGIC        round(sum(net_amount_eur) / 1e6, 1) AS net_sales_eur_m,
# MAGIC        round(sum(volume_kg) / 1e6, 1) AS volume_kt,
# MAGIC        round(100 * (1 - sum(cogs_eur) / sum(net_amount_eur)), 1) AS gross_margin_pct
# MAGIC FROM nestle_dev.silver.sales_order_lines
# MAGIC WHERE NOT is_deleted AND order_status <> 'Cancelled'
# MAGIC GROUP BY 1 ORDER BY 1
