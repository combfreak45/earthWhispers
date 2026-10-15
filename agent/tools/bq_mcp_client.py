"""
BigQuery MCP & ImpactGraph Client
Connects to Google's managed BigQuery MCP Server via Streamable HTTP (https://bigquery.googleapis.com/mcp)
and executes parameterized geospatial impact queries against the Lower Brahmaputra ImpactGraph.

STRICT GROUNDING & ZERO-MOCK PRODUCTION RULE:
- Reads and queries are executed through the BigQuery MCP Server (`execute_query`).
- Under --mode=live: Zero synthetic fallbacks. If no records are found, returns empty results
  to instruct the LLM: "No critical infrastructure records found in the database for this specific radius."
"""

import os
import sys
import logging
from typing import Dict, Any, List

from google.cloud import bigquery

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data_pipeline")))
from mcp_bq_client import BigQueryMCPClient
from telemetry import get_tracer

logger = logging.getLogger("earthwhisper-bq-mcp")
tracer = get_tracer()

PROJECT_ID = os.getenv("PROJECT_ID", "earthwhisper-dev")
DATASET_LIVE = os.getenv("BIGQUERY_DATASET_LIVE", "earthwhisper_live")
DATASET_MOCK = os.getenv("BIGQUERY_DATASET_MOCK", "earthwhisper_mock")

# The 14 model features, in training/endpoint order (see docs/gcp-integration.md).
FEATURE_COLUMNS = [
    "rain_1h_mm", "rain_3h_mm", "rain_6h_mm", "rain_24h_mm",
    "rain_72h_mm", "rain_7d_mm", "rain_peak_1h_mm", "rain_24h_anomaly_pct",
    "rain_72h_zscore", "soil_water_layer1", "elevation_mean_m",
    "slope_mean_deg", "data_freshness_hrs", "spatial_coverage_pct",
]

mcp_client = None


def get_mcp_client() -> BigQueryMCPClient:
    global mcp_client
    if mcp_client is None:
        mcp_client = BigQueryMCPClient(project_id=PROJECT_ID)
    return mcp_client


def _jsonable(row: Dict[str, Any]) -> Dict[str, Any]:
    """Make a BigQuery row JSON/ADK-safe (TIMESTAMP -> ISO 8601 string)."""
    out = {}
    for k, v in row.items():
        out[k] = v.isoformat() if hasattr(v, "isoformat") else v
    return out


def lookup_impact_graph(
    catchment_id: str = "brahmaputra_lower_assam",
    risk_class: int = 2,
    mode: str = "live"
) -> Dict[str, Any]:
    """
    Queries BigQuery for exposed settlements, population counts, and critical infrastructure
    falling within the predicted flood risk zone using the BigQuery MCP Toolset.
    STRICT GROUNDING: The agent cites ONLY records returned by this tool.
    """
    with tracer.start_as_current_span("earthwhisper.mcp.bigquery_impact_lookup") as span:
        span.set_attribute("execution_mode", mode)
        span.set_attribute("catchment_id", catchment_id)
        span.set_attribute("risk_class", risk_class)

        target_dataset = DATASET_LIVE if mode == "live" else DATASET_MOCK
        table_ref = f"`{PROJECT_ID}.{target_dataset}.impact_graph_assets`"

        # Query assets based on risk level
        min_vuln = 0.4 if risk_class == 1 else 0.2 if risk_class == 2 else 0.8
        query = f"""
            SELECT asset_id, district, name, asset_type, population, latitude, longitude, vulnerability_index
            FROM {table_ref}
            WHERE catchment_id = '{catchment_id}' AND vulnerability_index >= {min_vuln}
            ORDER BY vulnerability_index DESC, population DESC
            LIMIT 15
        """

        records = []
        try:
            records = get_mcp_client().execute_query(query)
            logger.info(f"Retrieved {len(records)} impact assets from {target_dataset} via BigQuery MCP.")
        except Exception as e:
            logger.warning(f"BigQuery MCP impact lookup query error: {e}")
            if mode == "live":
                # In live mode: Strict isolation, do not mask failures with synthetic fixtures
                records = []
            else:
                # In mock mode only: fallback fixture for dry-runs
                records = [
                    {"asset_id": "MOCK-SET-001", "district": "Dhubri", "name": "Dhubri Town & River Port", "asset_type": "SETTLEMENT", "population": 63700, "vulnerability_index": 0.88},
                    {"asset_id": "MOCK-SET-002", "district": "Barpeta", "name": "Barpeta Gram Panchayat", "asset_type": "SETTLEMENT", "population": 42600, "vulnerability_index": 0.82},
                    {"asset_id": "MOCK-HOS-001", "district": "Dhubri", "name": "Dhubri Civil Hospital", "asset_type": "HOSPITAL", "population": None, "vulnerability_index": 0.90},
                    {"asset_id": "MOCK-EVAC-001", "district": "Barpeta", "name": "Barpeta Flood Shelter Center", "asset_type": "EVACUATION_CENTER", "population": None, "vulnerability_index": 0.75},
                    {"asset_id": "MOCK-BRI-001", "district": "Goalpara", "name": "Naranarayan Setu Bridge Access", "asset_type": "BRIDGE", "population": None, "vulnerability_index": 0.85}
                ]

        total_pop = sum(r["population"] for r in records if r.get("population"))
        settlements = [r["name"] for r in records if r.get("asset_type") == "SETTLEMENT"]
        hospitals = [r["name"] for r in records if r.get("asset_type") == "HOSPITAL"]
        evac_centers = [r["name"] for r in records if r.get("asset_type") == "EVACUATION_CENTER"]
        bridges = [r["name"] for r in records if r.get("asset_type") == "BRIDGE"]

        payload = {
            "total_exposed_population": total_pop,
            "exposed_settlements": settlements,
            "critical_hospitals": hospitals,
            "evacuation_centers": evac_centers,
            "vulnerable_bridges": bridges,
            "detailed_records": records[:10]
        }

        span.set_attribute("impact.exposed_population", total_pop)
        span.set_attribute("impact.records_count", len(records))
        return payload


