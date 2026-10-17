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
from datetime import datetime, timezone
from typing import Dict, Any, List

from google.cloud import bigquery

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
try:
    from common.mcp_bq_client import BigQueryMCPClient
except ImportError:
    from mcp_bq_client import BigQueryMCPClient

try:
    from telemetry import get_tracer
except ImportError:
    from opentelemetry import trace
    def get_tracer():
        return trace.get_tracer("earthwhisper-bq-mcp")

logger = logging.getLogger("earthwhisper-bq-mcp")
logger.setLevel(logging.INFO)
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
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif ("timestamp" in k.lower() or "time" in k.lower()) and v is not None:
            try:
                out[k] = datetime.fromtimestamp(float(str(v)), tz=timezone.utc).isoformat()
            except (ValueError, TypeError, OverflowError):
                out[k] = v
        else:
            out[k] = v
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
            records = []

        if not records and mode == "live":
            try:
                from google.cloud import bigquery as bq_direct
                direct_client = bq_direct.Client(project=PROJECT_ID)
                direct_rows = list(direct_client.query(query).result())
                if direct_rows:
                    records = [dict(r.items()) for r in direct_rows]
                    logger.info(f"Direct BigQuery impact lookup retrieved {len(records)} assets.")
            except Exception as direct_err:
                logger.warning(f"Direct BigQuery impact lookup error: {direct_err}")

        if not records and mode == "mock":
            records = [
                {"asset_id": "MOCK-SET-001", "district": "Dhubri", "name": "Dhubri Town & River Port", "asset_type": "SETTLEMENT", "population": 63700, "vulnerability_index": 0.88},
                {"asset_id": "MOCK-SET-002", "district": "Barpeta", "name": "Barpeta Gram Panchayat", "asset_type": "SETTLEMENT", "population": 42600, "vulnerability_index": 0.82},
                {"asset_id": "MOCK-HOS-001", "district": "Dhubri", "name": "Dhubri Civil Hospital", "asset_type": "HOSPITAL", "population": None, "vulnerability_index": 0.90},
                {"asset_id": "MOCK-EVAC-001", "district": "Barpeta", "name": "Barpeta Flood Shelter Center", "asset_type": "EVACUATION_CENTER", "population": None, "vulnerability_index": 0.75},
                {"asset_id": "MOCK-BRI-001", "district": "Goalpara", "name": "Naranarayan Setu Bridge Access", "asset_type": "BRIDGE", "population": None, "vulnerability_index": 0.85}
            ]

        def _safe_int(v):
            try:
                return int(v) if v is not None else 0
            except (ValueError, TypeError):
                return 0

        total_pop = sum(_safe_int(r.get("population")) for r in records)
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
    scenario_id: str = "2024_ASSAM_BRAHMAPUTRA_SURGE",
) -> Dict[str, Any]:
    """
    Fetch the latest operational telemetry row for a catchment from
    `catchment_features`, returning the 14-feature dict the Vertex model needs
    plus freshness metadata. Returns {"error": ...} if no row is found (live).
    In mock mode, falls back to the verified historical replay scenario.
    """
    with tracer.start_as_current_span("earthwhisper.mcp.fetch_latest_features") as span:
        span.set_attribute("execution_mode", mode)
        span.set_attribute("catchment_id", catchment_id)
        span.set_attribute("scenario_id", scenario_id)

        # In mock mode, immediately return the selected historical replay fixture
        if mode == "mock":
            try:
                try:
                    from common.replay_generator import get_mock_scenario
                except ImportError:
                    from replay_generator import get_mock_scenario
                scenario_data = get_mock_scenario(scenario_id)
                features = {k: scenario_data.get(k) for k in FEATURE_COLUMNS}
                obs_ts = scenario_data.get("observation_timestamp")
                obs_iso = obs_ts.isoformat() if hasattr(obs_ts, "isoformat") else str(obs_ts)
                span.set_attribute("features.observation_timestamp", obs_iso)
                span.set_attribute("features.freshness_status", scenario_data.get("freshness_status"))
                return {
                    "catchment_id": scenario_data.get("catchment_id", catchment_id),
                    "observation_timestamp": obs_iso,
                    "ingestion_timestamp": obs_iso,
                    "features": features,
                    "freshness_status": scenario_data.get("freshness_status", "FRESH_NOMINAL"),
                    "feature_version": scenario_data.get("feature_version", "v1.0-replay"),
                }
            except Exception as e:
                return {"error": f"Failed loading mock scenario {scenario_id}: {e}", "features": {}}
       
        # In live mode, query BigQuery live dataset
        dataset = DATASET_LIVE
        table_ref = f"`{PROJECT_ID}.{dataset}.catchment_features`"
        cols = ", ".join(FEATURE_COLUMNS)
        logger.info("dataset, table_ref, scenario_id : %s, %s, %s", dataset, table_ref, scenario_id)

        query = f"""
            SELECT catchment_id, observation_timestamp, ingestion_timestamp,
                   {cols}, freshness_status, feature_version
            FROM {table_ref}
            WHERE catchment_id = @catchment_id
            ORDER BY observation_timestamp DESC
            LIMIT 1
        """
        params = [bigquery.ScalarQueryParameter("catchment_id", "STRING", catchment_id)]

        rows = []
        try:
            rows = get_mcp_client().execute_query(query, params)
        except Exception as e:
            logger.warning(f"catchment_features MCP query error: {e}")

        if not rows:
            logger.info("MCP execute_query returned empty list. Retrying with direct BigQuery client...")
            try:
                from google.cloud import bigquery as bq_direct
                direct_client = bq_direct.Client(project=PROJECT_ID)
                job_config = bq_direct.QueryJobConfig(query_parameters=params)
                direct_rows = list(direct_client.query(query, job_config=job_config).result())
                if direct_rows:
                    rows = [dict(r.items()) for r in direct_rows]
                    logger.info("Direct BigQuery query returned %d row(s).", len(rows))
            except Exception as direct_err:
                logger.warning("Direct BigQuery query attempt also failed: %s", direct_err)

        if not rows:
            return {
                "error": f"No telemetry found in live BigQuery table for catchment_id={catchment_id}. "
                         f"Please run data_pipeline/ingest_worker.py or switch to '🧪 Historical Replay / Benchmark' mode.",
                "features": {}
            }

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

        rows = []
        try:
            rows = get_mcp_client().execute_query(query, params)
        except Exception as e:
            logger.warning(f"catchment_climate_baseline query error: {e}")
            if mode == "live":
                return {"error": f"Baseline query failed: {e}"}

        if not rows and mode == "live":
            try:
                from google.cloud import bigquery as bq_direct
                direct_client = bq_direct.Client(project=PROJECT_ID)
                job_config = bq_direct.QueryJobConfig(query_parameters=params)
                direct_rows = list(direct_client.query(query, job_config=job_config).result())
                if direct_rows:
                    rows = [dict(r.items()) for r in direct_rows]
            except Exception as direct_err:
                logger.warning(f"Direct BigQuery baseline query error: {direct_err}")

        if not rows:
            if mode == "live":
                return {"error": f"No baseline found for catchment_id={catchment_id}, doy={doy}"}
            # Mock mode fallback
            return {
                "doy": doy,
                "mean_rain_24h_mm": 58.2,
                "std_rain_24h_mm": 48.5,
                "mean_rain_72h_mm": 135.0,
                "std_rain_72h_mm": 95.0,
                "baseline_window_years": 20
            }
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
        try:
            get_mcp_client().insert_rows(table_id, [record])
            logger.info(f"Audit {record.get('audit_id')} written to {table_id}.")
            return {"status": "written", "audit_id": record.get("audit_id"), "table": table_id}
        except Exception as e:
            logger.warning(f"BigQuery audit write failed via MCP client ({e}). Retrying via direct client...")
            try:
                from google.cloud import bigquery as bq_direct
                direct_client = bq_direct.Client(project=PROJECT_ID)
                table = direct_client.get_table(table_id)
                errors = direct_client.insert_rows_json(table, [record])
                if errors:
                    raise RuntimeError(f"insert_rows_json errors: {errors}")
                logger.info(f"Audit {record.get('audit_id')} written to {table_id} via direct BigQuery client.")
                return {"status": "written", "audit_id": record.get("audit_id"), "table": table_id}
            except Exception as d_err:
                logger.error(f"Direct BigQuery audit write failed: {d_err}")
                if mode == "live":
                    raise d_err
                return {"status": "mock_recorded", "audit_id": record.get("audit_id"), "table": table_id}

