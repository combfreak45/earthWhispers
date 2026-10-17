"""
EarthWhisper XGBoost Training Pipeline from BigQuery
Trains a calibrated 3-class Flood Susceptibility & Risk model (0: Low, 1: Moderate, 2: High)
directly using historical observations stored in BigQuery (`earthwhisper_live.training_dataset`).
Exports model artifacts compatible with Vertex AI Model Registry and Prediction Endpoints.
"""

import os
import sys
import json
import argparse
import logging
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import classification_report, accuracy_score, f1_score, roc_auc_score

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from common.mcp_bq_client import BigQueryMCPClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("earthwhisper-trainer")

FEATURE_NAMES = [
    "rain_1h_mm",
    "rain_3h_mm",
    "rain_6h_mm",
    "rain_24h_mm",
    "rain_72h_mm",
    "rain_7d_mm",
    "rain_peak_1h_mm",
    "rain_24h_anomaly_pct",
    "rain_72h_zscore",
    "soil_water_layer1",
    "elevation_mean_m",
    "slope_mean_deg",
    "data_freshness_hrs",
    "spatial_coverage_pct"
]

ARTIFACTS_DIR = os.path.join(os.path.dirname(__file__), "artifacts")


def load_dataset_from_bigquery(project_id: str, dataset_id: str = "earthwhisper_live") -> pd.DataFrame:
    """
    Loads historical training dataset directly from BigQuery via the BigQuery MCP Toolset.
    """
    mcp_client = BigQueryMCPClient(project_id=project_id)
    table_id = f"{project_id}.{dataset_id}.training_dataset"
    logger.info(f"Loading cleaned training dataset from BigQuery table via MCP: {table_id}...")

    query = f"""
        SELECT 
            rain_1h_mm, rain_3h_mm, rain_6h_mm, rain_24h_mm, rain_72h_mm, rain_7d_mm,
            rain_peak_1h_mm, rain_24h_anomaly_pct, rain_72h_zscore, soil_water_layer1,
            elevation_mean_m, slope_mean_deg, data_freshness_hrs, spatial_coverage_pct,
            flood_risk_level, split
        FROM `{table_id}`
        ORDER BY observation_timestamp ASC
    """
    rows = mcp_client.execute_query(query)
    df = pd.DataFrame(rows)
    for col in FEATURE_NAMES:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    df["flood_risk_level"] = pd.to_numeric(df["flood_risk_level"], errors="coerce").fillna(0).astype(int)
    logger.info(f"Successfully retrieved and parsed {len(df)} rows from BigQuery via MCP!")
    return df


def train_model(project_id: str, dataset_id: str = "earthwhisper_live"):
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    df = load_dataset_from_bigquery(project_id, dataset_id)

    # Use chronological splits from BigQuery
    train_df = df[df["split"] == "TRAIN"]
    val_df = df[df["split"] == "VAL"]
    test_df = df[df["split"] == "TEST"]

    logger.info(f"Chronological Splits: Train={len(train_df)}, Val={len(val_df)}, Test={len(test_df)}")

    X_train, y_train = train_df[FEATURE_NAMES].values, train_df["flood_risk_level"].astype(int).values
    X_val, y_val = val_df[FEATURE_NAMES].values, val_df["flood_risk_level"].astype(int).values
    X_test, y_test = test_df[FEATURE_NAMES].values, test_df["flood_risk_level"].astype(int).values

    clf = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=5,
        learning_rate=0.06,
        objective="multi:softprob",
        num_class=3,
        subsample=0.85,
        colsample_bytree=0.85,
        random_state=42,
        eval_metric="mlogloss"
    )

    clf.fit(
        X_train, y_train,
        eval_set=[(X_train, y_train), (X_val, y_val)],
        verbose=False
    )

    # Evaluate on Holdout Test Split
    test_preds = clf.predict(X_test)
    test_probs = clf.predict_proba(X_test)

    acc = accuracy_score(y_test, test_preds)
    f1 = f1_score(y_test, test_preds, average="weighted")
    roc_auc = roc_auc_score(y_test, test_probs, multi_class="ovr")

    logger.info(f"Model Evaluation on Holdout Test Set (Assam Floods):")
    logger.info(f"Accuracy: {acc:.4f} | Weighted F1: {f1:.4f} | Multi-Class ROC-AUC: {roc_auc:.4f}")
    logger.info("\nClassification Report:\n" + classification_report(y_test, test_preds, target_names=["Low (0)", "Moderate (1)", "Severe (2)"]))

    # Save model artifacts for Vertex AI
    # Vertex AI pre-built XGBoost prediction container expects 'model.bst'
    model_bst_path = os.path.join(ARTIFACTS_DIR, "model.bst")
    clf.save_model(model_bst_path)

    metadata = {
        "model_name": "earthwhisper-xgboost",
        "version": "v1.0",
        "target": "flood_risk_level",
        "classes": ["Low", "Moderate", "Severe"],
        "num_classes": 3,
        "feature_names": FEATURE_NAMES,
        "source_dataset": f"{project_id}.{dataset_id}.training_dataset",
        "accuracy": round(acc, 4),
        "weighted_f1": round(f1, 4),
        "roc_auc_ovr": round(roc_auc, 4),
        "training_samples": len(X_train),
        "test_samples": len(X_test),
        "feature_importance": dict(zip(FEATURE_NAMES, [float(x) for x in clf.feature_importances_]))
    }

    metadata_path = os.path.join(ARTIFACTS_DIR, "metadata.json")
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)

    logger.info(f"Model saved successfully to {model_bst_path} and metadata to {metadata_path}")
    return clf, metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train XGBoost model directly from BigQuery")
    parser.add_argument("--project_id", required=True, help="GCP Project ID")
    parser.add_argument("--dataset_id", default="earthwhisper_live", help="Dataset ID (earthwhisper_live)")
    args = parser.parse_args()

    train_model(args.project_id, args.dataset_id)
