import time
import logging
import datetime
import threading
import requests
from typing import Optional
from app.config import Config
from app.lifecycle import app_lifecycle

logger = logging.getLogger(__name__)

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

    def _format_timestamp(self, ts: float) -> str:
        if ts <= 0:
            return "Never"
        dt = datetime.datetime.fromtimestamp(ts)
        return dt.strftime("%Y-%m-%d %H:%M:%S")

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
            from app.imou_poller import imou_poller
            from app.exotel_service import get_last_call_timestamp

            status_str = "Paused" if app_lifecycle.is_paused else "Active"
            last_imou_check = self._format_timestamp(imou_poller.last_poll_timestamp)
            device_id = getattr(self.config, "IMOU_DEVICE_ID", Config.IMOU_DEVICE_ID)
            last_exotel_dial = self._format_timestamp(get_last_call_timestamp(device_id))

            reply = (
                "<b>📊 Imou-Exotel System Status</b>\n\n"
                f"• <b>Monitoring State:</b> {'⛔️ Paused' if app_lifecycle.is_paused else '✅ Active'}\n"
                f"• <b>Last Imou Check:</b> {last_imou_check}\n"
                f"• <b>Last Exotel Dial:</b> {last_exotel_dial}\n"
                f"• <b>Monitored Device:</b> <code>{device_id}</code>"
            )
            send_telegram_notification(reply, chat_id=sender_chat_id, config=self.config)

        elif cmd == "/checknow":
            from app.imou_poller import imou_poller
            send_telegram_notification("🔍 <b>Executing instant Imou API camera check...</b>", chat_id=sender_chat_id, config=self.config)
            res = imou_poller.poll_once(ignore_pause=True)
            
            if res.get("status") == "success":
                is_online = res.get("is_online", True)
                state_emoji = "🟢 ONLINE" if is_online else "🔴 OFFLINE"
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
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_updates, name="TelegramBotPollerThread", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

# Global telegram poller instance
telegram_bot_poller = TelegramBotPoller()
