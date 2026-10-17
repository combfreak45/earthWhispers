# AGENTS.md — EarthWhisper Agent Guidelines & Operating Principles

This document defines the strict, non-negotiable operating principles, architectural rules, and safety protocols governing all agents, subagents, and automated workers across the **EarthWhisper** platform. Every AI coding agent, reasoning assistant, and autonomous tool interacting with this codebase MUST strictly adhere to these instructions.

---

## 1. The Cardinal Rule: Complete Mock & Live Separation
> [!IMPORTANT]
> **FIRST PRINCIPLE: NEVER LET MOCK DATA INTERACT WITH OR CONTAMINATE PRODUCTION RUNS.**
> Live production execution paths and mock/test execution paths must remain strictly isolated at every layer: architectural, structural, database, messaging, and runtime.

### 1.1 Structural Isolation Rules
1. **Explicit Mode Parameterization**:
   - Every entrypoint (Cloud Scheduler payload, CLI script, Pub/Sub message, Cloud Run endpoint, and agent invocation) MUST explicitly specify an execution mode:
     - `--mode=live` (Production observation, live Earth Engine queries, live Vertex AI endpoints, live BigQuery tables).
     - `--mode=mock` (Unit tests, local dry-runs, synthetic fixtures, reproducible historical replays).
2. **Zero Hardcoded Fallbacks in Live Mode**:
   - Under `--mode=live`, **NEVER** use hardcoded strings, synthetic fallback dictionaries, or simulated responses to mask API failures.
   - If an external dependency fails in live mode (e.g., Earth Engine times out, Vertex AI endpoint is unavailable, BigQuery returns empty), the system MUST raise an explicit, typed error (e.g., `DataSourceUnavailableError`), log the degradation, and attach a data quality flag. It must NEVER silently fall back to mock data.
3. **Storage & Dataset Segregation**:
   - **BigQuery Live Dataset**: `earthwhisper_live` (Only genuine satellite observations, real Vertex AI model predictions, and live audit trails).
   - **BigQuery Mock Dataset**: `earthwhisper_mock` (Synthetic records, unit test fixtures, historical benchmark replays).
   - **Cloud Storage Live Bucket**: `gs://${PROJECT_ID}-data-live`
   - **Cloud Storage Mock Bucket**: `gs://${PROJECT_ID}-data-mock`

---

## 2. Agent Grounding & Hallucination Prevention
The Google ADK Agent (`earthwhisper_orchestrator`) is an **analytical orchestrator**, not an oracle or numerical calculator.

1. **Numerical Authority**:
   - The numerical flood risk score ($0.0 \dots 1.0$), risk class (`0: Low`, `1: Moderate`, `2: High`), and probability distribution come **EXCLUSIVELY** from the `predict_flood_risk` tool backed by the deployed Vertex AI XGBoost endpoint.
   - The LLM MUST NEVER recalculate, adjust, or invent risk percentages or flood probabilities.
2. **Deterministic Calculations**:
   - All rolling rainfall sums ($1\text{h}, 3\text{h}, 6\text{h}, 24\text{h}, 72\text{h}, 7\text{d}$), peak intensities, $Z$-scores, and percentage anomalies are computed using **deterministic Python/SQL math** in the ingestion worker.
   - The LLM receives precomputed values from tool outputs and MUST NEVER attempt to calculate mathematical deviations on the fly.
3. **Impact Grounding**:
   - Affected settlements, population figures, evacuation centers, and critical infrastructure cited in the briefing MUST originate from the `lookup_impact_graph` tool executed via the BigQuery MCP server.
   - The LLM MUST NEVER invent village names, casualties, damage estimates, or affected population numbers. If the tool returns no records, the agent must state: *"No critical infrastructure records found in the database for this specific radius."*

---

## 3. Tool Usage Standards & Protocol
Agents communicate with tools using strict typed interfaces:

### 3.1 Vertex AI Prediction Tool (`predict_flood_risk`)
- **Input**: Strictly validated Pydantic model (`CatchmentFeatures`) containing:
  - `rain_1h_mm`, `rain_3h_mm`, `rain_6h_mm`, `rain_24h_mm`, `rain_72h_mm`, `rain_7d_mm`
  - `rain_peak_1h_mm`, `rain_24h_anomaly_pct`, `rain_72h_zscore`
  - `soil_water_layer1`, `elevation_mean_m`, `slope_mean_deg`
  - `data_freshness_hrs`, `spatial_coverage_pct`
- **Output**: Typed `PredictionResult` (`risk_class`, `risk_score`, `model_version`, `top_contributing_features`).

### 3.2 BigQuery MCP Toolset (`https://bigquery.googleapis.com/mcp`)
- Transport: **Streamable HTTP**.
- Authentication: Google Cloud Application Default Credentials (ADC) / Cloud Run Service Account.
- Queries executed must be read-only parameter-bound SQL queries against `impact_graph_assets` or `catchment_climate_baseline`.

### 3.3 Multimodal Vision Tool (`analyze_ground_imagery`)
- Analyzes user-submitted ground photos or Sentinel-1 SAR imagery.
- Must focus solely on visible environmental markers: waterlogging height, standing water extent, breached river banks, road submersion.
- Must include a clear caveat: *"Ground photos represent localized, unverified point observations and do not establish catchment-wide flood extent on their own."*

---

## 4. Safety & Policy Gate
1. **Experimental Prototype Disclaimer**:
   - Every briefing and dashboard response MUST display:
     > *"NOTICE: EarthWhisper is an experimental research prototype for the Google Cloud AI Builder Cup. It is NOT an official emergency management alert system. Consult official local disaster management authorities (NDMA/ASDMA) for binding evacuation advisories."*
2. **Alert Policy Gate**:
   - High-risk alerts must pass deduplication checks (e.g., minimum 6-hour cooldown per catchment unless risk level increases) before publishing to the outbound alert bus.
   - In demonstration mode, alerts are explicitly flagged with `simulated: true`.

---

## 5. Lineage & Auditability
Every record produced by the agent and inserted into `alert_audits` MUST contain:
- `execution_mode`: `"live"` or `"mock"`
- `trace_id`: OpenTelemetry distributed trace identifier
- `source_observation_time`: UTC timestamp of the underlying satellite sensor data
- `ingestion_timestamp`: UTC timestamp when the data was ingested
- `evaluation_timestamp`: UTC timestamp of agent execution
- `feature_version`: Semantic version of the feature engineering pipeline (e.g., `"v1.0"`)
- `model_version`: Vertex AI Model Registry version ID
- `data_freshness_status`: `"FRESH_NOMINAL"`, `"STALE_ACCEPTABLE"`, or `"STALE_CRITICAL"`
- `tool_call_log`: JSON snapshot of all tool inputs, raw outputs, and execution latencies.
