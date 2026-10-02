# Nestlé European FMCG Lakehouse | Project scope v1.0

> Portfolio project. Not affiliated with Nestlé S.A. Company data is synthetic; public data sources are real.
> Author: João Paúra | linkedin.com/in/joaopaura | github.com/joaopaura
> Date: 2 Oct 2026 (v1.1) | Repo: github.com/joaopaura/nestle-azure-databricks-lakehouse

## 1. Objective
Show hands-on, end-to-end delivery on the **Azure Databricks** stack that Polish and European employers ask for
(PySpark, Delta Lake, Unity Catalog, Lakeflow / DLT, MLflow, ADF, Asset Bundles), applied to a realistic FMCG case:
migrating a legacy ERP into a governed lakehouse, reconciling it, forecasting demand and serving executives in Power BI.

Audience: hiring managers for Data Engineer / Analytics Engineer / Senior Data Analyst roles, and C-level style dashboard viewers.

## 2. Business case (synthetic company)
"Nestlé Europe" commercial organisation, sell-in to retailers and distributors, plus distributor sell-out.

| Item | Scope |
|---|---|
| Period | Jan 2022 to Sep 2026 (actuals), forecast 12 weeks ahead |
| Reporting currency | EUR (source data in EUR, PLN, GBP, CHF, SEK, converted with real ECB rates) |
| Markets (12) | Poland, Germany, France, United Kingdom, Italy, Spain, Switzerland, Netherlands, Belgium, Austria, Portugal, Sweden |
| Categories (7) | Coffee, Confectionery, Water, Pet Care, Dairy, Culinary, Infant Nutrition |
| SKUs | ~350 fictitious SKUs (real Nestlé-style category names, invented product names) |
| Customers | ~2,500 (retail chains, wholesalers, distributors, e-commerce, out-of-home) |
| Channels (4) | Modern trade, Traditional trade, E-commerce, Out-of-home |
| Volume | ~14M rows: ~10.8M sales order lines, 640k orders, 1.9M distributor sell-out rows in 3,480 dirty files, 620k POS events (sized for the Azure SQL free offer and serverless budget) |

Built-in business stories (planted in the generator, discovered in the dashboard):
1. Pricing drives growth in 2022 to 2023 (inflation), volume (RIG) recovers in 2025 to 2026.
2. Coffee and Pet Care lead growth; Water is weather sensitive (hot weeks lift sales).
3. Poland and Spain grow fastest; UK flat after FX.
4. One distributor overstocks before a promotion (sell-in spike, sell-out does not follow).
5. Forecast is weaker for Water and Confectionery (seasonality, Easter / Christmas).

## 3. Data sources

| Source | Type | Landing | Notes |
|---|---|---|---|
| Legacy ERP (customers, products, price list, sales orders, order lines, promotions, returns) | Synthetic, Python | Azure SQL Database (reuse server `sql-lloyds-joaopaura`, new DB `nestle_erp`) | Source for migration + reconciliation |
| Distributor sell-out files | Synthetic, dirty CSV / JSON | ADLS Gen2 `landing/sellout/` | Duplicates, mixed date formats, country spellings, numbers as text |
| POS events | Synthetic JSON files | ADLS Gen2 `landing/pos_stream/` | Simulated stream, Auto Loader `availableNow` |
| ECB FX rates | Real, public | ADLS Gen2 `landing/public/fx/` | Daily, EUR base |
| Eurostat HICP | Real, public | ADLS Gen2 `landing/public/hicp/` | Monthly inflation per country |
| Open-Meteo weather | Real, public | ADLS Gen2 `landing/public/weather/` | Daily temperature, 12 capitals |

## 4. Architecture and stack
```
Python generator ──> Azure SQL "legacy ERP" ─┐
Dirty distributor files ─────────────────────┤
Public data (ECB, Eurostat, Open-Meteo) ─────┼──> ADLS Gen2 landing ──> Azure Databricks (Unity Catalog)
POS JSON events (simulated stream) ──────────┘        catalog nestle_dev: bronze ──> silver ──> gold  (+ ops, ml)
                                                      Lakeflow Declarative Pipelines / PySpark notebooks
                                                      Delta MERGE, SCD2, OPTIMIZE / liquid clustering
                                                      Reconciliation Azure SQL vs Delta, MLflow forecast
Orchestration: Databricks Workflow + ADF pipeline (manual runs) | CI: Asset Bundle + GitHub Actions
Serving: Power BI (Import, Databricks connector) ──> Publish to web
```
Stack: Azure Databricks (Premium trial), Unity Catalog, Delta Lake, PySpark, Spark SQL, Lakeflow / DLT, Auto Loader,
MLflow, Azure SQL Database, ADLS Gen2, Azure Data Factory, Databricks Asset Bundles, GitHub Actions, Python, DAX, Power BI.

## 5. In scope / out of scope

| In scope | Out of scope |
|---|---|
| Medallion lakehouse with data quality expectations | Real Nestlé data or internal systems |
| SCD2 for customer and product | Continuous streaming / always-on clusters |
| Migration reconciliation (row counts, sums, hashes) | Scheduled runs after screenshots (static demo) |
| Governance: grants, row filter, column mask, tags, lineage | Multi-workspace / prod environment |
| Weekly demand forecast with MLflow, model in Unity Catalog | Model serving endpoint |
| Optimisation benchmark (before / after) | Terraform (already shown in Roche project) |
| Power BI, 4 pages, Publish to web | Live connection after trial ends (Import mode only) |

## 6. Dashboard (Power BI, 4 pages: 1 cover + 3 data pages, light theme, 1920 x 1080, same grid as Roche / Shell)

