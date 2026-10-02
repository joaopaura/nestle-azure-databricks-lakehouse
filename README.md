# Nestlé European FMCG Lakehouse | Azure Databricks

> Portfolio project. Not affiliated with Nestlé S.A. Company data is synthetic; public data sources are real.

End-to-end data engineering project on **Azure Databricks**: a legacy ERP (Azure SQL) is migrated into a governed
Delta lakehouse (Unity Catalog, bronze / silver / gold), reconciled against the source, enriched with real public data
(ECB FX, Eurostat HICP, Open-Meteo weather) and used to forecast weekly demand with MLflow. Served in Power BI.

**Status:** in progress (Phase 1: data generation). Scope: [docs/scope.md](docs/scope.md)

## Generate the data
```bash
pip install -r generator/requirements.txt
python generator/download_public.py   # real public data: ECB FX, Eurostat / ONS food inflation, Open-Meteo weather
python generator/run_all.py           # synthetic ERP, dirty distributor files, POS event stream (~8 min)
python generator/validate.py          # row counts + business story checks
```

## Repository layout
| Folder | Content |
|---|---|
| `generator/` | Python synthetic data generator + public data download |
| `sql/` | Azure SQL legacy ERP DDL and load scripts |
| `databricks/` | Notebooks, Lakeflow / DLT pipelines, Asset Bundle |
| `ml/` | Demand forecast training and MLflow registration |
| `adf/` | Azure Data Factory pipeline JSON |
| `infra/` | Azure CLI scripts and setup notes |
| `tests/` | Unit tests (pytest) |
| `powerbi/` | PBIP report, theme, backgrounds |
| `docs/` | Scope, architecture, screenshots |

Author: João Paúra | [LinkedIn](https://linkedin.com/in/joaopaura) | [GitHub](https://github.com/joaopaura)
