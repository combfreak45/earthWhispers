"""
EarthWhisper Vertex AI Model Deployment Script
Uploads model artifact to Cloud Storage, registers the model in Vertex AI Model Registry,
and deploys the model to the deployed Vertex AI Endpoint.
"""

import os
import argparse
import logging
from google.cloud import storage
from google.cloud import aiplatform

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("earthwhisper-deployer")

# Official Google pre-built prediction container for XGBoost (XGBoost 2.1 LTS)
PREBUILT_XGBOOST_IMAGE = "us-docker.pkg.dev/vertex-ai/prediction/xgboost-cpu.2-1:latest"


def upload_artifact_to_gcs(project_id: str, local_path: str, bucket_name: str, gcs_dest_folder: str = "xgboost/v1"):
    client = storage.Client(project=project_id)
    bucket = client.bucket(bucket_name)
    blob_name = f"{gcs_dest_folder}/model.bst"
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(local_path)
    gcs_uri = f"gs://{bucket_name}/{gcs_dest_folder}/"
    logger.info(f"Model artifact uploaded to {gcs_uri}")
    return gcs_uri


def deploy_model_to_vertex(
    project_id: str,
    region: str,
    bucket_name: str,
    endpoint_display_name: str = "EarthWhisper XGBoost Flood Risk Endpoint"
):
    aiplatform.init(project=project_id, location=region)

    local_model_path = os.path.join(os.path.dirname(__file__), "artifacts", "model.bst")
    if not os.path.exists(local_model_path):
        raise FileNotFoundError(f"Missing {local_model_path}. Run train_xgboost.py first.")

    # 1. Upload model to Cloud Storage
    gcs_model_dir = upload_artifact_to_gcs(project_id, local_model_path, bucket_name)

    # 2. Register in Model Registry
    logger.info("Registering model in Vertex AI Model Registry...")
    model = aiplatform.Model.upload(
        display_name="earthwhisper-xgboost",
        artifact_uri=gcs_model_dir,
        serving_container_image_uri=PREBUILT_XGBOOST_IMAGE,
        description="EarthWhisper 3-class Flood Susceptibility & Risk XGBoost model.",
        labels={"project": "earthwhisper", "framework": "xgboost"}
    )
    logger.info(f"Model successfully registered! Resource Name: {model.resource_name}")

    # 3. Locate Vertex AI Endpoint
    logger.info(f"Locating Vertex AI Endpoint with display name: {endpoint_display_name}...")
    endpoints = aiplatform.Endpoint.list(
        filter=f'display_name="{endpoint_display_name}"',
        order_by="create_time desc"
    )

    if not endpoints:
        logger.warning(f"Endpoint '{endpoint_display_name}' not found. Creating a new one...")
        endpoint = aiplatform.Endpoint.create(display_name=endpoint_display_name)
    else:
        endpoint = endpoints[0]

    logger.info(f"Deploying model to Endpoint {endpoint.resource_name}...")
    deployed_model = model.deploy(
        endpoint=endpoint,
        deployed_model_display_name="earthwhisper-xgboost-v1",
        machine_type="n1-standard-2",
        min_replica_count=1,
        max_replica_count=2,
        traffic_percentage=100
    )

    logger.info(f"Deployment complete! Model is serving at Endpoint ID: {endpoint.name}")
    return endpoint


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project_id", required=True, help="GCP Project ID")
    parser.add_argument("--region", default="us-central1", help="GCP Region")
    parser.add_argument("--bucket_name", default="", help="Models Cloud Storage Bucket")
    args = parser.parse_args()

    bucket = args.bucket_name if args.bucket_name else f"{args.project_id}-models"
    deploy_model_to_vertex(args.project_id, args.region, bucket)
