import json
from pathlib import Path

MOCK_DATA_DIR = Path(__file__).parents[1] / "mock_data"


def load_signal_events() -> list:
    with open(MOCK_DATA_DIR / "signal_events.json") as f:
        return json.load(f)


def load_predictions() -> list:
    with open(MOCK_DATA_DIR / "predictions.json") as f:
        return json.load(f)


def load_impact_context(area_id: str) -> dict:
    with open(MOCK_DATA_DIR / "impact_context.json") as f:
        data = json.load(f)
    return data.get(area_id, {})


def get_enriched_predictions() -> list:
    """Join predictions with signal events for display."""
    events = {e["event_id"]: e for e in load_signal_events()}
    predictions = load_predictions()
    enriched = []
    for p in predictions:
        event = events.get(p["event_id"], {})
        enriched.append({**p, **event})
    return enriched