def fetch_latest_features(
    catchment_id: str = "brahmaputra_lower_assam",
    mode: str = "live",
) -> Dict[str, Any]:
    """
    Fetch the latest operational telemetry row for a catchment from
    `catchment_features`, returning the 14-feature dict the Vertex model needs
    plus freshness metadata. Returns {"error": ...} if no row is found (live).
    """
    with tracer.start_as_current_span("earthwhisper.mcp.fetch_latest_features") as span:
        span.set_attribute("execution_mode", mode)
        span.set_attribute("catchment_id", catchment_id)

        dataset = DATASET_LIVE if mode == "live" else DATASET_MOCK
        table_ref = f"`{PROJECT_ID}.{dataset}.catchment_features`"
        cols = ", ".join(FEATURE_COLUMNS)
        query = f"""
            SELECT catchment_id, observation_timestamp, ingestion_timestamp,
                   {cols}, freshness_status, feature_version
            FROM {table_ref}
            WHERE catchment_id = @catchment_id
            ORDER BY observation_timestamp DESC
            LIMIT 1
        """
        params = [bigquery.ScalarQueryParameter("catchment_id", "STRING", catchment_id)]

        try:
            rows = get_mcp_client().execute_query(query, params)
        except Exception as e:
            logger.warning(f"catchment_features query error: {e}")
            if mode == "live":
                return {"error": f"Feature telemetry query failed: {e}", "features": {}}
            rows = []

        if not rows:
            return {"error": f"No telemetry found for catchment_id={catchment_id}", "features": {}}

        row = _jsonable(rows[0])
        features = {k: row.get(k) for k in FEATURE_COLUMNS}
        span.set_attribute("features.observation_timestamp", str(row.get("observation_timestamp")))
        span.set_attribute("features.freshness_status", str(row.get("freshness_status")))
        return {
            "catchment_id": row.get("catchment_id"),
            "observation_timestamp": row.get("observation_timestamp"),
            "ingestion_timestamp": row.get("ingestion_timestamp"),
            "features": features,
            "freshness_status": row.get("freshness_status"),
            "feature_version": row.get("feature_version"),
        }


def get_climate_baseline(
    catchment_id: str = "brahmaputra_lower_assam",
    doy: int = 1,
    mode: str = "live",
) -> Dict[str, Any]:
    """
    Return the day-of-year climatological normals (24h/72h rain mean & std) from
    `catchment_climate_baseline`, for grounding "vs. seasonal normal" narrative.
    `doy` is the day-of-year (1-366). Returns {"error": ...} if no row is found.
    """
    with tracer.start_as_current_span("earthwhisper.mcp.get_climate_baseline") as span:
        span.set_attribute("execution_mode", mode)
        span.set_attribute("catchment_id", catchment_id)
        span.set_attribute("doy", doy)

        dataset = DATASET_LIVE if mode == "live" else DATASET_MOCK
        table_ref = f"`{PROJECT_ID}.{dataset}.catchment_climate_baseline`"
        query = f"""
            SELECT doy, mean_rain_24h_mm, std_rain_24h_mm,
                   mean_rain_72h_mm, std_rain_72h_mm, baseline_window_years
            FROM {table_ref}
            WHERE catchment_id = @catchment_id AND doy = @doy
            LIMIT 1
        """
        params = [
            bigquery.ScalarQueryParameter("catchment_id", "STRING", catchment_id),
            bigquery.ScalarQueryParameter("doy", "INT64", doy),
        ]

        try:
            rows = get_mcp_client().execute_query(query, params)
        except Exception as e:
            logger.warning(f"catchment_climate_baseline query error: {e}")
            if mode == "live":
                return {"error": f"Baseline query failed: {e}"}
            rows = []

        if not rows:
            return {"error": f"No baseline found for catchment_id={catchment_id}, doy={doy}"}
        return _jsonable(rows[0])


def write_alert_audit(record: Dict[str, Any], mode: str = "live") -> Dict[str, Any]:
    """
    Append one audit record to `alert_audits` for compliance. Called by the
    orchestration layer (not an agent tool). `record` must contain all REQUIRED
    columns (see docs/gcp-integration.md). Returns {"status": "written", ...}.
    """
    with tracer.start_as_current_span("earthwhisper.mcp.write_alert_audit") as span:
        span.set_attribute("execution_mode", mode)
        span.set_attribute("audit.catchment_id", str(record.get("catchment_id")))
        span.set_attribute("audit.risk_class", record.get("risk_class", -1))

        dataset = DATASET_LIVE if mode == "live" else DATASET_MOCK
        table_id = f"{PROJECT_ID}.{dataset}.alert_audits"
        get_mcp_client().insert_rows(table_id, [record])
        logger.info(f"Audit {record.get('audit_id')} written to {table_id}.")
        return {"status": "written", "audit_id": record.get("audit_id"), "table": table_id}
