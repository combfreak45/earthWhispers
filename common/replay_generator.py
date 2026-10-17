"""
EarthWhisper Historical Replay & Mock Fixture Generator
Provides isolated, realistic historical flood and baseline scenarios for
hackathon demonstrations, reproducible testing, and validation.
STRICT ISOLATION: These fixtures are strictly gated to --mode=mock and never
pollute live production tables or executions.
"""

from datetime import datetime, timezone
from typing import Dict, Any


def get_mock_scenario(scenario_id: str = "2022_ASSAM_CATASTROPHIC") -> Dict[str, Any]:
    """
    Returns verified historical replay data packages.
    Supported scenarios:
      - '2022_ASSAM_CATASTROPHIC': June 2022 extreme rainfall (>500mm 72h, Silchar & Brahmaputra valley)
      - '2017_ASSAM_BENCHMARK': July 2017 historic flood from Global Flood DB
      - 'DRY_SEASON_NOMINAL': January typical dry baseline (Low Risk 0)
      - 'STALE_DATA_DEGRADED': Sensor latency > 50 hours (Freshness failure test)
    """
    now = datetime.now(timezone.utc)
    
    if scenario_id == "2022_ASSAM_CATASTROPHIC":
        return {
            "catchment_id": "brahmaputra_lower_assam",
            "scenario_name": "June 2022 Assam Extreme Monsoon (Silchar / Lower Basin)",
            "observation_timestamp": now,
            "rain_1h_mm": 42.5,
            "rain_3h_mm": 98.0,
            "rain_6h_mm": 172.5,
            "rain_24h_mm": 285.0,
            "rain_72h_mm": 515.0,
            "rain_7d_mm": 740.0,
            "rain_peak_1h_mm": 55.0,
            "rain_24h_anomaly_pct": 380.0, # 380% above DOY mean
            "rain_72h_zscore": 3.85,        # 3.85 standard deviations
            "soil_water_layer1": 0.495,     # Fully saturated soil
            "elevation_mean_m": 125.0,
            "slope_mean_deg": 1.8,
            "data_freshness_hrs": 4.5,
            "spatial_coverage_pct": 96.0,
            "freshness_status": "FRESH_NOMINAL",
            "feature_version": "v1.0-replay"
        }

    elif scenario_id == "2024_ASSAM_BRAHMAPUTRA_SURGE":
        return {
            "catchment_id": "brahmaputra_lower_assam",
            "scenario_name": "July 2024 Brahmaputra Monsoon Surge (2.4M Displaced)",
            "observation_timestamp": now,
            "rain_1h_mm": 38.0,
            "rain_3h_mm": 86.5,
            "rain_6h_mm": 155.0,
            "rain_24h_mm": 245.0,
            "rain_72h_mm": 465.0,
            "rain_7d_mm": 680.0,
            "rain_peak_1h_mm": 48.0,
            "rain_24h_anomaly_pct": 320.0,
            "rain_72h_zscore": 3.45,
            "soil_water_layer1": 0.485,
            "elevation_mean_m": 125.0,
            "slope_mean_deg": 1.8,
            "data_freshness_hrs": 3.0,
            "spatial_coverage_pct": 97.5,
            "freshness_status": "FRESH_NOMINAL",
            "feature_version": "v1.0-replay"
        }
        
    elif scenario_id == "2017_ASSAM_BENCHMARK":
        return {
            "catchment_id": "brahmaputra_lower_assam",
            "scenario_name": "July 2017 Assam Flood (Global Flood DB Benchmark)",
            "observation_timestamp": now,
            "rain_1h_mm": 28.0,
            "rain_3h_mm": 64.5,
            "rain_6h_mm": 115.0,
            "rain_24h_mm": 195.0,
            "rain_72h_mm": 380.0,
            "rain_7d_mm": 520.0,
            "rain_peak_1h_mm": 35.0,
            "rain_24h_anomaly_pct": 210.0,
            "rain_72h_zscore": 2.95,
            "soil_water_layer1": 0.460,
            "elevation_mean_m": 125.0,
            "slope_mean_deg": 1.8,
            "data_freshness_hrs": 6.0,
            "spatial_coverage_pct": 98.0,
            "freshness_status": "FRESH_NOMINAL",
            "feature_version": "v1.0-replay"
        }
        
    elif scenario_id == "DRY_SEASON_NOMINAL":
        return {
            "catchment_id": "brahmaputra_lower_assam",
            "scenario_name": "Assam Winter Dry Season Baseline",
            "observation_timestamp": now,
            "rain_1h_mm": 0.0,
            "rain_3h_mm": 0.0,
            "rain_6h_mm": 0.0,
            "rain_24h_mm": 0.5,
            "rain_72h_mm": 1.2,
            "rain_7d_mm": 2.0,
            "rain_peak_1h_mm": 0.2,
            "rain_24h_anomaly_pct": -60.0,
            "rain_72h_zscore": -0.85,
            "soil_water_layer1": 0.210,
            "elevation_mean_m": 125.0,
            "slope_mean_deg": 1.8,
            "data_freshness_hrs": 8.0,
            "spatial_coverage_pct": 99.5,
            "freshness_status": "FRESH_NOMINAL",
            "feature_version": "v1.0-replay"
        }
        
    elif scenario_id == "STALE_DATA_DEGRADED":
        return {
            "catchment_id": "brahmaputra_lower_assam",
            "scenario_name": "Sensor Dropout / Degraded Latency Test",
            "observation_timestamp": now,
            "rain_1h_mm": 15.0,
            "rain_3h_mm": 32.0,
            "rain_6h_mm": 45.0,
            "rain_24h_mm": 80.0,
            "rain_72h_mm": 160.0,
            "rain_7d_mm": 220.0,
            "rain_peak_1h_mm": 20.0,
            "rain_24h_anomaly_pct": 80.0,
            "rain_72h_zscore": 1.40,
            "soil_water_layer1": 0.380,
            "elevation_mean_m": 125.0,
            "slope_mean_deg": 1.8,
            "data_freshness_hrs": 54.0, # > 48h Latency!
            "spatial_coverage_pct": 62.0, # < 70% Coverage!
            "freshness_status": "STALE_CRITICAL",
            "feature_version": "v1.0-replay"
        }
    else:
        raise ValueError(f"Unknown mock scenario ID: {scenario_id}")
