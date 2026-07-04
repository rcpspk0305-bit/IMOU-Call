from unittest.mock import patch, MagicMock
from app.imou_service import ImouService

class MockImouConfig:
    IMOU_APP_ID = "test_app_id"
    IMOU_APP_SECRET = "test_app_secret"
    IMOU_API_BASE_URL = "https://openapi.easy4ip.com/openapi"

@patch("requests.post")
def test_get_access_token_success(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "result": {
            "code": "0",
            "msg": "success",
            "data": {
                "accessToken": "mock_token_abc123",
                "expireTime": 3600
            }
        }
    }
    mock_post.return_value = mock_response

    service = ImouService(config=MockImouConfig)
    token, err = service.get_access_token()

    assert err is None
    assert token == "mock_token_abc123"
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert "https://openapi.easy4ip.com/openapi/accessToken" in args[0]
    assert kwargs["json"]["system"]["appId"] == "test_app_id"

@patch("requests.post")
def test_get_device_online_status_online(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "result": {
            "code": "0",
            "data": {
                "onLine": "1"
            }
        }
    }
    mock_post.return_value = mock_response

    service = ImouService(config=MockImouConfig)
    is_online, err = service.get_device_online_status("CAM_123", access_token="valid_token")

    assert err is None
    assert is_online is True

@patch("requests.post")
def test_get_device_online_status_offline(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "result": {
            "code": "0",
            "data": {
                "onLine": "0"
            }
        }
    }
    mock_post.return_value = mock_response

    service = ImouService(config=MockImouConfig)
    is_online, err = service.get_device_online_status("CAM_123", access_token="valid_token")

    assert err is None
    assert is_online is False
