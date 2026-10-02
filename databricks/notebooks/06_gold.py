# Databricks notebook source
# MAGIC %md
# MAGIC # 06 | Gold: dimensions + KPI marts for Power BI and the forecast
# MAGIC | Table | Grain | Used by |
# MAGIC |---|---|---|
# MAGIC | `dim_date`, `dim_country`, `dim_product`, `dim_customer` | one row per member (current version, no PII) | all pages |
# MAGIC | `fact_sales` | order line (reportable orders only) | drill-down, reconciliation |
# MAGIC | `mart_sales_monthly` | month x country x channel x SKU | Commercial page (net sales, OG, RIG, pricing, margin) |
# MAGIC | `mart_sellin_sellout_weekly` | week x distributor x category | Demand & Sell-out page |
# MAGIC | `mart_promo_performance` | promotion | promo uplift |
# MAGIC | `mart_demand_weekly` | week x country x category (+ real weather and inflation) | ML forecast |
# MAGIC | `platform_table_counts` | table | Platform & Data Quality page |
# MAGIC **Organic growth** = growth at constant FX (local currency converted at the 2022 average ECB rate).
# MAGIC RIG = volume growth (tonnes); Pricing = OG - RIG; FX effect = reported growth - OG.

# COMMAND ----------

# MAGIC %run ./_utils

# COMMAND ----------

def build(name: str, sql: str) -> None:
    started = now()
    spark.sql(f"CREATE OR REPLACE TABLE nestle_dev.gold.{name} AS {sql}")
    log_step("gold", "marts", f"nestle_dev.gold.{name}", table_rows(f"nestle_dev.gold.{name}"), started)

REPORTABLE = "NOT is_deleted AND order_status <> 'Cancelled'"

# COMMAND ----------

build("dim_date", """
SELECT d AS date, year(d) AS year, quarter(d) AS quarter, month(d) AS month, date_format(d, 'MMM') AS month_name,
       date_trunc('MONTH', d)::date AS month_start, date_trunc('WEEK', d)::date AS week_start,
       weekofyear(d) AS iso_week, dayofweek(d) AS day_of_week, concat(year(d), '-Q', quarter(d)) AS year_quarter
FROM (SELECT explode(sequence(DATE'2022-01-01', DATE'2026-12-31', INTERVAL 1 DAY)) AS d)""")

build("dim_country", """
SELECT c.country_code, c.country_name, c.currency, c.region, c.capital
FROM nestle_dev.silver.dim_country c""")

build("dim_product", """
SELECT sku, product_name, brand, category, subcategory, pack_size, units_per_case, case_weight_kg, ean, status,
       launch_date, discontinued_date
FROM nestle_dev.silver.products_scd2 WHERE is_current""")

build("dim_customer", """
SELECT customer_id, customer_name, country_code, channel, customer_type, key_account_manager, is_distributor
FROM nestle_dev.silver.customers_scd2 WHERE is_current""")

# COMMAND ----------

build("fact_sales", f"""
SELECT order_id, line_no, order_date, customer_id, customer_sk, country_code, channel, sku, product_sk, category,
       qty_cases, volume_kg, currency, net_amount_lc, gross_amount_eur, net_amount_eur, cogs_eur, is_promo, promo_id
FROM nestle_dev.silver.sales_order_lines WHERE {REPORTABLE}""")
spark.sql("ALTER TABLE nestle_dev.gold.fact_sales CLUSTER BY (order_date)")

build("mart_sales_monthly", f"""
WITH base_fx AS (
  SELECT currency, avg(rate_per_eur) AS rate_2022
  FROM nestle_dev.silver.fx_rates_daily WHERE year(rate_date) = 2022 AND NOT is_filled GROUP BY currency)
SELECT date_trunc('MONTH', s.order_date)::date AS month_start, s.country_code, s.channel, s.sku, s.category,
       sum(s.qty_cases) AS cases,
       round(sum(s.volume_kg) / 1000, 3) AS volume_t,
       round(sum(s.gross_amount_eur), 2) AS gross_sales_eur,
       round(sum(s.net_amount_eur), 2) AS net_sales_eur,
       round(sum(s.net_amount_lc / b.rate_2022), 2) AS net_sales_cfx_eur,
       round(sum(s.cogs_eur), 2) AS cogs_eur,
       round(sum(CASE WHEN s.is_promo THEN s.net_amount_eur ELSE 0 END), 2) AS promo_net_sales_eur,
       count(*) AS order_lines
FROM nestle_dev.silver.sales_order_lines s JOIN base_fx b ON b.currency = s.currency
WHERE {REPORTABLE}
GROUP BY ALL""")

