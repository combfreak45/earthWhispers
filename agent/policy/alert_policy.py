import yaml
from datetime import datetime, timezone, timedelta
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "policy_config.yaml"

# In-memory cooldown store — replace with BigQuery/Redis in production
_last_alert_times: dict[str, datetime] = {}


def load_policy() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)["alert_policy"]


def check_alert_policy(
    area_id: str,
    risk_class: str,
    risk_score: float,
    data_quality: str,
) -> dict:
    """
    Apply alert policy: thresholds, cooldown dedup, human review gate, data quality check.

    Returns:
        dict with decision ("send_alert" | "suppress" | "human_review") and reason
    """
    policy = load_policy()

    # Data quality gate
    if data_quality != policy["min_data_quality"]:
        return {
            "decision": "suppress",
            "reason": f"Data quality '{data_quality}' does not meet minimum '{policy['min_data_quality']}'. Not alerting.",
        }

    # Low risk — suppress
    if risk_score < policy["thresholds"]["low"]:
        return {
            "decision": "suppress",
            "reason": f"Risk score {risk_score:.2f} is below low threshold {policy['thresholds']['low']}.",
        }

    # Cooldown dedup
    cooldown = timedelta(minutes=policy["cooldown_minutes"])
    last_alert = _last_alert_times.get(area_id)
    if last_alert and (datetime.now(timezone.utc) - last_alert) < cooldown:
        remaining = cooldown - (datetime.now(timezone.utc) - last_alert)
        return {
            "decision": "suppress",
            "reason": f"Cooldown active for {area_id}. Next alert allowed in {int(remaining.total_seconds() / 60)} minutes.",
        }

    # Human review gate for high risk (demo safety)
    if risk_class == policy["human_review_above"] or risk_score >= policy["thresholds"]["high"]:
        return {
            "decision": "human_review",
            "reason": f"Risk class '{risk_class}' (score {risk_score:.2f}) requires human review before escalation.",
        }

    # Clear to send
    _last_alert_times[area_id] = datetime.now(timezone.utc)
    return {
        "decision": "send_alert",
        "reason": f"Risk class '{risk_class}' (score {risk_score:.2f}) meets threshold. Alert approved.",
    }
