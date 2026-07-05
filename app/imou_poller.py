import time
import logging
import threading
from typing import Optional, Callable
from app.config import Config
from app.imou_service import imou_service, ImouService
from app.exotel_service import trigger_exotel_call
from app.device_manager import device_manager
from app.lifecycle import app_lifecycle

logger = logging.getLogger(__name__)

class ImouPoller:
    """
    Background worker thread that actively polls the Imou API every 10-15 minutes (default: 600s)
    to monitor camera online status and trigger Exotel calls when offline.
    Controlled cleanly by the app lifecycle event flag and is_paused state.
    """
    def __init__(
        self,
        config: type = Config,
        service: Optional[ImouService] = None,
        call_handler: Optional[Callable] = None,
        poll_interval_seconds: Optional[int] = None,
        device_id: Optional[str] = None
    ):
        self.config = config
        self.imou_service = service if service is not None else imou_service
        self.call_handler = call_handler if call_handler is not None else trigger_exotel_call
        self.poll_interval_seconds = poll_interval_seconds if poll_interval_seconds is not None else config.IMOU_POLL_INTERVAL_SECONDS
        self.device_id = device_id if device_id is not None else config.IMOU_DEVICE_ID

        self.last_poll_timestamp: float = 0.0
        self._poll_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # Track persistent state
        self.last_known_state = "ONLINE"
        self.offline_alerts_sent = 0
        self.last_offline_alert_time = 0.0
        self.last_processed_alarm_id = None

    def poll_once(self, ignore_pause: bool = False) -> dict:
        """
        Executes a single polling cycle:
        1. Verify lifecycle and pause state.
        2. Fetch open API accessToken.
        3. Query device online status.
        4. Trigger actions based on escalated alerting lifecycle rules.
        """
        if not app_lifecycle.is_running:
            logger.info("Imou poller poll_once skipped: application lifecycle is stopping.")
            return {"status": "skipped", "reason": "lifecycle_stopping"}

        # Requirement 2: Check if monitoring is paused
        if app_lifecycle.is_paused and not ignore_pause:
            logger.info("Monitoring is currently paused. Skipping cycle.")
            return {"status": "skipped", "reason": "monitoring_paused"}

        if not self.device_id or self.device_id == "YOUR_IMOU_DEVICE_ID":
            logger.warning("Imou poller skipped: IMOU_DEVICE_ID is not configured.")
            return {"status": "skipped", "reason": "unconfigured_device_id"}

        logger.info("Starting active Imou status poll cycle for device '%s'", self.device_id)

        with self._poll_lock:
            self.last_poll_timestamp = time.time()

        # Step 1: Fetch accessToken
        token, err = self.imou_service.get_access_token()
        if err or not token:
            logger.error("Active poll failed: Could not retrieve Imou access token. Error: %s", err)
            return {"status": "error", "error": f"Token error: {err}"}

        # Step 2: Query device online status
        is_online, err = self.imou_service.get_device_online_status(self.device_id, access_token=token)
        if err or is_online is None:
            logger.error("Active poll failed: Could not query device online status for '%s'. Error: %s", self.device_id, err)
            return {"status": "error", "error": f"Status query error: {err}"}

        # Check for human detection alarms via getAlarmMessageList
        try:
            self.check_human_alarms()
        except Exception as ex_err:
            logger.exception("Error checking human detection alarms: %s", str(ex_err))

        # Step 3: Trigger action based on status
        if is_online:
            if self.last_known_state == "OFFLINE":
                logger.warning("Recovery detected: Device '%s' transitioned from OFFLINE back to ONLINE. Executing recovery alerts.", self.device_id)
                call_result = None
                
                # Check if handler supports ignore_lockout / is_recovery (like mock vs real)
                import inspect
                try:
                    sig = inspect.signature(self.call_handler)
                    has_kwargs = 'ignore_lockout' in sig.parameters
                except Exception:
                    has_kwargs = False
                
                try:
                    if has_kwargs or self.call_handler == trigger_exotel_call:
                        call_result = self.call_handler(self.device_id, ignore_lockout=True, is_recovery=True)
                    else:
                        call_result = self.call_handler(self.device_id)
                        from app.telegram_service import send_telegram_notification
                        send_telegram_notification(
                            f"✅ <b>CAMERA RECOVERY ALERT!</b>\n"
                            f"Camera <code>{self.device_id}</code> is back ONLINE!",
                            config=self.config
                        )
                except Exception as ex_err:
                    logger.error("Error executing recovery alert handler: %s", str(ex_err))
                
                # System Reset: reset state immediately after online recovery alert executes
                self.last_known_state = "ONLINE"
                self.offline_alerts_sent = 0
                self.last_offline_alert_time = 0.0
                
                device_manager.handle_device_event(self.device_id, "online")
                return {
                    "status": "success",
                    "device_id": self.device_id,
                    "is_online": True,
                    "recovery_triggered": True,
                    "call_result": call_result
                }
            else:
                logger.info("Active poll result: Device '%s' is ONLINE. No alert needed.", self.device_id)
                device_manager.handle_device_event(self.device_id, "online")
                return {"status": "success", "device_id": self.device_id, "is_online": True}
        else:
            logger.warning("Active poll result: Device '%s' is OFFLINE!", self.device_id)
            self.last_known_state = "OFFLINE"
            device_manager.handle_device_event(self.device_id, "offline")
            
            call_result = None
            alert_fired = False
            
            # Check if handler supports ignore_lockout / is_recovery (like mock vs real)
            import inspect
            try:
                sig = inspect.signature(self.call_handler)
                has_kwargs = 'ignore_lockout' in sig.parameters
            except Exception:
                has_kwargs = False
            
            if self.offline_alerts_sent == 0:
                logger.warning("Offline state detected. Instantly firing Telegram alert and Exotel call.")
                try:
                    if has_kwargs or self.call_handler == trigger_exotel_call:
                        call_result = self.call_handler(self.device_id, ignore_lockout=True, is_recovery=False)
                    else:
                        call_result = self.call_handler(self.device_id)
                        from app.telegram_service import send_telegram_notification
                        send_telegram_notification(
                            f"🚨 <b>CAMERA OFFLINE ALERT!</b>\n"
                            f"Camera <code>{self.device_id}</code> dropped offline!",
                            config=self.config
                        )
                except Exception as ex_err:
                    logger.error("Error executing offline alert handler (round 1): %s", str(ex_err))
                self.offline_alerts_sent = 1
                self.last_offline_alert_time = time.time()
                alert_fired = True
            elif self.offline_alerts_sent == 1:
                elapsed = time.time() - self.last_offline_alert_time
                if elapsed >= 150:
                    logger.warning("Device still offline after %.1f seconds. Triggering second backup round.", elapsed)
                    try:
                        if has_kwargs or self.call_handler == trigger_exotel_call:
                            call_result = self.call_handler(self.device_id, ignore_lockout=True, is_recovery=False)
                        else:
                            call_result = self.call_handler(self.device_id)
                            from app.telegram_service import send_telegram_notification
                            send_telegram_notification(
                                f"🚨 <b>CAMERA OFFLINE ALERT!</b>\n"
                                f"Camera <code>{self.device_id}</code> dropped offline!",
                                config=self.config
                            )
                    except Exception as ex_err:
                        logger.error("Error executing offline alert handler (round 2): %s", str(ex_err))
                    self.offline_alerts_sent = 2
                    alert_fired = True
                else:
                    logger.info("Device still offline, but backup interval not met. Elapsed: %.1f seconds.", elapsed)
            else:
                logger.info("Device still offline, but maximum alert limit reached (2 rounds). No further alerts fired.")

            return {
                "status": "success",
                "device_id": self.device_id,
                "is_online": False,
                "call_triggered": alert_fired,
                "call_result": call_result
            }

    def check_human_alarms(self) -> Optional[str]:
        """
        Hits the Imou Open API 'getAlarmMessageList' endpoint, filters for human detection alarms,
        verifies it's a new alarm, dispatches Telegram photo alerts, and updates last_processed_alarm_id.
        """
        token, err = self.imou_service.get_access_token()
        if err or not token:
            logger.error("Failed to retrieve Imou access token for getAlarmMessageList: %s", err)
            return None

        # Generate system header parameters
        system_time = int(time.time())
        import random, string, uuid, requests
        nonce = str(uuid.uuid4()).replace("-", "")
        sign = self.imou_service._generate_signature(system_time, nonce, self.config.IMOU_APP_SECRET)

        # Generate begin/end time in 'yyyy-MM-dd HH:mm:ss' format
        import datetime
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        begin_dt = now_dt - datetime.timedelta(hours=2) # poll recent 2 hours
        begin_time = begin_dt.strftime("%Y-%m-%d %H:%M:%S")
        end_time = now_dt.strftime("%Y-%m-%d %H:%M:%S")

        payload = {
            "system": {
                "ver": "1.1",
                "sign": sign,
                "appId": self.config.IMOU_APP_ID,
                "time": system_time,
                "nonce": nonce
            },
            "params": {
                "token": token,
                "deviceId": self.device_id,
                "channelId": "0",
                "count": 10,
                "beginTime": begin_time,
                "endTime": end_time
            },
            "id": str(uuid.uuid4()).replace("-", "")
        }

        url = f"{self.config.IMOU_API_BASE_URL.rstrip('/')}/getAlarmMessageList"
        logger.info("Calling getAlarmMessageList for device %s", self.device_id)
        
        try:
            from app.imou_service import _execute_with_retry
            def op():
                return requests.post(url, json=payload, timeout=10)
            response = _execute_with_retry(op)
            if response.status_code != 200:
                logger.error("getAlarmMessageList request failed: HTTP %d: %s", response.status_code, response.text)
                return None

            data = response.json()
            result = data.get("result", {})
            alarm_list = result.get("data", {}).get("alarms", []) or result.get("alarms", []) or data.get("alarms", [])
            if not isinstance(alarm_list, list):
                if isinstance(result.get("data"), list):
                    alarm_list = result["data"]
                else:
                    alarm_list = []

            if not alarm_list:
                return None

            latest_alarm = alarm_list[0]
            if not isinstance(latest_alarm, dict):
                return None

            event_desc = str(latest_alarm.get("name") or latest_alarm.get("type") or latest_alarm.get("eventType") or "").lower()
            alarm_id = latest_alarm.get("alarmId") or latest_alarm.get("msgId")

            # Check if event contains human identifiers
            if "human" in event_desc or "person" in event_desc or "people" in event_desc:
                if alarm_id and alarm_id != self.last_processed_alarm_id:
                    pic_url = latest_alarm.get("picUrl") or latest_alarm.get("picurl") or latest_alarm.get("pic_url")
                    timestamp = latest_alarm.get("time") or latest_alarm.get("timestamp")
                    
                    if pic_url:
                        import io, requests
                        from app.telegram_service import telegram_bot_poller
                        
                        img_resp = requests.get(pic_url, timeout=15)
                        if img_resp.status_code == 200:
                            bio = io.BytesIO(img_resp.content)
                            bio.name = 'alarm_trigger.jpg'
                            
                            chat_id = getattr(self.config, "TELEGRAM_ALLOWED_CHAT_ID", None)
                            caption = f"⚠️ *Security Alert: Human Detected!*\nDevice: `{self.device_id}`\nTime: `{timestamp}`"
                            
                            sent = telegram_bot_poller.bot.send_photo(chat_id, bio, caption)
                            if sent:
                                self.last_processed_alarm_id = alarm_id
                                logger.info("Human detection alert sent successfully. last_processed_alarm_id updated to %s", alarm_id)
                                return alarm_id
            return None
        except Exception as e:
            logger.exception("Exception in check_human_alarms: %s", str(e))
            return None

    def _run_loop(self):
        logger.info("Imou active polling thread started. Interval: %d seconds", self.poll_interval_seconds)
        while not self._stop_event.is_set() and app_lifecycle.is_running:
            try:
                self.poll_once()
            except Exception as e:
                logger.exception("Unexpected exception in Imou polling loop: %s", str(e))
            
            self._stop_event.wait(timeout=self.poll_interval_seconds)
        logger.info("Imou active polling thread stopped.")

    def start(self):
        """Starts the background polling thread if not already running."""
        with self._poll_lock:
            if self._thread is not None and self._thread.is_alive():
                return

            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_loop, name="ImouPollerThread", daemon=True)
            self._thread.start()

    def stop(self):
        """Stops the background polling thread cleanly."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

# Global poller instance
imou_poller = ImouPoller()