# COMMAND ----------

build("mart_sellin_sellout_weekly", f"""
WITH si AS (
  SELECT date_add(date_trunc('WEEK', s.order_date)::date, 6) AS week_ending, s.customer_id AS distributor_id, s.category,
         sum(s.qty_cases) AS sell_in_cases, sum(s.net_amount_eur) AS sell_in_eur
  FROM nestle_dev.silver.sales_order_lines s
  JOIN nestle_dev.gold.dim_customer c ON c.customer_id = s.customer_id AND c.is_distributor
  WHERE {REPORTABLE.replace('is_deleted', 's.is_deleted')}
  GROUP BY ALL),
so AS (
  SELECT week_ending, distributor_id, category, sum(qty_cases) AS sell_out_cases, sum(stock_cases) AS stock_cases
  FROM nestle_dev.silver.sellout_weekly GROUP BY ALL),
j AS (
  SELECT coalesce(si.week_ending, so.week_ending) AS week_ending, coalesce(si.distributor_id, so.distributor_id) AS distributor_id,
         coalesce(si.category, so.category) AS category,
         coalesce(si.sell_in_cases, 0) AS sell_in_cases, coalesce(si.sell_in_eur, 0) AS sell_in_eur,
         coalesce(so.sell_out_cases, 0) AS sell_out_cases, so.stock_cases
  FROM si FULL OUTER JOIN so ON si.week_ending = so.week_ending AND si.distributor_id = so.distributor_id AND si.category = so.category)
SELECT j.*, c.country_code, c.customer_name AS distributor_name,
       avg(sell_out_cases) OVER (PARTITION BY j.distributor_id, j.category ORDER BY j.week_ending
                                 ROWS BETWEEN 3 PRECEDING AND CURRENT ROW) AS sell_out_4w_avg,
       round(stock_cases / nullif(avg(sell_out_cases) OVER (PARTITION BY j.distributor_id, j.category ORDER BY j.week_ending
                                 ROWS BETWEEN 3 PRECEDING AND CURRENT ROW), 0), 2) AS stock_cover_weeks
FROM j JOIN nestle_dev.gold.dim_customer c ON c.customer_id = j.distributor_id""")

# COMMAND ----------

build("mart_promo_performance", f"""
WITH wk AS (
  SELECT customer_id, category, date_trunc('WEEK', order_date)::date AS week_start,
         sum(qty_cases) AS cases, sum(net_amount_eur) AS net_eur, sum(cogs_eur) AS cogs_eur
  FROM nestle_dev.silver.sales_order_lines WHERE {REPORTABLE} GROUP BY ALL),
agg AS (
  SELECT p.promo_id, p.customer_id, p.category, p.mechanic, p.discount_pct, p.start_date, p.end_date, p.duration_weeks,
         p.planned_uplift_pct,
         sum(CASE WHEN wk.week_start BETWEEN p.start_date AND p.end_date THEN wk.cases END) AS promo_cases,
         sum(CASE WHEN wk.week_start BETWEEN p.start_date AND p.end_date THEN wk.net_eur END) AS promo_net_eur,
         sum(CASE WHEN wk.week_start BETWEEN p.start_date AND p.end_date THEN wk.cogs_eur END) AS promo_cogs_eur,
         sum(CASE WHEN wk.week_start < p.start_date THEN wk.cases END) / 8 * p.duration_weeks AS baseline_cases,
         sum(CASE WHEN wk.week_start < p.start_date THEN wk.net_eur END) / 8 * p.duration_weeks AS baseline_net_eur
  FROM nestle_dev.silver.promotions p
  JOIN wk ON wk.customer_id = p.customer_id AND wk.category = p.category
         AND wk.week_start BETWEEN date_sub(p.start_date, 56) AND p.end_date
  GROUP BY ALL)
SELECT a.*, c.country_code, c.channel,
       round(100 * (promo_cases / nullif(baseline_cases, 0) - 1), 1) AS uplift_pct,
       round(promo_net_eur - baseline_net_eur, 2) AS incremental_net_eur,
       round(promo_net_eur * discount_pct / (1 - discount_pct), 2) AS discount_cost_eur,
       round((promo_net_eur - promo_cogs_eur - baseline_net_eur * (1 - promo_cogs_eur / nullif(promo_net_eur, 0)))
             / nullif(promo_net_eur * discount_pct / (1 - discount_pct), 0), 2) AS promo_roi
FROM agg a JOIN nestle_dev.gold.dim_customer c ON c.customer_id = a.customer_id
WHERE baseline_cases > 0""")

