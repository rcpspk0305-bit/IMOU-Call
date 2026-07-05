from unittest.mock import patch, MagicMock
import pytest
from app.webhook import parse_imou_payload, process_imou_webhook_payload
from app.lifecycle import app_lifecycle

def test_parse_imou_payload_valid():
    payload = {
        "header": {"time": 123456},
        "params": {
            "deviceId": "CAM_IMOU_999",
            "status": "offline"
        }
    }
    device_id, status = parse_imou_payload(payload)
    assert device_id == "CAM_IMOU_999"
    assert status == "offline"

def test_parse_imou_payload_alternative():
    payload = {
        "deviceSerial": "SN_98765",
        "eventType": "deviceOffline"
    }
    device_id, status = parse_imou_payload(payload)
    assert device_id == "SN_98765"
    assert status == "deviceOffline"

def test_parse_imou_payload_missing():
    payload = {"status": "offline"}
    device_id, status = parse_imou_payload(payload)
    assert device_id is None
    assert status == "offline"

@patch("app.webhook.device_manager.handle_device_event")
def test_process_imou_webhook_payload_success(mock_handle):
    mock_handle.return_value = {"device_id": "CAM_IMOU_999", "status": "offline", "action": "timer_scheduled"}
    payload = {
        "header": {"time": 123456},
        "params": {
            "deviceId": "CAM_IMOU_999",
            "status": "offline"
        }
    }
    res = process_imou_webhook_payload(payload)
    assert res["message"] == "Webhook processed successfully"
    assert res["result"]["device_id"] == "CAM_IMOU_999"
    assert res["result"]["status"] == "offline"
    mock_handle.assert_called_once_with("CAM_IMOU_999", "offline")

def test_process_imou_webhook_payload_missing_device():
    payload = {"status": "offline"}
    res = process_imou_webhook_payload(payload)
    assert "error" in res
    assert "Missing device identifier" in res["error"]

def test_process_imou_webhook_payload_service_stopping():
    app_lifecycle._lifecycle_flag.clear()
    try:
        res = process_imou_webhook_payload({"deviceId": "CAM_1", "status": "online"})
        assert "error" in res
        assert "shutting down" in res["error"].lower()
    finally:
        app_lifecycle._lifecycle_flag.set()

@patch("requests.get")
@patch("app.telegram_service.send_telegram_photo")
def test_process_imou_webhook_payload_human_detection(mock_send_photo, mock_get):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"fake webhook image bytes"
    mock_get.return_value = mock_response
    mock_send_photo.return_value = True
    
    payload = {
        "params": {
            "name": "human",
            "picUrl": "https://example.com/alarm.jpg",
            "time": 1720101234
        }
    }
    res = process_imou_webhook_payload(payload)
    assert res["message"] == "Human detection alarm processed successfully"
    assert res["triggered"] is True
    assert res["pic_url"] == "https://example.com/alarm.jpg"
    assert res["event"] == "human"
    
    # Verify requests.get was called to download the image
    mock_get.assert_called_once_with("https://example.com/alarm.jpg", timeout=15)
    
    # Verify send_telegram_photo was called with BytesIO stream and caption
    mock_send_photo.assert_called_once()
    args, kwargs = mock_send_photo.call_args
    assert hasattr(args[0], "read")
    assert getattr(args[0], "name") == "alarm_trigger.jpg"
    assert args[1] == "⚠️ *Security Alert: Human Detected at Home!*"
