"""
EarthWhisper Data Freshness and Quality Validator
Validates sensor timestamp freshness, latency hours, spatial coverage percentage,
and prevents stale or corrupted data from silently triggering false high-risk alerts.
"""

from datetime import datetime, timezone
from typing import Dict, Any, Tuple
from pydantic import BaseModel, Field


class QualityAssessment(BaseModel):
    data_freshness_hrs: float = Field(..., description="Latency of satellite observation in hours.")
    spatial_coverage_pct: float = Field(..., description="Percentage of catchment with valid sensor returns.")
    freshness_status: str = Field(..., description="FRESH_NOMINAL, STALE_ACCEPTABLE, STALE_CRITICAL, or INCOMPLETE_COVERAGE")
    is_valid_for_evaluation: bool = Field(..., description="Whether data meets minimum threshold to evaluate.")
    warning_message: str = Field(default="", description="Explanatory warning if degraded.")


def validate_observation_quality(
    observation_time_utc: datetime,
    valid_pixel_pct: float,
    current_time_utc: datetime = None
) -> QualityAssessment:
    """
    Evaluates observation freshness against UTC clock and spatial completeness.
    """
    if current_time_utc is None:
        current_time_utc = datetime.now(timezone.utc)
        
    if observation_time_utc.tzinfo is None:
        observation_time_utc = observation_time_utc.replace(tzinfo=timezone.utc)

    # Compute latency
    time_diff = current_time_utc - observation_time_utc
    latency_hours = max(0.0, round(time_diff.total_seconds() / 3600.0, 2))
    
    # Assess spatial coverage
    spatial_coverage = max(0.0, min(100.0, round(valid_pixel_pct, 2)))
    
    # Classification rules
    warning = ""
    is_valid = True
    
    if spatial_coverage < 70.0:
        status = "INCOMPLETE_COVERAGE"
        warning = f"Spatial coverage across catchment is only {spatial_coverage}%. Sensor returns may be degraded by dense atmospheric occlusion or data dropouts."
        # Low coverage can still be processed, but with explicit limitation
    elif latency_hours <= 18.0:
        status = "FRESH_NOMINAL"
    elif latency_hours <= 48.0:
        status = "STALE_ACCEPTABLE"
        warning = f"Sensor latency is {latency_hours} hours. Acceptable for rolling 72-hour assessment but near-term onset confidence is reduced."
    else:
        status = "STALE_CRITICAL"
        warning = f"Sensor observation is {latency_hours} hours old. Critical latency threshold exceeded (>48h). High-risk alerts must be suppressed from auto-escalation."
        is_valid = False  # Triggers strict limitation flag
        
    return QualityAssessment(
        data_freshness_hrs=latency_hours,
        spatial_coverage_pct=spatial_coverage,
        freshness_status=status,
        is_valid_for_evaluation=is_valid,
        warning_message=warning
    )
