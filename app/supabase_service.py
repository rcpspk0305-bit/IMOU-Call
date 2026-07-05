import os
import streamlit as st
from supabase import create_client, Client

SYSTEM_STATE_UUID = "00000000-0000-0000-0000-000000000001"

def fetch_secret(primary_key: str, section: str = None) -> str:
    """Adaptive secrets resolver checking flat, nested, and OS environment scopes."""
    # 1. Try flat uppercase root (e.g., SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    flat_upper = f"{section.upper()}_{primary_key.upper()}" if section else primary_key.upper()
    if flat_upper in st.secrets:
        return str(st.secrets[flat_upper]).strip()
        
    # 2. Try flat lowercase root (e.g., supabase_url, service_role_key)
    flat_lower = f"{section.lower()}_{primary_key.lower()}" if section else primary_key.lower()
    if flat_lower in st.secrets:
        return str(st.secrets[flat_lower]).strip()
        
    # 3. Try direct key fallback at root
    if primary_key in st.secrets:
        return str(st.secrets[primary_key]).strip()
        
    # 4. Try nested TOML dictionary parsing block (original case)
    if section and section in st.secrets:
        sec_block = st.secrets[section]
        if hasattr(sec_block, "get") or isinstance(sec_block, dict):
            if primary_key in sec_block:
                return str(sec_block[primary_key]).strip()
            # fallback to case-insensitive keys
            if primary_key.lower() in sec_block:
                return str(sec_block[primary_key.lower()]).strip()
            if primary_key.upper() in sec_block:
                return str(sec_block[primary_key.upper()]).strip()
    # 5. Try nested TOML dictionary parsing block (lowercase section name)
    if section and section.lower() in st.secrets:
        sec_block = st.secrets[section.lower()]
        if hasattr(sec_block, "get") or isinstance(sec_block, dict):
            if primary_key.lower() in sec_block:
                return str(sec_block[primary_key.lower()]).strip()
            if primary_key.upper() in sec_block:
                return str(sec_block[primary_key.upper()]).strip()

    # 6. Fallback to OS system environment mapping
    env_val = os.getenv(flat_upper) or os.getenv(flat_lower) or os.getenv(primary_key.upper())
    if env_val:
        return env_val.strip()
        
    raise KeyError(f"Configuration parameter '{primary_key}' under section '{section}' could not be resolved.")

def get_frontend_client() -> Client:
    url = fetch_secret("url", "supabase")
    try:
        anon_key = fetch_secret("anon_key", "supabase")
    except KeyError:
        try:
            anon_key = fetch_secret("anon_public_key", "supabase")
        except KeyError:
            anon_key = fetch_secret("key", "supabase")
    return create_client(url, anon_key)

def get_backend_service_client() -> Client:
    url = fetch_secret("url", "supabase")
    try:
        service_key = fetch_secret("service_role_key", "supabase")
    except KeyError:
        try:
            service_key = fetch_secret("service_key", "supabase")
        except KeyError:
            service_key = fetch_secret("key", "supabase")
    return create_client(url, service_key)

def _execute_with_retry(operation_func):
    return operation_func()

def get_system_paused(supabase_client) -> bool:
    def op():
        return supabase_client.table("system_state").select("is_paused").eq("id", SYSTEM_STATE_UUID).execute()
    try:
        response = _execute_with_retry(op)
        if response.data:
            return response.data[0]["is_paused"]
        return False
    except Exception as e:
        print(f"Error checking system pause status: {str(e)}")
        return False

def log_camera_status(supabase_client, device_id, event_type, exotel_success, telegram_success):
    # Enforce strict production schema parameters (Discards non-existent 'message' column)
    clean_payload = {
        "device_id": str(device_id),
        "event_type": str(event_type).lower(),
        "exotel_call_triggered": bool(exotel_success),
        "telegram_alert_sent": bool(telegram_success)
    }
    def op():
        return supabase_client.table("camera_logs").insert(clean_payload).execute()
    try:
        return _execute_with_retry(op)
    except Exception as e:
        print(f"Database write execution failed: {str(e)}")
        return None