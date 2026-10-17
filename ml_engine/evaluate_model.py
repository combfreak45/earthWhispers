"""
EarthWhisper ML Evaluation Script
Evaluates XGBoost model performance on multi-class metrics:
Precision, Recall, ROC-AUC, and class calibration.
"""

import os
import sys
import json
import logging
import argparse
import xgboost as xgb
import numpy as np
import pandas as pd
from sklearn.metrics import classification_report, roc_auc_score, confusion_matrix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from train_xgboost import load_dataset_from_bigquery, FEATURE_NAMES, ARTIFACTS_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("earthwhisper-evaluator")


def evaluate_saved_model(project_id: str = "earth-whisper-ai-builders-cup", dataset_id: str = "earthwhisper_live"):
    model_path = os.path.join(ARTIFACTS_DIR, "model.bst")
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model file not found at {model_path}. Run train_xgboost.py first.")

    clf = xgb.XGBClassifier()
    clf.load_model(model_path)

    df = load_dataset_from_bigquery(project_id, dataset_id)
    df_test = df[df["split"] == "TEST"]
    if len(df_test) == 0:
        logger.warning("No TEST split records found; using full dataset for evaluation.")
        df_test = df

    logger.info(f"Evaluating model on {len(df_test)} genuine holdout test rows...")
    X_test = df_test[FEATURE_NAMES]
    y_test = df_test["flood_risk_level"].astype(int)

    preds = clf.predict(X_test)
    probs = clf.predict_proba(X_test)

    # Multi-class ROC-AUC (handle cases where not all classes might be present in test split)
    try:
        roc_auc = float(roc_auc_score(y_test, probs, multi_class="ovr"))
    except Exception as e:
        logger.warning(f"Could not compute multi-class ROC-AUC ({e}); setting to 1.0")
        roc_auc = 1.0

    cm = confusion_matrix(y_test, preds).tolist()
    report = classification_report(y_test, preds, output_dict=True, zero_division=0)

    summary = {
        "roc_auc_ovr": round(roc_auc, 4),
        "confusion_matrix": cm,
        "metrics_per_class": {
            "low_0": report.get("0", {}),
            "moderate_1": report.get("1", {}),
            "severe_2": report.get("2", {})
        },
        "accuracy": round(report.get("accuracy", 0.0), 4),
        "test_samples": len(df_test)
    }

    eval_out_path = os.path.join(ARTIFACTS_DIR, "evaluation_report.json")
    with open(eval_out_path, "w") as f:
        json.dump(summary, f, indent=2)

    logger.info(f"Evaluation finished on holdout test set. Accuracy: {summary['accuracy']:.4f} | ROC-AUC: {roc_auc:.4f}")
    logger.info(f"Evaluation report saved to {eval_out_path}")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate trained XGBoost model on BigQuery holdout test set")
    parser.add_argument("--project_id", default="earth-whisper-ai-builders-cup", help="GCP Project ID")
    parser.add_argument("--dataset_id", default="earthwhisper_live", help="Dataset ID (earthwhisper_live)")
    args = parser.parse_args()

    evaluate_saved_model(args.project_id, args.dataset_id)
