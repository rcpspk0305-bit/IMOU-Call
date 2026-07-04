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
