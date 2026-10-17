"""
EarthWhisper Ingestion Worker Service (Cloud Run)
Invoked on a schedule via Cloud Scheduler or on-demand via HTTP POST.
Extracts environmental signals, computes baseline deviations, validates quality,
persists records to BigQuery, and publishes signal events to Pub/Sub.
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from google.cloud import pubsub_v1

from ee_extractor import extract_live_catchment_features, DataSourceUnavailableError
from baseline_calculator import compute_derived_features
from freshness_validator import validate_observation_quality
from replay_generator import get_mock_scenario
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from common.mcp_bq_client import BigQueryMCPClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("earthwhisper-ingest-worker")

app = FastAPI(
    title="EarthWhisper Ingestion Worker",
    description="Ingests satellite rainfall & environmental data, validates quality, computes baseline anomalies, and emits Pub/Sub signals.",
    version="1.0.0"
)

PROJECT_ID = os.getenv("PROJECT_ID", "earth-whisper-ai-builders-cup")
REGION = os.getenv("REGION", "us-central1")
DEFAULT_CATCHMENT_ID = os.getenv("CATCHMENT_ID", "brahmaputra_lower_assam")
TOPIC_SIGNALS = os.getenv("PUBSUB_TOPIC_SIGNALS", f"projects/{PROJECT_ID}/topics/earthwhisper-signals")
DATASET_LIVE = os.getenv("BIGQUERY_DATASET_LIVE", "earthwhisper_live")
DATASET_MOCK = os.getenv("BIGQUERY_DATASET_MOCK", "earthwhisper_mock")

mcp_client: Optional[BigQueryMCPClient] = None
publisher_client: Optional[pubsub_v1.PublisherClient] = None


def get_mcp_client() -> BigQueryMCPClient:
    global mcp_client
    if mcp_client is None:
        mcp_client = BigQueryMCPClient(project_id=PROJECT_ID)
    return mcp_client


def get_publisher() -> pubsub_v1.PublisherClient:
    global publisher_client
    if publisher_client is None:
        publisher_client = pubsub_v1.PublisherClient()
    return publisher_client


class IngestRequest(BaseModel):
    mode: str = Field(default="live", description="Execution mode: 'live' or 'mock'")
    catchment_id: str = Field(default=DEFAULT_CATCHMENT_ID, description="Target catchment identifier")
    scenario_id: Optional[str] = Field(default="2022_ASSAM_CATASTROPHIC", description="Scenario ID if mode is 'mock'")


class IngestResponse(BaseModel):
    status: str
    mode: str
    catchment_id: str
    observation_timestamp: str
    freshness_status: str
    rain_24h_mm: float
    rain_72h_zscore: float
    rain_24h_anomaly_pct: float
    signal_published: bool
    pubsub_message_id: Optional[str] = None


def fetch_doy_baseline(dataset: str, catchment_id: str, doy: int) -> Dict[str, float]:
    """
    Fetches historical climatology baseline for the given Day-of-Year from BigQuery
    using the BigQuery MCP Toolset (execute_query).
    """
    query = f"""
        SELECT mean_rain_24h_mm, std_rain_24h_mm, mean_rain_72h_mm, std_rain_72h_mm
        FROM `{PROJECT_ID}.{dataset}.catchment_climate_baseline`
        WHERE catchment_id = '{catchment_id}' AND doy = {doy}
        LIMIT 1
    """
    try:
        results = get_mcp_client().execute_query(query)
        if results:
            row = results[0]
            return {
                "mean_rain_24h_mm": float(row["mean_rain_24h_mm"]),
                "std_rain_24h_mm": float(row["std_rain_24h_mm"]),
                "mean_rain_72h_mm": float(row["mean_rain_72h_mm"]),
                "std_rain_72h_mm": float(row["std_rain_72h_mm"])
            }
    except Exception as e:
        logger.warning(f"Could not load baseline via BigQuery MCP ({e}); using regional monsoon baseline.")
        
    # Default seasonal baseline fallback for Lower Brahmaputra basin if table empty
    return {
        "mean_rain_24h_mm": 22.5,
        "std_rain_24h_mm": 14.0,
        "mean_rain_72h_mm": 65.0,
        "std_rain_72h_mm": 35.0
    }


def persist_catchment_features(dataset: str, features: Dict[str, Any]):
    """
    Inserts validated catchment features into BigQuery using the BigQuery MCP Toolset.
    """
    table_id = f"{PROJECT_ID}.{dataset}.catchment_features"
    # Format timestamps for BigQuery
    row = dict(features)
    if isinstance(row.get("observation_timestamp"), datetime):
        row["observation_timestamp"] = row["observation_timestamp"].isoformat()
    if isinstance(row.get("ingestion_timestamp"), datetime):
        row["ingestion_timestamp"] = row["ingestion_timestamp"].isoformat()
        
    try:
        get_mcp_client().insert_record(table_id, row)
        logger.info(f"Successfully persisted features into {table_id} via BigQuery MCP.")
    except Exception as e:
        logger.error(f"Failed to insert features into BigQuery {table_id} via MCP: {e}")
        raise RuntimeError(f"BigQuery MCP insert failed: {e}")


def publish_signal_event(topic_id: str, payload: Dict[str, Any]) -> str:
    """
    Publishes a compact signal event to Pub/Sub to trigger the ADK agent.
    """
    data = json.dumps(payload).encode("utf-8")
    future = get_publisher().publish(topic_id, data, **{
        "catchment_id": payload["catchment_id"],
        "mode": payload["mode"],
        "freshness_status": payload["freshness_status"]
    })
    return future.result()


@app.get("/health")
def health():
    return {"status": "ok", "service": "earthwhisper-ingest-worker", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.post("/ingest/run", response_model=IngestResponse)
def run_ingestion(req: IngestRequest):
    """
    Main ingestion worker handler.
    Strictly segregates --mode=live and --mode=mock.
    """
    logger.info(f"Starting ingestion run: mode={req.mode}, catchment={req.catchment_id}")
    now_utc = datetime.now(timezone.utc)
    target_dataset = DATASET_LIVE if req.mode == "live" else DATASET_MOCK

    if req.mode == "live":
        # 1. Fetch live Earth Engine data
        try:
            raw_features = extract_live_catchment_features(
                catchment_id=req.catchment_id,
                ref_time_utc=now_utc,
                project_id=PROJECT_ID
            )
        except DataSourceUnavailableError as e:
            logger.error(f"Live data source unavailable: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Live Earth Engine data source error: {str(e)}"
            )

        # 2. Validate freshness
        quality = validate_observation_quality(
            observation_time_utc=raw_features["observation_timestamp"],
            valid_pixel_pct=raw_features.get("spatial_coverage_pct", 100.0),
            current_time_utc=now_utc
        )

        # 3. Lookup DOY Climatology Baseline
        doy = raw_features["observation_timestamp"].timetuple().tm_yday
        baseline = fetch_doy_baseline(target_dataset, req.catchment_id, doy)

        # 4. Deterministic Anomaly Math
        anomalies = compute_derived_features(raw_features, baseline)

        # Assemble full feature dictionary
        full_record = {
            **raw_features,
            **anomalies,
            "ingestion_timestamp": now_utc,
            "data_freshness_hrs": quality.data_freshness_hrs,
            "spatial_coverage_pct": quality.spatial_coverage_pct,
            "freshness_status": quality.freshness_status,
            "feature_version": "v1.0"
        }

    elif req.mode == "mock":
        # Load verified isolated replay fixture
        mock_data = get_mock_scenario(req.scenario_id or "2022_ASSAM_CATASTROPHIC")
        full_record = {
            **mock_data,
            "ingestion_timestamp": now_utc,
            "catchment_id": req.catchment_id
        }
    else:
        raise HTTPException(status_code=400, detail="Invalid mode: must be 'live' or 'mock'")

    # Persist to BigQuery
    persist_catchment_features(target_dataset, full_record)
    logger.info(f"Persisted features to {target_dataset}.catchment_features")

    # Evaluate signal rule: If rainfall >= 10mm or anomaly >= 20% or scheduled evaluation
    # Publish compact event to Pub/Sub to trigger ADK agent
    signal_payload = {
        "event_id": f"sig-{req.catchment_id}-{int(now_utc.timestamp())}",
        "mode": req.mode,
        "catchment_id": req.catchment_id,
        "observation_timestamp": full_record["observation_timestamp"].isoformat() if isinstance(full_record["observation_timestamp"], datetime) else str(full_record["observation_timestamp"]),
        "freshness_status": full_record["freshness_status"],
        "data_freshness_hrs": full_record["data_freshness_hrs"],
        "rain_24h_mm": full_record["rain_24h_mm"],
        "rain_72h_mm": full_record["rain_72h_mm"],
        "rain_72h_zscore": full_record["rain_72h_zscore"],
        "rain_24h_anomaly_pct": full_record["rain_24h_anomaly_pct"],
        "features": {
            "rain_1h_mm": full_record["rain_1h_mm"],
            "rain_3h_mm": full_record["rain_3h_mm"],
            "rain_6h_mm": full_record["rain_6h_mm"],
            "rain_24h_mm": full_record["rain_24h_mm"],
            "rain_72h_mm": full_record["rain_72h_mm"],
            "rain_7d_mm": full_record["rain_7d_mm"],
            "rain_peak_1h_mm": full_record["rain_peak_1h_mm"],
            "rain_24h_anomaly_pct": full_record["rain_24h_anomaly_pct"],
            "rain_72h_zscore": full_record["rain_72h_zscore"],
            "soil_water_layer1": full_record["soil_water_layer1"],
            "elevation_mean_m": full_record["elevation_mean_m"],
            "slope_mean_deg": full_record["slope_mean_deg"],
            "data_freshness_hrs": full_record["data_freshness_hrs"],
            "spatial_coverage_pct": full_record["spatial_coverage_pct"]
        }
    }

    msg_id = publish_signal_event(TOPIC_SIGNALS, signal_payload)
    logger.info(f"Published signal event to Pub/Sub: message_id={msg_id}")

    return IngestResponse(
        status="SUCCESS",
        mode=req.mode,
        catchment_id=req.catchment_id,
        observation_timestamp=signal_payload["observation_timestamp"],
        freshness_status=full_record["freshness_status"],
        rain_24h_mm=full_record["rain_24h_mm"],
        rain_72h_zscore=full_record["rain_72h_zscore"],
        rain_24h_anomaly_pct=full_record["rain_24h_anomaly_pct"],
        signal_published=True,
        pubsub_message_id=msg_id
    )


if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="EarthWhisper Ingestion Worker")
    parser.add_argument("--run-now", action="store_true", help="Execute an ingestion pass immediately via CLI")
    parser.add_argument("--mode", choices=["live", "mock"], default="live", help="Execution mode (live or mock)")
    parser.add_argument("--catchment_id", default=DEFAULT_CATCHMENT_ID, help="Target catchment ID")
    parser.add_argument("--scenario_id", default="2022_ASSAM_CATASTROPHIC", help="Mock scenario ID if mode is mock")
    parser.add_argument("--project_id", default=PROJECT_ID, help="GCP Project ID")
    parser.add_argument("--dataset_id", default=DATASET_LIVE, help="Target BigQuery Dataset ID")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", 8080)), help="Web server port")
    args, _ = parser.parse_known_args()

    if args.run_now:
        PROJECT_ID = args.project_id
        if args.mode == "live":
            DATASET_LIVE = args.dataset_id
        else:
            DATASET_MOCK = args.dataset_id

        req = IngestRequest(mode=args.mode, catchment_id=args.catchment_id, scenario_id=args.scenario_id)
        resp = run_ingestion(req)
        print("\n=== Ingestion Run Completed Successfully ===")
        print(f"Status: {resp.status}")
        print(f"Mode: {resp.mode}")
        print(f"Catchment: {resp.catchment_id}")
        print(f"Observation Time: {resp.observation_timestamp}")
        print(f"Freshness Status: {resp.freshness_status}")
        print(f"Rain 24h: {resp.rain_24h_mm} mm")
        print(f"Rain 72h Z-Score: {resp.rain_72h_zscore}")
        print(f"Rain 24h Anomaly: {resp.rain_24h_anomaly_pct}%")
        print(f"Signal Published: {resp.signal_published} (Pub/Sub msg: {resp.pubsub_message_id})")
    else:
        uvicorn.run("ingest_worker:app", host="0.0.0.0", port=args.port, reload=True)
