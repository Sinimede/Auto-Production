
import threading
from typing import Callable, Any, Dict, Optional

class BaseService:
    """
    Base class for all business logic services.
    Handles threading and callback management.
    """
    def __init__(self, sw_client):
        self.sw = sw_client
        self._callbacks: Dict[str, Optional[Callable]] = {
            'log': None,
            'progress': None,
            'status': None,
            'finish': None,
            'error': None
        }
        self._is_running = False
        self._stop_event = threading.Event()

    def stop(self):
        """Request the service to stop."""
        self._stop_event.set()

    def set_callbacks(self, 
                      on_log: Callable[[str], None] = None, 
                      on_progress: Callable[[int, int], None] = None, 
                      on_status: Callable[[str], None] = None, 
                      on_finish: Callable[[int, int], None] = None,
                      on_error: Callable[[Exception], None] = None):
        """Registers UI callbacks."""
        if on_log: self._callbacks['log'] = on_log
        if on_progress: self._callbacks['progress'] = on_progress
        if on_status: self._callbacks['status'] = on_status
        if on_finish: self._callbacks['finish'] = on_finish
        if on_error: self._callbacks['error'] = on_error

    def _log(self, message: str, level: str = "INFO", tag: Optional[str] = None):
        if self._callbacks['log']:
            # The UI might expect a string or a LogEntry-like structure
            # For now, we pass the parameters and let the UI handle it.
            self._callbacks['log'](message, level, tag)

    def _set_progress(self, current: int, total: int):
        if self._callbacks['progress']:
            self._callbacks['progress'](current, total)

    def _set_status(self, status: str):
        if self._callbacks['status']:
            self._callbacks['status'](status)

    def _finish(self, ok_count: int, err_count: int):
        self._is_running = False
        if self._callbacks['finish']:
            self._callbacks['finish'](ok_count, err_count)

    def _handle_error(self, exception: Exception):
        self._log(f"ERRO FATAL: {exception}")
        if self._callbacks['error']:
            self._callbacks['error'](exception)
        self._finish(0, 1)

    def run_async(self, target, *args):
        """Helper to run a method in a background thread."""
        if self._is_running:
            return
        self._is_running = True
        threading.Thread(target=target, args=args, daemon=True).start()
