"""
EarthWhisper Mock & Test Fixtures Seeder
Populates `earthwhisper_mock` dataset with synthetic test records and historical replay scenarios
for unit testing, dry-runs, and local offline development.
STRICT ISOLATION: Targets earthwhisper_mock only. NEVER touches earthwhisper_live.
"""

import os
import argparse
import logging
import numpy as np
from google.cloud import bigquery

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("earthwhisper-mock-seeder")


def seed_mock_baseline(client: bigquery.Client, dataset_id: str = "earthwhisper_mock"):
    table_id = f"{client.project}.{dataset_id}.catchment_climate_baseline"
    logger.info(f"Seeding synthetic test baseline into {table_id}...")

    rows = []
    for doy in range(1, 367):
        mean_24h = 20.0 + 10.0 * np.sin(doy / 365.0 * 2 * np.pi)
        rows.append({
            "catchment_id": "brahmaputra_lower_assam",
            "doy": doy,
            "mean_rain_24h_mm": round(float(max(1.0, mean_24h)), 2),
            "std_rain_24h_mm": 12.0,
            "mean_rain_72h_mm": round(float(max(3.0, mean_24h * 2.8)), 2),
            "std_rain_72h_mm": 30.0,
            "baseline_window_years": "synthetic-test-v1"
        })

    errors = client.insert_rows_json(table_id, rows)
    if errors:
        logger.error(f"Failed to seed mock baseline rows: {errors}")
    else:
        logger.info(f"Successfully inserted {len(rows)} mock baseline rows into {table_id}!")


def seed_mock_impact_graph(client: bigquery.Client, dataset_id: str = "earthwhisper_mock"):
    table_id = f"{client.project}.{dataset_id}.impact_graph_assets"
    logger.info(f"Seeding mock test assets into {table_id}...")

    assets = [
        {
            "asset_id": "MOCK-SET-01", "catchment_id": "brahmaputra_lower_assam", "district": "Dhubri",
            "name": "Mock Test Village A", "asset_type": "SETTLEMENT",
            "population": 15000, "latitude": 26.02, "longitude": 89.98, "vulnerability_index": 0.85
        },
        {
            "asset_id": "MOCK-HOS-01", "catchment_id": "brahmaputra_lower_assam", "district": "Dhubri",
            "name": "Mock Health Center", "asset_type": "HOSPITAL",
            "population": None, "latitude": 26.03, "longitude": 89.99, "vulnerability_index": 0.90
        }
    ]

    errors = client.insert_rows_json(table_id, assets)
    if errors:
        logger.error(f"Failed to seed mock impact assets: {errors}")
    else:
        logger.info(f"Successfully inserted {len(assets)} mock assets into {table_id}!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--project_id",
        default=os.getenv("PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or "your-google-cloud-project-id",
        help="GCP Project ID",
    )
    args = parser.parse_args()

    bq = bigquery.Client(project=args.project_id)
    # Strictly isolated to earthwhisper_mock
    seed_mock_baseline(bq, "earthwhisper_mock")
    seed_mock_impact_graph(bq, "earthwhisper_mock")
