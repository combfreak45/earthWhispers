# Cloud Run Services: Ingestion Worker, ADK Agent, and Streamlit Dashboard

# -------------------------------------------------------------
# 1. Ingestion Worker Cloud Run Service
# -------------------------------------------------------------
resource "google_cloud_run_v2_service" "ingest_worker" {
  name     = "earthwhisper-ingest-worker"
  location = var.region
  project  = var.project_id

  template {
    service_account = google_service_account.sa_ingestion.email

    containers {
      image = var.container_images.ingest_worker

      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
      }

      env {
        name  = "PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "REGION"
        value = var.region
      }
      env {
        name  = "CATCHMENT_ID"
        value = var.catchment_id
      }
      env {
        name  = "PUBSUB_TOPIC_SIGNALS"
        value = google_pubsub_topic.signals_topic.id
      }
      env {
        name  = "BIGQUERY_DATASET_LIVE"
        value = google_bigquery_dataset.live_dataset.dataset_id
      }
      env {
        name  = "BIGQUERY_DATASET_MOCK"
        value = google_bigquery_dataset.mock_dataset.dataset_id
      }
    }

    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }
  }

  depends_on = [google_project_service.apis]
}

# -------------------------------------------------------------
# 2. ADK Agent Cloud Run Service (Private Authenticated)
# -------------------------------------------------------------
resource "google_cloud_run_v2_service" "adk_agent" {
  name     = "earthwhisper-adk-agent"
  location = var.region
  project  = var.project_id

  template {
    service_account = google_service_account.sa_adk_agent.email

    containers {
      image = var.container_images.adk_agent

      resources {
        limits = {
          cpu    = "2"
          memory = "4Gi"
        }
      }

      env {
        name  = "PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "REGION"
        value = var.region
      }
      env {
        name  = "VERTEX_ENDPOINT_ID"
        value = google_vertex_ai_endpoint.flood_risk_endpoint.name
      }
      env {
        name  = "BIGQUERY_MCP_URL"
        value = "https://bigquery.googleapis.com/mcp"
      }
      env {
        name  = "PUBSUB_TOPIC_ALERTS"
        value = google_pubsub_topic.alerts_topic.id
      }
      env {
        name  = "BIGQUERY_DATASET_LIVE"
        value = google_bigquery_dataset.live_dataset.dataset_id
      }
      env {
        name  = "BIGQUERY_DATASET_MOCK"
        value = google_bigquery_dataset.mock_dataset.dataset_id
      }
      env {
        name  = "GEMINI_MODEL"
        value = "gemini-2.5-flash"
      }
      env {
        name  = "OTEL_SERVICE_NAME"
        value = "earthwhisper-adk-agent"
      }
      # Gemini-via-Vertex for the grounded briefing (set manually 2026-10-17; codified here).
      env {
        name  = "GOOGLE_GENAI_USE_VERTEXAI"
        value = "true"
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GOOGLE_CLOUD_LOCATION"
        value = var.region
      }
    }

    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }
  }

  depends_on = [google_project_service.apis]
}

# IAM: Allow Pub/Sub Push Invoker Service Account to invoke ADK Agent
resource "google_cloud_run_v2_service_iam_member" "adk_agent_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.adk_agent.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.sa_pubsub_invoker.email}"
}

# IAM: Allow Cloud Scheduler to invoke Ingestion Worker
resource "google_cloud_run_v2_service_iam_member" "ingest_worker_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.ingest_worker.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.sa_scheduler_invoker.email}"
}

# -------------------------------------------------------------
# 3. Streamlit Dashboard Cloud Run Service
# -------------------------------------------------------------
resource "google_cloud_run_v2_service" "dashboard" {
  name     = "earthwhisper-dashboard"
  location = var.region
  project  = var.project_id

  template {
    service_account = google_service_account.sa_dashboard.email

    containers {
      image = var.container_images.dashboard

      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
      }

      env {
        name  = "PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "REGION"
        value = var.region
      }
      env {
        name  = "BIGQUERY_DATASET_LIVE"
        value = google_bigquery_dataset.live_dataset.dataset_id
      }
      env {
        name  = "BIGQUERY_DATASET_MOCK"
        value = google_bigquery_dataset.mock_dataset.dataset_id
      }
      env {
        name  = "ADK_SERVICE_URL"
        value = google_cloud_run_v2_service.adk_agent.uri
      }
      env {
        name  = "GCS_BUCKET_LIVE"
        value = google_storage_bucket.data_live_bucket.name
      }
    }

    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }
  }

  depends_on = [google_project_service.apis]
}

# Allow public (unauthenticated) access to Dashboard for hackathon evaluators
resource "google_cloud_run_v2_service_iam_member" "dashboard_public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.dashboard.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
