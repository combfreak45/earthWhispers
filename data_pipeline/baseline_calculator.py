"""
EarthWhisper Baseline Calculator
Provides 100% deterministic mathematical calculations for rolling rainfall
windows, Day-of-Year (DOY) baseline climatology deviations, and Z-scores.
Zero LLM or heuristic calculations are used here.
"""

from typing import Dict, Any, Optional
import math


def calculate_anomaly_pct(current_val: float, baseline_mean: float, epsilon: float = 1.0) -> float:
    """
    Computes percentage anomaly against historical mean.
    Formula: ((current - baseline_mean) / (baseline_mean + epsilon)) * 100
    """
    if baseline_mean < 0:
        return 0.0
    return ((current_val - baseline_mean) / (baseline_mean + epsilon)) * 100.0


def calculate_zscore(current_val: float, baseline_mean: float, baseline_std: float, epsilon: float = 0.1) -> float:
    """
    Computes standard score (Z-score) deviation from historical baseline distribution.
    Formula: (current - baseline_mean) / (baseline_std + epsilon)
    """
    effective_std = baseline_std if baseline_std > 0 else epsilon
    return (current_val - baseline_mean) / (effective_std + epsilon)


def compute_derived_features(
    raw_measurements: Dict[str, float],
    baseline_stats: Dict[str, float]
) -> Dict[str, Any]:
    """
    Takes deterministic raw sensor measurements and historical climatology baseline,
    and calculates all anomaly and deviation features.
    
    raw_measurements expected keys:
      - rain_1h_mm, rain_3h_mm, rain_6h_mm, rain_24h_mm, rain_72h_mm, rain_7d_mm
      - rain_peak_1h_mm, soil_water_layer1, elevation_mean_m, slope_mean_deg
      
    baseline_stats expected keys:
      - mean_rain_24h_mm, std_rain_24h_mm, mean_rain_72h_mm, std_rain_72h_mm
    """
    rain_24h = float(raw_measurements.get("rain_24h_mm", 0.0))
    rain_72h = float(raw_measurements.get("rain_72h_mm", 0.0))
    
    mean_24h = float(baseline_stats.get("mean_rain_24h_mm", 15.0))
    std_24h = float(baseline_stats.get("std_rain_24h_mm", 10.0))
    mean_72h = float(baseline_stats.get("mean_rain_72h_mm", 45.0))
    std_72h = float(baseline_stats.get("std_rain_72h_mm", 25.0))
    
    anomaly_24h = calculate_anomaly_pct(rain_24h, mean_24h)
    zscore_72h = calculate_zscore(rain_72h, mean_72h, std_72h)
    
    return {
        "rain_24h_anomaly_pct": round(anomaly_24h, 2),
        "rain_72h_zscore": round(zscore_72h, 2)
    }
