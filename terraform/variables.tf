variable "project_id" {
  description = "The GCP Project ID where EarthWhisper resources will be provisioned."
  type        = string
}

variable "region" {
  description = "The default GCP region for compute and storage resources."
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "The default GCP zone."
  type        = string
  default     = "us-central1-a"
}

variable "environment" {
  description = "Deployment environment (e.g. prod, dev, demo)."
  type        = string
  default     = "demo"
}

variable "catchment_id" {
  description = "Unique identifier for the primary study area catchment."
  type        = string
  default     = "brahmaputra_lower_assam"
}

variable "ingest_schedule_cron" {
  description = "Cron expression for the daily ingestion Cloud Scheduler job (UTC)."
  type        = string
  default     = "0 6 * * *" # Daily at 06:00 UTC
}

variable "container_images" {
  description = "Container image URIs for Cloud Run services. Defaults to placeholder for initial bootstrap."
  type = object({
    ingest_worker = string
    adk_agent     = string
    dashboard     = string
  })
  default = {
    ingest_worker = "gcr.io/google-samples/hello-app:1.0"
    adk_agent     = "gcr.io/google-samples/hello-app:1.0"
    dashboard     = "gcr.io/google-samples/hello-app:1.0"
  }
}
