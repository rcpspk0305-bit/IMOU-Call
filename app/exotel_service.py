import time
import logging
import threading
import requests
from typing import Dict
from app.config import Config
from app.telegram_service import send_telegram_notification
from app.lifecycle import app_lifecycle

logger = logging.getLogger(__name__)

# Thread-safe dictionary tracking last_call_timestamp per device_id
_last_call_timestamps: Dict[str, float] = {}
_lockout_lock = threading.Lock()

# Checkpoint for strict anti-spam lock (mandatory 20-minute quiet zone globally after an Exotel call finishes executing)
_last_alert_time = 0.0

def reset_lockout(device_id: str | None = None):
    """Utility function to clear lockout timestamps (used mainly in tests)."""
    global _last_alert_time
    with _lockout_lock:
        _last_alert_time = 0.0
        if device_id:
            _last_call_timestamps.pop(device_id, None)
        else:
            _last_call_timestamps.clear()

def get_last_call_timestamp(device_id: str) -> float:
    """Returns the last call timestamp for a device."""
    with _lockout_lock:
        return _last_call_timestamps.get(device_id, 0.0)

def trigger_exotel_call(device_id: str, config: type = Config, ignore_lockout: bool = False, is_recovery: bool = False) -> dict:
    """
    Executes an outbound HTTP POST call to the Exotel API to trigger the custom Call Flow Applet.
    Includes Agent Lockout protection and immediate Telegram alert notifications.
    Supports bypassing lockout rules and sending online recovery confirmations.
    """
    global _last_alert_time
    now = time.time()
    lockout_window = getattr(config, "EXOTEL_CALL_LOCKOUT_SECONDS", 1800)
    quiet_zone = 1200  # Enforce a mandatory 20-minute quiet zone (1200 seconds)

    # 1. Enforce strict anti-spam quiet zone after last alert finished
    if not ignore_lockout:
        with _lockout_lock:
            elapsed_since_last_alert = now - _last_alert_time
            if _last_alert_time > 0.0 and elapsed_since_last_alert < quiet_zone:
                remaining = int(quiet_zone - elapsed_since_last_alert)
                logger.warning(
                    "STRICT ANTI-SPAM LOCK ACTIVE: Only %.1f seconds passed since last alert call (quiet zone is 20m / 1200s). Alert suppressed. Remaining: %ds",
                    elapsed_since_last_alert, remaining
                )
                # Send digital record to Telegram that the alert is suppressed by strict anti-spam lock
                send_telegram_notification(
                    f"⚠️ <b>ALERT SUPPRESSED (Anti-Spam Quiet Zone):</b> Camera <code>{device_id}</code> is offline. "
                    f"Global quiet zone active for another {remaining} seconds.",
                    config=config
                )
                return {
                    "success": False,
                    "reason": "anti_spam_quiet_zone_active",
                    "suppressed": True,
                    "elapsed_seconds": round(elapsed_since_last_alert, 1),
                    "quiet_zone_seconds": quiet_zone
                }

    # 2. IMPLEMENT AN AGENT LOCKOUT: Verify at least 30 minutes passed since last call
    if not ignore_lockout:
        with _lockout_lock:
            last_call = _last_call_timestamps.get(device_id, 0.0)
            elapsed = now - last_call

            if last_call > 0 and elapsed < lockout_window:
                logger.warning(
                    "AGENT LOCKOUT ACTIVE for device '%s': Last call placed %.1f seconds ago (lockout is %ds). Call suppressed.",
                    device_id, elapsed, lockout_window
                )
                # Send digital record to Telegram even when call is suppressed by lockout
                send_telegram_notification(
                    f"⚠️ <b>ALERT SUPPRESSED (Agent Lockout):</b> Camera <code>{device_id}</code> is still OFFLINE! "
                    f"Last call was placed {int(elapsed)}s ago (Lockout: {lockout_window}s).",
                    config=config
                )
                return {
                    "success": False,
                    "reason": "agent_lockout_active",
                    "suppressed": True,
                    "elapsed_seconds": round(elapsed, 1),
                    "lockout_seconds": lockout_window
                }

    # Record timestamp for this call attempt
    with _lockout_lock:
        _last_call_timestamps[device_id] = now

    # Append state log to Supabase 'camera_logs' table before executing notification sequences
    try:
        from app.supabase_service import log_camera_status, supabase_client
        log_camera_status(
            supabase_client,
            device_id,
            "online" if is_recovery else "offline",
            True,
            True
        )
    except Exception as e:
        logger.exception("Failed to log state to Supabase: %s", str(e))

    # Send Telegram text notification IMMEDIATELY alongside Exotel phone call routine
    if is_recovery:
        send_telegram_notification(
            f"✅ <b>CAMERA RECOVERY ALERT!</b>\n"
            f"Camera <code>{device_id}</code> is back ONLINE!\n"
            f"📞 Triggering recovery confirmation voice call...",
            config=config
        )
    else:
        send_telegram_notification(
            f"🚨 <b>CAMERA OFFLINE ALERT!</b>\n"
            f"Camera <code>{device_id}</code> dropped offline!\n"
            f"📞 Triggering automated Exotel voice call now...",
            config=config
        )

    url = f"https://{config.EXOTEL_SUBDOMAIN}/v1/Accounts/{config.EXOTEL_SID}/Calls/connect.json"
    applet_url = f"http://my.exotel.in/exoml/start_voice/{config.APP_ID}"

    payload = {
        "From": config.FROM_NUMBER,
        "CallerId": config.CALLER_ID,
        "Url": applet_url,
        "CustomField": f"device_online:{device_id}" if is_recovery else f"device_offline:{device_id}"
    }

    logger.info(
        "Initiating Exotel call for device '%s'. Subdomain: %s, SID: %s, AppID: %s",
        device_id, config.EXOTEL_SUBDOMAIN, config.EXOTEL_SID, config.APP_ID
    )

    try:
        # ATOMIC EXECUTION VALIDATION: Perform a final runtime check of 'is_paused' exactly one line before Exotel API is invoked
        if app_lifecycle.is_paused:
            logger.warning("Abort alert sequence: application is paused right before invoking connection API.")
            return {"success": False, "reason": "paused_before_execution"}
        response = requests.post(
            url,
            data=payload,
            auth=(config.EXOTEL_KEY, config.EXOTEL_TOKEN),
            timeout=10
        )
        
        # Enforce quiet zone immediately after an Exotel call finishes executing
        with _lockout_lock:
            _last_alert_time = time.time()

        if response.status_code in (200, 201):
            logger.info("Exotel call triggered successfully for device '%s'. Response: %s", device_id, response.text)
            return {
                "success": True,
                "status_code": response.status_code,
                "data": response.json() if response.content else {}
            }
        else:
            logger.error(
                "Exotel API request failed for device '%s'. Status Code: %d, Response: %s",
                device_id, response.status_code, response.text
            )
            return {
                "success": False,
                "status_code": response.status_code,
                "error": response.text
            }
    except requests.RequestException as e:
        # Enforce quiet zone immediately after an Exotel call finishes executing (even if failure occurred)
        with _lockout_lock:
            _last_alert_time = time.time()
        logger.exception("Network exception encountered when triggering Exotel call for device '%s': %s", device_id, str(e))
        return {
            "success": False,
            "error": str(e)
        }

