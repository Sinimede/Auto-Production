import tkinter as tk
from tkinter import ttk

# Colors (as per main.py and requirements)
BG_CONTENT  = "#2a2a3e"
ACCENT      = "#0078D4"
TEXT        = "#e0e0e0"
TEXT_DIM    = "#8888aa"
BORDER      = "#3a3a5a"
TEXT_WHITE  = "#ffffff"

# Status Colors
STATUS_IDLE    = TEXT_DIM
STATUS_RUNNING = ACCENT
STATUS_SUCCESS = "#40c057"
STATUS_ERROR   = "#fa5252"

# Fonts
FONT_UI     = ("Segoe UI", 10)
FONT_LABEL  = ("Segoe UI", 9)
FONT_TITLE  = ("Segoe UI", 11, "bold")
FONT_ICON   = ("Segoe UI", 14)

class ProcessCard(tk.Frame):
    """
    A reusable UI component for the Dashboard that represents an export process.
    Features a modern appearance, status indicators, and progress tracking.
    """
    def __init__(self, parent, title, icon_text, on_click_fn):
        super().__init__(
            parent, 
            bg=BG_CONTENT, 
            highlightthickness=1, 
            highlightbackground=BORDER,
            padx=12,
            pady=10
        )
        
        self.title = title
        self.icon_text = icon_text
        self.on_click_fn = on_click_fn
        
        self._setup_ui()
        self._bind_click()
        
    def _setup_ui(self):
        # Configure layout grid
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        
        # Left side: Icon Placeholder
        self.icon_label = tk.Label(
            self, text=self.icon_text,
            bg=BG_CONTENT, fg=ACCENT,
            font=FONT_ICON
        )
        self.icon_label.grid(row=0, column=0, rowspan=2, padx=(0, 12), sticky="nsew")
        
        # Middle: Title and Status text
        self.title_label = tk.Label(
            self, text=self.title,
            bg=BG_CONTENT, fg=TEXT,
            font=FONT_TITLE, anchor="w"
        )
        self.title_label.grid(row=0, column=1, sticky="sw")
        
        self.status_text_label = tk.Label(
            self, text="Ready",
            bg=BG_CONTENT, fg=TEXT_DIM,
            font=FONT_LABEL, anchor="w"
        )
        self.status_text_label.grid(row=1, column=1, sticky="nw")
        
        # Right side: Status Indicator (Circle)
        self.status_indicator = tk.Canvas(
            self, width=12, height=12, 
            bg=BG_CONTENT, highlightthickness=0
        )
        self.status_indicator.grid(row=0, column=2, padx=(10, 0), sticky="ne")
        self.circle = self.status_indicator.create_oval(2, 2, 10, 10, fill=STATUS_IDLE, outline="")
        
        # Bottom: Small Progress Bar
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            self, variable=self.progress_var,
            orient="horizontal", mode="determinate"
        )
        # Note: 'height' is not a standard ttk.Progressbar option in all themes, 
        # so we rely on padding and placement for a 'mini' look.
        self.progress_bar.grid(row=2, column=0, columnspan=3, pady=(10, 0), sticky="ew")
        
    def _bind_click(self):
        """Binds click event to all internal components to ensure the entire card is clickable."""
        widgets = [self, self.icon_label, self.title_label, self.status_text_label, self.status_indicator, self.progress_bar]
        for w in widgets:
            w.bind("<Button-1>", lambda e: self.on_click_fn())
            w.configure(cursor="hand2")
            
    def set_state(self, state, status_text=None):
        """
        Updates the UI components based on the process state.
        States: IDLE, RUNNING, SUCCESS, ERROR
        """
        state = state.upper()
        
        # 1. Update Circle Indicator Color
        color = STATUS_IDLE
        if state == "RUNNING":
            color = STATUS_RUNNING
        elif state == "SUCCESS":
            color = STATUS_SUCCESS
        elif state == "ERROR":
            color = STATUS_ERROR
            
        self.status_indicator.itemconfig(self.circle, fill=color)
        
        # 2. Update Status Text Label
        if status_text:
            self.status_text_label.config(text=status_text)
        else:
            if state == "IDLE":
                self.status_text_label.config(text="Ready")
            elif state == "RUNNING":
                self.status_text_label.config(text="Processing...")
            elif state == "SUCCESS":
                self.status_text_label.config(text="Completed")
            elif state == "ERROR":
                self.status_text_label.config(text="Failed")
                
        # 3. Handle Progress Reset/Fill
        if state == "SUCCESS":
            self.progress_var.set(100)
        elif state == "IDLE":
            self.progress_var.set(0)
            
    def set_progress(self, value):
        """Explicitly set the progress bar value (0-100)."""
        self.progress_var.set(value)
