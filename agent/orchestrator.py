"""
EarthWhisper ADK Agent Orchestrator
Coordinates Vertex AI XGBoost predictions, BigQuery MCP ImpactGraph lookups,
and Gemini 2.5 Flash evidence synthesis.
"""

import os
import json
import logging
from typing import Dict, Any, Optional

from tools.vertex_predictor import predict_flood_risk
from tools.bq_mcp_client import lookup_impact_graph
from tools.vision_analyzer import analyze_ground_imagery
from policy_engine import evaluate_alert_policy, DISCLAIMER_TEXT
from telemetry import get_tracer

logger = logging.getLogger("earthwhisper-orchestrator")
tracer = get_tracer()

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


SYSTEM_INSTRUCTION = """You are EarthWhisper, an analytical flood-risk intelligence orchestrator built for the Google Cloud AI Builder Cup.
Your mission is to synthesize environmental features, numerical ML model outputs, and geospatial impact data into an objective, evidence-grounded risk briefing.

MANDATORY OPERATING PRINCIPLES:
1. STRICT GROUNDING: Never invent, extrapolate, or hallucinate casualty numbers, percentages, or rainfall quantities.
2. NUMERICAL AUTHORITY: The numerical flood risk score (0.0 to 1.0) and class (0: Low, 1: Moderate, 2: High) come EXCLUSIVELY from the `predict_flood_risk` tool. You must NEVER recalculate or alter these numbers.
3. IMPACT GROUNDING: The settlements, hospitals, schools, and bridges you cite MUST come directly from the `lookup_impact_graph` tool results. If no records are returned, state: "No critical infrastructure records found in the database for this specific radius."
4. CAVEATS & FRESHNESS: You must explicitly report the satellite sensor latency (hours) and state known limitations.
5. PREPAREDNESS GUIDANCE: Formulate cautious, practical preparedness actions tailored to local communities and gram panchayats in Assam.
6. NO EMERGENCY AUTHORITY: Always include the mandatory prototype research disclaimer. You are an experimental AI assistant, not an official civil authority."""


