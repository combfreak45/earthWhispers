# EarthWhisper — Product Requirements Document
“Give the Earth a Voice” | AI Builder Cup · Sustainability & Social Impact
## 1. Product summary
EarthWhisper is a flood-risk intelligence MVP that turns environmental signals into an evidence-backed, location-aware risk assessment and practical next steps. The prototype focuses on one selected river catchment or flood-prone area rather than attempting to cover every disaster type.
Objective: Provide flood susceptibility / near-term risk assessment unless reliable timestamped flood-onset labels are available to validate a specific forecast horizon. The goal is not to claim precise flood timing or deploy the prototype as an official emergency-warning system.
## 2. Goals and non-goals
### Goals
•	Ingest rainfall and supporting environmental data for one chosen study area.
•	Calculate recent rainfall windows and deviations from a historical baseline.
•	Use an XGBoost model to return a numerical risk score/class plus model version and input timestamp.
•	Use an ADK agent to orchestrate prediction, impact lookup, evidence-grounded explanation, and policy checks.
•	Show a map/dashboard with risk, evidence, data freshness, uncertainty, and affected assets/communities where data exists.
•	Replay a historical case or simulated signal end-to-end for the demo.
Non-goals
•	All-disaster prediction, nationwide operational coverage, or guaranteed 24-hour flood forecasts.
•	Autonomous public emergency alerts without explicit policy checks and human review for the demo.
•	A separate Vision AI service unless it adds value beyond Gemini multimodal image analysis.
•	Offline-first mobile support in the ten-day core scope.
## 3. Users and key journey
### Primary users: hackathon evaluators, local-response planners, and community-facing demonstrators.
1.	A scheduled worker processes the latest available data for the selected catchment.
2.	A signal rule detects a meaningful deviation or new evidence and publishes an event.
3.	The ADK agent calls the prediction service and retrieves exposed assets/community context.
4.	Gemini explains the result using returned evidence only; the policy layer decides whether to show or escalate it.
5.	The dashboard presents the result with timestamps, caveats, and suggested preparedness actions.
## 4. Data and signal definitions
Data source	Purpose	MVP status	Important limitation
NASA GPM IMERG V07 via Earth Engine	Half-hourly satellite-derived precipitation; aggregate to 1/3/6/24/72-hour rainfall features where data availability allows.	Core	Approx. 0.1° / 11 km grid; near-real-time products have latency and may be revised.
ERA5-Land hourly	Historical land/climate context such as soil moisture; supports baselines/features.	Optional if time permits	Reanalysis, not a live forecast.
Sentinel-1 SAR via Earth Engine	Independent flood-inundation evidence or historical validation.	Optional	Acquisition timing is intermittent; not a continuous live sensor.
Flood-event / gauge labels	Train and evaluate XGBoost; define what counts as a flood event.	Required for credible supervised prediction	Need event timestamps or a defensible target; flood polygons alone do not establish hourly onset.
Community photo/report	Supplementary ground observation with location and timestamp.	Stretch goal	A photo can be stale, misleading, or unverified; never treat it as proof on its own.
Signal rule: calculate recent rainfall accumulations/anomalies against a documented baseline for the same location and season/time window. Store source observation time, ingestion time, quality/status, baseline definition, and feature version. Thresholds should be configurable and described as MVP rules, not universal hydrological truths.
### Feed Links:
https://developers.google.com/earth-engine/datasets/catalog/NASA_GPM_L3_IMERG_V07#colab-python
https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S1_GRD#colab-python
https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_HOURLY
Historic Training Set: https://developers.google.com/earth-engine/datasets/catalog/GLOBAL_FLOOD_DB_MODIS_EVENTS_V1
## 5. Functional requirements
ID	Requirement	Acceptance intent
FR-01	Study area configuration	Define one catchment/area of interest and its geometry; persist its ID and source.
FR-02	Scheduled ingestion	Cloud Scheduler invokes a Cloud Run worker daily for the MVP; schedule is configurable.
FR-03	Data freshness and quality	Worker checks coverage, timestamps, missing values, and source status; stale/invalid inputs must not silently create a high-risk alert.
FR-04	Feature engineering	Generate rainfall accumulations, baseline deviation/anomaly, and available static catchment features.
FR-05	Persistence	Store tabular features, event metadata, predictions, model version, and impact lookup data in BigQuery; store raw/exported assets in Cloud Storage as needed. We can use MCP server for BigQuery as native GCP option (https://docs.cloud.google.com/bigquery/docs/use-bigquery-mcp)
FR-06	Signal event	Publish a compact Pub/Sub event with area ID, event type, time range, data freshness, and references to BigQuery/GCS records; do not send raster payloads through Pub/Sub.
FR-07	Prediction	ADK agent calls a typed prediction tool/API backed by a deployed XGBoost model; output risk score/class, model version, and explanation-friendly feature evidence.
FR-08	ImpactGraph lookup	Query BigQuery for nearby/exposed settlements and critical assets when suitable geospatial data is available. We can use MCP server for BigQuery as native GCP option (https://docs.cloud.google.com/bigquery/docs/use-bigquery-mcp)
FR-09	Evidence-grounded explanation	Gemini explains why the score changed and provides cautious preparedness guidance based on tool results; it must not invent probabilities, observations, or affected people.
FR-10	Alert policy	Apply configurable thresholds, deduplication/cooldown, and demo human-review gate before any simulated notification.
FR-11	Dashboard	Show area/map, current risk, trend, evidence, data timestamps, uncertainty/caveats, and action suggestions.
FR-12	Auditability	Record signal, feature version, model version, agent/tool outcomes, policy decision, and notification status.
## 6. Architecture and service responsibilities
 
•	Earth Engine: Access and process raster collections (IMERG, optionally ERA5-Land/Sentinel-1); derive spatial/time-window features.
•	Cloud Scheduler: Starts the ingestion job on a schedule; it does not calculate signals itself.
•	Cloud Run ingestion/feature worker: Fetches/processes data, validates freshness, computes baseline deviations/features, writes results, and emits Pub/Sub events when rules match.
•	Pub/Sub: Carries small event metadata asynchronously; supports retries and decouples ingestion from agent workflow.
•	ADK agent on Agent Platform runtime: Triggered by the event subscriber; coordinates tools and decisions. It is not the continuous polling daemon or the numerical model.
•	XGBoost model service: Computes the numeric prediction. Register/version the artifact in Vertex AI Model Registry, then deploy to a Vertex AI endpoint; alternatively serve the model in Cloud Run.
•	BigQuery: Stores time-series features, signal/prediction/alert records, and performs geospatial impact queries.
•	Cloud Storage: Stores raw files, exported rasters, imagery, training snapshots, and model-related artifacts where appropriate.
•	Gemini: Produces an evidence-grounded explanation and can inspect user-submitted photos if that feature is included.
•	Policy/dashboard: Applies alert rules, deduplication, and demo review; presents results. Notifications are simulated for the hackathon. Optional Gemini chat integration in the dashboard for new bees/ end users to chat with agent and get fresh results, explanations, location specific dynamics.
## 7. Event flow (recommended)
6.	Cloud Scheduler → Cloud Run ingestion worker.
7.	Worker reads/processes available IMERG data through Earth Engine; computes features and baseline deviations; validates data freshness.
8.	Worker writes feature rows to BigQuery and publishes a compact signal event to Pub/Sub when the signal rule is met.
9.	A Pub/Sub-triggered Cloud Run subscriber invokes the ADK agent on the agent runtime (or forwards the event to the configured agent entry point).
10.	ADK agent calls the XGBoost prediction API as a tool; the deployed endpoint/API returns the numeric risk result.
11.	Agent queries BigQuery for impact context and asks Gemini for a grounded explanation/action summary.
12.	Policy step checks thresholds, deduplicates repeated alerts, and routes to the demo dashboard or a human-review queue.
Important: Pub/Sub does not automatically invoke an arbitrary ADK agent by itself. Configure a subscriber/event handler that invokes the agent runtime using the supported integration. For the simplest MVP, a Cloud Run event handler can do this.
## 8. Model and evaluation requirements
•	Use XGBoost only if usable historical examples and target labels can be assembled within the timebox.
•	Candidate features: 1/3/6/24/72-hour rainfall totals, anomaly versus baseline, antecedent rainfall, available soil-moisture/terrain/catchment attributes, and river-flow features only where reliable gauge data exists.
•	Define the target before training. A ‘flood within next 24 hours’ target requires timestamped flood onset or gauge/threshold labels; otherwise label the output susceptibility/near-term risk rather than a validated 24-hour forecast.
•	Split chronologically and, where possible, by catchment/event to reduce leakage. Compare against a simple baseline.
•	Report precision, recall, false negatives, false alarms, calibration if feasible, and data coverage. Include model version and limitations in the UI.
•	If labels are inadequate, deliver a transparent rule-based signal plus a clearly labelled experimental XGBoost model; do not present unvalidated scores as reliable forecasts.
•	Use Vertex AI Gen AI Evaluation service for evaluating the agent.
## 9. Non-functional, safety, and reliability requirements
•	Data lineage: every result shows source timestamp, ingestion timestamp, baseline window, feature version, and model version.
•	Reliability: retries for transient failures, idempotent processing, deduplication keys, and dead-letter handling for failed events where configured.
•	Security: least-privilege service accounts, secrets in Secret Manager, and no public unauthenticated prediction endpoint.
•	Privacy: community reports should collect only necessary location/time/photo metadata; avoid exposing identifiable submitter details on the public dashboard.
•	Safety: label the prototype as experimental; no claim of official emergency warning. Use human review before simulated escalation.
•	Observability: structured logs and basic metrics for ingestion success, data freshness, model errors, event retries, and alert counts.
## 10. Definition of done
•	One configured area can be processed end-to-end from scheduled ingestion to dashboard output.
•	At least one documented signal rule is computed from real environmental data and its baseline is visible.
•	The prediction API responds to a typed request and returns a versioned result; if training labels are weak, the UI clearly says experimental/susceptibility.
•	A Pub/Sub event invokes the agent workflow through an explicit subscriber/event handler.
•	Agent output references actual model and BigQuery tool results; Gemini does not invent data.
•	Repeated events are deduplicated; stale or missing data is shown as a limitation rather than silently treated as safe/high risk.
•	The demo is reproducible and includes an end-to-end replay plus known limitations.
## 11. Key decisions to lock early
•	Which catchment/area will be demonstrated?
•	What timestamped flood-onset or river-gauge labels are available for that exact area?
•	Can the MVP validate a forecast horizon, or should it be framed as susceptibility/near-term risk?
•	Which critical-asset/community dataset is available and legally usable?
•	Will inference run on Vertex AI endpoint or Cloud Run? Choose based on time, cost, and deployment familiarity.
•	Will alerts remain dashboard-only/simulated? Recommended for the hackathon.
## 12. Official reference links
•	NASA GPM IMERG V07 in Earth Engine: https://developers.google.com/earth-engine/datasets/catalog/NASA_GPM_L3_IMERG_V07
•	ERA5-Land hourly in Earth Engine: https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_HOURLY
•	Sentinel-1 GRD in Earth Engine: https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S1_GRD
•	Vertex AI model prediction/deployment codelab: https://codelabs.developers.google.com/vertex-p2p-predictions
•	Earth Engine and BigQuery integration: https://developers.google.com/earth-engine/guides/bigquery_integrations
•	Global Flood Database: https://developers.google.com/earth-engine/datasets/catalog/GLOBAL_FLOOD_DB_MODIS_EVENTS_V1
