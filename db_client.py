import os
import threading
import logging
from typing import Optional
from supabase import create_client, Client
from app.config import Config

logger = logging.getLogger(__name__)

# Fetch Supabase parameters from centralized Config
SUPABASE_URL = Config.SUPABASE_URL
SUPABASE_KEY = Config.SUPABASE_KEY

class SupabaseDbClient:
    """
    Thread-safe database client utility encapsulating database queries
    using the Supabase Service Role client credentials.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self.client: Optional[Client] = None
        
        # Initialize client if environment variables are configured
        if SUPABASE_URL and SUPABASE_URL != "YOUR_SUPABASE_URL" and SUPABASE_KEY and SUPABASE_KEY != "YOUR_SUPABASE_SERVICE_ROLE_KEY":
            try:
                self.client = create_client(SUPABASE_URL, SUPABASE_KEY)
                logger.info("Supabase db_client initialized successfully.")
            except Exception as e:
                logger.exception("Failed to initialize Supabase client inside db_client: %s", str(e))
        else:
            logger.warning("Supabase credentials not configured in environment. Using fallback mode.")

    def get_system_paused(self, fallback: bool = False) -> bool:
        """
        Thread-safe query to fetch the 'is_paused' boolean from system_state table (id=1).
        """
        if not self.client:
            logger.warning("Supabase client uninitialized. get_system_paused returning fallback: %s", fallback)
            return fallback

        with self._lock:
            try:
                response = self.client.table("system_state").select("is_paused").eq("id", 1).execute()
                if response.data:
                    return bool(response.data[0]["is_paused"])
            except Exception as e:
                logger.exception("Error executing get_system_paused query: %s", str(e))
            return fallback

    def log_camera_drop(self, device_id: str, message: str) -> bool:
        """
        Thread-safe insertion of a new log row into the camera_logs table when a camera drops.
        """
        if not self.client:
            logger.error("Supabase client uninitialized. log_camera_drop aborted.")
            return False

        with self._lock:
            try:
                data = {
                    "device_id": device_id,
                    "status": "offline",
                    "message": message,
                    "notification_sent": True
                }
                response = self.client.table("camera_logs").insert(data).execute()
                if response.data:
                    logger.info("Successfully recorded camera drop in camera_logs table.")
                    return True
            except Exception as e:
                logger.exception("Error executing log_camera_drop query: %s", str(e))
            return False

# Global database client instance
db_client = SupabaseDbClient()
