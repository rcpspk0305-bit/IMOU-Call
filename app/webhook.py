import logging
from flask import Blueprint, request, jsonify
from app.device_manager import device_manager
from app.lifecycle import app_lifecycle

logger = logging.getLogger(__name__)

webhook_bp = Blueprint("webhook", __name__)

def parse_imou_payload(payload: dict) -> tuple[str | None, str | None]:
    """
    Parses various Imou Cloud and IoT webhook payload formats to extract Device ID and Status/Event.
    """
    if not isinstance(payload, dict):
        return None, None

    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}

    device_id = (
        params.get("deviceId") or
        params.get("deviceSerial") or
        params.get("sn") or
        payload.get("deviceId") or
        payload.get("deviceSerial") or
        payload.get("sn") or
        payload.get("uuid") or
        payload.get("id")
    )

    status = (
        params.get("status") or
        params.get("eventType") or
        payload.get("status") or
        payload.get("eventType") or
        payload.get("event") or
        payload.get("type")
    )

    if device_id:
        device_id = str(device_id).strip()
    if status:
        status = str(status).strip()

    return device_id, status

@webhook_bp.route("/imou-webhook", methods=["POST"])
def imou_webhook():
    """
    POST Endpoint for receiving Imou camera status webhooks.
    """
    if not app_lifecycle.is_running:
        return jsonify({"error": "Service is shutting down"}), 503

    if not request.is_json:
        logger.warning("Received non-JSON request to /imou-webhook")
        return jsonify({"error": "Content-Type must be application/json"}), 400

    payload = request.get_json()
    logger.info("Received /imou-webhook payload: %s", payload)

    device_id, status = parse_imou_payload(payload)

    if not device_id:
        logger.error("Could not parse Device ID from payload: %s", payload)
        return jsonify({"error": "Missing device identifier (deviceId, deviceSerial, sn, etc.)"}), 422

    if not status:
        logger.error("Could not parse Status/Event from payload: %s", payload)
        return jsonify({"error": "Missing status or event type in payload"}), 422

    result = device_manager.handle_device_event(device_id, status)

    return jsonify({
        "message": "Webhook processed successfully",
        "result": result
    }), 200

@webhook_bp.route("/stop", methods=["POST"])
def stop_application_route():
    """
    Dedicated POST /stop route on our web app.
    When pinged, toggles the lifecycle flag to False, safely terminates monitoring loops,
    closes open sessions/timers, and gracefully calls sys.exit(0).
    """
    logger.warning("Received POST /stop HTTP request.")
    result = app_lifecycle.initiate_stop()
    return jsonify(result), 200
