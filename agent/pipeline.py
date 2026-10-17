"""
Deterministic flood-risk assessment pipeline for EarthWhisper.

run_assessment() orchestrates the full live chain in a fixed order and writes a
compliance record to alert_audits. It is the orchestration-level path used by the
replay demo and the Pub/Sub handler, so audit fields come from real tool outputs
(not an LLM). The conversational LlmAgent in agent.py wraps the same tools.

Flow: fetch_latest_features -> predict_flood_risk -> get_climate_baseline
      -> lookup_impact_graph -> summarize_with_gemini -> check_alert_policy
      -> assemble + write alert_audits row.
"""

import json
import uuid
import logging
from datetime import datetime, timezone

from telemetry import get_tracer, get_current_trace_id
from tools.bq_mcp_client import (
    fetch_latest_features,
    get_climate_baseline,
    lookup_impact_graph,
    write_alert_audit,
)
from tools.vertex_predictor import predict_flood_risk
from tools.summarize_tool import summarize_with_gemini
from policy.alert_policy import check_alert_policy

logger = logging.getLogger("earthwhisper-pipeline")
tracer = get_tracer()


def _doy_from(observation_timestamp: str) -> int:
    """Day-of-year (1-366) from an ISO timestamp, falling back to today."""
    try:
        return datetime.fromisoformat(observation_timestamp).timetuple().tm_yday
    except Exception:
        return datetime.now(timezone.utc).timetuple().tm_yday


def _data_quality_from(freshness_status: str) -> str:
    """Map telemetry freshness_status onto the policy's data_quality vocabulary."""
    if not freshness_status:
        return "unknown"
    status_lower = str(freshness_status).lower()
    return "good" if status_lower in ("fresh", "good", "fresh_nominal") else freshness_status


def run_assessment(
    catchment_id: str = "brahmaputra_lower_assam",
    mode: str = "live",
    area_name: str = None,
    scenario_id: str = "2024_ASSAM_BRAHMAPUTRA_SURGE",
    features: dict = None,
    observation_timestamp: str = None,
    freshness_status: str = None,
) -> dict:
    """Run the end-to-end assessment and append an audit record. Returns a structured result.

    If `features` is supplied (e.g. straight from a Pub/Sub signal the ingest worker
    published), the BigQuery telemetry re-fetch is skipped and those features are used.
    """
    with tracer.start_as_current_span("earthwhisper.pipeline.run_assessment") as span:
        span.set_attribute("execution_mode", mode)
        span.set_attribute("catchment_id", catchment_id)
        span.set_attribute("scenario_id", scenario_id)
        trace_id = get_current_trace_id()
        area_name = area_name or catchment_id
        tool_log = []

        # 1. Telemetry -> 14 features (from the signal payload if provided, else BigQuery)
        if features:
            feat = {
                "features": features,
                "observation_timestamp": observation_timestamp or datetime.now(timezone.utc).isoformat(),
                "freshness_status": freshness_status or "FRESH_NOMINAL",
                "feature_version": "from-signal",
            }
        else:
            feat = fetch_latest_features(catchment_id, mode=mode, scenario_id=scenario_id)
        tool_log.append({
            "tool": "fetch_latest_features",
            "ok": "error" not in feat,
            "source": "signal" if features else "bigquery",
        })
        if feat.get("error") or not feat.get("features"):
            msg = feat.get("error", "No telemetry available")
            logger.warning("Assessment aborted: %s", msg)
            return {"status": "no_data", "catchment_id": catchment_id, "error": msg, "trace_id": trace_id}

        features = feat["features"]
        observation_timestamp = feat["observation_timestamp"]
        freshness_status = feat.get("freshness_status") or "unknown"

        # 2. Authoritative prediction from Vertex AI
        prediction = predict_flood_risk(features, mode=mode)
        risk_class = int(prediction["risk_class"])
        risk_label = prediction["risk_label"]
        risk_score = float(prediction["risk_score"])
        model_version = prediction.get("model_version", "unknown")
        tool_log.append({"tool": "predict_flood_risk", "risk_class": risk_class, "risk_score": risk_score})

        # 3. Seasonal baseline (grounding; best-effort)
        baseline = get_climate_baseline(catchment_id, _doy_from(observation_timestamp), mode=mode)
        tool_log.append({"tool": "get_climate_baseline", "ok": "error" not in baseline})

        # 4. Exposed assets / population
        impact = lookup_impact_graph(catchment_id, risk_class=risk_class, mode=mode)
        affected = (
            len(impact.get("exposed_settlements", []))
            + len(impact.get("critical_hospitals", []))
            + len(impact.get("evacuation_centers", []))
            + len(impact.get("vulnerable_bridges", []))
        )
        tool_log.append({"tool": "lookup_impact_graph", "affected_assets": affected,
                         "exposed_population": impact.get("total_exposed_population", 0)})

        # 5. Grounded briefing
        summary_result = summarize_with_gemini(
            area_name=area_name,
            risk_label=risk_label,
            risk_score=risk_score,
            features=features,
            baseline=baseline,
            impact=impact,
            model_version=model_version,
        )
        briefing = summary_result.get("summary", "")
        actions = summary_result.get("recommended_actions", [])
        tool_log.append({"tool": "summarize_with_gemini", "chars": len(briefing)})

        # 6. Alert policy
        data_quality = _data_quality_from(freshness_status)
        policy_result = check_alert_policy(
            area_id=catchment_id,
            risk_class=risk_label.lower(),
            risk_score=risk_score,
            data_quality=data_quality,
        )
        tool_log.append({"tool": "check_alert_policy", "decision": policy_result["decision"]})

        span.set_attribute("assessment.risk_class", risk_class)
        span.set_attribute("assessment.policy_decision", policy_result["decision"])

        # 7. Assemble + write the compliance audit record
        now_iso = datetime.now(timezone.utc).isoformat()
        audit_record = {
            "audit_id": uuid.uuid4().hex,
            "execution_mode": mode,
            "trace_id": trace_id or "no-trace",
            "catchment_id": catchment_id,
            "observation_timestamp": observation_timestamp,
            "evaluation_timestamp": now_iso,
            "risk_score": risk_score,
            "risk_class": risk_class,
            "model_version": model_version,
            "data_freshness_status": freshness_status,
            "policy_action": policy_result["decision"],
            "gemini_briefing": briefing,
            "tool_call_log": json.dumps(tool_log),
            "affected_assets_count": affected,
        }

        audit_status = None
        try:
            audit_status = write_alert_audit(audit_record, mode=mode)
        except Exception as e:
            logger.error("Audit write failed: %s", e)
            span.record_exception(e)
            audit_status = {"status": "error", "error": str(e)}

        return {
            "status": "ok",
            "catchment_id": catchment_id,
            "area_name": area_name,
            "observation_timestamp": observation_timestamp,
            "freshness_status": freshness_status,
            "features": features,
            "prediction": prediction,
            "baseline": baseline,
            "impact": impact,
            "summary": briefing,
            "recommended_actions": actions,
            "policy": policy_result,
            "affected_assets_count": affected,
            "trace_id": trace_id,
            "audit": {"record_id": audit_record["audit_id"], "write": audit_status},
        }