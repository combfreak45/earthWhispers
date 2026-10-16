"""
EarthWhisper Policy & Deduplication Engine
Enforces alert thresholds, deduplication cooldown windows, prototype disclaimers,
and prepares audit lineage records for BigQuery.
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Tuple

DISCLAIMER_TEXT = (
    "NOTICE: EarthWhisper is an experimental research prototype for the Google Cloud AI Builder Cup. "
    "It is NOT an official emergency management alert system. Consult official local disaster management "
    "authorities (NDMA/ASDMA) for binding evacuation advisories."
)

# In-memory cooldown cache per catchment for Cloud Run instance lifecycle
# (Production scales with BigQuery audit timestamp lookups)
_LAST_ALERT_CACHE: Dict[str, Tuple[datetime, int]] = {}


def evaluate_alert_policy(
    catchment_id: str,
    risk_class: int,
    risk_score: float,
    data_freshness_status: str,
    mode: str = "live",
    cooldown_hours: float = 6.0
) -> Dict[str, Any]:
    """
    Evaluates whether an alert should be escalated to the outbound alert bus.
    """
    now = datetime.now(timezone.utc)
    
    # 1. Freshness Policy: Stale data cannot trigger high-risk emergency escalation
    if data_freshness_status == "STALE_CRITICAL" and risk_class >= 1:
        return {
            "should_dispatch_alert": False,
            "policy_action": "SUPPRESSED_STALE_DATA",
            "reason": "Sensor latency exceeds critical 48-hour threshold. Escalation blocked.",
            "disclaimer": DISCLAIMER_TEXT,
            "is_simulated": mode == "mock"
        }

    # 2. Risk Threshold: Only Moderate (1) or Severe (2) are eligible for outbound alerts
    if risk_class == 0:
        return {
            "should_dispatch_alert": False,
            "policy_action": "LOGGED_NOMINAL",
            "reason": "Risk score is Low/Normal. No alert required.",
            "disclaimer": DISCLAIMER_TEXT,
            "is_simulated": mode == "mock"
        }

    # 3. Cooldown & Deduplication Gate
    last_record = _LAST_ALERT_CACHE.get(catchment_id)
    if last_record:
        last_time, last_class = last_record
        time_elapsed = (now - last_time).total_seconds() / 3600.0

        # If within cooldown AND risk level has NOT escalated, suppress duplicate
        if time_elapsed < cooldown_hours and risk_class <= last_class:
            return {
                "should_dispatch_alert": False,
                "policy_action": "SUPPRESSED_COOLDOWN",
                "reason": f"Deduplication cooldown active ({time_elapsed:.1f}h < {cooldown_hours}h) with same or lower severity.",
                "disclaimer": DISCLAIMER_TEXT,
                "is_simulated": mode == "mock"
            }

    # Update cooldown cache
    _LAST_ALERT_CACHE[catchment_id] = (now, risk_class)

    return {
        "should_dispatch_alert": True,
        "policy_action": "DISPATCHED_ALERT",
        "reason": f"Elevated risk class {risk_class} ({risk_score:.2f}) passed all policy gates.",
        "disclaimer": DISCLAIMER_TEXT,
        "is_simulated": mode == "mock"
    }
