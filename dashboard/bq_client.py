"""
Live BigQuery reader & Replay scenario provider for the EarthWhispers dashboard.

Produces enriched data structures for app.py, sourced from:
  - BigQuery live dataset (`earthwhisper_live`) when populated and reachable
  - Historical replay scenarios (July 2024 Catastrophic Surge, June 2022, Dry Baseline)
    for seamless, reliable offline/live hackathon presentations.
"""

import os
import sys
import math
import logging
from datetime import datetime, timezone
from pathlib import Path

from google.cloud import bigquery

# Ensure agent and data_pipeline are importable
sys.path.insert(0, str(Path(__file__).parent.parent / "agent"))
sys.path.insert(0, str(Path(__file__).parent.parent / "data_pipeline"))

logger = logging.getLogger("earthwhisper-dashboard-bq")

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
DATASET = os.getenv("BIGQUERY_DATASET_LIVE", "earthwhisper_live")

RISK_LABELS = {0: "low", 1: "medium", 2: "high"}

_client = None
_centroid_cache: dict = {}

# Verified real geospatial coordinates for Lower Brahmaputra flood corridor
DEFAULT_ASSETS = [
    {
        "name": "Dhubri Town & River Port",
        "asset_type": "SETTLEMENT",
        "population": 63700,
        "latitude": 26.02,
        "longitude": 89.98,
        "vulnerability_index": 0.88,
    },
    {
        "name": "Barpeta Gram Panchayat",
        "asset_type": "SETTLEMENT",
        "population": 42600,
        "latitude": 26.32,
        "longitude": 91.01,
        "vulnerability_index": 0.82,
    },
    {
        "name": "Dhubri Civil Hospital",
        "asset_type": "HOSPITAL",
        "population": None,
        "latitude": 26.02,
        "longitude": 89.97,
        "vulnerability_index": 0.90,
    },
    {
        "name": "Barpeta Flood Shelter Center",
        "asset_type": "EVACUATION_CENTER",
        "population": None,
        "latitude": 26.31,
        "longitude": 91.00,
        "vulnerability_index": 0.75,
    },
    {
        "name": "Naranarayan Setu Bridge Access",
        "asset_type": "BRIDGE",
        "population": None,
        "latitude": 26.21,
        "longitude": 90.56,
        "vulnerability_index": 0.85,
    },
    {
        "name": "Goalpara District Hospital",
        "asset_type": "HOSPITAL",
        "population": None,
        "latitude": 26.17,
        "longitude": 90.62,
        "vulnerability_index": 0.86,
    },
]


def _bq() -> bigquery.Client:
    global _client
    if _client is None:
        _client = bigquery.Client(project=PROJECT_ID)
    return _client


def _query(sql: str, params=None) -> list:
    try:
        job_config = bigquery.QueryJobConfig(query_parameters=params or [])
        return [dict(r.items()) for r in _bq().query(sql, job_config=job_config).result()]
    except Exception as e:
        logger.warning("Dashboard BigQuery query failed: %s", e)
        return []


def _pretty(catchment_id: str) -> str:
    return (catchment_id or "").replace("_", " ").title()


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * r * math.asin(math.sqrt(a)), 1)


def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else str(v)


def _get_centroid(area_id: str):
    """Average asset lat/lon for a catchment (cached), used as the map point."""
    if area_id in _centroid_cache:
        return _centroid_cache[area_id]
    rows = _query(
        f"SELECT AVG(latitude) AS lat, AVG(longitude) AS lon "
        f"FROM `{PROJECT_ID}.{DATASET}.impact_graph_assets` WHERE catchment_id = @cid",
        [bigquery.ScalarQueryParameter("cid", "STRING", area_id)],
    )
    centroid = (rows[0]["lat"], rows[0]["lon"]) if rows and rows[0].get("lat") is not None else (26.15, 90.50)
    _centroid_cache[area_id] = centroid
    return centroid


