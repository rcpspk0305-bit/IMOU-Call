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

    def poll_once(self, ignore_pause: bool = False) -> dict:
        """
        Executes a single polling cycle:
        1. Verify lifecycle and pause state.
        2. Fetch open API accessToken.
        3. Query device online status.
        4. If offline, trigger Exotel call helper function and update device manager.
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

        # Step 3: Trigger action based on status
        if is_online:
            logger.info("Active poll result: Device '%s' is ONLINE. No alert needed.", self.device_id)
            device_manager.handle_device_event(self.device_id, "online")
            return {"status": "success", "device_id": self.device_id, "is_online": True}
        else:
            logger.warning("Active poll result: Device '%s' is OFFLINE! Triggering Exotel call helper...", self.device_id)
            device_manager.handle_device_event(self.device_id, "offline")
            call_result = self.call_handler(self.device_id)
            return {
                "status": "success",
                "device_id": self.device_id,
                "is_online": False,
                "call_triggered": True,
                "call_result": call_result
            }

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
        if self._thread is not None and self._thread.is_alive():
            logger.warning("Imou poller thread is already running.")
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
