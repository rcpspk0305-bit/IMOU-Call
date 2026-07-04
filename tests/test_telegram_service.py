from unittest.mock import patch, MagicMock
import pytest
from app.config import Config
from app.lifecycle import app_lifecycle
from app.telegram_service import TelegramBotPoller, send_telegram_notification
from app.imou_poller import ImouPoller

class MockTelegramConfig:
    TELEGRAM_BOT_TOKEN = "mock_bot_token_123"
    TELEGRAM_ALLOWED_CHAT_ID = "999888777"
    IMOU_DEVICE_ID = "CAM_TEST_TELEGRAM"

def setup_function():
    app_lifecycle.is_paused = False

@patch("requests.post")
def test_send_telegram_notification_success(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_post.return_value = mock_response

    res = send_telegram_notification("Test Alert Message", config=MockTelegramConfig)
    assert res is True
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert kwargs["json"]["chat_id"] == "999888777"
    assert "Test Alert Message" in kwargs["json"]["text"]

@patch("app.telegram_service.send_telegram_notification")
def test_telegram_commands_pause_and_resume(mock_send):
    poller = TelegramBotPoller(config=MockTelegramConfig)

    # 1. Test /pause
    poller.process_command("/pause", sender_chat_id="999888777")
    assert app_lifecycle.is_paused is True
    mock_send.assert_called_with("⛔️ Monitoring paused. Exotel voice alerts disabled.", chat_id="999888777", config=MockTelegramConfig)

    # 2. Test /resume
    poller.process_command("/resume", sender_chat_id="999888777")
    assert app_lifecycle.is_paused is False
    mock_send.assert_called_with("✅ Monitoring resumed. Active tracking active.", chat_id="999888777", config=MockTelegramConfig)

@patch("app.telegram_service.send_telegram_notification")
def test_telegram_unauthorized_chat_id(mock_send):
    poller = TelegramBotPoller(config=MockTelegramConfig)

    # Attempt command from wrong chat ID
    poller.process_command("/pause", sender_chat_id="111222333")
    assert app_lifecycle.is_paused is False  # State must remain unchanged
    mock_send.assert_called_with("⚠️ <b>Access Denied:</b> Unauthorized chat ID.", chat_id="111222333", config=MockTelegramConfig)

@patch("app.telegram_service.send_telegram_notification")
def test_imou_poller_skips_when_paused(mock_send):
    mock_service = MagicMock()
    imou_poller = ImouPoller(service=mock_service, device_id="CAM_PAUSE_TEST")

    # Set paused state
    app_lifecycle.is_paused = True

    res = imou_poller.poll_once()
    assert res["status"] == "skipped"
    assert res["reason"] == "monitoring_paused"
    mock_service.get_access_token.assert_not_called()

@patch("app.supabase_service.get_backend_service_client")
@patch("app.telegram_service.send_telegram_notification")
def test_telegram_status_command(mock_send, mock_get_client):
    # Setup mock supabase client
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    
    # Mock system_state query
    mock_table_state = MagicMock()
    mock_select_state = MagicMock()
    mock_eq_state = MagicMock()
    mock_execute_state = MagicMock()
    
    mock_execute_state.execute.return_value = MagicMock(data=[{"is_paused": False}])
    mock_eq_state.eq.return_value = mock_execute_state
    mock_select_state.select.return_value = mock_eq_state
    
    # Mock camera_logs query
    mock_table_logs = MagicMock()
    mock_select_logs = MagicMock()
    mock_order_logs = MagicMock()
    mock_limit_logs = MagicMock()
    mock_execute_logs = MagicMock()
    
    mock_execute_logs.execute.return_value = MagicMock(data=[{"event_type": "online", "triggered_at": "2026-07-04 12:00:00"}])
    mock_limit_logs.limit.return_value = mock_execute_logs
    mock_order_logs.order.return_value = mock_limit_logs
    mock_select_logs.select.return_value = mock_order_logs
    
    # Define route side_effects for table()
    def table_side_effect(table_name):
        if table_name == "system_state":
            return mock_table_state
        elif table_name == "camera_logs":
            return mock_table_logs
        return MagicMock()
        
    mock_client.table.side_effect = table_side_effect
    
    mock_table_state.select.return_value = mock_eq_state
    mock_table_logs.select.return_value = mock_order_logs
    
    poller = TelegramBotPoller(config=MockTelegramConfig)
    poller.process_command("/status", sender_chat_id="999888777")
    
    mock_send.assert_called_once()
    args, kwargs = mock_send.call_args
    assert "Imou-Exotel System Status" in args[0]
    assert "🟢" in args[0]  # Online emoji
    assert "ONLINE" in args[0]
