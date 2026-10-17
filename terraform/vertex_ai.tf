# Vertex AI Endpoint for XGBoost Flood Risk Prediction Model

resource "google_vertex_ai_endpoint" "flood_risk_endpoint" {
  name         = "earthwhisper-flood-risk-endpoint"
  display_name = "EarthWhisper XGBoost Flood Risk Endpoint"
  description  = "Vertex AI endpoint hosting the 3-class XGBoost model for flood risk scoring."
  location     = var.region
  project      = var.project_id

  labels = {
    env        = var.environment
    managed_by = "terraform"
    project    = "earthwhisper"
  }

  depends_on = [google_project_service.apis]
}
