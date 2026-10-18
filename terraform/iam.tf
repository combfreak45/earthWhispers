# Least-Privilege IAM Service Accounts and Role Bindings

# 1. Ingestion Worker Service Account
resource "google_service_account" "sa_ingestion" {
  account_id   = "sa-ew-ingestion-worker"
  display_name = "EarthWhisper Ingestion Worker Service Account"
  project      = var.project_id
  depends_on   = [google_project_service.apis]
}

resource "google_project_iam_member" "ingestion_roles" {
  for_each = toset([
    "roles/bigquery.dataEditor",
    "roles/bigquery.jobUser",
    "roles/pubsub.publisher",
    "roles/storage.objectAdmin",
    "roles/cloudtrace.agent",
    # Earth Engine init needs these (added manually 2026-10-17; codified here):
    "roles/serviceusage.serviceUsageConsumer",
    "roles/earthengine.writer"
  ])
  project = var.project_id
  role    = each.key
  member  = "serviceAccount:${google_service_account.sa_ingestion.email}"
}

# 2. ADK Agent Service Account
resource "google_service_account" "sa_adk_agent" {
  account_id   = "sa-ew-adk-agent"
  display_name = "EarthWhisper ADK Agent Service Account"
  project      = var.project_id
  depends_on   = [google_project_service.apis]
}

resource "google_project_iam_member" "adk_agent_roles" {
  for_each = toset([
    "roles/aiplatform.user",
    "roles/bigquery.dataViewer",
    "roles/bigquery.dataEditor",
    "roles/bigquery.jobUser",
    "roles/pubsub.publisher",
    "roles/cloudtrace.agent",
    "roles/storage.objectViewer"
  ])
  project = var.project_id
  role    = each.key
  member  = "serviceAccount:${google_service_account.sa_adk_agent.email}"
}

# 3. Pub/Sub Push Subscription Invoker Service Account
resource "google_service_account" "sa_pubsub_invoker" {
  account_id   = "sa-ew-pubsub-invoker"
  display_name = "EarthWhisper Pub/Sub Push Invoker Service Account"
  project      = var.project_id
  depends_on   = [google_project_service.apis]
}

# 4. Cloud Scheduler Invoker Service Account
resource "google_service_account" "sa_scheduler_invoker" {
  account_id   = "sa-ew-scheduler-invoker"
  display_name = "EarthWhisper Cloud Scheduler Invoker Service Account"
  project      = var.project_id
  depends_on   = [google_project_service.apis]
}

# 5. Dashboard Service Account
resource "google_service_account" "sa_dashboard" {
  account_id   = "sa-ew-dashboard"
  display_name = "EarthWhisper Dashboard Service Account"
  project      = var.project_id
  depends_on   = [google_project_service.apis]
}

resource "google_project_iam_member" "dashboard_roles" {
  for_each = toset([
    "roles/bigquery.dataViewer",
    "roles/bigquery.jobUser",
    "roles/aiplatform.user",
    "roles/storage.objectAdmin",
    "roles/cloudtrace.agent"
  ])
  project = var.project_id
  role    = each.key
  member  = "serviceAccount:${google_service_account.sa_dashboard.email}"
}

# 6. Vertex AI Agent Engine (Reasoning Engine) runtime service agent.
# This SA is Google-managed (auto-created when the Agent Engine / aiplatform RE API
# is used). The deployed agent runs AS this identity, so it needs access to call the
# Vertex endpoint, read/write BigQuery, and use the project's APIs.
# Granted manually 2026-10-18; codified here so a rebuild recreates them.
resource "google_project_iam_member" "reasoning_engine_roles" {
  for_each = toset([
    "roles/aiplatform.user",
    "roles/bigquery.dataEditor",
    "roles/bigquery.jobUser",
    "roles/serviceusage.serviceUsageConsumer"
  ])
  project = var.project_id
  role    = each.key
  member  = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-aiplatform-re.iam.gserviceaccount.com"
}