def get_default_replay_scenarios() -> list:
    """Pre-built historical benchmark and live replay scenarios for hackathon demonstration."""
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    return [
        {
            "event_id": "REPLAY-2024-JULY-SURGE",
            "area_id": "brahmaputra_lower_assam",
            "area_name": "Brahmaputra Lower Assam (July 2024 Catastrophic Surge)",
            "predicted_at": now_iso,
            "event_time": now_iso,
            "ingestion_time": now_iso,
            "data_quality": "good",
            "source": "NASA GPM IMERG V07 & Sentinel-1 SAR",
            "geometry": {"coordinates": [90.50, 26.15]},
            "risk_class": "high",
            "risk_score": 0.88,
            "model_version": "earthwhisper-xgboost-v1.0",
            "is_experimental": True,
            "feature_version": "v1.0-replay",
            "triggered_rule": "72h rainfall z-score 3.45 (>2.5σ critical)",
            "rainfall_1h": 38.0,
            "rainfall_3h": 86.5,
            "rainfall_6h": 155.0,
            "rainfall_24h": 245.0,
            "rainfall_72h": 465.0,
            "baseline_24h": 58.2,
            "anomaly_score": 3.2,
            "policy_action": "human_review",
            "affected_assets_count": 5,
            "briefing": """### 1. Executive Risk Assessment
**Overall Status: HIGH RISK (Class 2)**
The Vertex AI XGBoost predictive model estimates a calibrated flood risk score of **0.88** (Severe flood probability: 0.75). The catchment is under active high-hazard flood threat driven by the July 2024 Brahmaputra Monsoon Surge.

### 2. Physical & Meteorological Evidence
- **Precipitation:** Cumulative 24-hour rainfall reached **245.0 mm**, with 72-hour antecedent rainfall totaling **465.0 mm**.
- **Historical Baseline Deviation:** 72-hour rainfall represents a **Z-Score anomaly of +3.45 σ** (320% above seasonal climatological normal for Day-of-Year).
- **Soil Saturation:** Volumetric soil water is at **0.485 m³/m³**, indicating near 100% saturation across the river corridor.

### 3. Vulnerable Communities & Critical Infrastructure
According to the BigQuery ImpactGraph:
- **Exposed Population:** Approximately **106,300** residents across vulnerable riverine zones.
- **Settlements at Risk:** Dhubri Town & River Port, Barpeta Gram Panchayat.
- **Key Infrastructure:** Priority protection required for Dhubri Civil Hospital, Barpeta Flood Shelter Center, and Naranarayan Setu Bridge Access.

### 4. Recommended Preparedness Actions
1. Verify emergency power and water filtration readiness at Dhubri Civil Hospital.
2. Pre-position non-motorized relief craft near Barpeta Flood Shelter Center.
3. Issue community alerts in gram panchayats with advice to elevate potable water stores and livestock.

### 5. Data Freshness & Sensor Limitations
- **Sensor Latency:** Current observation is 3.0 hours old (FRESH_NOMINAL).
- **Caveat:** GPM IMERG satellite rainfall represents ~11 km grid averages. Ground photos represent localized point observations.""",
        },
        {
            "event_id": "REPLAY-2022-JUNE-BENCHMARK",
            "area_id": "brahmaputra_lower_assam",
            "area_name": "Brahmaputra Lower Assam (June 2022 Benchmark)",
            "predicted_at": now_iso,
            "event_time": now_iso,
            "ingestion_time": now_iso,
            "data_quality": "good",
            "source": "NASA GPM IMERG V07 & ECMWF ERA5-Land",
            "geometry": {"coordinates": [90.50, 26.15]},
            "risk_class": "high",
            "risk_score": 0.92,
            "model_version": "earthwhisper-xgboost-v1.0",
            "is_experimental": True,
            "feature_version": "v1.0-replay",
            "triggered_rule": "72h rainfall z-score 3.85 (>3.5σ historic record)",
            "rainfall_1h": 42.5,
            "rainfall_3h": 98.0,
            "rainfall_6h": 172.5,
            "rainfall_24h": 285.0,
            "rainfall_72h": 515.0,
            "baseline_24h": 58.2,
            "anomaly_score": 3.8,
            "policy_action": "human_review",
            "affected_assets_count": 5,
            "briefing": """### 1. Executive Risk Assessment
**Overall Status: HIGH RISK (Class 2)**
Extreme record precipitation replay from the June 2022 Assam flood. Calibrated risk score: **0.92**. Catastrophic inundation threshold exceeded across Lower Brahmaputra basin.""",
        },
        {
            "event_id": "REPLAY-DRY-SEASON-NOMINAL",
            "area_id": "brahmaputra_lower_assam",
            "area_name": "Brahmaputra Lower Assam (Winter Dry Season Normal)",
            "predicted_at": now_iso,
            "event_time": now_iso,
            "ingestion_time": now_iso,
            "data_quality": "good",
            "source": "NASA GPM IMERG V07",
            "geometry": {"coordinates": [90.50, 26.15]},
            "risk_class": "low",
            "risk_score": 0.05,
            "model_version": "earthwhisper-xgboost-v1.0",
            "is_experimental": True,
            "feature_version": "v1.0-replay",
            "triggered_rule": "Normal seasonal baseline (Z-score -0.85)",
            "rainfall_1h": 0.0,
            "rainfall_3h": 0.0,
            "rainfall_6h": 0.0,
            "rainfall_24h": 0.5,
            "rainfall_72h": 1.2,
            "baseline_24h": 15.0,
            "anomaly_score": 0.0,
            "policy_action": "suppress",
            "affected_assets_count": 0,
            "briefing": """### 1. Executive Risk Assessment
**Overall Status: LOW RISK (Class 0)**
Normal dry season meteorological observations. Low risk score: **0.05**. No flood emergency threat detected.""",
        },
        {
            "event_id": "REPLAY-STALE-SENSOR-DEGRADED",
            "area_id": "brahmaputra_lower_assam",
            "area_name": "Brahmaputra Lower Assam (Sensor Dropout Test)",
            "predicted_at": now_iso,
            "event_time": now_iso,
            "ingestion_time": now_iso,
            "data_quality": "stale",
            "source": "Degraded Satellite Link",
            "geometry": {"coordinates": [90.50, 26.15]},
            "risk_class": "medium",
            "risk_score": 0.65,
            "model_version": "earthwhisper-xgboost-v1.0",
            "is_experimental": True,
            "feature_version": "v1.0-replay",
            "triggered_rule": "Sensor Latency > 54 hrs (Policy Gate Suppressed)",
            "rainfall_1h": 15.0,
            "rainfall_3h": 32.0,
            "rainfall_6h": 45.0,
            "rainfall_24h": 80.0,
            "rainfall_72h": 160.0,
            "baseline_24h": 58.2,
            "anomaly_score": 1.4,
            "policy_action": "suppress",
            "affected_assets_count": 2,
            "briefing": """### 1. Executive Risk Assessment
**Overall Status: MEDIUM RISK (Class 1) — SUPPRESSED DUE TO STALE DATA**
Safety policy gate blocked emergency alert dispatch because sensor latency is 54.0 hours (exceeds 48-hour critical freshness limit).""",
        },
    ]


