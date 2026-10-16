# Pub/Sub Messaging: Signals Topic, DLQ, Push Subscriptions, and Alert Bus

data "google_project" "current" {
  project_id = var.project_id
}

# -------------------------------------------------------------
# 1. Signal Topics (Ingestion -> ADK Agent)
# -------------------------------------------------------------

resource "google_pubsub_topic" "signals_topic" {
  name    = "earthwhisper-signals"
  project = var.project_id
  labels = {
    purpose = "ingestion-signals"
  }
  depends_on = [google_project_service.apis]
}

resource "google_pubsub_topic" "signals_dlq" {
  name    = "earthwhisper-signals-dlq"
  project = var.project_id
  labels = {
    purpose = "dead-letter-queue"
  }
  depends_on = [google_project_service.apis]
}

# Grant Pub/Sub service agent permission to forward to DLQ
resource "google_pubsub_topic_iam_member" "pubsub_dlq_publisher" {
  project = var.project_id
  topic   = google_pubsub_topic.signals_dlq.name
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

resource "google_pubsub_subscription_iam_member" "pubsub_dlq_subscriber" {
  project      = var.project_id
  subscription = google_pubsub_subscription.signals_push_sub.name
  role         = "roles/pubsub.subscriber"
  member       = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

# Authenticated Push Subscription directly invoking ADK Agent on Cloud Run
resource "google_pubsub_subscription" "signals_push_sub" {
  name                 = "sub-earthwhisper-signals-push"
  topic                = google_pubsub_topic.signals_topic.id
  project              = var.project_id
  ack_deadline_seconds = 120

  push_config {
    push_endpoint = "${google_cloud_run_v2_service.adk_agent.uri}/events"

    oidc_token {
      service_account_email = google_service_account.sa_pubsub_invoker.email
      audience              = google_cloud_run_v2_service.adk_agent.uri
    }
  }

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.signals_dlq.id
    max_delivery_attempts = 5
  }

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }

  depends_on = [google_cloud_run_v2_service.adk_agent]
}

# -------------------------------------------------------------
# 2. Outbound Alert Topic (Agent -> Regional Responders)
# -------------------------------------------------------------

resource "google_pubsub_topic" "alerts_topic" {
  name    = "earthwhisper-alerts"
  project = var.project_id
  labels = {
    purpose = "regional-alerts"
  }
  depends_on = [google_project_service.apis]
}

resource "google_pubsub_subscription" "alerts_sub" {
  name                 = "sub-earthwhisper-alerts"
  topic                = google_pubsub_topic.alerts_topic.id
  project              = var.project_id
  ack_deadline_seconds = 60
}
