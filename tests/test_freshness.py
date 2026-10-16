"""
Unit tests for data freshness and quality gate validation.
"""

import sys
import os
from datetime import datetime, timezone, timedelta
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data_pipeline")))

from freshness_validator import validate_observation_quality


def test_fresh_nominal():
    now = datetime.now(timezone.utc)
    obs = now - timedelta(hours=6)
    assessment = validate_observation_quality(obs, valid_pixel_pct=95.0, current_time_utc=now)
    assert assessment.freshness_status == "FRESH_NOMINAL"
    assert assessment.data_freshness_hrs == 6.0
    assert assessment.is_valid_for_evaluation is True


def test_stale_critical():
    now = datetime.now(timezone.utc)
    obs = now - timedelta(hours=52)
    assessment = validate_observation_quality(obs, valid_pixel_pct=90.0, current_time_utc=now)
    assert assessment.freshness_status == "STALE_CRITICAL"
    assert assessment.data_freshness_hrs == 52.0
    assert assessment.is_valid_for_evaluation is False


def test_incomplete_spatial_coverage():
    now = datetime.now(timezone.utc)
    obs = now - timedelta(hours=4)
    assessment = validate_observation_quality(obs, valid_pixel_pct=55.0, current_time_utc=now)
    assert assessment.freshness_status == "INCOMPLETE_COVERAGE"
    assert assessment.spatial_coverage_pct == 55.0
