from unittest.mock import MagicMock
from app.imou_poller import ImouPoller

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

def test_escalated_alerting_lifecycle():
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

