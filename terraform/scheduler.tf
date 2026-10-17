# Cloud Scheduler Job for Daily Automated Ingestion

resource "google_cloud_scheduler_job" "daily_ingest_job" {
  name             = "daily-earthwhisper-ingest"
  description      = "Triggers the Cloud Run Ingestion Worker daily for the Lower Brahmaputra catchment."
  schedule         = var.ingest_schedule_cron
  time_zone        = "UTC"
  attempt_deadline = "300s"
  project          = var.project_id
  region           = var.region

  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_v2_service.ingest_worker.uri}/ingest/run"
    body        = base64encode(jsonencode({
      mode         = "live"
      catchment_id = var.catchment_id
    }))

    headers = {
      "Content-Type" = "application/json"
    }

    oidc_token {
      service_account_email = google_service_account.sa_scheduler_invoker.email
      audience              = google_cloud_run_v2_service.ingest_worker.uri
    }
  }

  depends_on = [google_cloud_run_v2_service.ingest_worker]
}
