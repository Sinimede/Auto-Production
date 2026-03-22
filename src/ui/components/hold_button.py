import tkinter as tk
import time

class HoldButton(tk.Canvas):
    """
    A circular button that requires holding for a specific duration to trigger.
    Provides visual feedback via a filling ring.
    Supports 'normal' and 'disabled' states.
    """
    BG_RED = "#4a1a1a"
    BG_DISABLED = "#2a2a2a"
    ACCENT_RED = "#cc4444"
    ACCENT_DISABLED = "#555555"
    PROGRESS_RED = "#ff6b6b"
    TEXT_WHITE = "#ffffff"
    TEXT_DISABLED = "#888888"

    def __init__(self, parent, on_cancel_fn, size=60, hold_time_ms=1500):
        # Default size reduced to fit better in toolbar
        super().__init__(parent, width=size, height=size, bg=parent.cget("bg"), 
                         highlightthickness=0, borderwidth=0)
        self.on_cancel_fn = on_cancel_fn
        self.size = size
        self.hold_time_ms = hold_time_ms
        self.holding = False
        self.start_time = 0
        self.after_id = None
        self.state = "normal"

        self._draw_initial()

        self.bind("<ButtonPress-1>", self.on_press)
        self.bind("<ButtonRelease-1>", self.on_release)

    def _draw_initial(self):
        self.delete("all")
        padding = 4
        center = self.size / 2
        radius = (self.size / 2) - padding
        
        bg = self.BG_RED if self.state == "normal" else self.BG_DISABLED
        outline = self.ACCENT_RED if self.state == "normal" else self.ACCENT_DISABLED
        text_color = self.TEXT_WHITE if self.state == "normal" else self.TEXT_DISABLED
        
        # Base circle
        self.create_oval(
            center - radius, center - radius,
            center + radius, center + radius,
            fill=bg, outline=outline, width=2, tags="base"
        )
        
        # "CANCEL" text
        self.create_text(
            center, center, 
            text="HOLD", fill=text_color, 
            font=("Segoe UI", 8, "bold"), tags="text"
        )

        # Progress Ring (arc)
        if self.state == "normal":
            ring_padding = 2
            ring_radius = (self.size / 2) - ring_padding
            self.arc = self.create_arc(
                center - ring_radius, center - ring_radius,
                center + ring_radius, center + ring_radius,
                start=90, extent=0, outline=self.PROGRESS_RED, 
                width=3, style=tk.ARC, tags="progress"
            )

    def set_state(self, state):
        """Sets the button state to 'normal' or 'disabled'."""
        if state not in ("normal", "disabled"): return
        self.state = state
        self._draw_initial()

    def on_press(self, event):
        if self.state == "disabled": return
        self.holding = True
        self.start_time = time.time()
        self.update_arc()

    def on_release(self, event):
        if self.state == "disabled": return
        self.holding = False
        if self.after_id:
            self.after_cancel(self.after_id)
            self.after_id = None
        if hasattr(self, 'arc'):
            self.itemconfig(self.arc, extent=0)

    def update_arc(self):
        if not self.holding:
            return

        elapsed = (time.time() - self.start_time) * 1000
        
        if elapsed >= self.hold_time_ms:
            if hasattr(self, 'arc'):
                self.itemconfig(self.arc, extent=-359.9) # Full circle
            self.holding = False
            if self.on_cancel_fn:
                self.on_cancel_fn()
            # Brief visual confirmation before reset
            self.after(200, lambda: self.itemconfig(self.arc, extent=0) if hasattr(self, 'arc') else None)
            return

        # extent is in degrees, negative for clockwise filling from top (90 deg)
        angle = -360 * (elapsed / self.hold_time_ms)
        if hasattr(self, 'arc'):
            self.itemconfig(self.arc, extent=angle)
        
        # Refresh every ~20ms for smooth animation (~50fps)
        self.after_id = self.after(20, self.update_arc)
