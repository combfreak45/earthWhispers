import json
import os
from datetime import datetime, timezone
from pathlib import Path

MOCK_DATA_DIR = Path(__file__).parents[2] / "mock_data"


def fetch_observations(area_id: str, event_id: str = None) -> dict:
    """
    Fetch signal event for a given area from mock data.
    If event_id is provided, returns that specific event.
    Otherwise returns the most recent event for the area.
    In production: query BigQuery earthwhispers.signal_events.
    """
    with open(MOCK_DATA_DIR / "signal_events.json") as f:
        events = json.load(f)

    if event_id:
        match = next((e for e in events if e["event_id"] == event_id), None)
        if not match:
            return {"error": f"No event found with event_id={event_id}"}
        return match

    area_events = [e for e in events if e["area_id"] == area_id]
    if not area_events:
        return {"error": f"No signal events found for area_id={area_id}"}

    return sorted(area_events, key=lambda e: e["event_time"], reverse=True)[0]
