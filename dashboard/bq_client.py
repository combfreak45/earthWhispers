"""
Live BigQuery reader for the EarthWhispers dashboard.

Replaces the former mock loader: produces the same dict shapes app.py expects,
but sourced from the live earthwhisper_live tables written by the agent pipeline:
  - alert_audits            -> prediction/risk history (one row per agent run)
  - catchment_features      -> rainfall evidence (joined by observation_timestamp)
  - catchment_climate_baseline -> seasonal baseline (joined by day-of-year)
  - impact_graph_assets     -> exposed settlements & critical infrastructure

All queries degrade gracefully to empty results so the dashboard renders even if
BigQuery is unreachable or a table is empty.
"""

import os
import math
import logging

from google.cloud import bigquery

logger = logging.getLogger("earthwhisper-dashboard-bq")

PROJECT_ID = os.getenv("PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
DATASET = os.getenv("BIGQUERY_DATASET_LIVE", "earthwhisper_live")

RISK_LABELS = {0: "low", 1: "medium", 2: "high"}

_client = None
_centroid_cache: dict = {}


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
    return v.isoformat() if hasattr(v, "isoformat") else v


def _get_centroid(area_id: str):
    """Average asset lat/lon for a catchment (cached), used as the map point."""
    if area_id in _centroid_cache:
        return _centroid_cache[area_id]
    rows = _query(
        f"SELECT AVG(latitude) AS lat, AVG(longitude) AS lon "
        f"FROM `{PROJECT_ID}.{DATASET}.impact_graph_assets` WHERE catchment_id = @cid",
        [bigquery.ScalarQueryParameter("cid", "STRING", area_id)],
    )
    centroid = (rows[0]["lat"], rows[0]["lon"]) if rows and rows[0].get("lat") is not None else (26.1, 90.5)
    _centroid_cache[area_id] = centroid
    return centroid


def get_enriched_predictions() -> list:
    """One dict per agent run (alert_audits), enriched with rainfall + baseline evidence."""
    sql = f"""
        SELECT
            a.audit_id, a.catchment_id, a.observation_timestamp, a.evaluation_timestamp,
            a.risk_class, a.risk_score, a.model_version, a.data_freshness_status,
            a.policy_action, a.affected_assets_count,
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
            "data_quality": "good" if freshness == "fresh" else (freshness or "unknown"),
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
            "rainfall_24h": rain_24h,  # numeric or None (keeps the history column Arrow-clean)
            "rainfall_72h": r.get("rain_72h_mm", "N/A"),
            "baseline_24h": baseline_24h if baseline_24h is not None else "N/A",
            "anomaly_score": anomaly,
        })
    return out


def load_impact_context(area_id: str) -> dict:
    """Exposed settlements and critical assets for a catchment, with distance from centroid."""
    rows = _query(
        f"SELECT name, asset_type, population, latitude, longitude, vulnerability_index "
        f"FROM `{PROJECT_ID}.{DATASET}.impact_graph_assets` "
        f"WHERE catchment_id = @cid ORDER BY vulnerability_index DESC",
        [bigquery.ScalarQueryParameter("cid", "STRING", area_id)],
    )
    if not rows:
        return {"nearby_settlements": [], "critical_assets": []}

    clat, clon = _get_centroid(area_id)
    settlements, assets = [], []
    for r in rows:
        dist = _haversine_km(clat, clon, r["latitude"], r["longitude"])
        if r.get("asset_type") == "SETTLEMENT":
            settlements.append({
                "name": r["name"],
                "population": r.get("population") or 0,
                "distance_km": dist,
            })
        else:
            assets.append({
                "name": r["name"],
                "type": (r.get("asset_type") or "").lower(),
                "distance_km": dist,
            })
    return {"nearby_settlements": settlements, "critical_assets": assets}
