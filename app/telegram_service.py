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

def send_telegram_photo(photo_url: str, caption: str, chat_id: Optional[str] = None, config: type = Config) -> bool:
    """
    Sends a photo alert via Telegram Bot API using a URL.
    """
    token = getattr(config, "TELEGRAM_BOT_TOKEN", None) or Config.TELEGRAM_BOT_TOKEN
    target_chat_id = chat_id or getattr(config, "TELEGRAM_ALLOWED_CHAT_ID", None) or Config.TELEGRAM_ALLOWED_CHAT_ID

    if not token or token == "YOUR_TELEGRAM_BOT_TOKEN" or not target_chat_id or target_chat_id == "YOUR_TELEGRAM_ALLOWED_CHAT_ID":
        logger.warning("Telegram photo alert skipped: TELEGRAM_BOT_TOKEN or TELEGRAM_ALLOWED_CHAT_ID not configured.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    payload = {
        "chat_id": target_chat_id,
        "photo": photo_url,
        "caption": caption,
        "parse_mode": "Markdown"
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            logger.info("Telegram photo alert sent successfully to chat_id '%s'", target_chat_id)
            return True
        else:
            logger.error("Failed to send Telegram photo alert. Status: %d, Response: %s", response.status_code, response.text)
            return False
    except requests.RequestException as e:
        logger.exception("Network exception sending Telegram photo alert: %s", str(e))
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

    def _format_timestamp(self, ts: float) -> str:
        return format_to_ist(ts)

    def process_command(self, text: str, sender_chat_id: str):
        """
        Processes incoming bot commands with TELEGRAM_ALLOWED_CHAT_ID security check.
        """
        allowed_chat_id = str(getattr(self.config, "TELEGRAM_ALLOWED_CHAT_ID", Config.TELEGRAM_ALLOWED_CHAT_ID)).strip()
        sender_chat_id_str = str(sender_chat_id).strip()

        # Security Check: Restrict commands to TELEGRAM_ALLOWED_CHAT_ID
        if allowed_chat_id != "YOUR_TELEGRAM_ALLOWED_CHAT_ID" and sender_chat_id_str != allowed_chat_id:
            logger.warning("Unauthorized Telegram command attempt from chat_id '%s' (Allowed: '%s')", sender_chat_id_str, allowed_chat_id)
            send_telegram_notification("⚠️ <b>Access Denied:</b> Unauthorized chat ID.", chat_id=sender_chat_id, config=self.config)
            return

        cmd = text.strip().split()[0].lower()
        logger.info("Processing authorized Telegram command '%s' from chat_id '%s'", cmd, sender_chat_id_str)

        if cmd == "/pause":
            app_lifecycle.is_paused = True
            reply = "⛔️ Monitoring paused. Exotel voice alerts disabled."
            send_telegram_notification(reply, chat_id=sender_chat_id, config=self.config)

        elif cmd == "/resume":
            app_lifecycle.is_paused = False
            reply = "✅ Monitoring resumed. Active tracking active."
            send_telegram_notification(reply, chat_id=sender_chat_id, config=self.config)

        elif cmd == "/status":
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

        elif cmd == "/checknow":
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

        elif cmd == "/stop":
            send_telegram_notification("🛑 <b>Stop command received. Terminating application gracefully...</b>", chat_id=sender_chat_id, config=self.config)
            app_lifecycle.initiate_stop()

        else:
            send_telegram_notification("ℹ️ <b>Available Commands:</b> /pause, /resume, /status, /checknow, /stop", chat_id=sender_chat_id, config=self.config)

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
                        
                        if text.startswith("/"):
                            self.process_command(text, sender_chat_id)
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
