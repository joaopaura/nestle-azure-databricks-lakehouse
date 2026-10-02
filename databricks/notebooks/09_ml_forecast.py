# Databricks notebook source
# MAGIC %md
# MAGIC # 09 | Weekly demand forecast (12 weeks ahead) with MLflow + Unity Catalog model registry
# MAGIC * Data: `gold.mart_demand_weekly` (country x category x week, tonnes) with **real weather** and **real food inflation**
# MAGIC * Direct 12-week-ahead model: only information available 12 weeks before the target week (lags >= 12, yearly lag,
# MAGIC   seasonality, promo share, climatological temperature for the week of the year)
# MAGIC * Model: scikit-learn `HistGradientBoostingRegressor`, one global model for 84 series
# MAGIC * Baseline: seasonal naive (same week last year). Test: last 12 complete weeks (6 Jul to 21 Sep 2026)
# MAGIC * Metrics: WAPE (= 1 - forecast accuracy), MAPE, bias; logged to MLflow, model registered as `nestle_dev.ml.weekly_demand_forecast`
# MAGIC * Outputs: `ml.forecast_weekly` (test + next 12 weeks) and `ml.forecast_accuracy` (by category and country)

# COMMAND ----------

# MAGIC %run ./_utils

# COMMAND ----------

import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from mlflow.models import infer_signature
from sklearn.ensemble import HistGradientBoostingRegressor

H = 12
TEST_START, LAST_FULL_WEEK = pd.Timestamp("2026-07-06"), pd.Timestamp("2026-09-21")
df = spark.table("nestle_dev.gold.mart_demand_weekly").toPandas()
df["week_start"] = pd.to_datetime(df["week_start"])
df = df[df["week_start"] <= LAST_FULL_WEEK].sort_values(["country_code", "category", "week_start"])

# future frame: next 12 weeks after the last complete week
future = (df[["country_code", "category"]].drop_duplicates()
            .merge(pd.DataFrame({"week_start": pd.date_range(LAST_FULL_WEEK + pd.Timedelta(weeks=1), periods=H, freq="7D")}), how="cross"))
full = pd.concat([df, future], ignore_index=True).sort_values(["country_code", "category", "week_start"])
full["woy"] = full["week_start"].dt.isocalendar().week.astype(int)

g = full.groupby(["country_code", "category"])["volume_t"]
for k in (H, H + 1, H + 2, H + 3, 52):
    full[f"lag_{k}"] = g.shift(k)
full["roll4_lag12"] = g.transform(lambda s: s.shift(H).rolling(4).mean())
full["promo_lag12"] = full.groupby(["country_code", "category"])["promo_line_share"].shift(H)
clim = df.assign(woy=df["week_start"].dt.isocalendar().week.astype(int)).groupby(["country_code", "woy"])["temp_mean_c"].mean()
full["temp_clim_c"] = [clim.get((c, w), np.nan) for c, w in zip(full["country_code"], full["woy"])]
full["sin_woy"], full["cos_woy"] = np.sin(2 * np.pi * full["woy"] / 52), np.cos(2 * np.pi * full["woy"] / 52)
full["country_id"] = full["country_code"].astype("category").cat.codes
full["category_id"] = full["category"].astype("category").cat.codes
FEATURES = ["lag_12", "lag_13", "lag_14", "lag_15", "lag_52", "roll4_lag12", "promo_lag12", "temp_clim_c",
            "sin_woy", "cos_woy", "woy", "country_id", "category_id"]

data = full.dropna(subset=["lag_52", "roll4_lag12"])
train = data[(data["week_start"] < TEST_START) & data["volume_t"].notna()]
test = data[(data["week_start"] >= TEST_START) & (data["week_start"] <= LAST_FULL_WEEK)]
fut = data[data["week_start"] > LAST_FULL_WEEK]
print(f"train {len(train):,} rows ({train.week_start.min():%Y-%m-%d} to {train.week_start.max():%Y-%m-%d}) | test {len(test):,} | future {len(fut):,}")


