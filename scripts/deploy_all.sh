#!/usr/bin/env bash
# ==============================================================================
# EarthWhisper End-to-End GCP Deployment Script
# Google Cloud AI Builder Cup 2026
# ==============================================================================
set -euo pipefail

PROJECT_ID="${1:-${PROJECT_ID:-}}"
REGION="${2:-${REGION:-us-central1}}"

if [ -z "$PROJECT_ID" ]; then
    echo "Usage: ./scripts/deploy_all.sh <GCP_PROJECT_ID> [REGION]"
    exit 1
fi

echo "===================================================================="
echo " Starting EarthWhisper Deployment for Project: ${PROJECT_ID} (${REGION})"
echo "===================================================================="

# 1. Terraform Infrastructure Provisioning
echo "--> [1/5] Applying Terraform Infrastructure as Code..."
cd terraform
terraform init
terraform apply \
    -var="project_id=${PROJECT_ID}" \
    -var="region=${REGION}" \
    -auto-approve
cd ..

# 2. Seed Real BigQuery Climatology & Assam ImpactGraph
echo "--> [2/6] Seeding Real 10-Year DOY Baseline & Assam ImpactGraph into BigQuery Live..."
python data_pipeline/seed_real_climatology_baseline.py --project_id="${PROJECT_ID}"
python data_pipeline/seed_real_impact_graph.py --project_id="${PROJECT_ID}"

# 3. Ingest Cleaned Historical Dataset from Earth Engine into BigQuery
echo "--> [3/6] Extracting, Cleaning, and Ingesting Historical GPM/ERA5/GFD Data to BigQuery..."
python data_pipeline/extract_historical_to_bigquery.py --project_id="${PROJECT_ID}"

# 4. Train XGBoost Model Directly from BigQuery & Deploy to Vertex AI
echo "--> [4/6] Training XGBoost Directly from BigQuery & Deploying to Vertex AI Endpoint..."
python ml_engine/train_xgboost.py --project_id="${PROJECT_ID}"
python ml_engine/deploy_vertex.py --project_id="${PROJECT_ID}" --region="${REGION}"

# 4. Build & Deploy Cloud Run Containers
echo "--> [4/5] Building & Deploying Cloud Run Services..."
# Build Ingestion Worker
gcloud builds submit --config cloudbuild-worker.yaml .
gcloud run deploy earthwhisper-ingest-worker \
    --image "gcr.io/${PROJECT_ID}/earthwhisper-ingest-worker:v1" \
    --region "${REGION}" \
    --project "${PROJECT_ID}"

# Build ADK Agent
gcloud builds submit --config cloudbuild-agent.yaml .
gcloud run deploy earthwhisper-adk-agent \
    --image "gcr.io/${PROJECT_ID}/earthwhisper-adk-agent:v1" \
    --region "${REGION}" \
    --project "${PROJECT_ID}"

# Build Streamlit Dashboard
gcloud builds submit --config cloudbuild-dashboard.yaml .
gcloud run deploy earthwhisper-dashboard \
    --image "gcr.io/${PROJECT_ID}/earthwhisper-dashboard:v1" \
    --region "${REGION}" \
    --project "${PROJECT_ID}" \
    --allow-unauthenticated

# 5. Run Gen AI Evaluation Suite
echo "--> [5/5] Running Vertex AI Gen AI Evaluation Suite..."
cd evals
python run_agent_evals.py
cd ..

echo "===================================================================="
echo " EarthWhisper Deployment Completed Successfully!"
echo " Open your deployed Streamlit Dashboard URL to explore the demo."
echo "===================================================================="
