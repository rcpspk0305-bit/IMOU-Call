import time
import logging
import datetime
import threading
import requests
from typing import Optional
from app.config import Config
from app.lifecycle import app_lifecycle

logger = logging.getLogger(__name__)

def format_to_ist(dt_val) -> str:
    """
    Converts a datetime object, ISO string, or float timestamp to Asia/Kolkata timezone (IST)
    and formats it as 'YYYY-MM-DD HH:mm:ss IST'.
    """
    if dt_val is None:
        return "Never"
        
    try:
        from datetime import datetime, timezone, timedelta
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo("Asia/Kolkata")
        except Exception:
            tz = timezone(timedelta(hours=5, minutes=30))

        if isinstance(dt_val, (int, float)):
            if dt_val <= 0:
                return "Never"
            dt = datetime.fromtimestamp(dt_val, tz=timezone.utc)
        elif isinstance(dt_val, str):
            val_clean = dt_val.replace("Z", "+00:00")
            dt = datetime.fromisoformat(val_clean)
        elif isinstance(dt_val, datetime):
            dt = dt_val
        else:
            return str(dt_val)

        dt_ist = dt.astimezone(tz)
        return dt_ist.strftime("%Y-%m-%d %H:%M:%S IST")
    except Exception as e:
        logger.warning("Error localizing timestamp '%s' to IST: %s", str(dt_val), str(e))
        return str(dt_val)

