import pytest
from unittest.mock import MagicMock, patch
from app.supabase_service import get_system_paused, set_system_paused, log_camera_status, fetch_recent_logs

@pytest.fixture
def mock_supabase():
    with patch("app.supabase_service.supabase_client") as mock_client:
        yield mock_client

def test_get_system_paused_fallback(mock_supabase):
    # When supabase_client is None, it should return the fallback value
    with patch("app.supabase_service.supabase_client", None):
        assert get_system_paused(fallback=True) is True
        assert get_system_paused(fallback=False) is False

def test_get_system_paused_success(mock_supabase):
    # Setup mock query response
    mock_select = MagicMock()
    mock_eq = MagicMock()
    mock_execute = MagicMock()
    
    mock_supabase.table.return_value = mock_select
    mock_select.select.return_value = mock_eq
    mock_eq.eq.return_value = mock_execute
    mock_execute.execute.return_value = MagicMock(data=[{"is_paused": True}])
    
    assert get_system_paused(fallback=False) is True
    mock_supabase.table.assert_called_with("system_state")
    mock_select.select.assert_called_with("is_paused")
    mock_eq.eq.assert_called_with("id", "00000000-0000-0000-0000-000000000001")

def test_set_system_paused_unconfigured():
    with patch("app.supabase_service.supabase_client", None):
        assert set_system_paused(True) is False

def test_set_system_paused_success(mock_supabase):
    mock_update = MagicMock()
    mock_eq = MagicMock()
    mock_execute = MagicMock()
    
    mock_supabase.table.return_value = mock_update
    mock_update.update.return_value = mock_eq
    mock_eq.eq.return_value = mock_execute
    mock_execute.execute.return_value = MagicMock(data=[{"is_paused": True}])
    
    assert set_system_paused(True) is True
    mock_supabase.table.assert_called_with("system_state")
    mock_update.update.assert_called_with({"is_paused": True})
    mock_eq.eq.assert_called_with("id", "00000000-0000-0000-0000-000000000001")

def test_log_camera_status_success(mock_supabase):
    mock_insert = MagicMock()
    mock_execute = MagicMock()
    
    mock_supabase.table.return_value = mock_insert
    mock_insert.insert.return_value = mock_execute
    mock_execute.execute.return_value = MagicMock(data=[{"id": 123}])
    
    res = log_camera_status(mock_supabase, "CAM_123", "offline", True, True)
    assert res is not None
    mock_supabase.table.assert_called_with("camera_logs")
    mock_insert.insert.assert_called_with({
        "device_id": "CAM_123",
        "event_type": "offline",
        "exotel_call_triggered": True,
        "telegram_alert_sent": True
    })

def test_fetch_recent_logs_success(mock_supabase):
    mock_select = MagicMock()
    mock_order = MagicMock()
    mock_limit = MagicMock()
    mock_execute = MagicMock()
    
    mock_supabase.table.return_value = mock_select
    mock_select.select.return_value = mock_order
    mock_order.order.return_value = mock_limit
    mock_limit.limit.return_value = mock_execute
    mock_execute.execute.return_value = MagicMock(data=[{"device_id": "CAM_1"}])
    
    logs = fetch_recent_logs(limit=5)
    assert len(logs) == 1
    assert logs[0]["device_id"] == "CAM_1"
    mock_supabase.table.assert_called_with("camera_logs")
    mock_select.select.assert_called_with("*")
    mock_order.order.assert_called_with("triggered_at", desc=True)
    mock_limit.limit.assert_called_with(5)

def test_get_session_heartbeat_success(mock_supabase):
    mock_select = MagicMock()
    mock_eq = MagicMock()
    mock_execute = MagicMock()
    
    mock_supabase.table.return_value = mock_select
    mock_select.select.return_value = mock_eq
    mock_eq.eq.return_value = mock_execute
    mock_execute.execute.return_value = MagicMock(data=[{"last_active_at": "2026-07-05T12:00:00+00:00"}])
    
    from db_client import db_client
    old_client = db_client.client
    db_client.client = mock_supabase
    try:
        hb = db_client.get_session_heartbeat()
        assert hb == "2026-07-05T12:00:00+00:00"
        mock_supabase.table.assert_called_with("system_session")
        mock_select.select.assert_called_with("last_active_at")
        mock_eq.eq.assert_called_with("id", "00000000-0000-0000-0000-000000000001")
    finally:
        db_client.client = old_client