def synthesize_briefing_with_gemini(
    features: Dict[str, Any],
    prediction: Dict[str, Any],
    impact: Dict[str, Any],
    freshness_status: str
) -> str:
    """
    Calls Gemini 2.5 Flash to compose the structured risk briefing.
    """
    with tracer.start_as_current_span("earthwhisper.gemini.synthesis") as span:
        span.set_attribute("model", GEMINI_MODEL)
        
        prompt = f"""Synthesize an evidence-grounded flood risk situational report for the Lower Brahmaputra Basin (Assam) based ONLY on these verified tool outputs:

1. Environmental Observations:
- 24-hour Rainfall: {features.get('rain_24h_mm', 0)} mm
- 72-hour Antecedent Rainfall: {features.get('rain_72h_mm', 0)} mm
- 72-hour Rainfall Baseline Z-Score: {features.get('rain_72h_zscore', 0)}
- 24-hour Anomaly: {features.get('rain_24h_anomaly_pct', 0)}% above seasonal mean
- Volumetric Soil Moisture: {features.get('soil_water_layer1', 0)} m³/m³
- Sensor Latency: {features.get('data_freshness_hrs', 0)} hours ({freshness_status})

2. Vertex AI ML Prediction (XGBoost):
- Risk Class: {prediction['risk_class']} ({prediction['risk_label']})
- Risk Score: {prediction['risk_score']}
- Class Probabilities: Low: {prediction['class_probabilities']['low']}, Moderate: {prediction['class_probabilities']['moderate']}, Severe: {prediction['class_probabilities']['severe']}
- Top Contributing Drivers: {json.dumps(prediction.get('top_contributing_features', []))}

3. BigQuery ImpactGraph Assets:
- Total Exposed Population: {impact.get('total_exposed_population', 0):,}
- Vulnerable Settlements: {', '.join(impact.get('exposed_settlements', []))}
- Critical Hospitals: {', '.join(impact.get('critical_hospitals', []))}
- Evacuation Shelters: {', '.join(impact.get('evacuation_centers', []))}
- Key Bridges/Corridors: {', '.join(impact.get('vulnerable_bridges', []))}

Write a structured briefing with these exact headers:
### 1. Executive Risk Assessment
### 2. Physical & Meteorological Evidence
### 3. Vulnerable Communities & Critical Infrastructure
### 4. Recommended Preparedness Actions
### 5. Data Freshness & Sensor Limitations
"""

        try:
            from google import genai
            client = genai.Client()
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[prompt],
                config={"system_instruction": SYSTEM_INSTRUCTION}
            )
            return response.text
        except Exception as e:
            logger.warning(f"Gemini API call failed or running in test mode ({e}); generating grounded fallback template.")
            # Deterministic grounded template strictly using tool values
            return f"""### 1. Executive Risk Assessment
**Overall Status: {prediction['risk_label'].upper()} RISK (Class {prediction['risk_class']})**
The Vertex AI XGBoost predictive model estimates a calibrated flood risk score of **{prediction['risk_score']}** (Severe probability: {prediction['class_probabilities']['severe']:.2f}).

### 2. Physical & Meteorological Evidence
- **Precipitation:** Cumulative 24-hour rainfall reached **{features.get('rain_24h_mm', 0)} mm**, with 72-hour antecedent rainfall totaling **{features.get('rain_72h_mm', 0)} mm**.
- **Historical Baseline Deviation:** The 72-hour rainfall represents a **Z-Score anomaly of {features.get('rain_72h_zscore', 0):.2f}** ({features.get('rain_24h_anomaly_pct', 0):.1f}% above seasonal Day-of-Year climatological normal).
- **Soil Saturation:** Volumetric soil water in top layer is at **{features.get('soil_water_layer1', 0):.3f} m³/m³**, indicating elevated saturation in the river valley.

### 3. Vulnerable Communities & Critical Infrastructure
According to the BigQuery ImpactGraph:
- **Exposed Population:** Approximately **{impact.get('total_exposed_population', 0):,}** residents across vulnerable riverine zones.
- **Settlements at Risk:** {', '.join(impact.get('exposed_settlements', ['None identified']))}.
- **Key Infrastructure:** Priority monitoring required for {', '.join(impact.get('critical_hospitals', ['Regional health centers']))} and transport access via {', '.join(impact.get('vulnerable_bridges', ['Local river corridors']))}.

### 4. Recommended Preparedness Actions
1. Verify emergency power and water filtration readiness at {', '.join(impact.get('critical_hospitals', ['local health facilities']))}.
2. Pre-position non-motorized relief craft near {', '.join(impact.get('evacuation_centers', ['designated shelters']))}.
3. Issue community alerts in gram panchayats with advice to elevate potable water stores and livestock.

### 5. Data Freshness & Sensor Limitations
- **Sensor Latency:** Current observation is {features.get('data_freshness_hrs', 0)} hours old ({freshness_status}).
- **Caveat:** Earth observation satellites (GPM IMERG) measure atmospheric precipitation averages (~11 km grid) and do not directly measure instantaneous river discharge.
"""


def run_orchestration(signal_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Executes the complete ADK agent orchestration pipeline.
    """
    with tracer.start_as_current_span("earthwhisper.agent.run_orchestration") as span:
        mode = signal_payload.get("mode", "live")
        catchment_id = signal_payload.get("catchment_id", "brahmaputra_lower_assam")
        features = signal_payload.get("features", {})
        freshness_status = signal_payload.get("freshness_status", "FRESH_NOMINAL")

        span.set_attribute("execution_mode", mode)
        span.set_attribute("catchment_id", catchment_id)

        # 1. Tool Call: Vertex AI XGBoost Prediction
        prediction = predict_flood_risk(features, mode=mode)

        # 2. Tool Call: BigQuery ImpactGraph Lookup
        impact = lookup_impact_graph(catchment_id, risk_class=prediction["risk_class"], mode=mode)

        # 3. Tool Call / Synthesis: Gemini 2.5 Flash Grounded Briefing
        briefing = synthesize_briefing_with_gemini(features, prediction, impact, freshness_status)

        # 4. Policy Gate: Deduplication, Cooldown, and Escalation Checks
        policy = evaluate_alert_policy(
            catchment_id=catchment_id,
            risk_class=prediction["risk_class"],
            risk_score=prediction["risk_score"],
            data_freshness_status=freshness_status,
            mode=mode
        )

        result = {
            "catchment_id": catchment_id,
            "execution_mode": mode,
            "prediction": prediction,
            "impact": impact,
            "policy": policy,
            "briefing": briefing,
            "disclaimer": DISCLAIMER_TEXT
        }

        span.set_attribute("policy.should_dispatch", policy["should_dispatch_alert"])
        span.set_attribute("policy.action", policy["policy_action"])
        return result