def send_telegram_photo(photo, caption: str, chat_id: Optional[str] = None, config: type = Config) -> bool:
    """
    Sends a photo alert via Telegram Bot API. Accepts either a URL string or an in-memory byte stream.
    """
    token = getattr(config, "TELEGRAM_BOT_TOKEN", None) or Config.TELEGRAM_BOT_TOKEN
    target_chat_id = chat_id or getattr(config, "TELEGRAM_ALLOWED_CHAT_ID", None) or Config.TELEGRAM_ALLOWED_CHAT_ID

    if not token or token == "YOUR_TELEGRAM_BOT_TOKEN" or not target_chat_id or target_chat_id == "YOUR_TELEGRAM_ALLOWED_CHAT_ID":
        logger.warning("Telegram photo alert skipped: TELEGRAM_BOT_TOKEN or TELEGRAM_ALLOWED_CHAT_ID not configured.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    
    try:
        import io
        if hasattr(photo, "read") or isinstance(photo, (io.BytesIO, io.BufferedReader)):
            if hasattr(photo, "seek"):
                photo.seek(0)
            file_name = getattr(photo, "name", "photo.jpg")
            files = {"photo": (file_name, photo, "image/jpeg")}
            data = {
                "chat_id": target_chat_id,
                "caption": caption,
                "parse_mode": "Markdown"
            }
            response = requests.post(url, data=data, files=files, timeout=20)
        else:
            payload = {
                "chat_id": target_chat_id,
                "photo": str(photo),
                "caption": caption,
                "parse_mode": "Markdown"
            }
            response = requests.post(url, json=payload, timeout=10)

        if response.status_code == 200:
            logger.info("Telegram photo alert sent successfully to chat_id '%s'", target_chat_id)
            return True
        else:
            logger.error("Failed to send Telegram photo alert. Status: %d, Response: %s", response.status_code, response.text)
            return False
    except Exception as e:
        logger.exception("Exception sending Telegram photo alert: %s", str(e))
        return False

def send_telegram_photo_stream(photo_url: str, caption: str, chat_id: Optional[str] = None, config: type = Config) -> bool:
    """
    Downloads the photo from photo_url and uploads it to Telegram as a multipart file stream.
    """
    token = getattr(config, "TELEGRAM_BOT_TOKEN", None) or Config.TELEGRAM_BOT_TOKEN
    target_chat_id = chat_id or getattr(config, "TELEGRAM_ALLOWED_CHAT_ID", None) or Config.TELEGRAM_ALLOWED_CHAT_ID

    if not token or token == "YOUR_TELEGRAM_BOT_TOKEN" or not target_chat_id or target_chat_id == "YOUR_TELEGRAM_ALLOWED_CHAT_ID":
        logger.warning("Telegram photo stream alert skipped: Token or chat ID not configured.")
        return False

    try:
        # Download the image content
        img_resp = requests.get(photo_url, timeout=15)
        if img_resp.status_code != 200:
            logger.error("Failed to download alarm image from %s: HTTP %d", photo_url, img_resp.status_code)
            return False

        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        files = {
            "photo": ("alarm_snapshot.jpg", img_resp.content, "image/jpeg")
        }
        data = {
            "chat_id": target_chat_id,
            "caption": caption,
            "parse_mode": "Markdown"
        }
        
        response = requests.post(url, data=data, files=files, timeout=20)
        if response.status_code == 200:
            logger.info("Telegram photo stream alert sent successfully to chat_id '%s'", target_chat_id)
            return True
        else:
            logger.error("Failed to send Telegram photo stream. Status: %d, Response: %s", response.status_code, response.text)
            return False
    except Exception as e:
        logger.exception("Exception in send_telegram_photo_stream: %s", str(e))
        return False

def send_telegram_notification(text: str, chat_id: Optional[str] = None, config: type = Config) -> bool:
    """
    Sends a text message notification via Telegram Bot API to TELEGRAM_ALLOWED_CHAT_ID.
    """
    token = getattr(config, "TELEGRAM_BOT_TOKEN", None) or Config.TELEGRAM_BOT_TOKEN
    target_chat_id = chat_id or getattr(config, "TELEGRAM_ALLOWED_CHAT_ID", None) or Config.TELEGRAM_ALLOWED_CHAT_ID

    if not token or token == "YOUR_TELEGRAM_BOT_TOKEN" or not target_chat_id or target_chat_id == "YOUR_TELEGRAM_ALLOWED_CHAT_ID":
        logger.warning("Telegram notification skipped: TELEGRAM_BOT_TOKEN or TELEGRAM_ALLOWED_CHAT_ID not configured.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": target_chat_id,
        "text": text,
        "parse_mode": "HTML"
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            logger.info("Telegram notification sent successfully to chat_id '%s'", target_chat_id)
            return True
        else:
            logger.error("Failed to send Telegram notification. Status: %d, Response: %s", response.status_code, response.text)
            return False
    except requests.RequestException as e:
        logger.exception("Network exception sending Telegram notification: %s", str(e))
        return False

class TelegramBotProxy:
    def __init__(self, poller):
        self.poller = poller

    def send_photo(self, chat_id: str, photo, caption: str) -> bool:
        return send_telegram_photo(photo, caption, chat_id=chat_id, config=self.poller.config)

class TelegramBotPoller:
    """
    Background daemon thread handling Telegram Bot command control plane via long-polling getUpdates.
    Enforces TELEGRAM_ALLOWED_CHAT_ID access control.
    """
    def __init__(self, config: type = Config):
        self.config = config
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_update_id: int = 0
        self._lock = threading.Lock()
        self.bot = TelegramBotProxy(self)

    def _format_timestamp(self, ts: float) -> str:
        return format_to_ist(ts)

    def handle_telegram_snapshot_command(self, sender_chat_id: str):
        """
        Retrieves snapshot URL, downloads image locally into BytesIO, and dispatches via bot.send_photo.
        """
        from app.imou_service import imou_service
        device_id = getattr(self.config, "IMOU_DEVICE_ID", Config.IMOU_DEVICE_ID)
        send_telegram_notification("📸 <b>Requesting live snapshot from Imou camera...</b>", chat_id=sender_chat_id, config=self.config)
        
        snap_url, err = imou_service.set_device_snap_enhanced(device_id, channel_id="0")
        if err or not snap_url:
            send_telegram_notification(f"❌ <b>Snapshot Request Failed:</b> {err}", chat_id=sender_chat_id, config=self.config)
            return

        # Let the asset compile on the external server
        time.sleep(2.0)

        try:
            import io
            response = None
            for attempt in range(1, 4):
                try:
                    response = requests.get(snap_url, timeout=15)
                    if response.status_code == 200:
                        break
                except requests.RequestException as req_err:
                    logger.warning("Snapshot download attempt %d failed: %s", attempt, str(req_err))
                
                if attempt < 3:
                    time.sleep(1.5)

            if response is None or response.status_code != 200:
                status_str = str(response.status_code) if response is not None else "Unknown"
                send_telegram_notification(f"❌ <b>Failed to download snapshot image. HTTP {status_str}</b>", chat_id=sender_chat_id, config=self.config)
                return
            
            # Wrap the raw response content inside an in-memory binary stream using io.BytesIO
            bio = io.BytesIO(response.content)
            bio.name = 'snapshot.jpg'
            
            now_ist = format_to_ist(time.time())
            caption = f"📸 *Camera Live Snapshot*\nDevice: `{device_id}`\nTime: `{now_ist}`"
            
            # Pass this byte stream object directly as the photo parameter in bot.send_photo()
            sent = self.bot.send_photo(sender_chat_id, bio, caption)
            if not sent:
                send_telegram_notification("❌ <b>Failed to route snapshot image payload to chat ID.</b>", chat_id=sender_chat_id, config=self.config)
        except Exception as e:
            logger.exception("Exception in handle_telegram_snapshot_command: %s", str(e))
            send_telegram_notification(f"❌ <b>Snapshot command error:</b> {str(e)}", chat_id=sender_chat_id, config=self.config)

    def process_command(self, text: str, sender_chat_id: str, from_user_id: Optional[str] = None):
        """
        Processes incoming bot commands with TELEGRAM_ALLOWED_CHAT_ID security check.
        Supports comma-separated multi-ID validation.
        """
        authorized_chat_id = str(getattr(self.config, "TELEGRAM_ALLOWED_CHAT_ID", Config.TELEGRAM_ALLOWED_CHAT_ID)).strip()
        
        # 1. MULTI-ID PARSING
        auth_list = [str(i).strip() for i in str(authorized_chat_id).split(",")]
        
        chat_id_str = str(sender_chat_id).strip()
        user_id_str = str(from_user_id or sender_chat_id).strip()

        # 2. DUAL VALIDATION
        if "YOUR_TELEGRAM_ALLOWED_CHAT_ID" not in auth_list:
            if chat_id_str not in auth_list and user_id_str not in auth_list:
                logger.warning("Unauthorized Telegram command attempt from chat_id '%s', user_id '%s' (Allowed: %s)", chat_id_str, user_id_str, auth_list)
                send_telegram_notification("⚠️ <b>Access Denied:</b> Unauthorized chat ID.", chat_id=sender_chat_id, config=self.config)
                return

        # Extract base command string to support group chat syntax suffixes (e.g. /status@MyCamExotelBot)
        first_word = text.strip().split()[0] if text.strip().split() else ""
        base_command = first_word.split("@")[0].lower()
        logger.info("Processing authorized Telegram command '%s' (base: '%s') from chat_id '%s'", first_word, base_command, chat_id_str)

        if base_command == "/pause":
            app_lifecycle.is_paused = True
            reply = "⛔️ Monitoring paused. Exotel voice alerts disabled."
            send_telegram_notification(reply, chat_id=sender_chat_id, config=self.config)

        elif base_command == "/resume":
            app_lifecycle.is_paused = False
            reply = "✅ Monitoring resumed. Active tracking active."
            send_telegram_notification(reply, chat_id=sender_chat_id, config=self.config)

        elif base_command == "/status":
            from app.supabase_service import get_backend_service_client
            from app.imou_poller import imou_poller

            is_paused = app_lifecycle.is_paused
            last_state = "UNKNOWN"
            last_timestamp = "Never"
            device_id = getattr(self.config, "IMOU_DEVICE_ID", Config.IMOU_DEVICE_ID)

            try:
                client = get_backend_service_client()
                # Query system_state using UUID
                state_res = client.table("system_state").select("is_paused").eq("id", "00000000-0000-0000-0000-000000000001").execute()
                if state_res.data:
                    is_paused = state_res.data[0].get("is_paused", is_paused)
                    # Sync local app_lifecycle state with the database
                    app_lifecycle.is_paused = is_paused

                # Fetch single most recent row entry from public.camera_logs sorted by triggered_at descending
                logs_res = client.table("camera_logs").select("event_type", "triggered_at").order("triggered_at", desc=True).limit(1).execute()
                if logs_res.data:
                    last_state = logs_res.data[0].get("event_type", "UNKNOWN").upper()
                    last_timestamp = format_to_ist(logs_res.data[0].get("triggered_at"))
            except Exception as e:
                logger.error("Failed to query database for /status command: %s", str(e))
                last_state = "DATABASE_OFFLINE"

            # Emojis mapping
            # ⏸️ if the system tracking loop is currently paused.
            # Otherwise: 🟢 for Online, 🔴 for Offline
            if is_paused:
                state_emoji = "⏸️"
                camera_emoji = "⏸️"
            else:
                state_emoji = "✅"
                if "ONLINE" in last_state:
                    camera_emoji = "🟢"
                elif "OFFLINE" in last_state:
                    camera_emoji = "🔴"
                else:
                    camera_emoji = "❓"

            last_imou_check = self._format_timestamp(imou_poller.last_poll_timestamp)

            reply = (
                "<b>📊 Imou-Exotel System Status</b>\n\n"
                f"• <b>Monitoring State:</b> {state_emoji} {'Paused' if is_paused else 'Active'}\n"
                f"• <b>Last Known Camera State:</b> {camera_emoji} {last_state}\n"
                f"• <b>Last State Update:</b> <code>{last_timestamp}</code>\n"
                f"• <b>Last Poller Check:</b> <code>{last_imou_check}</code>\n"
                f"• <b>Monitored Device:</b> <code>{device_id}</code>"
            )
            send_telegram_notification(reply, chat_id=sender_chat_id, config=self.config)

        elif base_command == "/checknow":
            from app.imou_poller import imou_poller
            from app.supabase_service import get_backend_service_client
            
            device_id = getattr(self.config, "IMOU_DEVICE_ID", Config.IMOU_DEVICE_ID)
            send_telegram_notification("🔍 <b>Executing instant Imou API camera check...</b>", chat_id=sender_chat_id, config=self.config)
            res = imou_poller.poll_once(ignore_pause=True)
            
            if res.get("status") == "success":
                is_online = res.get("is_online", True)
                state_emoji = "🟢 ONLINE" if is_online else "🔴 OFFLINE"
                
                # Write instant check state update to Supabase camera_logs table
                try:
                    client = get_backend_service_client()
                    log_data = {
                        "device_id": device_id,
                        "event_type": "online" if is_online else "offline",
                        "exotel_call_triggered": not is_online,
                        "telegram_alert_sent": True
                    }
                    client.table("camera_logs").insert(log_data).execute()
                    logger.info("Successfully logged checknow status to database.")
                except Exception as log_err:
                    logger.error("Failed to write checknow status to database logs: %s", str(log_err))
                
                reply = f"<b>Instant Check Result:</b> Device <code>{res.get('device_id')}</code> is {state_emoji}."
            else:
                reply = f"❌ <b>Instant Check Failed:</b> {res.get('error') or res.get('reason')}"
            
            send_telegram_notification(reply, chat_id=sender_chat_id, config=self.config)

        elif base_command == "/snapshot":
            self.handle_telegram_snapshot_command(sender_chat_id)

        elif base_command == "/testcall":
            from app.exotel_service import trigger_exotel_call
            device_id = getattr(self.config, "IMOU_DEVICE_ID", Config.IMOU_DEVICE_ID)
            send_telegram_notification("📞 <b>Initiating manual Exotel telephony channel test...</b>", chat_id=sender_chat_id, config=self.config)
            
            try:
                res = trigger_exotel_call(device_id, config=self.config, ignore_lockout=True)
                if res.get("success"):
                    send_telegram_notification("✅ <b>Test Call Placed successfully!</b> Check your phone.", chat_id=sender_chat_id, config=self.config)
                else:
                    reason = res.get("reason") or res.get("error") or "Unknown error"
                    send_telegram_notification(f"⚠️ <b>Test Call Failed:</b> <code>{reason}</code>", chat_id=sender_chat_id, config=self.config)
            except Exception as e:
                logger.exception("Exception in /testcall command: %s", str(e))
                send_telegram_notification(f"⚠️ <b>Test Call Error:</b> <code>{str(e)}</code>", chat_id=sender_chat_id, config=self.config)

        elif base_command == "/stop":
            send_telegram_notification("🛑 <b>Stop command received. Terminating application gracefully...</b>", chat_id=sender_chat_id, config=self.config)
            app_lifecycle.initiate_stop()

        else:
            send_telegram_notification("ℹ️ <b>Available Commands:</b> /pause, /resume, /status, /checknow, /snapshot, /testcall, /stop", chat_id=sender_chat_id, config=self.config)

    def _poll_updates(self):
        token = getattr(self.config, "TELEGRAM_BOT_TOKEN", Config.TELEGRAM_BOT_TOKEN)
        if not token or token == "YOUR_TELEGRAM_BOT_TOKEN":
            logger.info("Telegram bot poller loop not started: TELEGRAM_BOT_TOKEN unconfigured.")
            return

        logger.info("Telegram bot control plane poller started.")
        url = f"https://api.telegram.org/bot{token}/getUpdates"

        while not self._stop_event.is_set() and app_lifecycle.is_running:
            try:
                params = {"offset": self._last_update_id + 1, "timeout": 5}
                response = requests.get(url, params=params, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    for update in data.get("result", []):
                        self._last_update_id = update["update_id"]
                        message = update.get("message", {})
                        text = message.get("text", "")
                        sender_chat_id = str(message.get("chat", {}).get("id", ""))
                        from_user_id = str(message.get("from", {}).get("id", ""))
                        
                        if text.startswith("/"):
                            self.process_command(text, sender_chat_id, from_user_id=from_user_id)
                elif response.status_code == 401:
                    logger.error("Telegram Bot Poller Unauthorized: Check TELEGRAM_BOT_TOKEN.")
                    break
            except Exception as e:
                logger.debug("Exception in Telegram polling loop: %s", str(e))

            self._stop_event.wait(timeout=2)
        logger.info("Telegram bot control plane poller stopped.")

    def start(self):
        token = getattr(self.config, "TELEGRAM_BOT_TOKEN", Config.TELEGRAM_BOT_TOKEN)
        if not token or token == "YOUR_TELEGRAM_BOT_TOKEN":
            return
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._poll_updates, name="TelegramBotPollerThread", daemon=True)
            self._thread.start()

    def stop(self):
        thread_to_join = None
        with self._lock:
            self._stop_event.set()
            if self._thread is not None:
                thread_to_join = self._thread
                self._thread = None
        if thread_to_join is not None:
            thread_to_join.join(timeout=3)

# Global telegram poller instance
telegram_bot_poller = TelegramBotPoller()
