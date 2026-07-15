from unittest.mock import MagicMock, patch
from app.imou_poller import ImouPoller
import pytest
from datetime import datetime, timezone

@pytest.fixture(autouse=True)
def mock_db_session_heartbeat():
    now_str = datetime.now(timezone.utc).isoformat()
    with patch("db_client.SupabaseDbClient.get_session_heartbeat", return_value=now_str):
        yield


def test_poller_device_online():
    mock_service = MagicMock()
    mock_service.get_access_token.return_value = ("mock_token", None)
    mock_service.get_device_online_status.return_value = (True, None)

    mock_call_handler = MagicMock()

    poller = ImouPoller(
        service=mock_service,
        call_handler=mock_call_handler,
        device_id="CAM_ONLINE_001"
    )

    res = poller.poll_once()

    assert res["status"] == "success"
    assert res["is_online"] is True
    mock_call_handler.assert_not_called()

def test_poller_device_offline_triggers_exotel_call():
    mock_service = MagicMock()
    mock_service.get_access_token.return_value = ("mock_token", None)
    mock_service.get_device_online_status.return_value = (False, None)

    mock_call_handler = MagicMock()
    mock_call_handler.return_value = {"success": True, "status_code": 200}

    poller = ImouPoller(
        service=mock_service,
        call_handler=mock_call_handler,
        device_id="CAM_OFFLINE_002"
    )

    res = poller.poll_once()

    assert res["status"] == "success"
    assert res["is_online"] is False
    assert res["call_triggered"] is True
    mock_call_handler.assert_called_once_with("CAM_OFFLINE_002")

@patch("app.aerator_analyzer.is_night_time", return_value=False)
@patch("app.imou_poller.ImouPoller.check_for_human_alarms", return_value=None)
def test_escalated_alerting_lifecycle(mock_check_alarms, mock_night_time):
    mock_service = MagicMock()
    mock_service.get_access_token.return_value = ("mock_token", None)
    
    # Control online status dynamically
    device_status = [False]  # Start offline
    def mock_get_status(*args, **kwargs):
        return (device_status[0], None)
    mock_service.get_device_online_status.side_effect = mock_get_status

    mock_call_handler = MagicMock()
    mock_call_handler.return_value = {"success": True}

    poller = ImouPoller(
        service=mock_service,
        call_handler=mock_call_handler,
        device_id="CAM_LIFECYCLE_TEST"
    )

    # 1. First offline detection (offline_alerts_sent is 0)
    res = poller.poll_once()
    assert res["status"] == "success"
    assert res["is_online"] is False
    assert res["call_triggered"] is True
    assert poller.offline_alerts_sent == 1
    assert poller.last_known_state == "OFFLINE"
    mock_call_handler.assert_called_once_with("CAM_LIFECYCLE_TEST")
    mock_call_handler.reset_mock()

    # 2. Second offline detection before 150 seconds (e.g. immediately)
    res = poller.poll_once()
    assert res["status"] == "success"
    assert res["is_online"] is False
    assert res["call_triggered"] is False
    assert poller.offline_alerts_sent == 1
    mock_call_handler.assert_not_called()

    # 3. Third offline detection after 150 seconds (we mock the timestamp)
    poller.last_offline_alert_time -= 160  # simulate time passing
    res = poller.poll_once()
    assert res["status"] == "success"
    assert res["is_online"] is False
    assert res["call_triggered"] is True
    assert poller.offline_alerts_sent == 2
    mock_call_handler.assert_called_once_with("CAM_LIFECYCLE_TEST")
    mock_call_handler.reset_mock()

    # 4. Subsequent offline detection does not fire alerts
    res = poller.poll_once()
    assert res["status"] == "success"
    assert res["is_online"] is False
    assert res["call_triggered"] is False
    assert poller.offline_alerts_sent == 2
    mock_call_handler.assert_not_called()

    # 5. Transition to online (should execute exactly 1 recovery alert and reset)
    device_status[0] = True  # now online
    res = poller.poll_once()
    assert res["status"] == "success"
    assert res["is_online"] is True
    assert res.get("recovery_triggered") is True
    assert poller.last_known_state == "ONLINE"
    assert poller.offline_alerts_sent == 0
    assert poller.last_offline_alert_time == 0.0

@patch("requests.post")
@patch("requests.get")
def test_check_human_alarms_dispatch(mock_get, mock_post):
    from unittest.mock import patch
    mock_service = MagicMock()
    mock_service.get_access_token.return_value = ("mock_token", None)
    mock_service._generate_signature.return_value = "mock_sig"
    
    # Mock alarm API response
    mock_alarm_response = MagicMock()
    mock_alarm_response.status_code = 200
    mock_alarm_response.json.return_value = {
        "result": {
            "data": {
                "alarms": [
                    {
                        "alarmId": "msg_111",
                        "name": "human detection event",
                        "picUrl": "https://example.com/alarm1.jpg",
                        "time": "2026-07-05 12:00:00"
                    },
                    {
                        "alarmId": "msg_222",
                        "name": "normal motion",
                        "picUrl": "https://example.com/alarm2.jpg",
                        "time": "2026-07-05 12:05:00"
                    }
                ]
            }
        }
    }
    
    # Mock Telegram response
    mock_telegram_response = MagicMock()
    mock_telegram_response.status_code = 200
    
    # Mock requests post side effects
    mock_post.side_effect = [mock_alarm_response, mock_telegram_response]
    
    # Mock requests get for image download
    mock_image_response = MagicMock()
    mock_image_response.status_code = 200
    mock_image_response.content = b"fake image bytes"
    mock_get.return_value = mock_image_response

    poller = ImouPoller(
        service=mock_service,
        device_id="CAM_ALARM_TEST"
    )
    
    # Run human alarms check
    dispatched = poller.check_human_alarms()
    
    # Verify the human alarm was dispatched and tracking state updated
    assert dispatched == "msg_111"
    assert poller.last_processed_alarm_id == "msg_111"
    
    # Verify image download was requested
    mock_get.assert_called_once_with("https://example.com/alarm1.jpg", timeout=15)
    
    # Verify both requests.post were called (one for getAlarmMessageList, one for sendPhoto)
    assert mock_post.call_count == 2

def test_is_session_active_valid(mock_db_session_heartbeat):
    poller = ImouPoller(device_id="CAM_TEST")
    assert poller.is_session_active() is True

def test_is_session_active_invalid():
    from datetime import datetime, timezone, timedelta
    old_time = (datetime.now(timezone.utc) - timedelta(seconds=45)).isoformat()
    with patch("db_client.SupabaseDbClient.get_session_heartbeat", return_value=old_time):
        poller = ImouPoller(device_id="CAM_TEST")
        assert poller.is_session_active() is False

def test_is_session_active_missing():
    with patch("db_client.SupabaseDbClient.get_session_heartbeat", return_value=None):
        poller = ImouPoller(device_id="CAM_TEST")
        assert poller.is_session_active() is False

def test_polling_cycle_skips_when_session_inactive():
    with patch("db_client.SupabaseDbClient.get_session_heartbeat", return_value=None):
        mock_service = MagicMock()
        poller = ImouPoller(service=mock_service, device_id="CAM_TEST")
        res = poller.poll_once()
        assert res["status"] == "skipped"
        assert res["reason"] == "inactive_session"
        mock_service.get_access_token.assert_not_called()



