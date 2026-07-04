import logging
import os
from typing import Optional, List, Dict, Any
from supabase import create_client, Client
from app.config import Config

logger = logging.getLogger(__name__)

try:
    import streamlit as st
except ImportError:
    st = None

def get_frontend_client() -> Client:
    """
    Initializes a frontend public anon Supabase client.
    First tries st.secrets, then falls back to Config.SUPABASE_URL and environment variables.
    """
    url = None
    anon_key = None
    if st is not None:
        try:
            if "supabase" in st.secrets:
                url = st.secrets["supabase"].get("url")
                anon_key = st.secrets["supabase"].get("anon_key")
        except Exception:
            pass
            
    if not url:
        url = Config.SUPABASE_URL
    if not anon_key:
        anon_key = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_KEY")
        
    if not url or url == "YOUR_SUPABASE_URL" or not anon_key or anon_key == "YOUR_SUPABASE_SERVICE_ROLE_KEY":
        raise ValueError("Supabase frontend credentials (anon_key) are not configured.")
        
    return create_client(url, anon_key)

def get_backend_service_client() -> Client:
    """
    Initializes an administrative service role Supabase client.
    First tries st.secrets, then falls back to Config.SUPABASE_URL and Config.SUPABASE_KEY.
    """
    url = None
    service_role_key = None
    if st is not None:
        try:
            if "supabase" in st.secrets:
                url = st.secrets["supabase"].get("url")
                service_role_key = st.secrets["supabase"].get("service_role_key")
        except Exception:
            pass
            
    if not url:
        url = Config.SUPABASE_URL
    if not service_role_key:
        service_role_key = Config.SUPABASE_KEY
        
    if not url or url == "YOUR_SUPABASE_URL" or not service_role_key or service_role_key == "YOUR_SUPABASE_SERVICE_ROLE_KEY":
        raise ValueError("Supabase backend service credentials (service_role_key) are not configured.")
        
    return create_client(url, service_role_key)

# Fallback/mock client if credentials are not configured or invalid to prevent startup crashes
supabase_client: Optional[Client] = None

try:
    supabase_client = get_backend_service_client()
    logger.info("Supabase service client initialized successfully via get_backend_service_client().")
except Exception as e:
    logger.warning("Could not initialize Supabase service client: %s. Using mock/none fallback client.", str(e))

import time
import random

def _execute_with_retry(operation_func, max_attempts=3, base_delay=1.0, max_delay=10.0):
    """
    Executes a database operation function with exponential backoff retries.
    If all attempts fail, it raises the last exception so the caller can handle it.
    """
    attempt = 1
    delay = base_delay
    while True:
        try:
            return operation_func()
        except Exception as e:
            if attempt >= max_attempts:
                logger.error("Supabase operation failed after %d consecutive attempts. Error: %s", attempt, str(e))
                raise e
            
            jitter = random.uniform(0, 0.1 * delay)
            sleep_time = min(delay + jitter, max_delay)
            logger.warning("Supabase attempt %d failed: %s. Retrying in %.2f seconds...", attempt, str(e), sleep_time)
            time.sleep(sleep_time)
            attempt += 1
            delay *= 2

def get_system_paused(fallback: bool = False) -> bool:
    """
    Queries the 'system_state' table to check if the monitoring application is paused.
    Falls back to the provided fallback value if Supabase is unconfigured or a query failure occurs.
    """
    if supabase_client is None:
        return fallback
    try:
        def op():
            return supabase_client.table("system_state").select("is_paused").eq("id", "00000000-0000-0000-0000-000000000001").execute()
        response = _execute_with_retry(op)
        if isinstance(response.data, list) and len(response.data) > 0:
            return bool(response.data[0].get("is_paused", fallback))
        else:
            # Seed the row if missing (only if it returned a real empty list)
            if isinstance(response.data, list):
                logger.info("system_state row 00000000-0000-0000-0000-000000000001 not found. Seeding is_paused = False...")
                def seed_op():
                    return supabase_client.table("system_state").insert({"id": "00000000-0000-0000-0000-000000000001", "is_paused": False}).execute()
                _execute_with_retry(seed_op)
    except Exception as e:
        logger.exception("Error querying is_paused state from Supabase after retries: %s", str(e))
    return fallback

def set_system_paused(paused: bool) -> bool:
    """
    Updates the 'is_paused' status in the 'system_state' table.
    """
    if supabase_client is None:
        logger.error("Supabase client is not initialized. Cannot set pause state.")
        return False
    try:
        def op():
            return supabase_client.table("system_state").update({"is_paused": paused}).eq("id", "00000000-0000-0000-0000-000000000001").execute()
        response = _execute_with_retry(op)
        if isinstance(response.data, list) and len(response.data) > 0:
            logger.info("Successfully updated database pause state to: %s", paused)
            return True
    except Exception as e:
        logger.exception("Error updating is_paused state in Supabase after retries: %s", str(e))
    return False

def log_camera_status(device_id: str, status: str, message: str, notification_sent: bool = True) -> bool:
    """
    Appends a new log row to the 'camera_logs' table to capture status changes or alerts.
    """
    if supabase_client is None:
        logger.error("Supabase client is not initialized. Cannot log status change.")
        return False
    try:
        data = {
            "device_id": device_id,
            "status": status,
            "message": message,
            "notification_sent": notification_sent
        }
        def op():
            return supabase_client.table("camera_logs").insert(data).execute()
        response = _execute_with_retry(op)
        if isinstance(response.data, list) and len(response.data) > 0:
            logger.info("Successfully logged status change in Supabase camera_logs.")
            return True
    except Exception as e:
        logger.exception("Error writing status log to Supabase after retries: %s", str(e))
    return False

def fetch_recent_logs(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Fetches recent offline alert logs from the Supabase history table.
    """
    if supabase_client is None:
        logger.warning("Supabase client not initialized. Cannot fetch recent logs.")
        return []
    try:
        def op():
            return supabase_client.table("camera_logs")\
                .select("*")\
                .order("created_at", desc=True)\
                .limit(limit)\
                .execute()
        response = _execute_with_retry(op)
        if isinstance(response.data, list):
            return response.data
        return []
    except Exception as e:
        logger.exception("Error fetching log history from Supabase after retries: %s", str(e))
    return []

