# Enable all required Google Cloud APIs for EarthWhisper MVP

locals {
  required_apis = [
    "run.googleapis.com",
    "aiplatform.googleapis.com",
    "bigquery.googleapis.com",
    "earthengine.googleapis.com",
    "pubsub.googleapis.com",
    "cloudscheduler.googleapis.com",
    "storage.googleapis.com",
    "cloudtrace.googleapis.com",
    "monitoring.googleapis.com",
    "secretmanager.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com",
    "iam.googleapis.com"
  ]
}

resource "google_project_service" "apis" {
  for_each           = toset(local.required_apis)
  project            = var.project_id
  service            = each.key
  disable_on_destroy = false
}
