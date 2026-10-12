import json
from pathlib import Path
from datetime import datetime, timezone

MOCK_DATA_DIR = Path(__file__).parents[1] / "mock_data"


def query_impact_graph(area_id: str) -> dict:
    """
    Return nearby settlements and critical assets for a given area.
    In production: query BigQuery earthwhispers.impact_context with geospatial join.

    Args:
        area_id: catchment identifier

    Returns:
        dict with nearby_settlements, critical_assets, data_source, coverage_notes
    """
    with open(MOCK_DATA_DIR / "impact_context.json") as f:
        impact_data = json.load(f)

    result = impact_data.get(area_id)
    if not result:
        return {
            "error": f"No impact context found for area_id={area_id}",
            "nearby_settlements": [],
            "critical_assets": [],
        }

    return {
        "queried_at": datetime.now(timezone.utc).isoformat(),
        "area_id": area_id,
        **result,
    }
