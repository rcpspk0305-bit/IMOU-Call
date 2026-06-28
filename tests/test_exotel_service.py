from unittest.mock import patch, MagicMock
from app.exotel_service import trigger_exotel_call, reset_lockout, get_last_call_timestamp

class MockConfig:
    EXOTEL_SUBDOMAIN = "api.in.exotel.com"
    EXOTEL_SID = "TEST_SID_123"
    EXOTEL_KEY = "TEST_KEY_456"
    EXOTEL_TOKEN = "TEST_TOKEN_789"
    FROM_NUMBER = "+919876543210"
    CALLER_ID = "08012345678"
    APP_ID = "123456"
    EXOTEL_CALL_LOCKOUT_SECONDS = 1800
    TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
    TELEGRAM_ALLOWED_CHAT_ID = "YOUR_TELEGRAM_ALLOWED_CHAT_ID"

def setup_function():
    reset_lockout()

@patch("requests.post")
def test_trigger_exotel_call_success(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b'{"Call": {"Sid": "call_123"}}'
    mock_response.json.return_value = {"Call": {"Sid": "call_123"}}
    mock_post.return_value = mock_response

    res = trigger_exotel_call("CAM_LOCKOUT_001", config=MockConfig)

    assert res["success"] is True
    assert res["status_code"] == 200
    assert get_last_call_timestamp("CAM_LOCKOUT_001") > 0

@patch("requests.post")
def test_trigger_exotel_call_lockout_active(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b'{}'
    mock_post.return_value = mock_response

    # First call succeeds and sets timestamp
    res1 = trigger_exotel_call("CAM_LOCKOUT_002", config=MockConfig)
    assert res1["success"] is True

    # Immediate second call within 30 minutes must be suppressed by Agent Lockout
    res2 = trigger_exotel_call("CAM_LOCKOUT_002", config=MockConfig)
    assert res2["success"] is False
    assert res2["reason"] == "agent_lockout_active"
    assert res2["suppressed"] is True

    # Verify requests.post was called only once!
    mock_post.assert_called_once()
