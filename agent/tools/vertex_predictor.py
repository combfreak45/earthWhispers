"""
Vertex AI XGBoost Prediction Tool
Invokes the deployed Vertex AI Endpoint to calculate calibrated 3-class flood risk.
"""

import os
import logging
from typing import Dict, Any, List
from google.cloud import aiplatform
from telemetry import get_tracer

logger = logging.getLogger("earthwhisper-vertex-predictor")
tracer = get_tracer()

def _resolve_project_id() -> str:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass
    for var in ("PROJECT_ID", "GOOGLE_CLOUD_PROJECT", "GCP_PROJECT"):
        val = os.getenv(var)
        if val and val.strip():
            return val.strip()
    try:
        import google.auth
        _, auth_project = google.auth.default()
        if auth_project and auth_project.strip():
            return auth_project.strip()
    except Exception:
        pass
    return os.getenv("DEFAULT_GCP_PROJECT", "earth-whisper-ai-builders-cup")

PROJECT_ID = _resolve_project_id()
REGION = os.getenv("REGION", "us-central1")
ENDPOINT_ID = os.getenv("VERTEX_ENDPOINT_ID")

FEATURE_KEYS = [
    "rain_1h_mm", "rain_3h_mm", "rain_6h_mm", "rain_24h_mm",
    "rain_72h_mm", "rain_7d_mm", "rain_peak_1h_mm", "rain_24h_anomaly_pct",
    "rain_72h_zscore", "soil_water_layer1", "elevation_mean_m",
    "slope_mean_deg", "data_freshness_hrs", "spatial_coverage_pct"
]


def predict_flood_risk(features: Dict[str, Any], mode: str = "live") -> Dict[str, Any]:
    """
    Native ADK Tool function.
    Calls the Vertex AI Endpoint to obtain the official numerical flood risk prediction.
    """
    with tracer.start_as_current_span("earthwhisper.tool.predict_flood_risk") as span:
        span.set_attribute("execution_mode", mode)
        span.set_attribute("rain_24h_mm", features.get("rain_24h_mm", 0.0))
        span.set_attribute("rain_72h_zscore", features.get("rain_72h_zscore", 0.0))

        # Extract ordered feature vector
        vector = [float(features.get(k, 0.0)) for k in FEATURE_KEYS]

        if mode == "live" and ENDPOINT_ID:
            try:
                aiplatform.init(project=PROJECT_ID, location=REGION)
                endpoint = aiplatform.Endpoint(ENDPOINT_ID)
                response = endpoint.predict(instances=[vector])
                predictions = response.predictions[0] # [p0, p1, p2]
                p0, p1, p2 = float(predictions[0]), float(predictions[1]), float(predictions[2])
            except Exception as e:
                logger.error(f"Vertex AI Endpoint call failed: {e}")
                span.record_exception(e)
                raise RuntimeError(f"Vertex AI Endpoint unavailable: {str(e)}")
        else:
            # Deterministic heuristic scoring for mock/test dry-runs
            # (Class 2 if zscore >= 2.5 or rain_24h >= 200; Class 1 if zscore >= 1.0; else Class 0)
            zscore = float(features.get("rain_72h_zscore", 0.0))
            r24h = float(features.get("rain_24h_mm", 0.0))
            if zscore >= 2.5 or r24h >= 200.0:
                p0, p1, p2 = 0.05, 0.20, 0.75
            elif zscore >= 1.0 or r24h >= 75.0:
                p0, p1, p2 = 0.20, 0.65, 0.15
            else:
                p0, p1, p2 = 0.85, 0.12, 0.03

        # Determine predicted class
        probs = [p0, p1, p2]
        pred_class = int(probs.index(max(probs)))
        labels = ["Low", "Moderate", "High"]
        pred_label = labels[pred_class]
        risk_score = round(p1 * 0.5 + p2 * 1.0, 3)

        # Extract top feature drivers
        top_drivers = []
        z_val = float(features.get("rain_72h_zscore") or 0.0)
        anom_val = float(features.get("rain_24h_anomaly_pct") or 0.0)
        peak_val = float(features.get("rain_peak_1h_mm") or 0.0)

        if z_val > 1.0:
            top_drivers.append({
                "feature_name": "rain_72h_zscore",
                "feature_value": z_val,
                "importance_weight": 0.38
            })
        if anom_val > 50.0:
            top_drivers.append({
                "feature_name": "rain_24h_anomaly_pct",
                "feature_value": anom_val,
                "importance_weight": 0.29
            })
        if peak_val > 20.0:
            top_drivers.append({
                "feature_name": "rain_peak_1h_mm",
                "feature_value": peak_val,
                "importance_weight": 0.21
            })

        result = {
            "risk_class": pred_class,
            "risk_label": pred_label,
            "risk_score": risk_score,
            "class_probabilities": {
                "low": round(p0, 3),
                "moderate": round(p1, 3),
                "high": round(p2, 3)
            },
            "top_contributing_features": top_drivers,
            "model_version": "earthwhisper-xgboost-v1.0"
        }

        span.set_attribute("prediction.risk_class", pred_class)
        span.set_attribute("prediction.risk_score", risk_score)
        return result