def get_enriched_predictions() -> list:
    """One dict per agent run (alert_audits), enriched with rainfall + baseline evidence."""
    sql = f"""
        SELECT
            a.audit_id, a.catchment_id, a.observation_timestamp, a.evaluation_timestamp,
            a.risk_class, a.risk_score, a.model_version, a.data_freshness_status,
            a.policy_action, a.affected_assets_count, a.gemini_briefing,
            cf.ingestion_timestamp, cf.feature_version,
            cf.rain_1h_mm, cf.rain_3h_mm, cf.rain_6h_mm, cf.rain_24h_mm, cf.rain_72h_mm,
            cf.rain_24h_anomaly_pct, cf.rain_72h_zscore,
            b.mean_rain_24h_mm AS baseline_24h
        FROM `{PROJECT_ID}.{DATASET}.alert_audits` a
        LEFT JOIN `{PROJECT_ID}.{DATASET}.catchment_features` cf
            ON cf.catchment_id = a.catchment_id
            AND cf.observation_timestamp = a.observation_timestamp
        LEFT JOIN `{PROJECT_ID}.{DATASET}.catchment_climate_baseline` b
            ON b.catchment_id = a.catchment_id
            AND b.doy = EXTRACT(DAYOFYEAR FROM a.observation_timestamp)
        ORDER BY a.evaluation_timestamp DESC
        LIMIT 50
    """
    rows = _query(sql)
    out = []
    for r in rows:
        rc = RISK_LABELS.get(r.get("risk_class"), "low")
        rain_24h = r.get("rain_24h_mm")
        baseline_24h = r.get("baseline_24h")
        if rain_24h is not None and baseline_24h:
            anomaly = round(rain_24h / baseline_24h, 1)
        elif r.get("rain_24h_anomaly_pct") is not None:
            anomaly = round(1 + r["rain_24h_anomaly_pct"] / 100.0, 1)
        else:
            anomaly = "N/A"
        z = r.get("rain_72h_zscore")
        lat, lon = _get_centroid(r.get("catchment_id"))
        freshness = r.get("data_freshness_status")
        out.append({
            "event_id": r.get("audit_id"),
            "area_id": r.get("catchment_id"),
            "area_name": _pretty(r.get("catchment_id")),
            "predicted_at": _iso(r.get("evaluation_timestamp")),
            "event_time": _iso(r.get("observation_timestamp")),
            "ingestion_time": _iso(r.get("ingestion_timestamp")),
            "data_quality": "good" if str(freshness).lower() in ("fresh", "good", "fresh_nominal") else (freshness or "unknown"),
            "source": "NASA GPM IMERG (catchment_features)",
            "geometry": {"coordinates": [lon, lat]},
            "risk_class": rc,
            "risk_score": r.get("risk_score", 0) or 0,
            "model_version": r.get("model_version", ""),
            "is_experimental": True,
            "feature_version": r.get("feature_version", "N/A"),
            "triggered_rule": f"72h rainfall z-score {z:.1f}" if isinstance(z, (int, float)) else "rainfall anomaly",
            "rainfall_1h": r.get("rain_1h_mm", "N/A"),
            "rainfall_3h": r.get("rain_3h_mm", "N/A"),
            "rainfall_6h": r.get("rain_6h_mm", "N/A"),
            "rainfall_24h": rain_24h,
            "rainfall_72h": r.get("rain_72h_mm", "N/A"),
            "baseline_24h": baseline_24h if baseline_24h is not None else "N/A",
            "anomaly_score": anomaly,
            "policy_action": r.get("policy_action", "human_review"),
            "affected_assets_count": r.get("affected_assets_count", 0),
            "briefing": r.get("gemini_briefing", ""),
        })

    # If BigQuery table has no records or offline, provide default replay events
    if not out:
        out = get_default_replay_scenarios()
    return out


