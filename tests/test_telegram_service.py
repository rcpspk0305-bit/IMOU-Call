from unittest.mock import patch, MagicMock
import pytest
from app.config import Config
from app.lifecycle import app_lifecycle
from app.telegram_service import TelegramBotPoller, send_telegram_notification
from app.imou_poller import ImouPoller
from datetime import datetime, timezone

@pytest.fixture(autouse=True)
def mock_db_session_heartbeat():
    now_str = datetime.now(timezone.utc).isoformat()
    with patch("db_client.SupabaseDbClient.get_session_heartbeat", return_value=now_str):
        yield


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

@patch("app.supabase_service.set_system_paused")
@patch("app.supabase_service.get_system_paused")
@patch("app.telegram_service.send_telegram_notification")
def test_telegram_commands_pause_and_resume(mock_send, mock_get_paused, mock_set_paused):
    local_state = {"paused": False}
    mock_get_paused.side_effect = lambda *args, **kwargs: local_state["paused"]
    def mock_set(val):
        local_state["paused"] = val
        return True
    mock_set_paused.side_effect = mock_set

    poller = TelegramBotPoller(config=MockTelegramConfig)

    # 1. Test /pause
    poller.process_command("/pause", sender_chat_id="999888777")
    assert app_lifecycle.is_paused is True
    mock_send.assert_called_with("⛔️ Monitoring paused. Exotel voice alerts disabled.", chat_id="999888777", config=MockTelegramConfig)

    # 2. Test /resume
    poller.process_command("/resume", sender_chat_id="999888777")
    assert app_lifecycle.is_paused is False
    mock_send.assert_called_with("✅ Monitoring resumed. Active tracking active.", chat_id="999888777", config=MockTelegramConfig)

@patch("app.supabase_service.set_system_paused")
@patch("app.supabase_service.get_system_paused")
@patch("app.telegram_service.send_telegram_notification")
def test_telegram_unauthorized_chat_id(mock_send, mock_get_paused, mock_set_paused):
    local_state = {"paused": False}
    mock_get_paused.side_effect = lambda *args, **kwargs: local_state["paused"]
    def mock_set(val):
        local_state["paused"] = val
        return True
    mock_set_paused.side_effect = mock_set

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

@patch("time.sleep")
@patch("requests.get")
@patch("app.telegram_service.send_telegram_notification")
@patch("app.imou_service.imou_service.set_device_snap_enhanced")
def test_telegram_snapshot_command(mock_snap, mock_send, mock_get, mock_sleep):
    mock_snap.return_value = ("https://example.com/live_snapshot.jpg", None)
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"fake snapshot image bytes"
    mock_get.return_value = mock_response
    
    poller = TelegramBotPoller(config=MockTelegramConfig)
    
    # Mock bot.send_photo
    poller.bot.send_photo = MagicMock()
    poller.bot.send_photo.return_value = True
    
    poller.process_command("/snapshot", sender_chat_id="999888777")
    
    # Verify snapshot API was called
    mock_snap.assert_called_once_with("CAM_TEST_TELEGRAM", channel_id="0")
    
    # Verify requests.get was called
    mock_get.assert_called_once_with("https://example.com/live_snapshot.jpg", timeout=15)
    
    # Verify send_photo was called on the bot proxy with BytesIO stream
    poller.bot.send_photo.assert_called_once()
    args, kwargs = poller.bot.send_photo.call_args
    assert args[0] == "999888777"
    assert hasattr(args[1], "read")
    assert getattr(args[1], "name") == "snapshot.jpg"
    assert "Camera Live Snapshot" in args[2]

@patch("app.telegram_service.send_telegram_notification")
@patch("app.exotel_service.trigger_exotel_call")
def test_telegram_testcall_command_success(mock_trigger, mock_send):
    mock_trigger.return_value = {"success": True}
    
    poller = TelegramBotPoller(config=MockTelegramConfig)
    poller.process_command("/testcall", sender_chat_id="999888777")
    
    mock_trigger.assert_called_once_with("CAM_TEST_TELEGRAM", config=MockTelegramConfig, ignore_lockout=True)
    assert mock_send.call_count == 2
    
    # Check that second send is success notification
    args, kwargs = mock_send.call_args_list[1]
    assert "Test Call Placed successfully" in args[0]

