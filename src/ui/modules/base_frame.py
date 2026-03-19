
import tkinter as tk
from tkinter import ttk

# Colors
BG_SIDEBAR  = "#1e1e2e"
BG_MAIN     = "#13131f"
BG_CONTENT  = "#2a2a3e"
BG_HEADER   = "#1a1a2a"
ACCENT      = "#0078D4"
ACCENT_DARK = "#005fa3"
TEXT        = "#e0e0e0"
TEXT_DIM    = "#8888aa"
TEXT_WHITE  = "#ffffff"
LOG_BG      = "#0d0d1a"
BORDER      = "#3a3a5a"

# Fonts
FONT_UI     = ("Segoe UI", 10)
FONT_LABEL  = ("Segoe UI", 9)
FONT_TITLE  = ("Segoe UI", 12, "bold")
FONT_NAV    = ("Segoe UI", 10)
FONT_LOG    = ("Consolas", 9)
FONT_BTN    = ("Segoe UI", 10, "bold")

class BaseFrame(tk.Frame):
    """
    Base class for all UI modules.
    Provides shared methods for logging, status and progress updates.
    """
    def __init__(self, parent, service, log_fn, get_asm_path):
        super().__init__(parent, bg=BG_CONTENT)
        self.service = service
        self._log_fn = log_fn
        self._get_asm_path = get_asm_path
        
        self.columnconfigure(1, weight=1)
        
        # Shared UI variables
        self.status_var = tk.StringVar(value="Pronto.")
        self.progress_var = tk.DoubleVar(value=0)
        
        # Configure service callbacks
        if self.service:
            self.service.set_callbacks(
                on_log=self._on_log,
                on_progress=self._on_progress,
                on_status=self._on_status,
                on_finish=self._on_finish,
                on_error=self._on_error
            )

    def _on_log(self, message: str):
        self.after(0, lambda: self._log_fn(message))

    def _on_progress(self, current: int, total: int):
        def update():
            self.progress.configure(maximum=total or 1)
            self.progress_var.set(current)
        self.after(0, update)

    def _on_status(self, status: str):
        self.after(0, lambda: self.status_var.set(status))

    def _on_finish(self, ok_count: int, err_count: int):
        def update():
            self._log_fn("\u2500" * 68)
            self._log_fn(f"Resultado: {ok_count} exportado(s)  |  {err_count} erro(s)")
            self.set_state("normal")
        self.after(0, update)

    def _on_error(self, exception: Exception):
        self.after(0, lambda: self.set_state("normal"))

    def set_state(self, state: str):
        """Override in subclasses to enable/disable buttons."""
        pass
