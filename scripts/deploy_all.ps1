# ==============================================================================
# EarthWhisper End-to-End GCP Deployment Script (PowerShell for Windows)
# Google Cloud AI Builder Cup 2026
# ==============================================================================
param (
    [Parameter(Mandatory=$true)]
    [string]$ProjectId,
    [string]$Region = "us-central1"
)

$ErrorActionPreference = "Stop"

Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host " Starting EarthWhisper Deployment for Project: $ProjectId ($Region)" -ForegroundColor Cyan
Write-Host "====================================================================" -ForegroundColor Cyan

# 1. Terraform Infrastructure Provisioning
Write-Host "--> [1/5] Applying Terraform Infrastructure as Code..." -ForegroundColor Yellow
Set-Location terraform
terraform init
terraform apply -var="project_id=$ProjectId" -var="region=$Region" -auto-approve
Set-Location ..

# 2. Seed Real BigQuery Climatology & Assam ImpactGraph
Write-Host "--> [2/6] Seeding Real 10-Year DOY Baseline & Assam ImpactGraph into BigQuery Live..." -ForegroundColor Yellow
python data_pipeline/seed_real_climatology_baseline.py --project_id="$ProjectId"
python data_pipeline/seed_real_impact_graph.py --project_id="$ProjectId"

# 3. Ingest Cleaned Historical Dataset from Earth Engine into BigQuery
Write-Host "--> [3/6] Extracting, Cleaning, and Ingesting Historical GPM/ERA5/GFD Data to BigQuery..." -ForegroundColor Yellow
python data_pipeline/extract_historical_to_bigquery.py --project_id="$ProjectId"

# 4. Train XGBoost Model Directly from BigQuery & Deploy to Vertex AI
Write-Host "--> [4/6] Training XGBoost Directly from BigQuery & Deploying to Vertex AI Endpoint..." -ForegroundColor Yellow
python ml_engine/train_xgboost.py --project_id="$ProjectId"
python ml_engine/deploy_vertex.py --project_id="$ProjectId" --region="$Region"

# 4. Build & Deploy Cloud Run Containers
Write-Host "--> [4/5] Building & Deploying Cloud Run Services..." -ForegroundColor Yellow
gcloud builds submit --config cloudbuild-worker.yaml .
gcloud run deploy earthwhisper-ingest-worker --image "gcr.io/$ProjectId/earthwhisper-ingest-worker:v1" --region "$Region" --project "$ProjectId"

gcloud builds submit --config cloudbuild-agent.yaml .
gcloud run deploy earthwhisper-adk-agent --image "gcr.io/$ProjectId/earthwhisper-adk-agent:v1" --region "$Region" --project "$ProjectId"

gcloud builds submit --config cloudbuild-dashboard.yaml .
gcloud run deploy earthwhisper-dashboard --image "gcr.io/$ProjectId/earthwhisper-dashboard:v1" --region "$Region" --project "$ProjectId" --allow-unauthenticated

# 5. Run Gen AI Evaluation Suite
Write-Host "--> [5/5] Running Vertex AI Gen AI Evaluation Suite..." -ForegroundColor Yellow
Set-Location evals
python run_agent_evals.py
Set-Location ..

Write-Host "====================================================================" -ForegroundColor Green
Write-Host " EarthWhisper Deployment Completed Successfully!" -ForegroundColor Green
Write-Host "====================================================================" -ForegroundColor Green