@patch("app.telegram_service.send_telegram_notification")
@patch("app.exotel_service.trigger_exotel_call")
def test_telegram_testcall_command_failure(mock_trigger, mock_send):
    mock_trigger.return_value = {"success": False, "reason": "lockout_active"}
    
    poller = TelegramBotPoller(config=MockTelegramConfig)
    poller.process_command("/testcall", sender_chat_id="999888777")
    
    mock_trigger.assert_called_once_with("CAM_TEST_TELEGRAM", config=MockTelegramConfig, ignore_lockout=True)
    assert mock_send.call_count == 2
    
    # Check that second send is failure notification
    args, kwargs = mock_send.call_args_list[1]
    assert "Test Call Failed" in args[0]

@patch("app.supabase_service.set_system_paused")
@patch("app.supabase_service.get_system_paused")
@patch("app.telegram_service.send_telegram_notification")
def test_telegram_command_group_suffix(mock_send, mock_get_paused, mock_set_paused):
    local_state = {"paused": False}
    mock_get_paused.side_effect = lambda *args, **kwargs: local_state["paused"]
    def mock_set(val):
        local_state["paused"] = val
        return True
    mock_set_paused.side_effect = mock_set

    poller = TelegramBotPoller(config=MockTelegramConfig)
    
    # 1. Test /pause@MyCamExotelBot
    app_lifecycle.is_paused = False
    poller.process_command("/pause@MyCamExotelBot", sender_chat_id="999888777")
    assert app_lifecycle.is_paused is True
    mock_send.assert_called_with("⛔️ Monitoring paused. Exotel voice alerts disabled.", chat_id="999888777", config=MockTelegramConfig)

    # 2. Test /resume@MyCamExotelBot
    poller.process_command("/resume@MyCamExotelBot", sender_chat_id="999888777")
    assert app_lifecycle.is_paused is False
    mock_send.assert_called_with("✅ Monitoring resumed. Active tracking active.", chat_id="999888777", config=MockTelegramConfig)

@patch("app.supabase_service.set_system_paused")
@patch("app.supabase_service.get_system_paused")
@patch("app.telegram_service.send_telegram_notification")
def test_telegram_multi_id_verification(mock_send, mock_get_paused, mock_set_paused):
    local_state = {"paused": False}
    mock_get_paused.side_effect = lambda *args, **kwargs: local_state["paused"]
    def mock_set(val):
        local_state["paused"] = val
        return True
    mock_set_paused.side_effect = mock_set

    # Configuration with comma-separated IDs
    class MultiIdConfig:
        TELEGRAM_BOT_TOKEN = "mock_bot_token_123"
        TELEGRAM_ALLOWED_CHAT_ID = "999888777, 111222333"
        IMOU_DEVICE_ID = "CAM_TEST_TELEGRAM"

    poller = TelegramBotPoller(config=MultiIdConfig)

    # 1. Valid sender_chat_id (999888777)
    app_lifecycle.is_paused = False
    poller.process_command("/pause", sender_chat_id="999888777")
    assert app_lifecycle.is_paused is True
    mock_send.assert_called_with("⛔️ Monitoring paused. Exotel voice alerts disabled.", chat_id="999888777", config=MultiIdConfig)

    # 2. Valid from_user_id (111222333) in group chat (group_chat_id = -444555666)
    app_lifecycle.is_paused = True
    poller.process_command("/resume", sender_chat_id="-444555666", from_user_id="111222333")
    assert app_lifecycle.is_paused is False
    mock_send.assert_called_with("✅ Monitoring resumed. Active tracking active.", chat_id="-444555666", config=MultiIdConfig)

    # 3. Unauthorized interaction (neither sender_chat_id nor from_user_id is allowed)
    poller.process_command("/pause", sender_chat_id="777777777", from_user_id="888888888")
    assert app_lifecycle.is_paused is False  # remains unchanged
    mock_send.assert_called_with("⚠️ <b>Access Denied:</b> Unauthorized chat ID.", chat_id="777777777", config=MultiIdConfig)


