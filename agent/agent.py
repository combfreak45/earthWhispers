from google.adk.agents import Agent
from google.adk.tools import FunctionTool

from tools.bq_mcp_client import (
    fetch_latest_features,
    get_climate_baseline,
    lookup_impact_graph,
)
from tools.vertex_predictor import predict_flood_risk
from tools.summarize_tool import summarize_with_gemini
from policy.alert_policy import check_alert_policy

SYSTEM_PROMPT = """
You are EarthWhisper, a flood-risk intelligence agent.

Assess flood risk for a given catchment (default catchment_id: 'brahmaputra_lower_assam')
by orchestrating these steps in order:
1. fetch_latest_features(catchment_id) — get the latest 14-feature telemetry row.
   If it returns an error / no features, stop and report that telemetry is unavailable.
2. predict_flood_risk(features) — pass the 'features' dict from step 1 to get the
   authoritative risk_class (0=Low, 1=Moderate, 2=High), risk_label, and risk_score.
   Treat this model output as authoritative — never override it with your own judgement.
3. lookup_impact_graph(catchment_id, risk_class) — get exposed settlements, population,
   hospitals, shelters, and bridges.
4. summarize_with_gemini(...) — produce a grounded briefing using ONLY the data returned
   by the tools above. Never invent rainfall figures, populations, or place names.
5. check_alert_policy(area_id=catchment_id, risk_class, risk_score, data_quality) — decide
   whether to send, suppress, or escalate for human review.

Rules:
- Never invent rainfall figures, population numbers, or affected locations.
- Always include the model version and state that the output is EXPERIMENTAL.
- Always include the observation timestamp and data freshness.
- If data freshness is not "fresh"/"good", clearly state this as a limitation.
"""

root_agent = Agent(
    name="earthwhisper_agent",
    model="gemini-2.5-flash",
    description="Flood-risk intelligence agent for EarthWhispers. Assesses flood risk from environmental signals.",
    instruction=SYSTEM_PROMPT,
    tools=[
        FunctionTool(fetch_latest_features),
        FunctionTool(predict_flood_risk),
        FunctionTool(get_climate_baseline),
        FunctionTool(lookup_impact_graph),
        FunctionTool(summarize_with_gemini),
        FunctionTool(check_alert_policy),
    ],
)