def metrics(y, p):
    y, p = np.asarray(y, float), np.asarray(p, float)
    return {"wape_pct": 100 * np.abs(y - p).sum() / y.sum(), "mape_pct": 100 * np.mean(np.abs(y - p) / y),
            "bias_pct": 100 * (p.sum() - y.sum()) / y.sum()}

# COMMAND ----------

mlflow.set_registry_uri("databricks-uc")
mlflow.set_experiment(f"/Users/{spark.sql('SELECT current_user()').first()[0]}/nestle_weekly_demand_forecast")
params = {"max_iter": 400, "learning_rate": 0.05, "max_leaf_nodes": 31, "min_samples_leaf": 20, "l2_regularization": 0.1}

with mlflow.start_run(run_name="hgb_direct_12w") as run:
    model = HistGradientBoostingRegressor(categorical_features=[FEATURES.index("country_id"), FEATURES.index("category_id")],
                                          random_state=2026, **params)
    model.fit(train[FEATURES], train["volume_t"])
    pred, naive = model.predict(test[FEATURES]), test["lag_52"].to_numpy()
    m_model, m_naive = metrics(test["volume_t"], pred), metrics(test["volume_t"], naive)
    mlflow.log_params({**params, "horizon_weeks": H, "features": ",".join(FEATURES), "train_rows": len(train)})
    mlflow.log_metrics({f"test_{k}": v for k, v in m_model.items()})
    mlflow.log_metrics({f"baseline_seasonal_naive_{k}": v for k, v in m_naive.items()})
    mlflow.log_metric("test_forecast_accuracy_pct", 100 - m_model["wape_pct"])
    info = mlflow.sklearn.log_model(model, artifact_path="model", input_example=train[FEATURES].head(5),
                                    signature=infer_signature(train[FEATURES], pred),
                                    registered_model_name="nestle_dev.ml.weekly_demand_forecast")
    version = info.registered_model_version
print(f"Model    WAPE {m_model['wape_pct']:.2f}% | MAPE {m_model['mape_pct']:.2f}% | bias {m_model['bias_pct']:+.2f}%")
print(f"Baseline WAPE {m_naive['wape_pct']:.2f}% | MAPE {m_naive['mape_pct']:.2f}% | bias {m_naive['bias_pct']:+.2f}%")
print(f"Registered nestle_dev.ml.weekly_demand_forecast version {version}")

# COMMAND ----------

started = now()
out = pd.concat([
    test.assign(forecast_t=pred, baseline_t=naive, is_future=False),
    fut.assign(forecast_t=model.predict(fut[FEATURES]), baseline_t=fut["lag_52"], is_future=True)])
out = out[["week_start", "country_code", "category", "volume_t", "forecast_t", "baseline_t", "is_future"]] \
        .rename(columns={"volume_t": "actual_t"}).assign(model_version=str(version), mlflow_run_id=run.info.run_id)
out["forecast_t"] = out["forecast_t"].round(3)
spark.createDataFrame(out).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("nestle_dev.ml.forecast_weekly")
log_step("ml", "forecast", "nestle_dev.ml.forecast_weekly", len(out), started)

started = now()
rows = []
for level in ["category", "country_code"]:
    for key, grp in test.assign(forecast_t=pred).groupby(level):
        m = metrics(grp["volume_t"], grp["forecast_t"])
        rows.append((level, key, round(m["wape_pct"], 2), round(m["mape_pct"], 2), round(m["bias_pct"], 2), str(version)))
rows.append(("total", "all", round(m_model["wape_pct"], 2), round(m_model["mape_pct"], 2), round(m_model["bias_pct"], 2), str(version)))
spark.createDataFrame(rows, "level string, member string, wape_pct double, mape_pct double, bias_pct double, model_version string") \
     .write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("nestle_dev.ml.forecast_accuracy")
log_step("ml", "forecast", "nestle_dev.ml.forecast_accuracy", len(rows), started)

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT level, member, wape_pct, round(100 - wape_pct, 1) AS forecast_accuracy_pct, mape_pct, bias_pct
# MAGIC FROM nestle_dev.ml.forecast_accuracy
# MAGIC WHERE level IN ('category', 'total')
# MAGIC ORDER BY level DESC, wape_pct DESC
