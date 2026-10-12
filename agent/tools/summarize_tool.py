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
- Always include data quality and observation timestamp.
- If data quality is not "good", clearly highlight this as a limitation.
- End with a numbered list of recommended preparedness actions appropriate to the risk level.
- Keep the summary concise — under 300 words.
"""


def summarize_with_gemini(
    area_name: str,
    risk_score: float,
    risk_class: str,
    observations: dict,
    impact: dict,
    model_version: str,
    is_experimental: bool,
) -> dict:
    """
    Generate a grounded flood risk explanation using Gemini.
    Only uses evidence passed in — never invents data.

    Returns:
        dict with summary (str) and recommended_actions (list)
    """
    settlements = impact.get("nearby_settlements", [])
    assets = impact.get("critical_assets", [])

    settlement_text = "\n".join(
        f"  - {s['name']}: population {s['population']:,}, {s['distance_km']} km away"
        for s in settlements
    ) or "  - No settlement data available"

    asset_text = "\n".join(
        f"  - {a['name']} ({a['type']}): {a['distance_km']} km away"
        for a in assets
    ) or "  - No critical asset data available"

    experimental_note = "(EXPERIMENTAL — not an official forecast)" if is_experimental else ""

    prompt = f"""
Generate a flood risk summary for the following situation:

AREA: {area_name} {experimental_note}
RISK LEVEL: {risk_class.upper()} (score: {risk_score:.2f}, model: {model_version})

OBSERVED SIGNALS:
- 1-hour rainfall: {observations.get('rainfall_1h', 'N/A')} mm
- 3-hour rainfall: {observations.get('rainfall_3h', 'N/A')} mm
- 6-hour rainfall: {observations.get('rainfall_6h', 'N/A')} mm
- 24-hour rainfall: {observations.get('rainfall_24h', 'N/A')} mm
- 72-hour rainfall: {observations.get('rainfall_72h', 'N/A')} mm
- Seasonal baseline (24h): {observations.get('baseline_24h', 'N/A')} mm
- Anomaly score: {observations.get('anomaly_score', 'N/A')}x above baseline
- Signal rule triggered: {observations.get('triggered_rule', 'N/A')}
- Data quality: {observations.get('data_quality', 'unknown')}
- Observation time: {observations.get('event_time', 'unknown')}

NEARBY COMMUNITIES:
{settlement_text}

CRITICAL INFRASTRUCTURE:
{asset_text}

Provide a concise summary and numbered recommended actions.
"""

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

    if not api_key:
        return _mock_summary(area_name, risk_score, risk_class, observations, impact, model_version, is_experimental)

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            max_output_tokens=512,
            temperature=0.2,
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


def _mock_summary(area_name, risk_score, risk_class, observations, impact, model_version, is_experimental) -> dict:
    """Fallback when no API key is set — used for local development."""
    settlements = impact.get("nearby_settlements", [])
    assets = impact.get("critical_assets", [])
    caveat = "(EXPERIMENTAL)" if is_experimental else ""

    summary = (
        f"[Mock Summary — set GEMINI_API_KEY to enable real Gemini responses]\n\n"
        f"Flood risk assessment for {area_name} {caveat}\n"
        f"Risk: {risk_class.upper()} (score: {risk_score:.2f}, model: {model_version})\n\n"
        f"24h rainfall: {observations.get('rainfall_24h', 'N/A')} mm "
        f"({observations.get('anomaly_score', 'N/A')}x above baseline of {observations.get('baseline_24h', 'N/A')} mm)\n"
        f"Data quality: {observations.get('data_quality', 'unknown')} | "
        f"Observed at: {observations.get('event_time', 'unknown')}\n\n"
        f"Nearby communities: {', '.join(s['name'] for s in settlements) or 'None'}\n"
        f"Critical assets: {', '.join(a['name'] for a in assets) or 'None'}"
    )

    actions = _recommend_actions(risk_class)
    return {"summary": summary, "recommended_actions": actions}


def _recommend_actions(risk_class: str) -> list:
    if risk_class == "high":
        return [
            "Alert local disaster response authorities immediately",
            "Activate flood early warning systems in affected communities",
            "Prepare evacuation routes for low-lying settlements",
            "Inspect and secure critical infrastructure (bridges, power stations)",
            "Monitor river gauge levels continuously",
        ]
    elif risk_class == "medium":
        return [
            "Issue precautionary advisories to communities within 30 km",
            "Put emergency response teams on standby",
            "Monitor rainfall and river levels closely over next 6 hours",
            "Verify critical asset readiness (hospitals, shelters)",
        ]
    else:
        return [
            "Continue routine monitoring",
            "No immediate action required — situation is within normal range",
        ]
