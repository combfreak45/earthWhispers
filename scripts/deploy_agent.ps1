# ==============================================================================
# EarthWhisper Agent Multi-Runtime Deployment Script (PowerShell)
# Deploys to:
#  1. Google Cloud Run (Containerized ADK Agent with Pub/Sub & Webhook Endpoints)
#  2. Agent Runtime (Managed Reasoning Engine Platform)
# Google Cloud AI Builder Cup 2026
# ==============================================================================
param (
    [string]$ProjectId = $env:PROJECT_ID,
    [string]$Region = "us-central1",
    [ValidateSet("All", "CloudRun", "AgentEngine")]
    [string]$Target = "All"
)

$ErrorActionPreference = "Stop"

if (-not $ProjectId) {
    $ProjectId = "your-google-cloud-project-id"
}

Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host " Deploying EarthWhisper Agent" -ForegroundColor Cyan
Write-Host " Project: $ProjectId | Region: $Region | Target: $Target" -ForegroundColor Cyan
Write-Host "====================================================================" -ForegroundColor Cyan

# ------------------------------------------------------------------------------
# 1. Deploy to Google Cloud Run Agent Runtime
# ------------------------------------------------------------------------------
if ($Target -eq "All" -or $Target -eq "CloudRun") {
    Write-Host "`n--> [1/2] Deploying Agent to Google Cloud Run..." -ForegroundColor Yellow
    Write-Host "    Building container image via Cloud Build (root context)..." -ForegroundColor Gray
    gcloud builds submit --config cloudbuild-agent.yaml --project "$ProjectId" .

    Write-Host "    Deploying earthwhisper-adk-agent service..." -ForegroundColor Gray
    gcloud run deploy earthwhisper-adk-agent `
        --image "gcr.io/$ProjectId/earthwhisper-adk-agent:v1" `
        --region "$Region" `
        --project "$ProjectId" `
        --memory 2Gi `
        --cpu 2 `
        --timeout 300 `
        --concurrency 80 `
        --update-env-vars "PROJECT_ID=$ProjectId,REGION=$Region,GOOGLE_GENAI_USE_VERTEXAI=true,VERTEX_ENDPOINT_ID=earthwhisper-flood-risk-endpoint,BIGQUERY_DATASET_LIVE=earthwhisper_live"

    $AgentUrl = gcloud run services describe earthwhisper-adk-agent --region "$Region" --project "$ProjectId" --format="value(status.url)"
    Write-Host "    Cloud Run Service URL: $AgentUrl" -ForegroundColor Cyan
    Write-Host "    Pub/Sub EventArc Target: $AgentUrl/events" -ForegroundColor Cyan
    Write-Host "    [OK] Cloud Run Agent Runtime Active!" -ForegroundColor Green
}

# ------------------------------------------------------------------------------
# 2. Deploy to Agent Runtime (Reasoning Engine)
# ------------------------------------------------------------------------------
if ($Target -eq "All" -or $Target -eq "AgentEngine") {
    Write-Host "`n--> [2/2] Deploying Agent to Agent Runtime (Managed Platform)..." -ForegroundColor Yellow
    $StagingBucket = "gs://$ProjectId-models"
    
    $PythonCmd = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } elseif (Test-Path "..\.venv\Scripts\python.exe") { "..\.venv\Scripts\python.exe" } else { "python" }
    
    & $PythonCmd agent/deploy_vertex_agent_engine.py `
        --project_id="$ProjectId" `
        --location="$Region" `
        --staging_bucket="$StagingBucket" `
        --display_name="earthwhisper-agent-engine"

    Write-Host "    [OK] Agent Runtime Deployment Succeeded!" -ForegroundColor Green
}

Write-Host "`n====================================================================" -ForegroundColor Green
Write-Host " EarthWhisper Agent Deployment Completed Successfully!" -ForegroundColor Green
Write-Host "====================================================================" -ForegroundColor Green
