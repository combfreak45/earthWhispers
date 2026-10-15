# EarthWhisper — Google Cloud Integration Reference

Single source of truth for the live GCP wiring (Vertex AI endpoint + BigQuery).
All values below were **confirmed via `gcloud`/`bq` on 2026-10-15**.

> Scope: this documents the migration of the ADK agent from mock JSON
> (`agent/mock_data/*.json`) to live Google Cloud sources described in the
> project spec. Related code: `agent/tools/vertex_predictor.py`,
> `agent/tools/bq_mcp_client.py`.

---

## 1. Project configuration

| Key | Value |
|---|---|
| Project ID | `earth-whisper-ai-builders-cup` |
| Project number | `303899581896` |
| Region | `us-central1` |
| BigQuery live dataset | `earthwhisper_live` |

Environment variables (set these in `.env`; the code's `earthwhisper-dev` default is **wrong**):

```bash
PROJECT_ID=earth-whisper-ai-builders-cup
REGION=us-central1
VERTEX_ENDPOINT_ID=earthwhisper-flood-risk-endpoint
BIGQUERY_DATASET_LIVE=earthwhisper_live
BIGQUERY_DATASET_MOCK=earthwhisper_mock
```

> ⚠️ `gcloud ai ...` and `gcloud projects ...` require the project **ID**, not the number.
> ⚠️ `vertex_predictor.py` reads `REGION`, but `.env.example` had `VERTEX_ENDPOINT_REGION` — align them.

Auth for local runs:
```bash
gcloud auth login
gcloud auth application-default login   # so the Python aiplatform/bigquery libs authenticate
gcloud config set project earth-whisper-ai-builders-cup
```

---

## 2. Vertex AI endpoint

| Attribute | Value |
|---|---|
| Endpoint ID | `earthwhisper-flood-risk-endpoint` (**custom string ID**, not numeric) |
| Display name | EarthWhisper XGBoost Flood Risk Endpoint |
| Model | XGBoost, 3-class flood risk (deployed model `earthwhisper-xgboost-v1`, modelVersion 1) |
| Resource name | `projects/303899581896/locations/us-central1/endpoints/earthwhisper-flood-risk-endpoint` |
| Predict URL | `https://us-central1-aiplatform.googleapis.com/v1/projects/303899581896/locations/us-central1/endpoints/earthwhisper-flood-risk-endpoint:predict` |
| Status | ✅ Live & healthy (confirmed 2026-10-15). `n1-standard-2`, 1–2 replicas. Managed by Terraform, `env: demo`. |

**Deployed models / traffic:** two deployed models exist; **100% of traffic routes to deployed-model `6183726512135471104`** (`trafficSplit`). `endpoint.predict()` honors the split automatically — the code does **not** need to pass a deployed-model ID.

**Input:** ordered 14-feature vector `{"instances": [[v1 … v14]]}` in the exact `FEATURE_KEYS` order below.
**Output:** ✅ **Confirmed** (live `:predict`, 2026-10-15) — `{"predictions": [[p0, p1, p2]]}`, three class probabilities. Matches `vertex_predictor.py` parsing (`response.predictions[0]` → `[p0,p1,p2]`). Sample high-risk input returned `[0.031, 0.044, 0.925]` → class 2. No code change needed.

**Class labels:** `0 = Low`, `1 = Moderate`, `2 = High`.
> Note: `vertex_predictor.py` currently labels class 2 as **"Severe"** — spec says **"High"**. Pick one and keep it consistent across the agent and `alert_audits.risk_class`.

---

## 3. The 14 model features (authoritative order)

Confirmed to match `training_dataset` column order **and** `vertex_predictor.py` `FEATURE_KEYS`:

```
1.  rain_1h_mm            8.  rain_24h_anomaly_pct
2.  rain_3h_mm            9.  rain_72h_zscore
3.  rain_6h_mm            10. soil_water_layer1
4.  rain_24h_mm           11. elevation_mean_m
5.  rain_72h_mm           12. slope_mean_deg
6.  rain_7d_mm            13. data_freshness_hrs
7.  rain_peak_1h_mm       14. spatial_coverage_pct
```

Training label: `flood_risk_level` (INTEGER, 0/1/2).

---

## 4. BigQuery table schemas (`earthwhisper_live`)

### `impact_graph_assets` — exposed settlements / infrastructure
Used by `lookup_impact_graph` in `bq_mcp_client.py`. All columns below confirmed present.

| Column | Type | Mode |
|---|---|---|
| asset_id | STRING | REQUIRED |
| catchment_id | STRING | REQUIRED |
| district | STRING | REQUIRED |
| name | STRING | REQUIRED |
| asset_type | STRING | REQUIRED |
| population | INTEGER | NULLABLE |
| latitude | FLOAT | REQUIRED |
| longitude | FLOAT | REQUIRED |
| vulnerability_index | FLOAT | REQUIRED |

### `catchment_features` — latest operational telemetry
Source of the 14 features. Query: latest row per catchment by `observation_timestamp`.
Partitioned by DAY on `observation_timestamp`.

Columns: `catchment_id`, `observation_timestamp` (TS), `ingestion_timestamp` (TS),
the **14 features** (all NULLABLE except `data_freshness_hrs`, `spatial_coverage_pct`),
`freshness_status` (STRING), `feature_version` (STRING).

### `catchment_climate_baseline` — 366 day-of-year normals
Join on `doy` for the "vs. seasonal normal" narrative.

| Column | Type |
|---|---|
| catchment_id | STRING |
| doy | INTEGER |
| mean_rain_24h_mm | FLOAT |
| std_rain_24h_mm | FLOAT |
| mean_rain_72h_mm | FLOAT |
| std_rain_72h_mm | FLOAT |
| baseline_window_years | STRING |

### `alert_audits` — compliance log (append every briefing)
Partitioned by DAY on `evaluation_timestamp`. **All fields REQUIRED** — the audit insert must populate every one.

| Column | Type |
|---|---|
| audit_id | STRING |
| execution_mode | STRING |
| trace_id | STRING |
| catchment_id | STRING |
| observation_timestamp | TIMESTAMP |
| evaluation_timestamp | TIMESTAMP |
| risk_score | FLOAT |
| risk_class | INTEGER |
| model_version | STRING |
| data_freshness_status | STRING |
| policy_action | STRING |
| gemini_briefing | STRING |
| tool_call_log | STRING |
| affected_assets_count | INTEGER |

### `training_dataset` — (reference only, not queried at runtime)
Confirms feature order. 14 features + `flood_risk_level` label + `event_id`, `split`.

---

## 5. Decisions locked in

- **BigQuery access method: plain `google-cloud-bigquery` client.** The missing
  `data_pipeline/mcp_bq_client.py` will wrap the standard Python client behind an
  `execute_query()` method, keeping the caller interface identical so a real MCP
  layer can be swapped in later with no change to `bq_mcp_client.py`.
- **Strict grounding:** in `--mode=live`, no synthetic fallbacks. Empty results are
  returned as-is so the agent states "no records found" rather than inventing data.

---

## 6. Outstanding work (migration status)

| Piece | File | Status |
|---|---|---|
| Vertex AI prediction | `agent/tools/vertex_predictor.py` | ✅ live-verified (class 2, correct probs) |
| Impact graph lookup | `agent/tools/bq_mcp_client.py` | ✅ live-verified (464k exposed, real assets) |
| `telemetry.py` (`get_tracer`) | `agent/telemetry.py` | ✅ built |
| `mcp_bq_client.py` (`BigQueryMCPClient`) | `data_pipeline/mcp_bq_client.py` | ✅ built (auto-detects dataset location) |
| Latest-telemetry query | `catchment_features` | ✅ `fetch_latest_features` (live-verified) |
| Baseline lookup | `catchment_climate_baseline` | ✅ `get_climate_baseline` (live-verified) |
| Audit append | `alert_audits` | ✅ `write_alert_audit` via `run_assessment` (rows confirmed) |
| Orchestration + agent wiring | `agent/pipeline.py`, `agent/agent.py`, `agent/main.py`, `replay.py` | ✅ live end-to-end (HIGH→human_review, audited) |
| Env var alignment | `.env.example` | ✅ updated for live config |
| Dead mock code | `fetch_observations/predict_tool/impact_tool`, `mock_data/*` | ✅ removed |

> Note: `catchment_features` was empty; one high-risk row was seeded from
> `training_dataset` (`feature_version="seed-from-training-v1"`) for the live demo.
> A real pipeline should populate this table operationally.
