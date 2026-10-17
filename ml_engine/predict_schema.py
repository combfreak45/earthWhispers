"""
EarthWhisper Typed Feature and Prediction Schemas
Used across the ML pipeline, Vertex AI Endpoint, and Google ADK Agent tools.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class CatchmentFeatures(BaseModel):
    rain_1h_mm: float = Field(..., description="Precipitation accumulation in the last 1 hour (mm)")
    rain_3h_mm: float = Field(..., description="Precipitation accumulation in the last 3 hours (mm)")
    rain_6h_mm: float = Field(..., description="Precipitation accumulation in the last 6 hours (mm)")
    rain_24h_mm: float = Field(..., description="Precipitation accumulation in the last 24 hours (mm)")
    rain_72h_mm: float = Field(..., description="Precipitation accumulation in the last 72 hours (mm)")
    rain_7d_mm: float = Field(..., description="Cumulative precipitation in the last 7 days (mm)")
    rain_peak_1h_mm: float = Field(..., description="Maximum 1-hour rainfall intensity observed in last 24h (mm/h)")
    rain_24h_anomaly_pct: float = Field(..., description="Percentage anomaly against historical Day-of-Year baseline mean")
    rain_72h_zscore: float = Field(..., description="Z-score deviation of 72h rainfall against historical baseline")
    soil_water_layer1: float = Field(..., description="Volumetric soil water content in top 0-7cm layer (m³/m³)")
    elevation_mean_m: float = Field(..., description="Catchment mean elevation (meters)")
    slope_mean_deg: float = Field(..., description="Catchment mean slope (degrees)")
    data_freshness_hrs: float = Field(..., description="Satellite sensor latency in hours")
    spatial_coverage_pct: float = Field(..., description="Percentage of catchment with valid sensor returns")

    def to_feature_vector(self) -> List[float]:
        return [
            self.rain_1h_mm,
            self.rain_3h_mm,
            self.rain_6h_mm,
            self.rain_24h_mm,
            self.rain_72h_mm,
            self.rain_7d_mm,
            self.rain_peak_1h_mm,
            self.rain_24h_anomaly_pct,
            self.rain_72h_zscore,
            self.soil_water_layer1,
            self.elevation_mean_m,
            self.slope_mean_deg,
            self.data_freshness_hrs,
            self.spatial_coverage_pct
        ]


class FeatureContribution(BaseModel):
    feature_name: str
    feature_value: float
    importance_weight: float


class PredictionResult(BaseModel):
    risk_class: int = Field(..., description="0: Low / Normal, 1: Moderate / Alert, 2: High / Severe")
    risk_label: str = Field(..., description="'Low', 'Moderate', or 'Severe'")
    risk_score: float = Field(..., description="Calibrated flood risk probability score (0.0 to 1.0)")
    class_probabilities: Dict[str, float] = Field(..., description="Class probability distribution")
    top_contributing_features: List[FeatureContribution] = Field(default_factory=list, description="Top drivers of risk")
    model_version: str = Field(..., description="Vertex AI Model Registry version ID")
