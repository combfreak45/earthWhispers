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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

session_service = InMemorySessionService()
runner = Runner(
    agent=root_agent,
    app_name="earthwhisper",
    session_service=session_service,
    auto_create_session=True,
)

APP_NAME = "earthwhisper"
USER_ID = "system"


def _run_agent(message: str, area_id: str) -> str:
    """Run the agent — session is auto-created by the runner."""
    session_id = f"{area_id}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"

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
            final_response = event_chunk.content.parts[0].text
            break

    return final_response


@app.route("/", methods=["POST"])
def pubsub_handler():
    """Receives Pub/Sub push message from EventArc and triggers the agent."""
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

    area_id = event.get("area_id")
    event_id = event.get("event_id")
    if not area_id or not event_id:
        return jsonify({"error": "Missing area_id or event_id"}), 400

    logger.info(f"Received signal event: event_id={event_id}, area_id={area_id}")
    message = (
        f"A flood signal has been detected. "
        f"Please assess flood risk for area_id='{area_id}' using event_id='{event_id}'."
    )
    response = _run_agent(message, area_id)
    return jsonify({"status": "ok", "response": response}), 200


@app.route("/run", methods=["POST"])
def chat_handler():
    """Direct chat endpoint for dashboard agent chat page."""
    body = request.get_json(silent=True)
    if not body or "message" not in body:
        return jsonify({"error": "Missing 'message' in request body"}), 400

    message = body["message"]
    area_id = body.get("area_id", "catchment_brahmaputra_assam")

    logger.info(f"Chat request: area_id={area_id}, message={message[:60]}")
    response = _run_agent(message, area_id)
    return jsonify({"status": "ok", "response": response}), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
