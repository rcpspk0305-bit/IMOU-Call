import os
import threading
import logging
from typing import Optional
from supabase import create_client, Client
from app.config import Config
from app.supabase_service import get_backend_service_client

logger = logging.getLogger(__name__)

class SupabaseDbClient:
    """
    Thread-safe database client utility encapsulating database queries
    using the Supabase Service Role client credentials.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self.client: Optional[Client] = None
        
        try:
            self.client = get_backend_service_client()
            logger.info("Supabase db_client initialized successfully via get_backend_service_client().")
        except Exception as e:
            logger.warning("Supabase credentials not configured for db_client: %s. Using fallback mode.", str(e))

    def get_system_paused(self, fallback: bool = False) -> Optional[bool]:
        """
        Thread-safe query to fetch the 'is_paused' boolean from system_state table (id=1).
        """
        if not self.client:
            logger.warning("Supabase client uninitialized. get_system_paused returning fallback: %s", fallback)
            return fallback

        from postgrest.exceptions import APIError

        with self._lock:
            try:
                response = self.client.table("system_state").select("is_paused").eq("id", "00000000-0000-0000-0000-000000000001").execute()
                if response.data:
                    row = response.data[0]
                    return bool(row.get("is_paused", fallback))
            except APIError as api_err:
                logger.error("Postgrest APIError executing get_system_paused query: %s", str(api_err))
                return None
            except Exception as e:
                logger.exception("Error executing get_system_paused query: %s", str(e))
            return fallback

    def log_camera_drop(self, device_id: str, message: str) -> Optional[bool]:
        """
        Thread-safe insertion of a new log row into the camera_logs table when a camera drops.
        """
        if not self.client:
            logger.error("Supabase client uninitialized. log_camera_drop aborted.")
            return False

        from postgrest.exceptions import APIError

        with self._lock:
            try:
                data = {
                    "device_id": device_id,
                    "event_type": "offline",
                    "exotel_call_triggered": True,
                    "telegram_alert_sent": True
                }
                response = self.client.table("camera_logs").insert(data).execute()
                if response.data:
                    logger.info("Successfully recorded camera drop in camera_logs table.")
                    return True
            except APIError as api_err:
                logger.error("Postgrest APIError executing log_camera_drop query: %s", str(api_err))
                return None
            except Exception as e:
                logger.exception("Error executing log_camera_drop query: %s", str(e))
            return False

    def get_session_heartbeat(self) -> Optional[str]:
        """
        Thread-safe query to fetch the 'last_active_at' timestamp from system_state table (id=1).
        """
        if not self.client:
            logger.warning("Supabase client uninitialized. get_session_heartbeat returning None")
            return None

        from postgrest.exceptions import APIError

        with self._lock:
            try:
                response = self.client.table("system_state").select("*").eq("id", "00000000-0000-0000-0000-000000000001").execute()
                if response.data:
                    row = response.data[0]
                    return row.get("last_active_at") or row.get("updated_at") or row.get("triggered_at")
            except APIError as api_err:
                logger.error("Postgrest APIError executing get_session_heartbeat query: %s", str(api_err))
                return None
            except Exception as e:
                logger.exception("Error executing get_session_heartbeat query: %s", str(e))
                return None
            return None

# Global database client instance
db_client = SupabaseDbClient()
