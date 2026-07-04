import sys
import logging
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)

class AppLifecycle:
    """
    Manages application lifecycle state using threading flags and locks.
    Provides runtime state toggles (is_paused) and clean shutdown mechanisms.
    """
    def __init__(self):
        # Threading event flag controlling the lifecycle loop (True = running, False = stopping)
        self._lifecycle_flag = threading.Event()
        self._lifecycle_flag.set()

        # Globally tracked runtime pause flag
        self._is_paused = False
        self._pause_lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        return self._lifecycle_flag.is_set()

    @property
    def is_paused(self) -> bool:
        with self._pause_lock:
            local_val = self._is_paused
        
        try:
            from app.supabase_service import get_system_paused
            db_val = get_system_paused(fallback=local_val)
            with self._pause_lock:
                self._is_paused = db_val
            return db_val
        except Exception as e:
            logger.error("Exception checking system pause state from database: %s", str(e))
            return local_val

    @is_paused.setter
    def is_paused(self, value: bool):
        val_bool = bool(value)
        try:
            from app.supabase_service import set_system_paused
            set_system_paused(val_bool)
        except Exception as e:
            logger.error("Exception setting system pause state in database: %s", str(e))
            
        with self._pause_lock:
            self._is_paused = val_bool
            logger.info("Application monitoring state updated: is_paused = %s", self._is_paused)

    def get_lifecycle_flag(self) -> threading.Event:
        return self._lifecycle_flag

    def initiate_stop(self, exit_delay_seconds: float = 0.5, exit_func: Optional[Callable] = None) -> dict:
        """
        Safely terminates monitoring loops, closes client sessions, and gracefully calls sys.exit(0).
        """
        if not self.is_running:
            logger.warning("Stop mechanism triggered but application is already stopping.")
            return {"status": "already_stopping", "message": "Shutdown sequence in progress"}

        logger.warning("SHUTDOWN REQUESTED. Toggling lifecycle flag to False...")
        self._lifecycle_flag.clear()

        # 1. Safely terminate monitoring loops and timers
        from app.imou_poller import imou_poller
        from app.device_manager import device_manager
        from app.telegram_service import telegram_bot_poller

        try:
            imou_poller.stop()
            logger.info("Imou background poller terminated successfully.")
        except Exception as e:
            logger.exception("Exception while stopping Imou poller: %s", str(e))

        try:
            telegram_bot_poller.stop()
            logger.info("Telegram bot poller terminated successfully.")
        except Exception as e:
            logger.exception("Exception while stopping Telegram poller: %s", str(e))

        try:
            device_manager.stop_all_timers()
            logger.info("Device manager timers cancelled successfully.")
        except Exception as e:
            logger.exception("Exception while cancelling device manager timers: %s", str(e))

        # 2. Schedule process exit gracefully
        def _deferred_exit():
            logger.info("Application shutdown complete. Gracefully executing sys.exit(0)...")
            if exit_func:
                exit_func(0)
            else:
                sys.exit(0)

        timer = threading.Timer(exit_delay_seconds, _deferred_exit)
        timer.daemon = True
        timer.start()

        return {"status": "stopping", "message": "Application shutdown sequence initiated gracefully"}

# Global singleton lifecycle instance
app_lifecycle = AppLifecycle()
