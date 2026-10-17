"""
Cloud Run entry point for EarthWhisper ADK agent.
Receives Pub/Sub push messages via EventArc and runs the agent.
"""
import base64
import json
import logging
import os
from datetime import datetime, timezone

from flask import Flask, request, jsonify
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agent import root_agent
from pipeline import run_assessment

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

APP_NAME = "earthwhisper"
USER_ID = "system"

session_service = InMemorySessionService()

# Dynamically initialize Runner with cross-version google-adk compatibility
import inspect
runner_kwargs = {
    "agent": root_agent,
    "app_name": APP_NAME,
    "session_service": session_service,
}
try:
    sig = inspect.signature(Runner.__init__)
    if "auto_create_session" in sig.parameters:
        runner_kwargs["auto_create_session"] = True
except Exception:
    pass

try:
    runner = Runner(**runner_kwargs)
except TypeError:
    runner = Runner(
        agent=root_agent,
        app_name=APP_NAME,
        session_service=session_service,
    )


def _run_agent(message: str, area_id: str) -> str:
    """Run the agent — ensures session exists before running."""
    session_id = f"{area_id}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"

    # Explicitly ensure session exists for ADK versions without auto_create_session
    if not getattr(runner, "auto_create_session", False):
        try:
            import asyncio
            asyncio.run(
                session_service.create_session(
                    app_name=APP_NAME,
                    user_id=USER_ID,
                    session_id=session_id,
                )
            )
        except Exception as e:
            logger.debug(f"Pre-create session notice: {e}")

    final_response = None
    for event_chunk in runner.run(
        user_id=USER_ID,
        session_id=session_id,
        new_message=types.Content(
            role="user",
            parts=[types.Part(text=message)],
        ),
    ):
        if event_chunk.is_final_response():
            if event_chunk.content and event_chunk.content.parts:
                final_response = event_chunk.content.parts[0].text
                break

    return final_response or "Agent returned no response."


@app.route("/", methods=["POST"])
@app.route("/events", methods=["POST"])
def pubsub_handler():
    """Receives Pub/Sub push message from EventArc and triggers the agent.

    Served on both "/" and "/events" — the Pub/Sub push subscription targets /events.
    """
    envelope = request.get_json(silent=True)
    if not envelope or "message" not in envelope:
        return jsonify({"error": "Invalid message"}), 400

    pubsub_message = envelope["message"]
    try:
        data = base64.b64decode(pubsub_message["data"]).decode("utf-8")
        event = json.loads(data)
    except Exception as e:
        logger.error(f"Failed to decode message: {e}")
        return jsonify({"error": "Bad message payload"}), 400

    # Worker publishes "catchment_id"; older/manual signals may use "area_id".
    catchment_id = event.get("catchment_id") or event.get("area_id")
    event_id = event.get("event_id")
    if not catchment_id or not event_id:
        return jsonify({"error": "Missing catchment_id/area_id or event_id"}), 400

    logger.info(f"Received signal event: event_id={event_id}, catchment_id={catchment_id}")
    # Use the 14 features the worker already shipped in the signal (no BQ re-fetch);
    # falls back to a BigQuery fetch inside run_assessment if the payload lacks them.
    result = run_assessment(
        catchment_id=catchment_id,
        mode=event.get("mode", "live"),
        features=event.get("features"),
        observation_timestamp=event.get("observation_timestamp"),
        freshness_status=event.get("freshness_status"),
    )
    pred = result.get("prediction", {})
    return jsonify({
        "status": result.get("status"),
        "catchment_id": catchment_id,
        "event_id": event_id,
        "risk_label": pred.get("risk_label"),
        "risk_score": pred.get("risk_score"),
        "policy_decision": result.get("policy", {}).get("decision"),
        "summary": result.get("summary"),
        "error": result.get("error"),
        "audit": result.get("audit"),
    }), 200


@app.route("/run", methods=["POST"])
def chat_handler():
    """Direct chat endpoint for dashboard agent chat page."""
    body = request.get_json(silent=True)
    if not body or "message" not in body:
        return jsonify({"error": "Missing 'message' in request body"}), 400

    message = body["message"]
    area_id = body.get("area_id", "brahmaputra_lower_assam")

    logger.info(f"Chat request: area_id={area_id}, message={message[:60]}")
    response = _run_agent(message, area_id)
    return jsonify({"status": "ok", "response": response}), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
