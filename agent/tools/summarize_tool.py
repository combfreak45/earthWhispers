import os
from google import genai
from google.genai import types

SYSTEM_INSTRUCTION = """
You are EarthWhisper's explanation engine. Your job is to produce a clear,
evidence-grounded flood risk summary for emergency responders and community planners.

Rules you MUST follow:
- Use ONLY the data provided in the prompt. Never invent rainfall figures,
  population numbers, place names, or probabilities.
- Always state the model version and that the output is experimental.
- Always include the observation timestamp context and data freshness if provided.
- End with a numbered list of recommended preparedness actions appropriate to the risk level.
- Keep the summary concise — under 300 words.
"""


def summarize_with_gemini(
    area_name: str,
    risk_label: str,
    risk_score: float,
    features: dict,
    baseline: dict,
    impact: dict,
    model_version: str,
) -> dict:
    """
    Generate a grounded flood risk explanation using Gemini, from live tool outputs.
    Only uses evidence passed in — never invents data.

    Returns:
        dict with summary (str) and recommended_actions (list)
    """
    records = impact.get("detailed_records", [])
    settlements = [r for r in records if r.get("asset_type") == "SETTLEMENT" and r.get("population")]
    settlement_text = "\n".join(
        f"  - {r['name']}: population {r['population']:,}" for r in settlements
    ) or "  - No settlement data available"

    assets = (
        [("Hospital", n) for n in impact.get("critical_hospitals", [])]
        + [("Evacuation center", n) for n in impact.get("evacuation_centers", [])]
        + [("Bridge", n) for n in impact.get("vulnerable_bridges", [])]
    )
    asset_text = "\n".join(f"  - {n} ({t})" for t, n in assets) or "  - No critical asset data available"

    base = baseline if isinstance(baseline, dict) and "error" not in baseline else {}
    experimental_note = "(EXPERIMENTAL — not an official forecast)"

    prompt = f"""
Generate a flood risk summary for the following situation:

AREA: {area_name} {experimental_note}
RISK LEVEL: {risk_label.upper()} (score: {risk_score:.2f}, model: {model_version})

OBSERVED RAINFALL (live telemetry):
- 1-hour: {features.get('rain_1h_mm', 'N/A')} mm
- 6-hour: {features.get('rain_6h_mm', 'N/A')} mm
- 24-hour: {features.get('rain_24h_mm', 'N/A')} mm
- 72-hour: {features.get('rain_72h_mm', 'N/A')} mm
- 7-day: {features.get('rain_7d_mm', 'N/A')} mm
- 24h anomaly: {features.get('rain_24h_anomaly_pct', 'N/A')}% vs normal
- 72h z-score: {features.get('rain_72h_zscore', 'N/A')}
- Soil water (layer 1): {features.get('soil_water_layer1', 'N/A')}

SEASONAL BASELINE (day-of-year normals):
- Mean 24h rainfall: {base.get('mean_rain_24h_mm', 'N/A')} mm (± {base.get('std_rain_24h_mm', 'N/A')})
- Mean 72h rainfall: {base.get('mean_rain_72h_mm', 'N/A')} mm (± {base.get('std_rain_72h_mm', 'N/A')})

EXPOSED POPULATION: {impact.get('total_exposed_population', 0):,}

NEARBY COMMUNITIES:
{settlement_text}

CRITICAL INFRASTRUCTURE:
{asset_text}

Provide a concise summary and numbered recommended actions.
"""

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    use_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI")

    if api_key:
        client = genai.Client(api_key=api_key)
    elif use_vertex:
        client = genai.Client()  # Vertex AI via GOOGLE_GENAI_USE_VERTEXAI/PROJECT_ID/REGION
    else:
        return _mock_summary(area_name, risk_label, risk_score, features, impact, model_version)

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            max_output_tokens=1024,
            temperature=0.2,
            # gemini-2.5-flash "thinking" otherwise consumes the output budget and
            # truncates the briefing; we don't need reasoning tokens for a summary.
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )

    summary_text = response.text
    actions = _extract_actions(summary_text)

    return {
        "summary": summary_text,
        "recommended_actions": actions,
    }


def _extract_actions(summary_text: str) -> list:
    """Extract numbered action items from Gemini response."""
    actions = []
    for line in summary_text.splitlines():
        line = line.strip()
        if line and line[0].isdigit() and "." in line[:3]:
            actions.append(line.split(".", 1)[-1].strip())
    return actions if actions else ["Monitor situation closely and follow local authority guidance."]


def _mock_summary(area_name, risk_label, risk_score, features, impact, model_version) -> dict:
    """Fallback when no Gemini access is configured — used for local development."""
    settlements = [r for r in impact.get("detailed_records", []) if r.get("asset_type") == "SETTLEMENT"]
    summary = (
        f"[Mock Summary — set GEMINI_API_KEY or GOOGLE_GENAI_USE_VERTEXAI to enable Gemini]\n\n"
        f"Flood risk assessment for {area_name} (EXPERIMENTAL)\n"
        f"Risk: {risk_label.upper()} (score: {risk_score:.2f}, model: {model_version})\n\n"
        f"24h rainfall: {features.get('rain_24h_mm', 'N/A')} mm "
        f"({features.get('rain_24h_anomaly_pct', 'N/A')}% vs normal, "
        f"72h z-score {features.get('rain_72h_zscore', 'N/A')})\n"
        f"Exposed population: {impact.get('total_exposed_population', 0):,}\n"
        f"Nearby communities: {', '.join(r['name'] for r in settlements) or 'None'}"
    )
    return {"summary": summary, "recommended_actions": _recommend_actions(risk_label)}


def _recommend_actions(risk_label: str) -> list:
    label = (risk_label or "").lower()
    if label == "high":
        return [
            "Alert local disaster response authorities immediately",
            "Activate flood early warning systems in affected communities",
            "Prepare evacuation routes for low-lying settlements",
            "Inspect and secure critical infrastructure (bridges, power stations)",
            "Monitor river gauge levels continuously",
        ]
    elif label == "moderate":
        return [
            "Issue precautionary advisories to communities within the catchment",
            "Put emergency response teams on standby",
            "Monitor rainfall and river levels closely over next 6 hours",
            "Verify critical asset readiness (hospitals, shelters)",
        ]
    else:
        return [
            "Continue routine monitoring",
            "No immediate action required — situation is within normal range",
        ]