def load_impact_context(area_id: str) -> dict:
    """Exposed settlements and critical assets for a catchment, with real coordinates."""
    rows = _query(
        f"SELECT name, asset_type, population, latitude, longitude, vulnerability_index "
        f"FROM `{PROJECT_ID}.{DATASET}.impact_graph_assets` "
        f"WHERE catchment_id = @cid ORDER BY vulnerability_index DESC",
        [bigquery.ScalarQueryParameter("cid", "STRING", area_id)],
    )
    if not rows:
        rows = DEFAULT_ASSETS

    clat, clon = _get_centroid(area_id)
    settlements, assets, all_pins = [], [], []
    for r in rows:
        lat = r.get("latitude") or 26.15
        lon = r.get("longitude") or 90.50
        dist = _haversine_km(clat, clon, lat, lon)
        atype = (r.get("asset_type") or "").upper()
        
        pin = {
            "name": r["name"],
            "type": atype,
            "lat": lat,
            "lon": lon,
            "population": r.get("population"),
            "vulnerability": r.get("vulnerability_index", 0.8),
            "distance_km": dist,
        }
        all_pins.append(pin)

        if atype == "SETTLEMENT":
            settlements.append({
                "name": r["name"],
                "population": r.get("population") or 0,
                "distance_km": dist,
                "lat": lat,
                "lon": lon,
            })
        else:
            assets.append({
                "name": r["name"],
                "type": atype.lower(),
                "distance_km": dist,
                "lat": lat,
                "lon": lon,
            })
    return {"nearby_settlements": settlements, "critical_assets": assets, "map_pins": all_pins}


def execute_agent_assessment(scenario_id: str = "2024_ASSAM_BRAHMAPUTRA_SURGE", mode: str = "mock") -> dict:
    """Runs the full end-to-end agent pipeline and returns the live result."""
    from pipeline import run_assessment
    return run_assessment(catchment_id="brahmaputra_lower_assam", mode=mode, scenario_id=scenario_id)