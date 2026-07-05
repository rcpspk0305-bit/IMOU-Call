import os
import streamlit as st
from supabase import create_client, Client

SYSTEM_STATE_UUID = "00000000-0000-0000-0000-000000000001"

def get_frontend_client() -> Client:
    url = st.secrets["supabase"]["url"]
    anon_key = st.secrets["supabase"]["anon_key"]
    return create_client(url, anon_key)

def get_backend_service_client() -> Client:
    url = st.secrets["supabase"]["url"]
    service_key = st.secrets["supabase"]["service_role_key"]
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
    # Fixes PGRST204: Discard 'message' key to match target production database schema columns
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