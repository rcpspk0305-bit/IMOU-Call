import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta
import numpy as np
import cv2
import time
import io

from app.aerator_analyzer import is_night_time, analyze_motion
from app.imou_poller import ImouPoller

# Mock Helper to construct dummy image bytes
def create_dummy_image_bytes(val=128, shape=(100, 100), motion=False):
    img = np.ones(shape, dtype=np.uint8) * val
    if motion:
        # Add a block that moves/changes
        img[30:70, 30:70] = 255
    else:
        img[30:70, 30:70] = 0
    _, buf = cv2.imencode(".jpg", img)
    return buf.tobytes()

def test_is_night_time():
    # 18:00 IST -> 12:30 UTC
    dt_18_ist = datetime(2026, 7, 11, 12, 30, 0, tzinfo=timezone.utc)
    with patch("app.aerator_analyzer.datetime") as mock_dt:
        mock_dt.now.return_value = dt_18_ist
        assert is_night_time() is True

    # 05:59 IST -> 00:29 UTC
    dt_559_ist = datetime(2026, 7, 11, 0, 29, 0, tzinfo=timezone.utc)
    with patch("app.aerator_analyzer.datetime") as mock_dt:
        mock_dt.now.return_value = dt_559_ist
        assert is_night_time() is True

    # 06:00 IST -> 00:30 UTC
    dt_6_ist = datetime(2026, 7, 11, 0, 30, 0, tzinfo=timezone.utc)
    with patch("app.aerator_analyzer.datetime") as mock_dt:
        mock_dt.now.return_value = dt_6_ist
        assert is_night_time() is False

    # 17:59 IST -> 12:29 UTC
    dt_1759_ist = datetime(2026, 7, 11, 12, 29, 0, tzinfo=timezone.utc)
    with patch("app.aerator_analyzer.datetime") as mock_dt:
        mock_dt.now.return_value = dt_1759_ist
        assert is_night_time() is False

def test_analyze_motion_no_motion():
    frame1 = create_dummy_image_bytes(val=100, motion=False)
    frame2 = create_dummy_image_bytes(val=100, motion=False)
    
    mean_mag, state = analyze_motion(frame1, frame2, threshold=1.0)
    assert mean_mag == 0.0
    assert state == "STOPPED"

def test_analyze_motion_with_motion():
    frame1 = create_dummy_image_bytes(val=100, motion=False)
    frame2 = create_dummy_image_bytes(val=100, motion=True)
    
    mean_mag, state = analyze_motion(frame1, frame2, threshold=0.1)
    assert mean_mag > 0.0
    assert state == "WORKING"

@patch("app.imou_poller.ImouPoller.is_session_active", return_value=True)
@patch("app.telegram_service.telegram_bot_poller")
def test_poller_aerator_escalation_workflow(mock_bot_poller, mock_active):
    mock_service = MagicMock()
    mock_service.get_access_token.return_value = ("mock_token", None)
    mock_service.get_device_online_status.return_value = (True, None)
    # Return fake snapshot URLs
    mock_service.set_device_snap_enhanced.return_value = ("https://example.com/snap.jpg", None)

    mock_call_handler = MagicMock()

    poller = ImouPoller(
        service=mock_service,
        call_handler=mock_call_handler,
        device_id="CAM_AERATOR_TEST"
    )

    # Mock night time to be True and human alarm checks to be bypassed
    with patch("app.aerator_analyzer.is_night_time", return_value=True), \
         patch("app.imou_poller.ImouPoller.check_for_human_alarms", return_value=None), \
         patch("requests.get") as mock_get:
        
        # Frame decoding results in a STOPPED state (no motion)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        # Create identical frames to simulate stopped aerator
        mock_resp.content = create_dummy_image_bytes(motion=False)
        mock_get.return_value = mock_resp

        # 1. Round 1 transition: WORKING -> STOPPED
        res = poller.poll_once()
        assert poller.aerator_state == "STOPPED"
        assert poller.aerator_alerts_sent == 1
        assert mock_call_handler.call_count == 1
        
        # Reset mock
        mock_call_handler.reset_mock()

        # 2. Duplicate check within 3 minutes (should not trigger alert)
        poller.poll_once()
        assert poller.aerator_alerts_sent == 1
        mock_call_handler.assert_not_called()

        # 3. Escalate to Round 2 after 180 seconds elapsed
        poller.last_aerator_alert_time -= 190
        poller.poll_once()
        assert poller.aerator_alerts_sent == 2
        assert mock_call_handler.call_count == 1
        
        # Reset mock
        mock_call_handler.reset_mock()

        # 4. Transition to WORKING -> Recovery trigger
        # Mock requests.get content to return moving frame for the second frame
        mock_resp1 = MagicMock()
        mock_resp1.status_code = 200
        mock_resp1.content = create_dummy_image_bytes(motion=False)

        mock_resp2 = MagicMock()
        mock_resp2.status_code = 200
        mock_resp2.content = create_dummy_image_bytes(motion=True)
        
        mock_get.side_effect = [mock_resp1, mock_resp2]

        poller.poll_once()
        assert poller.aerator_state == "WORKING"
        assert poller.aerator_alerts_sent == 0
        assert poller.last_aerator_alert_time == 0.0
        assert mock_call_handler.call_count == 1