@patch("app.supabase_service.get_backend_service_client")
@patch("app.imou_poller.imou_poller.poll_once")
@patch("app.telegram_service.send_telegram_notification")
def test_telegram_checknow_command_success(mock_send, mock_poll, mock_get_backend_client):
    mock_poll.return_value = {"status": "success", "device_id": "CAM_TEST_TELEGRAM", "is_online": True}
    
    mock_client = MagicMock()
    mock_get_backend_client.return_value = mock_client
    
    poller = TelegramBotPoller(config=MockTelegramConfig)
    poller.process_command("/checknow", sender_chat_id="999888777")
    
    # Assertions
    mock_poll.assert_called_once_with(ignore_pause=True, ignore_session=True)
    mock_get_backend_client.assert_called_once()
    mock_client.table.assert_called_once_with("camera_logs")
    mock_client.table("camera_logs").insert.assert_called_once()
    
    assert mock_send.call_count == 2
    # Verify the first message (checking...)
    assert "Executing instant Imou API camera check" in mock_send.call_args_list[0][0][0]
    # Verify the second message (clean success string + IST timestamp)
    success_msg = mock_send.call_args_list[1][0][0]
    assert "Instant Check Successful" in success_msg
    assert "ONLINE" in success_msg
    assert "IST" in success_msg


@patch("requests.post")
@patch("requests.get")
def test_send_telegram_photo_url_download(mock_get, mock_post):
    from app.telegram_service import send_telegram_photo
    import io

    # Mock requests.get for image download
    mock_get_response = MagicMock()
    mock_get_response.status_code = 200
    mock_get_response.content = b"fake_downloaded_image_bytes"
    mock_get.return_value = mock_get_response

    # Mock requests.post for Telegram upload
    mock_post_response = MagicMock()
    mock_post_response.status_code = 200
    mock_post.return_value = mock_post_response

    class LocalTestConfig:
        TELEGRAM_BOT_TOKEN = "test_bot_token"
        TELEGRAM_ALLOWED_CHAT_ID = "12345"

    photo_url = "https://example.com/some_alarm_image.jpg"
    res = send_telegram_photo(photo_url, "Test Caption", config=LocalTestConfig)

    assert res is True
    # Verify image was downloaded
    mock_get.assert_called_once_with(photo_url, timeout=15)
    # Verify image was uploaded as multipart
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert "https://api.telegram.org/bottest_bot_token/sendPhoto" in args[0]
    
    files = kwargs.get("files")
    assert files is not None
    photo_file = files.get("photo")
    assert photo_file is not None
    assert photo_file[0] == "image.jpg"  # assigned file name
    assert photo_file[1].read() == b"fake_downloaded_image_bytes"
    assert photo_file[2] == "image/jpeg"

    data = kwargs.get("data")
    assert data is not None
    assert data["chat_id"] == "12345"
    assert data["caption"] == "Test Caption"
    assert data["parse_mode"] == "Markdown"


@patch("app.telegram_service.send_telegram_photo")
@patch("requests.get")
def test_telegram_bot_proxy_send_photo_url_download(mock_get, mock_send_photo):
    from app.telegram_service import TelegramBotPoller
    import io

    # Mock requests.get for image download
    mock_get_response = MagicMock()
    mock_get_response.status_code = 200
    mock_get_response.content = b"proxy_fake_image_bytes"
    mock_get.return_value = mock_get_response

    mock_send_photo.return_value = True

    class ProxyTestConfig:
        TELEGRAM_BOT_TOKEN = "proxy_token"
        TELEGRAM_ALLOWED_CHAT_ID = "67890"

    poller = TelegramBotPoller(config=ProxyTestConfig)
    photo_url = "https://example.com/proxy_image.jpg"
    
    # Call bot.send_photo
    res = poller.bot.send_photo("67890", photo_url, "Proxy Caption", parse_mode="HTML")

    assert res is True
    # Verify image was downloaded
    mock_get.assert_called_once_with(photo_url, timeout=20)
    # Verify send_telegram_photo was called with BytesIO object
    mock_send_photo.assert_called_once()
    args, kwargs = mock_send_photo.call_args
    
    # First arg is photo (BytesIO)
    photo_arg = args[0]
    assert hasattr(photo_arg, "read")
    assert photo_arg.read() == b"proxy_fake_image_bytes"
    assert getattr(photo_arg, "name") == "image.jpg"
    
    # Second arg is caption
    assert args[1] == "Proxy Caption"
    # Keyword arguments
    assert kwargs["chat_id"] == "67890"
    assert kwargs["parse_mode"] == "HTML"


