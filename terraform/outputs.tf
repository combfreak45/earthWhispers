# Terraform Outputs for EarthWhisper MVP

output "ingest_worker_url" {
  description = "Cloud Run Ingestion Worker service URL"
  value       = google_cloud_run_v2_service.ingest_worker.uri
}

output "adk_agent_url" {
  description = "Cloud Run ADK Agent service URL (Private Authenticated)"
  value       = google_cloud_run_v2_service.adk_agent.uri
}

output "dashboard_url" {
  description = "Cloud Run Streamlit Dashboard service URL (Public Demo UI)"
  value       = google_cloud_run_v2_service.dashboard.uri
}

output "vertex_endpoint_id" {
  description = "Vertex AI Flood Risk Endpoint Name/ID"
  value       = google_vertex_ai_endpoint.flood_risk_endpoint.name
}

output "signals_topic_id" {
  description = "Pub/Sub Signals Topic ID"
  value       = google_pubsub_topic.signals_topic.id
}

output "alerts_topic_id" {
  description = "Pub/Sub Outbound Alerts Topic ID"
  value       = google_pubsub_topic.alerts_topic.id
}

output "live_dataset_id" {
  description = "BigQuery Live Production Dataset"
  value       = google_bigquery_dataset.live_dataset.dataset_id
}

output "mock_dataset_id" {
  description = "BigQuery Mock & Fixture Dataset"
  value       = google_bigquery_dataset.mock_dataset.dataset_id
}

output "models_bucket_name" {
  description = "Cloud Storage bucket for serialized ML model artifacts"
  value       = google_storage_bucket.models_bucket.name
}

output "data_live_bucket_name" {
  description = "Cloud Storage bucket for live observations and community photo uploads"
  value       = google_storage_bucket.data_live_bucket.name
}
