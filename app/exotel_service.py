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

def fetch_exotel_credential(key: str, config: type = Config) -> str:
    """
    Adaptive credential scanner for Exotel settings.
    Scans flat scopes, nested st.secrets["exotel"], environment variables, and Config class.
    """
    import streamlit as st
    import os

    key_upper = key.upper()
    key_lower = key.lower()

    # 1. Check nested st.secrets["exotel"] block
    try:
        if "exotel" in st.secrets:
            ex_block = st.secrets["exotel"]
            if hasattr(ex_block, "get") or isinstance(ex_block, dict):
                if key in ex_block:
                    return str(ex_block[key]).strip()
                if key_lower in ex_block:
                    return str(ex_block[key_lower]).strip()
                if key_upper in ex_block:
                    return str(ex_block[key_upper]).strip()
    except Exception:
        pass

    # 2. Check flat st.secrets root with prefix EXOTEL_
    flat_exotel_upper = f"EXOTEL_{key_upper}"
    flat_exotel_lower = f"exotel_{key_lower}"
    try:
        if flat_exotel_upper in st.secrets:
            return str(st.secrets[flat_exotel_upper]).strip()
        if flat_exotel_lower in st.secrets:
            return str(st.secrets[flat_exotel_lower]).strip()
    except Exception:
        pass

    # 3. Check flat st.secrets root directly
    try:
        if key_upper in st.secrets:
            return str(st.secrets[key_upper]).strip()
        if key_lower in st.secrets:
            return str(st.secrets[key_lower]).strip()
        if key in st.secrets:
            return str(st.secrets[key]).strip()
    except Exception:
        pass

    # 4. Check environment variables
    env_val = (
        os.getenv(flat_exotel_upper) or
        os.getenv(flat_exotel_lower) or
        os.getenv(key_upper) or
        os.getenv(key_lower) or
        os.getenv(key)
    )
    if env_val:
        return env_val.strip()

    # 5. Fallback to passed config attributes or Config class
    for cfg in (config, Config):
        if cfg is None:
            continue
        # Check matching uppercase config attributes
        cfg_upper = f"EXOTEL_{key_upper}"
        if hasattr(cfg, cfg_upper):
            return str(getattr(cfg, cfg_upper)).strip()
        if hasattr(cfg, key_upper):
            return str(getattr(cfg, key_upper)).strip()
        
        # Check special alias mappings
        if key_upper == "TO_PHONE" and hasattr(cfg, "FROM_NUMBER"):
            return str(getattr(cfg, "FROM_NUMBER")).strip()
        if key_upper == "VIRTUAL_NUMBER" and hasattr(cfg, "CALLER_ID"):
            return str(getattr(cfg, "CALLER_ID")).strip()
        if key_upper == "APP_ID" and hasattr(cfg, "APP_ID"):
            return str(getattr(cfg, "APP_ID")).strip()

    return ""

def trigger_exotel_call(device_id: str, config: type = Config, ignore_lockout: bool = False, is_recovery: bool = False) -> dict:
    """
    Executes an outbound HTTP POST call to the Exotel API to trigger the custom Call Flow Applet.
    Includes Agent Lockout protection and immediate Telegram alert notifications.
    Supports bypassing lockout rules, adaptive credential resolution, and online recovery confirmations.
    """
    global _last_alert_time
    now = time.time()

    # Resolve credentials adaptively
    api_sid = fetch_exotel_credential("api_sid", config) or fetch_exotel_credential("sid", config)
    api_key = fetch_exotel_credential("api_key", config) or fetch_exotel_credential("key", config)
    api_token = fetch_exotel_credential("api_token", config) or fetch_exotel_credential("token", config)
    to_phone = fetch_exotel_credential("to_phone", config) or fetch_exotel_credential("from_number", config)
    virtual_number = fetch_exotel_credential("virtual_number", config) or fetch_exotel_credential("caller_id", config)
    app_id = fetch_exotel_credential("app_id", config)
    subdomain = fetch_exotel_credential("subdomain", config) or "api.exotel.com"

    lockout_window = getattr(config, "EXOTEL_CALL_LOCKOUT_SECONDS", 1800)
    quiet_zone = 1200  # Enforce a mandatory 20-minute quiet zone (1200 seconds)

    # 1. Enforce strict anti-spam quiet zone after last alert finished
    if not ignore_lockout:
        with _lockout_lock:
            elapsed_since_last_alert = now - _last_alert_time
            if _last_alert_time > 0.0 and elapsed_since_last_alert < quiet_zone:
                remaining = int(quiet_zone - elapsed_since_last_alert)
                logger.warning(
                    "STRICT ANTI-SPAM LOCK ACTIVE: Only %.1f seconds passed since last alert call. Suppressing alert.",
                    elapsed_since_last_alert
                )
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

    # 2. IMPLEMENT AN AGENT LOCKOUT: Verify lockout interval
    if not ignore_lockout:
        with _lockout_lock:
            last_call = _last_call_timestamps.get(device_id, 0.0)
            elapsed = now - last_call

            if last_call > 0 and elapsed < lockout_window:
                logger.warning(
                    "AGENT LOCKOUT ACTIVE for device '%s': Last call placed %.1f seconds ago. Suppressing call.",
                    device_id, elapsed
                )
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

    url = f"https://{subdomain}/v1/Accounts/{api_sid}/Calls/connect.json"

    # Enforce standard form data serialization and parameter fallback gates
    payload = {
        "From": to_phone,
        "CallerId": virtual_number,
        "CallType": "trans",
        "CustomField": f"device_online:{device_id}" if is_recovery else f"device_offline:{device_id}"
    }

    if app_id:
        applet_url = f"http://my.exotel.in/exoml/start_voice/{app_id}"
        payload["Url"] = applet_url
    else:
        payload["To"] = to_phone

    logger.info(
        "Initiating Exotel call for device '%s'. Subdomain: %s, SID: %s, AppID: %s",
        device_id, subdomain, api_sid, app_id
    )

    try:
        # ATOMIC EXECUTION VALIDATION
        if app_lifecycle.is_paused:
            logger.warning("Abort alert sequence: application is paused right before invoking connection API.")
            return {"success": False, "reason": "paused_before_execution"}
            
        response = requests.post(
            url,
            data=payload,
            auth=(api_key, api_token),
            timeout=10
        )
        
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
        with _lockout_lock:
            _last_alert_time = time.time()
        logger.exception("Network exception encountered when triggering Exotel call for device '%s': %s", device_id, str(e))
        return {
            "success": False,
            "error": str(e)
        }

