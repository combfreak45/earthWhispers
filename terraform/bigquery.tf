# BigQuery Datasets & Tables for Live and Isolated Mock Executions

# -------------------------------------------------------------
# 1. BigQuery Datasets
# -------------------------------------------------------------

resource "google_bigquery_dataset" "live_dataset" {
  dataset_id                  = "earthwhisper_live"
  friendly_name               = "EarthWhisper Live Production Dataset"
  description                 = "Contains genuine satellite observations, real Vertex AI inferences, and production audits."
  location                    = var.region
  project                     = var.project_id
  delete_contents_on_destroy  = true
  depends_on                  = [google_project_service.apis]
}

resource "google_bigquery_dataset" "mock_dataset" {
  dataset_id                  = "earthwhisper_mock"
  friendly_name               = "EarthWhisper Mock & Test Dataset"
  description                 = "Isolated dataset for synthetic benchmark replays, dry-runs, and unit test fixtures."
  location                    = var.region
  project                     = var.project_id
  delete_contents_on_destroy  = true
  depends_on                  = [google_project_service.apis]
}

# -------------------------------------------------------------
# 2. Table Schemas (Defined as reusable locals)
# -------------------------------------------------------------

locals {
  catchment_features_schema = jsonencode([
    { name = "catchment_id", type = "STRING", mode = "REQUIRED" },
    { name = "observation_timestamp", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "ingestion_timestamp", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "rain_1h_mm", type = "FLOAT", mode = "NULLABLE" },
    { name = "rain_3h_mm", type = "FLOAT", mode = "NULLABLE" },
    { name = "rain_6h_mm", type = "FLOAT", mode = "NULLABLE" },
    { name = "rain_24h_mm", type = "FLOAT", mode = "NULLABLE" },
    { name = "rain_72h_mm", type = "FLOAT", mode = "NULLABLE" },
    { name = "rain_7d_mm", type = "FLOAT", mode = "NULLABLE" },
    { name = "rain_peak_1h_mm", type = "FLOAT", mode = "NULLABLE" },
    { name = "rain_24h_anomaly_pct", type = "FLOAT", mode = "NULLABLE" },
    { name = "rain_72h_zscore", type = "FLOAT", mode = "NULLABLE" },
    { name = "soil_water_layer1", type = "FLOAT", mode = "NULLABLE" },
    { name = "elevation_mean_m", type = "FLOAT", mode = "NULLABLE" },
    { name = "slope_mean_deg", type = "FLOAT", mode = "NULLABLE" },
    { name = "data_freshness_hrs", type = "FLOAT", mode = "REQUIRED" },
    { name = "spatial_coverage_pct", type = "FLOAT", mode = "REQUIRED" },
    { name = "freshness_status", type = "STRING", mode = "REQUIRED" },
    { name = "feature_version", type = "STRING", mode = "REQUIRED" }
  ])

  catchment_baseline_schema = jsonencode([
    { name = "catchment_id", type = "STRING", mode = "REQUIRED" },
    { name = "doy", type = "INTEGER", mode = "REQUIRED" },
    { name = "mean_rain_24h_mm", type = "FLOAT", mode = "REQUIRED" },
    { name = "std_rain_24h_mm", type = "FLOAT", mode = "REQUIRED" },
    { name = "mean_rain_72h_mm", type = "FLOAT", mode = "REQUIRED" },
    { name = "std_rain_72h_mm", type = "FLOAT", mode = "REQUIRED" },
    { name = "baseline_window_years", type = "STRING", mode = "REQUIRED" }
  ])

  impact_graph_assets_schema = jsonencode([
    { name = "asset_id", type = "STRING", mode = "REQUIRED" },
    { name = "catchment_id", type = "STRING", mode = "REQUIRED" },
    { name = "district", type = "STRING", mode = "REQUIRED" },
    { name = "name", type = "STRING", mode = "REQUIRED" },
    { name = "asset_type", type = "STRING", mode = "REQUIRED" }, # SETTLEMENT, HOSPITAL, SCHOOL, BRIDGE, EVACUATION_CENTER
    { name = "population", type = "INTEGER", mode = "NULLABLE" },
    { name = "latitude", type = "FLOAT", mode = "REQUIRED" },
    { name = "longitude", type = "FLOAT", mode = "REQUIRED" },
    { name = "vulnerability_index", type = "FLOAT", mode = "REQUIRED" }
  ])

  alert_audits_schema = jsonencode([
    { name = "audit_id", type = "STRING", mode = "REQUIRED" },
    { name = "execution_mode", type = "STRING", mode = "REQUIRED" }, # live or mock
    { name = "trace_id", type = "STRING", mode = "REQUIRED" },
    { name = "catchment_id", type = "STRING", mode = "REQUIRED" },
    { name = "observation_timestamp", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "evaluation_timestamp", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "risk_score", type = "FLOAT", mode = "REQUIRED" },
    { name = "risk_class", type = "INTEGER", mode = "REQUIRED" }, # 0, 1, 2
    { name = "model_version", type = "STRING", mode = "REQUIRED" },
    { name = "data_freshness_status", type = "STRING", mode = "REQUIRED" },
    { name = "policy_action", type = "STRING", mode = "REQUIRED" }, # SUPPRESSED_COOLDOWN, LOGGED_ONLY, DISPATCHED_ALERT
    { name = "gemini_briefing", type = "STRING", mode = "REQUIRED" },
    { name = "tool_call_log", type = "STRING", mode = "REQUIRED" },
    { name = "affected_assets_count", type = "INTEGER", mode = "REQUIRED" }
  ])

  training_dataset_schema = jsonencode([
    { name = "catchment_id", type = "STRING", mode = "REQUIRED" },
    { name = "observation_timestamp", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "rain_1h_mm", type = "FLOAT", mode = "REQUIRED" },
    { name = "rain_3h_mm", type = "FLOAT", mode = "REQUIRED" },
    { name = "rain_6h_mm", type = "FLOAT", mode = "REQUIRED" },
    { name = "rain_24h_mm", type = "FLOAT", mode = "REQUIRED" },
    { name = "rain_72h_mm", type = "FLOAT", mode = "REQUIRED" },
    { name = "rain_7d_mm", type = "FLOAT", mode = "REQUIRED" },
    { name = "rain_peak_1h_mm", type = "FLOAT", mode = "REQUIRED" },
    { name = "rain_24h_anomaly_pct", type = "FLOAT", mode = "REQUIRED" },
    { name = "rain_72h_zscore", type = "FLOAT", mode = "REQUIRED" },
    { name = "soil_water_layer1", type = "FLOAT", mode = "REQUIRED" },
    { name = "elevation_mean_m", type = "FLOAT", mode = "REQUIRED" },
    { name = "slope_mean_deg", type = "FLOAT", mode = "REQUIRED" },
    { name = "data_freshness_hrs", type = "FLOAT", mode = "REQUIRED" },
    { name = "spatial_coverage_pct", type = "FLOAT", mode = "REQUIRED" },
    { name = "flood_risk_level", type = "INTEGER", mode = "REQUIRED" }, # Target Label (0, 1, 2)
    { name = "event_id", type = "STRING", mode = "NULLABLE" },
    { name = "split", type = "STRING", mode = "REQUIRED" } # TRAIN, VAL, TEST
  ])
}

