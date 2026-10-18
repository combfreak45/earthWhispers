"""
Deploy EarthWhisper Flood-Risk Intelligence Agent to Agent Runtime (Reasoning Engine).

Agent Runtime provides fully managed runtime hosting for Google ADK and Python agents,
with built-in scaling, authentication, and integration with Vertex AI Model Garden & Gemini.
"""

import os
import sys
import argparse
import logging
from typing import Dict, Any, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("earthwhisper-agent-engine-deploy")


class EarthWhisperReasoningEngine:
    """
    Managed Agent Runtime wrapper for EarthWhisper.
    Executes the deterministic flood assessment pipeline backed by Vertex AI XGBoost and BigQuery.
    """

    def __init__(self, project_id: str = "your-google-cloud-project-id", location: str = "us-central1"):
        self.project_id = project_id
        self.location = location

    def set_up(self):
        """Initializes runtime environment on the remote Vertex AI container."""
        import os
        os.environ["PROJECT_ID"] = self.project_id
        os.environ["GOOGLE_CLOUD_PROJECT"] = self.project_id
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
        os.environ["VERTEX_ENDPOINT_ID"] = "earthwhisper-flood-risk-endpoint"
        os.environ["BIGQUERY_DATASET_LIVE"] = "earthwhisper_live"

    def query(
        self,
        message: str = "Assess flood risk",
        catchment_id: str = "brahmaputra_lower_assam",
        mode: str = "live",
        **kwargs
    ) -> Dict[str, Any]:
        """
        Executes the assessment pipeline or answers conversational inquiries.
        """
        try:
            from pipeline import run_assessment
        except ImportError:
            from agent.pipeline import run_assessment

        return run_assessment(catchment_id=catchment_id, mode=mode, **kwargs)


def deploy_agent_engine(
    project_id: str,
    location: str = "us-central1",
    staging_bucket: Optional[str] = None,
    display_name: str = "earthwhisper-agent-engine",
):
    """
    Packages and deploys the EarthWhisper agent to Agent Runtime (Reasoning Engine).
    """
    import vertexai
    from vertexai.preview import reasoning_engines

    if not staging_bucket:
        staging_bucket = f"gs://{project_id}-models"

    logger.info("Initializing Vertex AI SDK for project=%s, location=%s, staging_bucket=%s", project_id, location, staging_bucket)
    vertexai.init(project=project_id, location=location, staging_bucket=staging_bucket)

    requirements = [
        "google-cloud-aiplatform>=1.54.0",
        "google-cloud-bigquery>=3.25.0",
        "google-genai>=0.1.1",
        "xgboost>=2.0.0",
        "pydantic>=2.7.0",
        "requests>=2.32.0",
    ]

    logger.info("Submitting Reasoning Engine creation to Agent Runtime...")
    engine_instance = EarthWhisperReasoningEngine(project_id=project_id, location=location)

    remote_engine = reasoning_engines.ReasoningEngine.create(
        engine_instance,
        requirements=requirements,
        display_name=display_name,
        description="EarthWhisper Autonomous Flood Risk Intelligence Agent (Google Cloud AI Builder Cup 2026)",
    )

    logger.info("SUCCESS: Agent deployed to Agent Runtime!")
    logger.info("Resource Name: %s", remote_engine.resource_name)
    logger.info("Display Name: %s", remote_engine.display_name)
    return remote_engine


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deploy EarthWhisper to Agent Runtime")
    parser.add_argument("--project_id", default=os.getenv("PROJECT_ID", "your-google-cloud-project-id"), help="GCP Project ID")
    parser.add_argument("--location", default=os.getenv("REGION", "us-central1"), help="GCP Region")
    parser.add_argument("--staging_bucket", default=None, help="GCS staging bucket (e.g. gs://PROJECT_ID-models)")
    parser.add_argument("--display_name", default="earthwhisper-agent-engine", help="Agent Engine display name")
    args = parser.parse_args()

    deploy_agent_engine(
        project_id=args.project_id,
        location=args.location,
        staging_bucket=args.staging_bucket,
        display_name=args.display_name,
    )