# COMMAND ----------

build("mart_demand_weekly", f"""
WITH s AS (
  SELECT date_trunc('WEEK', order_date)::date AS week_start, country_code, category,
         round(sum(volume_kg) / 1000, 3) AS volume_t, round(sum(net_amount_eur), 2) AS net_sales_eur,
         round(avg(CASE WHEN is_promo THEN 1.0 ELSE 0.0 END), 4) AS promo_line_share
  FROM nestle_dev.silver.sales_order_lines WHERE {REPORTABLE} GROUP BY ALL),
w AS (
  SELECT date_trunc('WEEK', weather_date)::date AS week_start, country_code,
         round(avg(temp_mean_c), 2) AS temp_mean_c, round(sum(precipitation_mm), 1) AS precipitation_mm
  FROM nestle_dev.silver.weather_daily GROUP BY ALL)
SELECT s.*, w.temp_mean_c, w.precipitation_mm, i.food_inflation_yoy_pct
FROM s
LEFT JOIN w ON w.week_start = s.week_start AND w.country_code = s.country_code
LEFT JOIN nestle_dev.silver.food_inflation_monthly i
  ON i.country_code = s.country_code AND i.month = date_trunc('MONTH', s.week_start)::date""")

# COMMAND ----------

# Row counts per layer for the Platform page
started = now()
rows = []
for layer in ["bronze", "silver", "gold"]:
    for t in spark.sql(f"SHOW TABLES IN nestle_dev.{layer}").collect():
        if not t.isTemporary:
            rows.append((layer, t.tableName, spark.table(f"nestle_dev.{layer}.{t.tableName}").count()))
spark.createDataFrame(rows, "layer string, table_name string, row_count bigint") \
     .withColumn("counted_at", F.current_timestamp()) \
     .write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("nestle_dev.gold.platform_table_counts")
log_step("gold", "platform", "nestle_dev.gold.platform_table_counts", len(rows), started)

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Organic growth bridge, Jan to Sep of each year (constant FX). Pricing = OG - RIG.
# MAGIC WITH y AS (
# MAGIC   SELECT year(month_start) AS year, sum(net_sales_eur) AS ns, sum(net_sales_cfx_eur) AS ns_cfx, sum(volume_t) AS vol
# MAGIC   FROM nestle_dev.gold.mart_sales_monthly WHERE month(month_start) <= 9 GROUP BY 1)
# MAGIC SELECT year, round(ns / 1e6, 1) AS net_sales_eur_m,
# MAGIC        round(100 * (ns_cfx / lag(ns_cfx) OVER (ORDER BY year) - 1), 1) AS organic_growth_pct,
# MAGIC        round(100 * (vol / lag(vol) OVER (ORDER BY year) - 1), 1) AS rig_pct,
# MAGIC        round(100 * (ns_cfx / lag(ns_cfx) OVER (ORDER BY year) - vol / lag(vol) OVER (ORDER BY year)), 1) AS pricing_pct,
# MAGIC        round(100 * (ns / lag(ns) OVER (ORDER BY year) - ns_cfx / lag(ns_cfx) OVER (ORDER BY year)), 1) AS fx_effect_pct
# MAGIC FROM y ORDER BY year
