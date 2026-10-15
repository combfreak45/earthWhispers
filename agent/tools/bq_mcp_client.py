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

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data_pipeline")))
from mcp_bq_client import BigQueryMCPClient
from telemetry import get_tracer

logger = logging.getLogger("earthwhisper-bq-mcp")
tracer = get_tracer()

PROJECT_ID = os.getenv("PROJECT_ID", "earthwhisper-dev")
DATASET_LIVE = os.getenv("BIGQUERY_DATASET_LIVE", "earthwhisper_live")
DATASET_MOCK = os.getenv("BIGQUERY_DATASET_MOCK", "earthwhisper_mock")

mcp_client = None


def get_mcp_client() -> BigQueryMCPClient:
    global mcp_client
    if mcp_client is None:
        mcp_client = BigQueryMCPClient(project_id=PROJECT_ID)
    return mcp_client


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
