# EarthWhisper — “Give the Earth a Voice”
### Google Cloud AI Builder Cup · Sustainability & Social Impact Track

[![Google Cloud](https://img.shields.io/badge/Google%20Cloud-Platform-4285F4?logo=google-cloud&logoColor=white)](https://cloud.google.com/)
[![Vertex AI](https://img.shields.io/badge/Vertex%20AI-Gemini%203.8%20Flash-blue?logo=google)](https://cloud.google.com/vertex-ai)
[![Earth Engine](https://img.shields.io/badge/Google-Earth%20Engine-34A853?logo=google-earth)](https://earthengine.google.com/)
[![Terraform](https://img.shields.io/badge/IaC-Terraform-7B42BC?logo=terraform&logoColor=white)](https://www.terraform.io/)
[![BigQuery MCP](https://img.shields.io/badge/MCP-BigQuery%20Streamable%20HTTP-009688)](https://cloud.google.com/bigquery)

**EarthWhisper** is an end-to-end flood-risk intelligence MVP that transforms satellite Earth observation streams into an evidence-grounded, location-aware risk assessment with actionable preparedness recommendations.

Built specifically for the **Lower Brahmaputra River Basin (Assam, India)**, EarthWhisper combines planetary-scale remote sensing, numerical machine learning, managed Model Context Protocol (MCP) data grounding, and Google ADK agent orchestration.

---

## 🏛️ System Architecture

```
               [ Planetary Data Sources ]
     NASA GPM IMERG V07 | ECMWF ERA5-Land | Sentinel-1 GRD
                          │
                          ▼
            [ Cloud Run Ingestion Worker ]
            (Triggered Daily via Cloud Scheduler)
       - Earth Engine extraction & spatial aggregation
       - Deterministic DOY baseline & Z-score anomaly math
       - Data freshness and completeness validation
                          │
          ┌───────────────┴───────────────┐
          ▼                               ▼
   [ BigQuery Live ]            [ Pub/Sub Topic ]
   (Features & Baselines)    (earthwhisper-signals)
                                          │
                                          │ Authenticated HTTP Push
                                          │ (OIDC + Dead-Letter Queue)
                                          ▼
                             [ Cloud Run ADK Agent ]
                             (Google Agent Dev Kit)
                                          │
        ┌─────────────────────────────────┼────────────────────────────────┐
        ▼                                 ▼                                ▼
[ Vertex AI Endpoint ]         [ BigQuery MCP Server ]           [ Gemini 3.8 Flash ]
 (XGBoost 3-Class Risk)       (Streamable HTTP: googleapis)     (Grounded Explanation
                               - ImpactGraph Settlements         & Multimodal Vision)
                               - Critical Infrastructure
                                          │
                                          ▼
                               [ Policy & Alert Engine ]
                               - Threshold & cooldown gating
                               - Audit logging to BigQuery
                                          │
                  ┌───────────────────────┴───────────────────────┐
                  ▼                                               ▼
      [ Streamlit Dashboard ]                       [ Pub/Sub Alert Bus ]
      - 2D/3D Catchment Map                         (earthwhisper-alerts)
      - Anomaly & Risk Gauges                                     │
      - Real-Time Agent Chat                                      ▼
      - Community Photo Upload                     [ Regional Responders ]
                                                   (Assam Disaster Authority)
```

---

## 🚀 Key Technical Highlights

1. **Deterministic Baseline Anomaly Math**:
   - Zero LLM hallucination for mathematical calculations.
   - The Ingestion Worker computes rolling rainfall ($1\text{h}, 3\text{h}, 6\text{h}, 24\text{h}, 72\text{h}, 7\text{d}$) and compares them against a 10-year Day-of-Year (DOY) historical baseline in BigQuery using strict mathematical formulas:
     $$\text{Anomaly\%} = \frac{P_{24h} - \mu_{doy}}{\mu_{doy} + 1.0} \times 100 \qquad Z_{\text{score}} = \frac{P_{72h} - \mu_{doy}}{\sigma_{doy} + 0.1}$$
2. **Quality & Freshness Validation Gate**:
   - Prevents stale satellite data from silently triggering emergency alerts. Sensor latency ($>48\text{h}$) automatically downgrades risk certainty and attaches visible caveats.
3. **Calibrated Numerical ML (Vertex AI)**:
   - 3-class Flood Susceptibility & Risk model (`0: Low`, `1: Moderate`, `2: High`) trained with XGBoost on Global Flood DB MODIS historical flood events (2000–2018).
   - Artifacts versioned in **Vertex AI Model Registry** and served via private **Vertex AI Endpoints**.
4. **Google ADK Agent with Remote BigQuery MCP**:
   - The ADK agent connects to Google's managed BigQuery MCP Server (`https://bigquery.googleapis.com/mcp`) via **Streamable HTTP** using `McpToolset`.
   - Queries an `ImpactGraph` mapping affected villages, population densities, schools, and hospitals in Assam so every cited entity is verified in SQL.
5. **Multimodal Ground & SAR Verification**:
   - Evaluators or local volunteers can submit ground photos in the dashboard; Gemini 3.8 Flash analyzes waterlogging markers and combines them with Sentinel-1 SAR radar evidence.
6. **Strict Observability & Distributed Tracing**:
   - 100% instrumented with OpenTelemetry, exporting spans across Cloud Run, Vertex AI, BigQuery, and Gemini to **Google Cloud Trace**.
7. **Vertex AI Gen AI Evaluation Suite**:
   - Automated evaluation suite evaluating Groundedness ($\ge 0.95$), Safety ($1.0$), and Instruction Adherence.
8. **Strict Mock vs. Live Data Isolation**:
   - Governed by [`AGENTS.md`](./AGENTS.md): Mock data NEVER touches production pipelines. Dedicated BigQuery datasets (`earthwhisper_live` vs `earthwhisper_mock`) and CLI parameterization (`--mode=live` vs `--mode=mock`).

---

## 📁 Repository Structure

```
.
├── AGENTS.md                  # Strict agent operating guidelines & isolation rules
├── README.md                  # System overview, architecture & user guide
├── IMPLEMENTATION_PLAN.md     # Full technical specification & architecture design
├── terraform/                 # 100% Terraform Infrastructure as Code
│   ├── main.tf                # Provider setup & core definitions
│   ├── variables.tf           # GCP project, region, and catchment configs
│   ├── outputs.tf             # Service URLs, endpoint IDs, and topic names
│   ├── apis.tf                # Enables 10+ Google Cloud APIs
│   ├── iam.tf                 # Least-privilege Service Accounts & IAM bindings
│   ├── pubsub.tf              # Signal & Alert topics, DLQs, push subscriptions
│   ├── bigquery.tf            # Live and Mock datasets, schemas, and baselines
│   ├── storage.tf             # GCS buckets for models and imagery
│   ├── cloud_run.tf           # Ingestion worker, ADK agent, and dashboard services
│   ├── scheduler.tf           # Daily Cloud Scheduler job
│   └── vertex_ai.tf           # Model registry and endpoint resources
├── data_pipeline/             # Ingestion & Earth Engine Processing
│   ├── Dockerfile
│   ├── ingest_worker.py       # Cloud Run FastAPI entrypoint
│   ├── ee_extractor.py        # Earth Engine GPM IMERG, ERA5, S1 extractor
│   ├── baseline_calculator.py # Deterministic DOY baseline & anomaly math
│   ├── freshness_validator.py # Latency, coverage, and sensor health checks
│   └── replay_generator.py    # 2017 & 2022/2024 Assam flood replay data
├── ml_engine/                 # Machine Learning (XGBoost & Vertex AI)
│   ├── train_xgboost.py       # Global Flood DB extraction & model training
│   ├── evaluate_model.py      # Precision, recall, ROC-AUC, calibration metrics
│   ├── deploy_vertex.py       # Model Registry registration & Endpoint deployment
│   └── predict_schema.py      # Typed Pydantic schemas for features & outputs
├── agent/                     # Google ADK Agent Service
│   ├── Dockerfile
│   ├── agent_service.py       # Cloud Run Push subscriber entrypoint
│   ├── orchestrator.py        # LlmAgent definition (Gemini 3.8 Flash)
│   ├── tools/
│   │   ├── vertex_predictor.py# Native Vertex AI XGBoost tool
│   │   ├── bq_mcp_client.py   # Streamable HTTP BigQuery MCP client
│   │   └── vision_analyzer.py # Gemini 3.8 Flash multimodal photo inspection
│   ├── policy_engine.py       # Cooldown gating, deduplication, audit records
│   └── telemetry.py           # OpenTelemetry tracer & Cloud Trace export
├── evals/                     # Gen AI Evaluation Harness
│   ├── run_agent_evals.py     # Vertex AI Gen AI Evaluation runner
│   ├── test_cases.json        # Golden evaluation scenarios
│   └── eval_metrics.py        # Groundedness, safety, and adherence evaluators
├── dashboard/                 # Streamlit UI & Command Center
│   ├── Dockerfile
│   ├── app.py                 # Main Streamlit application
│   ├── components/
│   │   ├── map_view.py        # Folium 2D & PyDeck 3D geospatial maps
│   │   ├── metrics_view.py    # Real-time risk gauges & anomaly curves
│   │   ├── chat_view.py       # Interactive conversational chat with ADK agent
│   │   └── vision_view.py     # Ground photo upload & AI analysis
│   └── requirements.txt
└── scripts/
    ├── deploy_all.sh          # End-to-end automated deployment script
    └── seed_bigquery.py       # Seeds DOY baseline & Assam ImpactGraph assets
```

---

## 🛠️ Deployment Guide (New GCP Project)

### Prerequisites
1. [Google Cloud SDK (`gcloud`)](https://cloud.google.com/sdk/docs/install) authenticated with project owner/editor privileges:
   ```bash
   gcloud auth login
   gcloud auth application-default login
   gcloud config set project YOUR_PROJECT_ID
   ```
2. [Terraform (>= 1.5.0)](https://developer.hashicorp.com/terraform/downloads) installed locally.
3. [Python (>= 3.10)](https://www.python.org/) and [Docker](https://www.docker.com/).

### Step 1: Initialize Infrastructure with Terraform
```bash
cd terraform
terraform init
terraform plan -var="project_id=YOUR_PROJECT_ID" -var="region=us-central1"
terraform apply -var="project_id=YOUR_PROJECT_ID" -var="region=us-central1" -auto-approve
```
*Terraform will automatically enable all required APIs, create least-privilege Service Accounts, set up BigQuery datasets, deploy Cloud Storage buckets, configure Pub/Sub topics with push subscriptions and DLQs, deploy Cloud Run services, and schedule daily ingestion.*

### Step 2: Seed BigQuery Climatology & ImpactGraph
```bash
python scripts/seed_bigquery.py --project_id=YOUR_PROJECT_ID --mode=live
```

### Step 3: Train & Deploy the ML Model to Vertex AI
```bash
cd ml_engine
python train_xgboost.py --project_id=YOUR_PROJECT_ID
python deploy_vertex.py --project_id=YOUR_PROJECT_ID --region=us-central1
```

### Step 4: Run the Automated Agent Evaluation Suite
```bash
cd evals
python run_agent_evals.py --project_id=YOUR_PROJECT_ID
```

### Step 5: Launch & Explore the Streamlit Dashboard
Open the deployed Cloud Run service URL output by Terraform:
```bash
terraform output dashboard_url
```
Or run locally for development:
```bash
cd dashboard
streamlit run app.py
```

---

## 🔒 Security & Least Privilege

- **Zero Public Ingestion/Agent Endpoints**: Cloud Run services are deployed as private. Pub/Sub invokes the ADK Agent using signed Google OIDC identity tokens.
- **Dedicated Service Accounts**:
  - `sa-ingestion-worker`: Scoped exclusively to BigQuery editor and Pub/Sub publisher.
  - `sa-adk-agent`: Scoped exclusively to Vertex AI user, BigQuery viewer/editor, and Cloud Trace agent.
  - `sa-pubsub-invoker`: Scoped strictly to `roles/run.invoker`.
- **Audit Lineage**: Every decision, tool invocation, model version, and trace ID is immutably recorded in BigQuery `alert_audits`.

---

## 📄 License & Attribution
- Project created for the **Google Cloud AI Builder Cup 2026** (Sustainability & Social Impact).
- Data sources: NASA GPM IMERG, ECMWF ERA5-Land, Copernicus Sentinel-1, Global Flood Database.
- Governed by the guidelines outlined in [`AGENTS.md`](./AGENTS.md).
