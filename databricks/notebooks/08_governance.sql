-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 08 | Governance with Unity Catalog
-- MAGIC * **Row-level security**: country managers only see their countries (`gold.fact_sales`, `gold.mart_sales_monthly`).
-- MAGIC   Access is data-driven through `ops.user_country_access` (user, country or `ALL`).
-- MAGIC * **Column masking**: customer contact data (PII) in silver is masked unless the user is in `ops.pii_readers`.
-- MAGIC * **Tags and comments**: layer / domain / PII classification for discovery and audit.
-- MAGIC * **Grants**: business users read gold only; bronze and silver stay with the data team.
-- MAGIC * **Lineage** is captured automatically by Unity Catalog (screenshots in `docs/`).
-- MAGIC Run after `06_gold` (re-creating a table removes its policies, so this notebook is part of the pipeline).

-- COMMAND ----------

USE CATALOG nestle_dev;

CREATE TABLE IF NOT EXISTS ops.user_country_access (user_email STRING, country_code STRING)
COMMENT 'Row-level security mapping: which countries each user may see (ALL = every country)';
CREATE TABLE IF NOT EXISTS ops.pii_readers (user_email STRING)
COMMENT 'Users allowed to see unmasked customer contact data';

MERGE INTO ops.user_country_access t
USING (SELECT current_user() AS user_email, 'ALL' AS country_code) s
ON t.user_email = s.user_email
WHEN NOT MATCHED THEN INSERT *;

-- COMMAND ----------

CREATE OR REPLACE FUNCTION ops.rf_country(country STRING)
RETURNS BOOLEAN
COMMENT 'Row filter: true when the current user may see this country'
RETURN EXISTS (SELECT 1 FROM nestle_dev.ops.user_country_access a
               WHERE a.user_email = current_user() AND (a.country_code = 'ALL' OR a.country_code = country));

CREATE OR REPLACE FUNCTION ops.mask_pii(value STRING)
RETURNS STRING
COMMENT 'Column mask: full value for PII readers, otherwise first character + ***'
RETURN CASE WHEN EXISTS (SELECT 1 FROM nestle_dev.ops.pii_readers r WHERE r.user_email = current_user()) THEN value
            WHEN value IS NULL THEN NULL
            ELSE concat(left(value, 1), '***') END;

-- COMMAND ----------

ALTER TABLE gold.fact_sales SET ROW FILTER ops.rf_country ON (country_code);
ALTER TABLE gold.mart_sales_monthly SET ROW FILTER ops.rf_country ON (country_code);

ALTER TABLE silver.customers_scd2 ALTER COLUMN contact_name SET MASK ops.mask_pii;
ALTER TABLE silver.customers_scd2 ALTER COLUMN contact_email SET MASK ops.mask_pii;
ALTER TABLE silver.customers_scd2 ALTER COLUMN contact_phone SET MASK ops.mask_pii;
ALTER TABLE silver.customers_scd2 ALTER COLUMN vat_number SET MASK ops.mask_pii;

-- COMMAND ----------

-- Tags (classification) and comments
ALTER SCHEMA bronze SET TAGS ('layer' = 'bronze');
ALTER SCHEMA silver SET TAGS ('layer' = 'silver');
ALTER SCHEMA gold SET TAGS ('layer' = 'gold');
ALTER TABLE gold.fact_sales SET TAGS ('domain' = 'sales', 'grain' = 'order_line', 'rls' = 'country');
ALTER TABLE gold.mart_sales_monthly SET TAGS ('domain' = 'sales', 'grain' = 'month_country_channel_sku', 'rls' = 'country');
ALTER TABLE gold.mart_sellin_sellout_weekly SET TAGS ('domain' = 'distribution', 'grain' = 'week_distributor_category');
ALTER TABLE silver.customers_scd2 SET TAGS ('domain' = 'customer', 'contains_pii' = 'true', 'scd' = 'type2');
ALTER TABLE silver.customers_scd2 ALTER COLUMN contact_email SET TAGS ('pii' = 'email');
ALTER TABLE silver.customers_scd2 ALTER COLUMN contact_phone SET TAGS ('pii' = 'phone');
ALTER TABLE silver.customers_scd2 ALTER COLUMN contact_name SET TAGS ('pii' = 'name');
ALTER TABLE silver.customers_scd2 ALTER COLUMN vat_number SET TAGS ('pii' = 'tax_id');

COMMENT ON TABLE gold.mart_sales_monthly IS 'Monthly sell-in by country, channel and SKU. net_sales_cfx_eur = local currency at 2022 average ECB rate (organic growth).';
COMMENT ON COLUMN gold.mart_sales_monthly.net_sales_cfx_eur IS 'Net sales at constant FX (2022 average ECB rate), used for organic growth';
COMMENT ON COLUMN gold.mart_sales_monthly.volume_t IS 'Volume in tonnes, pack size valid on the order date (shrinkflation-aware)';
COMMENT ON TABLE gold.mart_sellin_sellout_weekly IS 'Distributor sell-in (ERP) vs sell-out (distributor files), stock and stock cover in weeks';

-- COMMAND ----------

-- Grants: business users (all account users in this demo) read gold only
GRANT USE CATALOG ON CATALOG nestle_dev TO `account users`;
GRANT USE SCHEMA, SELECT ON SCHEMA nestle_dev.gold TO `account users`;
SHOW GRANTS ON SCHEMA nestle_dev.gold;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ### Demo: the same query as a Poland country manager
-- MAGIC Temporarily restrict the current user to PL, query, then restore ALL.

-- COMMAND ----------

SELECT 'before (ALL)' AS access, count(DISTINCT country_code) AS countries_visible, round(sum(net_sales_eur) / 1e6, 1) AS net_sales_eur_m
FROM gold.mart_sales_monthly;

-- COMMAND ----------

UPDATE ops.user_country_access SET country_code = 'PL' WHERE user_email = current_user();
SELECT 'as PL country manager' AS access, count(DISTINCT country_code) AS countries_visible,
       round(sum(net_sales_eur) / 1e6, 1) AS net_sales_eur_m, min(country_code) AS country
FROM gold.mart_sales_monthly;

-- COMMAND ----------

UPDATE ops.user_country_access SET country_code = 'ALL' WHERE user_email = current_user();
SELECT customer_id, customer_name, contact_name, contact_email, contact_phone, vat_number
FROM silver.customers_scd2 LIMIT 5;
