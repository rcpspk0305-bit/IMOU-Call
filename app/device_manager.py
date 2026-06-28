import logging
import threading
from typing import Dict, Optional, Callable
from app.config import Config
from app.exotel_service import trigger_exotel_call

logger = logging.getLogger(__name__)

class DeviceManager:
    """
    Manages camera device online/offline states and schedules safety buffer delays
    to prevent false alarms during brief network blips.
    """
    def __init__(self, buffer_delay_seconds: Optional[int] = None, call_handler: Optional[Callable] = None):
        self.buffer_delay_seconds = buffer_delay_seconds if buffer_delay_seconds is not None else Config.BUFFER_DELAY_SECONDS
        self.call_handler = call_handler if call_handler is not None else trigger_exotel_call
        self._device_states: Dict[str, str] = {}
        self._timers: Dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def handle_device_event(self, device_id: str, status: str) -> dict:
        """
        Processes an incoming device status event ('offline' or 'online').
        """
        status_clean = status.strip().lower()
        with self._lock:
            self._device_states[device_id] = status_clean
            logger.info("Device '%s' status updated to '%s'", device_id, status_clean)

            if status_clean in ("offline", "deviceoffline", "off"):
                if device_id in self._timers and self._timers[device_id].is_alive():
                    logger.info("Alert timer already running for device '%s'. Maintaining active buffer timer.", device_id)
                    return {"device_id": device_id, "status": "offline", "action": "timer_already_active"}

                logger.info(
                    "Scheduling safety buffer timer (%d seconds) for device '%s'.",
                    self.buffer_delay_seconds, device_id
                )
                timer = threading.Timer(
                    self.buffer_delay_seconds,
                    self._on_safety_buffer_expired,
                    args=[device_id]
                )
                self._timers[device_id] = timer
                timer.daemon = True
                timer.start()
                return {"device_id": device_id, "status": "offline", "action": "timer_scheduled", "buffer_seconds": self.buffer_delay_seconds}

            elif status_clean in ("online", "deviceonline", "on"):
                if device_id in self._timers:
                    timer = self._timers.pop(device_id)
                    timer.cancel()
                    logger.info(
                        "Device '%s' came back online within safety buffer window. Cancelled false alarm call!",
                        device_id
                    )
                    return {"device_id": device_id, "status": "online", "action": "timer_cancelled_false_alarm_prevented"}
                return {"device_id": device_id, "status": "online", "action": "status_updated"}

            else:
                logger.warning("Unrecognized device status '%s' for device '%s'", status, device_id)
                return {"device_id": device_id, "status": status, "action": "ignored_unknown_status"}

    def _on_safety_buffer_expired(self, device_id: str):
        """
        Callback executed when the safety buffer timer expires.
        Verifies if the device is still offline before triggering the Exotel voice call.
        """
        with self._lock:
            current_status = self._device_states.get(device_id)
            self._timers.pop(device_id, None)

            if current_status in ("offline", "deviceoffline", "off"):
                logger.warning(
                    "Safety buffer timer expired for device '%s' and device is STILL offline. Triggering Exotel voice call!",
                    device_id
                )
            else:
                logger.info(
                    "Safety buffer timer expired for device '%s', but device status is now '%s'. Skipping call.",
                    device_id, current_status
                )
                return

        try:
            self.call_handler(device_id)
        except Exception as e:
            logger.exception("Failed executing call handler for device '%s': %s", device_id, str(e))

    def stop_all_timers(self):
        """Cancels all active background buffer timers safely."""
        with self._lock:
            count = len(self._timers)
            for device_id, timer in list(self._timers.items()):
                timer.cancel()
            self._timers.clear()
            logger.info("Cancelled all %d active device manager timers.", count)

    def get_device_status(self, device_id: str) -> Optional[str]:
        with self._lock:
            return self._device_states.get(device_id)

    def is_timer_active(self, device_id: str) -> bool:
        with self._lock:
            timer = self._timers.get(device_id)
            return timer is not None and timer.is_alive()

# Global singleton instance for app usage
device_manager = DeviceManager()