# -------------------------------------------------------------
# 3. Live Tables
# -------------------------------------------------------------

resource "google_bigquery_table" "live_catchment_features" {
  dataset_id          = google_bigquery_dataset.live_dataset.dataset_id
  table_id            = "catchment_features"
  project             = var.project_id
  schema              = local.catchment_features_schema
  time_partitioning {
    type  = "DAY"
    field = "observation_timestamp"
  }
}

resource "google_bigquery_table" "live_catchment_baseline" {
  dataset_id          = google_bigquery_dataset.live_dataset.dataset_id
  table_id            = "catchment_climate_baseline"
  project             = var.project_id
  schema              = local.catchment_baseline_schema
}

resource "google_bigquery_table" "live_impact_graph_assets" {
  dataset_id          = google_bigquery_dataset.live_dataset.dataset_id
  table_id            = "impact_graph_assets"
  project             = var.project_id
  schema              = local.impact_graph_assets_schema
}

resource "google_bigquery_table" "live_alert_audits" {
  dataset_id          = google_bigquery_dataset.live_dataset.dataset_id
  table_id            = "alert_audits"
  project             = var.project_id
  schema              = local.alert_audits_schema
  time_partitioning {
    type  = "DAY"
    field = "evaluation_timestamp"
  }
}

resource "google_bigquery_table" "live_training_dataset" {
  dataset_id          = google_bigquery_dataset.live_dataset.dataset_id
  table_id            = "training_dataset"
  project             = var.project_id
  schema              = local.training_dataset_schema
  time_partitioning {
    type  = "DAY"
    field = "observation_timestamp"
  }
}

# -------------------------------------------------------------
# 4. Mock Tables (Completely Segregated)
# -------------------------------------------------------------

resource "google_bigquery_table" "mock_catchment_features" {
  dataset_id          = google_bigquery_dataset.mock_dataset.dataset_id
  table_id            = "catchment_features"
  project             = var.project_id
  schema              = local.catchment_features_schema
}

resource "google_bigquery_table" "mock_catchment_baseline" {
  dataset_id          = google_bigquery_dataset.mock_dataset.dataset_id
  table_id            = "catchment_climate_baseline"
  project             = var.project_id
  schema              = local.catchment_baseline_schema
}

resource "google_bigquery_table" "mock_impact_graph_assets" {
  dataset_id          = google_bigquery_dataset.mock_dataset.dataset_id
  table_id            = "impact_graph_assets"
  project             = var.project_id
  schema              = local.impact_graph_assets_schema
}

resource "google_bigquery_table" "mock_alert_audits" {
  dataset_id          = google_bigquery_dataset.mock_dataset.dataset_id
  table_id            = "alert_audits"
  project             = var.project_id
  schema              = local.alert_audits_schema
}

resource "google_bigquery_table" "mock_training_dataset" {
  dataset_id          = google_bigquery_dataset.mock_dataset.dataset_id
  table_id            = "training_dataset"
  project             = var.project_id
  schema              = local.training_dataset_schema
}
