import time
from unittest.mock import MagicMock
from app.device_manager import DeviceManager

def test_device_manager_offline_and_reconnect_cancels_timer():
    mock_call_handler = MagicMock()
    dm = DeviceManager(buffer_delay_seconds=1, call_handler=mock_call_handler)

    # 1. Device goes offline
    res_offline = dm.handle_device_event("CAM_TEST_1", "offline")
    assert res_offline["action"] == "timer_scheduled"
    assert dm.get_device_status("CAM_TEST_1") == "offline"
    assert dm.is_timer_active("CAM_TEST_1") is True

    # 2. Device reconnects within 0.2s (well before 1 second buffer)
    res_online = dm.handle_device_event("CAM_TEST_1", "online")
    assert res_online["action"] == "timer_cancelled_false_alarm_prevented"
    assert dm.get_device_status("CAM_TEST_1") == "online"
    assert dm.is_timer_active("CAM_TEST_1") is False

    # Wait 1.2 seconds to ensure timer would have fired
    time.sleep(1.2)
    mock_call_handler.assert_not_called()

def test_device_manager_offline_triggers_call_after_buffer():
    mock_call_handler = MagicMock()
    # Use 0.2s buffer for fast test execution
    dm = DeviceManager(buffer_delay_seconds=0.2, call_handler=mock_call_handler)

    res_offline = dm.handle_device_event("CAM_TEST_2", "offline")
    assert res_offline["action"] == "timer_scheduled"

    # Wait 0.4 seconds for safety buffer to expire
    time.sleep(0.4)

    mock_call_handler.assert_called_once_with("CAM_TEST_2")
