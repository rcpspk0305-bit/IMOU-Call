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
