-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 00 | Unity Catalog setup
-- MAGIC Storage credential `cred_nestle_adls` (access connector managed identity, created in the UI) gives Unity Catalog
-- MAGIC access to the ADLS Gen2 account `stnestlejp01`. This notebook creates the external locations, the catalog
-- MAGIC `nestle_dev` (managed storage in the `lakehouse` container), the medallion schemas and a volume over the landing zone.
-- MAGIC Run on **Serverless**. Idempotent.

-- COMMAND ----------

CREATE EXTERNAL LOCATION IF NOT EXISTS ext_landing
  URL 'abfss://landing@stnestlejp01.dfs.core.windows.net/'
  WITH (STORAGE CREDENTIAL cred_nestle_adls)
  COMMENT 'Raw landing zone: public data, distributor sell-out files, POS event stream';

CREATE EXTERNAL LOCATION IF NOT EXISTS ext_lakehouse
  URL 'abfss://lakehouse@stnestlejp01.dfs.core.windows.net/'
  WITH (STORAGE CREDENTIAL cred_nestle_adls)
  COMMENT 'Managed storage for catalog nestle_dev (Delta tables)';

-- COMMAND ----------

CREATE CATALOG IF NOT EXISTS nestle_dev
  MANAGED LOCATION 'abfss://lakehouse@stnestlejp01.dfs.core.windows.net/nestle_dev'
  COMMENT 'Nestlé European FMCG lakehouse (portfolio project, synthetic company data)';

USE CATALOG nestle_dev;

CREATE SCHEMA IF NOT EXISTS bronze COMMENT 'Raw data as received (ERP extract, files, events) + ingestion metadata';
CREATE SCHEMA IF NOT EXISTS silver COMMENT 'Cleaned, typed, deduplicated, conformed; SCD2 dimensions';
CREATE SCHEMA IF NOT EXISTS gold   COMMENT 'Star schema and KPI marts for Power BI';
CREATE SCHEMA IF NOT EXISTS ops    COMMENT 'Run log, data quality results, reconciliation, benchmarks';
CREATE SCHEMA IF NOT EXISTS ml     COMMENT 'Feature tables, forecasts, registered models';

-- COMMAND ----------

CREATE EXTERNAL VOLUME IF NOT EXISTS nestle_dev.bronze.landing
  LOCATION 'abfss://landing@stnestlejp01.dfs.core.windows.net/'
  COMMENT 'Read access to the landing zone files';

-- COMMAND ----------

-- Smoke test: the three landing folders must be visible
LIST '/Volumes/nestle_dev/bronze/landing/';

-- COMMAND ----------

LIST '/Volumes/nestle_dev/bronze/landing/sellout/C000813/' LIMIT 5;
