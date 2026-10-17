"""
EarthWhisper BigQuery Seeder Dispatcher
Enforces strict segregation between live production seeding and mock test fixtures.
STRICT ISOLATION RULE (AGENTS.md):
- NEVER inject mock fixtures into `earthwhisper_live`.
- In --mode=live, calls genuine Earth Engine data pipeline seeders using the BigQuery MCP Toolset.
- In --mode=mock, delegates to `seed_mock_fixtures.py` targeting `earthwhisper_mock` only.
"""

import os
import sys
import argparse
import logging
import subprocess

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("earthwhisper-seeder-dispatcher")


def main():
    parser = argparse.ArgumentParser(description="EarthWhisper BigQuery Seeder Dispatcher")
    parser.add_argument("--project_id", default=os.getenv("PROJECT_ID", "earthwhisper-dev"), help="GCP Project ID")
    parser.add_argument("--mode", required=True, choices=["live", "mock"], help="Execution mode: 'live' or 'mock'")
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    if args.mode == "mock":
        logger.info("Executing MOCK fixture seeder targeting 'earthwhisper_mock'...")
        mock_script = os.path.join(base_dir, "scripts", "seed_mock_fixtures.py")
        subprocess.run([sys.executable, mock_script, "--project_id", args.project_id], check=True)
        logger.info("Mock fixtures successfully seeded into earthwhisper_mock.")

    elif args.mode == "live":
        logger.info("Executing LIVE Earth Engine remote sensing pipelines targeting 'earthwhisper_live' via BigQuery MCP...")
        
        # 1. Seed Real NASA GPM IMERG V07 Climatology Baseline
        climatology_script = os.path.join(base_dir, "data_pipeline", "seed_real_climatology_baseline.py")
        subprocess.run([sys.executable, climatology_script, "--project_id", args.project_id, "--dataset_id", "earthwhisper_live"], check=True)

        # 2. Seed Real ImpactGraph Assets with WorldPop population density
        impact_script = os.path.join(base_dir, "data_pipeline", "seed_real_impact_graph.py")
        subprocess.run([sys.executable, impact_script, "--project_id", args.project_id, "--dataset_id", "earthwhisper_live"], check=True)

        logger.info("Live production tables successfully seeded into earthwhisper_live via BigQuery MCP!")


if __name__ == "__main__":
    main()
