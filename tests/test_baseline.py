"""
Unit tests for deterministic baseline and anomaly math.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data_pipeline")))

from baseline_calculator import calculate_anomaly_pct, calculate_zscore, compute_derived_features


def test_calculate_anomaly_pct():
    # Current = 50, Baseline = 25 -> ((50 - 25) / (25 + 1)) * 100 = 25 / 26 * 100 = ~96.15%
    anomaly = calculate_anomaly_pct(50.0, 25.0)
    assert round(anomaly, 1) == 96.2

    # Current = 25, Baseline = 25 -> ((25 - 25) / 26) * 100 = 0%
    anomaly_zero = calculate_anomaly_pct(25.0, 25.0)
    assert anomaly_zero == 0.0

    # Negative baseline edge case
    assert calculate_anomaly_pct(10.0, -5.0) == 0.0


def test_calculate_zscore():
    # Current = 70, Mean = 50, Std = 10 -> (70 - 50) / (10 + 0.1) = 20 / 10.1 = ~1.98
    z = calculate_zscore(70.0, 50.0, 10.0)
    assert 1.95 <= z <= 2.00

    # Current = 50, Mean = 50 -> 0.0
    z_mean = calculate_zscore(50.0, 50.0, 10.0)
    assert z_mean == 0.0


def test_compute_derived_features():
    raw = {"rain_24h_mm": 100.0, "rain_72h_mm": 250.0}
    baseline = {
        "mean_rain_24h_mm": 20.0,
        "std_rain_24h_mm": 10.0,
        "mean_rain_72h_mm": 60.0,
        "std_rain_72h_mm": 30.0
    }
    derived = compute_derived_features(raw, baseline)
    assert "rain_24h_anomaly_pct" in derived
    assert "rain_72h_zscore" in derived
    assert derived["rain_72h_zscore"] > 5.0
