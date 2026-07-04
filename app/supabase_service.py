import logging
from typing import Optional, List, Dict, Any
from supabase import create_client, Client
from app.config import Config

logger = logging.getLogger(__name__)

# Initialize Supabase client
supabase_url = Config.SUPABASE_URL
supabase_key = Config.SUPABASE_KEY

# Fallback/mock client if credentials are not configured or invalid to prevent startup crashes
supabase_client: Optional[Client] = None

if supabase_url and supabase_url != "YOUR_SUPABASE_URL" and supabase_key and supabase_key != "YOUR_SUPABASE_SERVICE_ROLE_KEY":
    try:
        supabase_client = create_client(supabase_url, supabase_key)
        logger.info("Supabase client initialized successfully.")
    except Exception as e:
        logger.exception("Failed to initialize Supabase client: %s", str(e))
else:
    logger.warning("Supabase credentials not fully configured. Using mock/none fallback client.")

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
            return supabase_client.table("system_state").select("is_paused").eq("id", 1).execute()
        response = _execute_with_retry(op)
        if isinstance(response.data, list) and len(response.data) > 0:
            return bool(response.data[0].get("is_paused", fallback))
        else:
            # Seed the row if missing (only if it returned a real empty list)
            if isinstance(response.data, list):
                logger.info("system_state row 1 not found. Seeding is_paused = False...")
                def seed_op():
                    return supabase_client.table("system_state").insert({"id": 1, "is_paused": False}).execute()
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
            return supabase_client.table("system_state").update({"is_paused": paused}).eq("id", 1).execute()
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

