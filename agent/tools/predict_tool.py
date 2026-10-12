import json
import os
from pathlib import Path

MOCK_DATA_DIR = Path(__file__).parents[1] / "mock_data"


def predict_flood_risk(event_id: str, features: dict) -> dict:
    """
    Call XGBoost model endpoint and return risk score + class.
    In production: call Vertex AI endpoint using google-cloud-aiplatform.

    Args:
        event_id: ID of the signal event being evaluated
        features: dict of rainfall/anomaly features from signal_events

    Returns:
        dict with risk_score, risk_class, model_version, is_experimental
    """
    with open(MOCK_DATA_DIR / "predictions.json") as f:
        predictions = json.load(f)

    match = next((p for p in predictions if p["event_id"] == event_id), None)
    if match:
        return {
            "prediction_id": match["prediction_id"],
            "risk_score": match["risk_score"],
            "risk_class": match["risk_class"],
            "model_version": match["model_version"],
            "is_experimental": match["is_experimental"],
        }

    # Fallback: rule-based mock if no matching prediction
    anomaly = features.get("anomaly_score", 0)
    if anomaly >= 3.0:
        risk_score, risk_class = 0.88, "high"
    elif anomaly >= 1.5:
        risk_score, risk_class = 0.65, "medium"
    else:
        risk_score, risk_class = 0.20, "low"

    return {
        "prediction_id": f"mock_{event_id}",
        "risk_score": risk_score,
        "risk_class": risk_class,
        "model_version": "xgb_v1.2_mock",
        "is_experimental": True,
    }
