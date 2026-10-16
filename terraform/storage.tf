# Cloud Storage Buckets for Models, Live Data, and Isolated Mock Fixtures

# 1. Vertex AI Model Artifacts Bucket
resource "google_storage_bucket" "models_bucket" {
  name                        = "${var.project_id}-models"
  location                    = var.region
  project                     = var.project_id
  force_destroy               = true
  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  depends_on = [google_project_service.apis]
}

# 2. Live Environmental Data & Community Uploads Bucket
resource "google_storage_bucket" "data_live_bucket" {
  name                        = "${var.project_id}-data-live"
  location                    = var.region
  project                     = var.project_id
  force_destroy               = true
  uniform_bucket_level_access = true

  versioning {
    enabled = false
  }

  lifecycle_rule {
    condition {
      age = 90
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.apis]
}

# 3. Mock & Synthetic Fixture Data Bucket (Strictly Isolated)
resource "google_storage_bucket" "data_mock_bucket" {
  name                        = "${var.project_id}-data-mock"
  location                    = var.region
  project                     = var.project_id
  force_destroy               = true
  uniform_bucket_level_access = true

  depends_on = [google_project_service.apis]
}
