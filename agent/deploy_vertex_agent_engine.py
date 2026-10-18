"""
Deploy EarthWhisper Flood-Risk Intelligence Agent to Agent Runtime (Reasoning Engine).

Agent Runtime provides fully managed runtime hosting for Google ADK and Python agents,
with built-in scaling, authentication, and integration with Vertex AI Model Garden & Gemini.

The engine wraps the deterministic pipeline (agent/pipeline.py::run_assessment). Local code
(agent/ + common/) is shipped via extra_packages, and sys.path is set up at runtime so
pipeline.py's flat imports (telemetry/tools/policy) and common.* both resolve remotely.
"""

import os
import argparse
import logging
from typing import Dict, Any, Optional

from google.api_core.exceptions import GoogleAPIError

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("earthwhisper-agent-engine-deploy")


class EarthWhisperReasoningEngine:
    """
    Managed Agent Runtime wrapper for EarthWhisper.
    Executes the deterministic flood assessment pipeline backed by Vertex AI XGBoost and BigQuery.
    """

    def __init__(self, project_id: Optional[str] = None, location: str = "us-central1"):
        self.project_id = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT")
        if not self.project_id:
            raise ValueError("project_id must be provided or set via GOOGLE_CLOUD_PROJECT environment variable.")
        self.location = location

    @staticmethod
    def _ensure_paths():
        """Put the bundled code on sys.path. cwd holds agent/ and common/ (extra_packages);
        cwd/agent lets pipeline.py's flat imports (telemetry/tools/policy) resolve."""
        import os
        import sys
        cwd = os.getcwd()
        for p in (cwd, os.path.join(cwd, "agent")):
            if os.path.isdir(p) and p not in sys.path:
                sys.path.insert(0, p)

    def set_up(self):
        """Initializes runtime environment on the remote Vertex AI container."""
        os.environ["PROJECT_ID"] = self.project_id
        os.environ["GOOGLE_CLOUD_PROJECT"] = self.project_id
        os.environ["REGION"] = self.location
        os.environ["GOOGLE_CLOUD_LOCATION"] = self.location
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
        os.environ["VERTEX_ENDPOINT_ID"] = "earthwhisper-flood-risk-endpoint"
        os.environ["BIGQUERY_DATASET_LIVE"] = "earthwhisper_live"
        self._ensure_paths()

    def query(
        self,
        message: str = "Assess flood risk",
        catchment_id: str = "brahmaputra_lower_assam",
        mode: str = "live",
    ) -> Dict[str, Any]:
        """Executes the flood assessment pipeline and returns the structured result."""
        self._ensure_paths()
        try:
            from pipeline import run_assessment
        except ImportError:
            from agent.pipeline import run_assessment
        return run_assessment(catchment_id=catchment_id, mode=mode)


def deploy_agent_engine(
    project_id: str,
    location: str = "us-central1",
    staging_bucket: Optional[str] = None,
    display_name: str = "earthwhisper-agent-engine",
    extra_packages: Optional[list] = None,
):
    """
    Packages and deploys the EarthWhisper agent to Agent Runtime (Reasoning Engine).
    """
    import vertexai
    from vertexai.preview import reasoning_engines

    # Run from the repo root so relative extra_packages resolve regardless of invocation CWD.
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    os.chdir(repo_root)

    if not staging_bucket:
        staging_bucket = f"gs://{project_id}-models"

    logger.info("Initializing Vertex AI SDK for project=%s, location=%s, staging_bucket=%s", project_id, location, staging_bucket)
    try:
        vertexai.init(project=project_id, location=location, staging_bucket=staging_bucket)
    except GoogleAPIError as e:
        logger.error(f"Vertex AI initialization failed: {e}")
        raise

    # Full dependency set the run_assessment import chain needs:
    #   pipeline -> telemetry (opentelemetry), tools.vertex_predictor (aiplatform),
    #   tools.bq_mcp_client -> common.mcp_bq_client (requests/google-auth + bigquery),
    #   tools.summarize_tool (google-genai), policy.alert_policy (pyyaml).
    requirements = [
        "google-cloud-aiplatform>=1.54.0",
        "google-cloud-bigquery>=3.25.0",
        "google-genai>=0.1.1",
        "google-auth>=2.29.0",
        "pyyaml>=6.0.2",
        "requests>=2.32.0",
        "pydantic>=2.7.0",
        "opentelemetry-api>=1.25.0",
        "opentelemetry-sdk>=1.25.0",
    ]

    # Ship BOTH agent/ and common/ so run_assessment and all its imports exist remotely.
    if extra_packages is None:
        extra_packages = ["./agent", "./common"]

    logger.info("Submitting Reasoning Engine creation to Agent Runtime (extra_packages=%s)...", extra_packages)
    engine_instance = EarthWhisperReasoningEngine(project_id=project_id, location=location)

    try:
        remote_engine = reasoning_engines.ReasoningEngine.create(
            engine_instance,
            requirements=requirements,
            extra_packages=extra_packages,
            display_name=display_name,
            description="EarthWhisper Autonomous Flood Risk Intelligence Agent (Google Cloud AI Builder Cup 2026)",
        )
        logger.info("SUCCESS: Agent deployed to Agent Runtime!")
        logger.info("Resource Name: %s", remote_engine.resource_name)
        logger.info("Display Name: %s", remote_engine.display_name)
        return remote_engine
    except GoogleAPIError as e:
        logger.error(f"Deployment failed due to a Google Cloud API error: {e}")
        raise
    except Exception as e:
        logger.error(f"An unexpected error occurred during deployment: {e}")
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deploy EarthWhisper to Agent Runtime")
    parser.add_argument("--project_id", required=True, help="GCP Project ID")
    parser.add_argument("--location", default=os.getenv("REGION", "us-central1"), help="GCP Region")
    parser.add_argument("--staging_bucket", default=None, help="GCS staging bucket (e.g. gs://PROJECT_ID-models)")
    parser.add_argument("--display_name", default="earthwhisper-agent-engine", help="Agent Engine display name")
    parser.add_argument("--extra_packages", nargs="*", default=["./agent", "./common"], help="Paths to local packages to upload")
    args = parser.parse_args()

    deploy_agent_engine(
        project_id=args.project_id,
        location=args.location,
        staging_bucket=args.staging_bucket,
        display_name=args.display_name,
        extra_packages=args.extra_packages,
    )
