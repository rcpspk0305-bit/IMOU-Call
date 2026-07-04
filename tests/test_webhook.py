import pytest
from app import create_app

@pytest.fixture
def client():
    app = create_app(start_poller=False)
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client

def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json["status"] == "ok"

def test_imou_webhook_non_json(client):
    response = client.post("/imou-webhook", data="not json")
    assert response.status_code == 400

def test_imou_webhook_missing_device_id(client):
    response = client.post("/imou-webhook", json={"status": "offline"})
    assert response.status_code == 422
    assert "Missing device identifier" in response.json["error"]

def test_imou_webhook_standard_imou_payload(client):
    payload = {
        "header": {"time": 123456},
        "params": {
            "deviceId": "CAM_IMOU_999",
            "status": "offline"
        }
    }
    response = client.post("/imou-webhook", json=payload)
    assert response.status_code == 200
    assert response.json["message"] == "Webhook processed successfully"
    assert response.json["result"]["device_id"] == "CAM_IMOU_999"
    assert response.json["result"]["status"] == "offline"

def test_imou_webhook_alternative_payload_format(client):
    payload = {
        "deviceSerial": "SN_98765",
        "eventType": "deviceOffline"
    }
    response = client.post("/imou-webhook", json=payload)
    assert response.status_code == 200
    assert response.json["result"]["device_id"] == "SN_98765"
