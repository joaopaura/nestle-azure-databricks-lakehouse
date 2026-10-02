/* Legacy ERP schema (source system for the migration to the Azure Databricks lakehouse).
   Database: sqldb-nestle-erp on sql-lloyds-joaopaura (Azure SQL free offer, Sweden Central).
   Idempotent: drops and recreates the tables. Loaded by infra/load_erp_to_sql.py. */

IF SCHEMA_ID('erp') IS NULL EXEC('CREATE SCHEMA erp');
GO

DROP TABLE IF EXISTS erp.returns, erp.sales_order_lines, erp.sales_orders, erp.promotions, erp.product_changes,
                     erp.customer_changes, erp.standard_cost, erp.price_list, erp.customers, erp.products, erp.countries;
GO

CREATE TABLE erp.countries (
    country_code   CHAR(2)       NOT NULL CONSTRAINT pk_countries PRIMARY KEY,
    country_name   NVARCHAR(50)  NOT NULL,
    currency       CHAR(3)       NOT NULL,
    capital        NVARCHAR(50)  NULL
);

CREATE TABLE erp.products (
    sku               INT            NOT NULL CONSTRAINT pk_products PRIMARY KEY,
    product_name      NVARCHAR(120)  NOT NULL,
    brand             NVARCHAR(40)   NOT NULL,
    category          NVARCHAR(30)   NOT NULL,
    subcategory       NVARCHAR(30)   NULL,
    pack_size         NVARCHAR(30)   NULL,
    units_per_case    INT            NOT NULL,
    case_weight_kg    DECIMAL(9,2)   NOT NULL,
    ean               VARCHAR(13)    NOT NULL,
    launch_date       DATE           NULL,
    discontinued_date DATE           NULL,
    status            VARCHAR(15)    NOT NULL
);

CREATE TABLE erp.customers (
    customer_id         VARCHAR(10)    NOT NULL CONSTRAINT pk_customers PRIMARY KEY,
    customer_name       NVARCHAR(100)  NOT NULL,
    country_code        CHAR(2)        NOT NULL,
    channel             NVARCHAR(30)   NOT NULL,
    customer_type       NVARCHAR(30)   NOT NULL,
    key_account_manager NVARCHAR(60)   NULL,
    credit_limit_eur    INT            NULL,
    contact_name        NVARCHAR(80)   NULL,   -- PII
    contact_email       NVARCHAR(120)  NULL,   -- PII
    contact_phone       VARCHAR(30)    NULL,   -- PII
    vat_number          VARCHAR(20)    NULL,
    created_at          DATETIME2(0)   NULL,
    is_distributor      BIT            NOT NULL
);

CREATE TABLE erp.price_list (
    sku             INT            NOT NULL,
    country_code    CHAR(2)        NOT NULL,
    currency        CHAR(3)        NOT NULL,
    list_price_case DECIMAL(12,2)  NOT NULL,
    valid_from      DATE           NOT NULL,
    valid_to        DATE           NOT NULL,
    CONSTRAINT pk_price_list PRIMARY KEY (sku, country_code, valid_from)
);

CREATE TABLE erp.standard_cost (
    sku               INT           NOT NULL,
    fiscal_quarter    VARCHAR(6)    NOT NULL,
    std_cost_eur_case DECIMAL(12,2) NOT NULL,
    CONSTRAINT pk_standard_cost PRIMARY KEY (sku, fiscal_quarter)
);

CREATE TABLE erp.customer_changes (
    change_id   INT            NOT NULL CONSTRAINT pk_customer_changes PRIMARY KEY,
    customer_id VARCHAR(10)    NOT NULL,
    field_name  VARCHAR(40)    NOT NULL,
    old_value   NVARCHAR(120)  NULL,
    new_value   NVARCHAR(120)  NULL,
    changed_at  DATETIME2(0)   NOT NULL
);

CREATE TABLE erp.product_changes (
    change_id  INT            NOT NULL CONSTRAINT pk_product_changes PRIMARY KEY,
    sku        INT            NOT NULL,
    field_name VARCHAR(40)    NOT NULL,
    old_value  NVARCHAR(120)  NULL,
    new_value  NVARCHAR(120)  NULL,
    changed_at DATETIME2(0)   NOT NULL
);

CREATE TABLE erp.promotions (
    promo_id           VARCHAR(10)   NOT NULL CONSTRAINT pk_promotions PRIMARY KEY,
    customer_id        VARCHAR(10)   NOT NULL,
    category           NVARCHAR(30)  NOT NULL,
    duration_weeks     INT           NOT NULL,
    discount_pct       DECIMAL(5,4)  NOT NULL,
    mechanic           NVARCHAR(40)  NOT NULL,
    start_date         DATE          NOT NULL,
    end_date           DATE          NOT NULL,
    planned_uplift_pct DECIMAL(6,1)  NULL
);

CREATE TABLE erp.sales_orders (
    order_id                BIGINT        NOT NULL CONSTRAINT pk_sales_orders PRIMARY KEY,
    customer_id             VARCHAR(10)   NOT NULL,
    order_date              DATE          NOT NULL,
    requested_delivery_date DATE          NULL,
    currency                CHAR(3)       NOT NULL,
    order_status            VARCHAR(12)   NOT NULL,
    sales_channel           NVARCHAR(30)  NOT NULL,
    is_deleted              BIT           NOT NULL,
    created_at              DATETIME2(0)  NOT NULL
);

CREATE TABLE erp.sales_order_lines (
    order_id        BIGINT         NOT NULL,
    line_no         INT            NOT NULL,
    sku             INT            NOT NULL,
    qty_cases       INT            NOT NULL,
    list_price_case DECIMAL(12,2)  NOT NULL,
    discount_pct    DECIMAL(6,4)   NOT NULL,
    net_amount      DECIMAL(14,2)  NOT NULL,
    promo_id        VARCHAR(10)    NULL,
    CONSTRAINT pk_sales_order_lines PRIMARY KEY (order_id, line_no)
);

CREATE TABLE erp.returns (
    return_id     INT IDENTITY(1,1) NOT NULL CONSTRAINT pk_returns PRIMARY KEY,
    order_id      BIGINT        NOT NULL,
    line_no       INT           NOT NULL,
    return_date   DATE          NOT NULL,
    qty_cases     INT           NOT NULL,
    reason_code   VARCHAR(12)   NOT NULL,
    credit_amount DECIMAL(14,2) NOT NULL
);
GO
