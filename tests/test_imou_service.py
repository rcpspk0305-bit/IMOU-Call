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
    assert "https://openapi-sg.easy4ip.com/openapi/accessToken" in args[0]
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

@patch("requests.post")
def test_get_device_online_status_retry_on_invalid_token(mock_post):
    # Setup mock responses: first returns INVALID_TOKEN, second (token request) returns success token, third (retry) returns status online
    mock_resp_invalid = MagicMock()
    mock_resp_invalid.status_code = 200
    mock_resp_invalid.json.return_value = {
        "result": {
            "code": "INVALID_TOKEN",
            "msg": "invalid access token"
        }
    }

    mock_resp_token = MagicMock()
    mock_resp_token.status_code = 200
    mock_resp_token.json.return_value = {
        "result": {
            "code": "0",
            "data": {
                "accessToken": "fresh_new_token",
                "expireTime": 3600
            }
        }
    }

    mock_resp_online = MagicMock()
    mock_resp_online.status_code = 200
    mock_resp_online.json.return_value = {
        "result": {
            "code": "0",
            "data": {
                "onLine": "1"
            }
        }
    }

    mock_post.side_effect = [mock_resp_invalid, mock_resp_token, mock_resp_online]

    service = ImouService(config=MockImouConfig)
    # Put a token in cached token to ensure it gets cleared
    service._cached_token = "old_token"
    service._token_expires_at = 9999999999.0

    is_online, err = service.get_device_online_status("CAM_123")

    assert err is None
    assert is_online is True
    assert service._cached_token == "fresh_new_token"
    assert mock_post.call_count == 3