| # | Page | KPI cards | Main visuals |
|---|---|---|---|
| 1 | Home (cover) | Rows processed, Reconciliation checks passed, Forecast accuracy | Large Nestlé logo, title, description, stack chips, 4 facts, 3 navigation cards |
| 2 | Commercial Performance | Net sales, Organic growth, RIG (volume), Pricing, Gross margin %, Volume (tonnes) | Net sales trend vs PY, Organic growth bridge (RIG + pricing + FX), Net sales by category, by country, channel mix |
| 3 | Demand & Sell-out | Forecast accuracy, MAPE, Bias, Sell-out, Sell-through %, Promo uplift | Actual vs forecast (weekly), Sell-in vs sell-out, Forecast error by category, Stock cover by distributor, Promo uplift by category |
| 4 | Platform & Data Quality | Pipeline runs, Rows processed, DQ expectations passed, Reconciliation pass rate, Last run duration, Estimated DBU cost | Rows by layer, Reconciliation Azure SQL vs Delta, Architecture diagram, DQ expectations |

KPI card standard (as previous dashboards): value card + label card with arrow and colour measure, data labels on all charts.

## 7. Design system

| Element | Value |
|---|---|
| Logo | Official Nestlé logo (nest + wordmark, blue), transparent PNG `powerbi/design/nestle_logo.png`. Cover: large and prominent, height 270 px, centred over the navigation cards. Pages: top right, height 58 px |
| Primary (brand) | Nestlé Blue `#005BA5` (sampled from the logo): title separator, active nav button, links, main series |
| Primary dark | `#003E73`: chip text, emphasis |
| Accent | Light blue `#7FADD2`: KPI bar, card accent, stripe right half |
| Secondary series | Nestlé Oak `#64513D` (corporate brown): prior year / comparison series |
| Soft fills | Blue soft `#E8F1F9` (chips, architecture boxes), Oak soft `#F3EEE8` |
| Page background | `#F6F8FA` |
| Card | `#FFFFFF`, border `#E1E7EE`, radius 12 px |
| Text | Ink `#1C2B3A`, secondary `#5B6B7B`, muted `#8D9AA7` |
| Status | Good `#2E7D4F`, neutral `#D08A2E`, bad `#C2402E`, grey `#A9B4BF` |
| Fonts | Backgrounds: Inter (400 / 500 / 600 / 700). Power BI visuals: Segoe UI and Segoe UI Semibold |
| Footer | "Developed by João Paúra | Data Engineering & BI portfolio project | Synthetic company data, real public data (ECB, Eurostat, Open-Meteo), processed on Azure Databricks | Independent project, not affiliated with or endorsed by Nestlé S.A." + "linkedin.com/in/joaopaura | github.com/joaopaura" |

## 8. Phases, effort and cost

| Phase | Content | Azure cost est. | Priority |
|---|---|---|---|
| 0 | Azure checks (credit, quota, budget alert, providers), resource group, repo skeleton, scope, design | US$0 | MVP |
| 1 | Python generator + public data, ERP into Azure SQL, files into ADLS | < US$2 | MVP |
| 2 | Databricks workspace (Premium trial), Unity Catalog, external location | US$0 (DBU trial) + VM | MVP |
| 3 | Bronze / silver / gold, SCD2, optimisation benchmark | ~US$10 to 25 | MVP |
| 4 | Migration reconciliation | ~US$3 | MVP |
| 5 | Governance (grants, row filter, column mask, tags, lineage) | ~US$2 | MVP |
| 6 | ML forecast + MLflow | ~US$5 to 10 | 2nd |
| 7 | Streaming (Auto Loader availableNow) | ~US$3 | 3rd |
| 8 | Workflow + ADF manual runs, Asset Bundle + GitHub Actions | ~US$3 | MVP light |
| 9 | Power BI, screenshots, README, delete workspace | ~US$3 | MVP |
| 10 | LinkedIn post + CV update | US$0 | after |

Budget cap US$150 of ~US$198 credit (trial ends ~28 Oct 2026). Never click Upgrade.

## 9. Cost guardrails
- Compute: Databricks **serverless** (notebooks, jobs, pipelines) in Sweden Central. Decision 2 Oct 2026: the trial subscription has only 3 vCPUs per region (checked Sweden Central, North Europe, West Europe, Germany West Central, France Central) and quota increases need an upgrade, so a 4-vCPU classic node is not possible. Serverless does not use the subscription vCPU quota.
- No SQL warehouse left running; stop serverless sessions after each working block.
- Budget alerts every ~US$30. Check Cost analysis at the end of every working session.
- Workspace created only when data and code are ready (14-day DBU trial starts at creation).
- After screenshots: delete Databricks workspace + managed resource group, pause / delete Azure SQL DB `nestle_erp`.

## 10. Risks

| Risk | Mitigation |
|---|---|
| vCPU quota too low (trial: 3 vCPU / region, no increase) | Serverless compute (confirmed decision) |
| DBU / VM cost overrun | Budget alerts, auto-termination, sample data option (10M rows) |
| DLT not available on the tier | Same logic in PySpark notebooks with expectations table |
| Unity Catalog metastore setup on personal tenant | Use workspace auto-provisioned metastore; document steps |
| Power BI needs live Databricks after trial | Import mode + Publish to web before deleting workspace |

## 11. Success criteria
- Public repo with code, notebooks, bundle, tests, architecture diagram and screenshots.
- Reconciliation: 100% of checks pass (one planted failure fixed and documented as an interview story).
- Forecast accuracy reported honestly (MAPE per category), model registered in Unity Catalog.
- Power BI report published (4 pages), total Azure spend below US$150.
