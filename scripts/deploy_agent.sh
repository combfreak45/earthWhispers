#!/usr/bin/env bash
# ==============================================================================
# EarthWhisper Agent Multi-Runtime Deployment Script (Bash)
# Deploys to:
#  1. Google Cloud Run (Containerized ADK Agent with Pub/Sub & Webhook Endpoints)
#  2. Agent Runtime (Managed Reasoning Engine Platform)
# Google Cloud AI Builder Cup 2026
# ==============================================================================
set -euo pipefail

PROJECT_ID="${1:-${PROJECT_ID:-your-google-cloud-project-id}}"
REGION="${2:-${REGION:-us-central1}}"
TARGET="${3:-All}"

echo "===================================================================="
echo " Deploying EarthWhisper Agent"
echo " Project: ${PROJECT_ID} | Region: ${REGION} | Target: ${TARGET}"
echo "===================================================================="

# 1. Deploy to Google Cloud Run
if [ "${TARGET}" = "All" ] || [ "${TARGET}" = "CloudRun" ]; then
    echo ""
    echo "--> [1/2] Deploying Agent to Google Cloud Run..."
    gcloud builds submit --config cloudbuild-agent.yaml --project "${PROJECT_ID}" .

    gcloud run deploy earthwhisper-adk-agent \
        --image "gcr.io/${PROJECT_ID}/earthwhisper-adk-agent:v1" \
        --region "${REGION}" \
        --project "${PROJECT_ID}" \
        --memory 2Gi \
        --cpu 2 \
        --timeout 300 \
        --concurrency 80 \
        --update-env-vars "PROJECT_ID=${PROJECT_ID},REGION=${REGION},GOOGLE_GENAI_USE_VERTEXAI=true,VERTEX_ENDPOINT_ID=earthwhisper-flood-risk-endpoint,BIGQUERY_DATASET_LIVE=earthwhisper_live"

    AGENT_URL=$(gcloud run services describe earthwhisper-adk-agent --region "${REGION}" --project "${PROJECT_ID}" --format="value(status.url)")
    echo "    Cloud Run Service URL: ${AGENT_URL}"
    echo "    Pub/Sub EventArc Target: ${AGENT_URL}/events"
    echo "    [OK] Cloud Run Agent Runtime Active!"
fi

# 2. Deploy to Agent Runtime (Reasoning Engine)
if [ "${TARGET}" = "All" ] || [ "${TARGET}" = "AgentEngine" ]; then
    echo ""
    echo "--> [2/2] Deploying Agent to Agent Runtime..."
    STAGING_BUCKET="gs://${PROJECT_ID}-models"

    PYTHON_CMD="python"
    if [ -f ".venv/bin/python" ]; then
        PYTHON_CMD=".venv/bin/python"
    elif [ -f "../.venv/bin/python" ]; then
        PYTHON_CMD="../.venv/bin/python"
    elif [ -f ".venv/Scripts/python.exe" ]; then
        PYTHON_CMD=".venv/Scripts/python.exe"
    elif [ -f "../.venv/Scripts/python.exe" ]; then
        PYTHON_CMD="../.venv/Scripts/python.exe"
    fi

    ${PYTHON_CMD} agent/deploy_vertex_agent_engine.py \
        --project_id="${PROJECT_ID}" \
        --location="${REGION}" \
        --staging_bucket="${STAGING_BUCKET}" \
        --display_name="earthwhisper-agent-engine"

    echo "    [OK] Agent Runtime Deployment Succeeded!"
fi

echo ""
echo "===================================================================="
echo " EarthWhisper Agent Deployment Completed Successfully!"
echo "===================================================================="
