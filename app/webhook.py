import logging
from app.device_manager import device_manager
from app.lifecycle import app_lifecycle

logger = logging.getLogger(__name__)

def parse_imou_alarm_details(payload: dict) -> tuple[str | None, str | None, str | None]:
    """
    Extracts alarm timestamp, event description, and picture URL from Imou alarm webhook payload.
    """
    if not isinstance(payload, dict):
        return None, None, None

    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}

    # Extract picUrl
    pic_url = (
        payload.get("picUrl") or
        payload.get("picurl") or
        payload.get("pic_url") or
        params.get("picUrl") or
        params.get("picurl") or
        params.get("pic_url")
    )

    # Extract event description
    event_desc = (
        payload.get("name") or
        payload.get("event") or
        payload.get("type") or
        payload.get("eventType") or
        payload.get("msgType") or
        params.get("name") or
        params.get("event") or
        params.get("type") or
        params.get("eventType") or
        params.get("msgType")
    )

    # Extract occurrence timestamp
    timestamp = (
        payload.get("time") or
        payload.get("timestamp") or
        params.get("time") or
        params.get("timestamp")
    )

    # Convert timestamp to string/float representation if numeric
    if timestamp is not None:
        timestamp = str(timestamp)

    return timestamp, event_desc, pic_url

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

def process_imou_webhook_payload(payload: dict) -> dict:
    """
    Direct Python function to process raw webhook payloads and trigger device manager logic.
    Refactored from the Flask route to allow programmatic execution and unit testing without Flask.
    """
    if not app_lifecycle.is_running:
        return {"error": "Service is shutting down"}

    # Intercept human detection alarm events
    alarm_time, alarm_desc, pic_url = parse_imou_alarm_details(payload)
    if alarm_desc and ("human" in str(alarm_desc).lower() or "people" in str(alarm_desc).lower() or "person" in str(alarm_desc).lower()):
        if pic_url:
            from app.telegram_service import send_telegram_photo
            caption = "⚠️ *Security Alert: Human Detected at Home!*"
            send_telegram_photo(pic_url, caption)
            logger.info("Processed human detection alarm webhook event. Telegram photo alert sent. Time: %s, Desc: %s", alarm_time, alarm_desc)
            return {
                "message": "Human detection alarm processed successfully",
                "triggered": True,
                "timestamp": alarm_time,
                "event": alarm_desc,
                "pic_url": pic_url
            }

    device_id, status = parse_imou_payload(payload)

    if not device_id:
        logger.error("Could not parse Device ID from payload: %s", payload)
        return {"error": "Missing device identifier (deviceId, deviceSerial, sn, etc.)"}

    if not status:
        logger.error("Could not parse Status/Event from payload: %s", payload)
        return {"error": "Missing status or event type in payload"}

    result = device_manager.handle_device_event(device_id, status)
    return {
        "message": "Webhook processed successfully",
        "result": result
    }
