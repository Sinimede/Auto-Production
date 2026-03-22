"""
main.py — Auto Production
Unified export tool for SolidWorks assemblies.
Sidebar navigation, shared assembly path, shared log.

Usage:
    python main.py [--path "C:/path/to/assembly.sldasm"]
"""

import os
import sys
import datetime
import argparse
import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk

# Ensure sibling modules are importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.all_module import AllModule
from modules.dxf_module import DxfModule
from modules.step_module import StepModule
from modules.listas_module import ListasModule

# ---------------------------------------------------------------------------
# Structured Logging
# ---------------------------------------------------------------------------

class LogEntry:
    """Represents a single log entry with structured data."""
    def __init__(self, message: str, level: str = "INFO", tag: str = None):
        self.timestamp = datetime.datetime.now()
        self.message = message
        self.level = level
        self.tag = tag

    def __str__(self) -> str:
        """String representation for display in the log widget."""
        ts = self.timestamp.strftime("%H:%M:%S")
        prefix = f"[{ts}] "
        if self.level != "INFO":
            prefix += f"{self.level}: "
        if self.tag:
            prefix += f"[{self.tag}] "
        return f"{prefix}{self.message}"

# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------

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

FONT_UI     = ("Segoe UI", 10)
FONT_LABEL  = ("Segoe UI", 9)
FONT_TITLE  = ("Segoe UI", 12, "bold")
FONT_NAV    = ("Segoe UI", 10)
FONT_LOG    = ("Consolas", 9)


# ---------------------------------------------------------------------------
# Module registry — add new features here
# ---------------------------------------------------------------------------

MODULES = [
    ("Gerar Tudo",        "all",  AllModule),
    ("DXF Export",        "dxf",  DxfModule),
    ("STEP Export",       "step", StepModule),
    ("Listas",            "listas", ListasModule),
]


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(tk.Tk):
    def __init__(self, initial_path=None):
        super().__init__()
        self.title("Auto Production")
        self.configure(bg=BG_MAIN)
        self.minsize(820, 560)
        self.resizable(True, True)

        self._log_entries = []
        self._initial_path = initial_path

        self._apply_ttk_theme()
        self._build_ui()
        
        if self._initial_path:
            self.asm_var.set(self._initial_path)
            self._log(f"Opened assembly via CLI: {self._initial_path}")
            
        self._switch_module("all")  # Show Gerar Tudo by default

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _apply_ttk_theme(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TProgressbar",
                         troughcolor=BG_MAIN,
                         background=ACCENT,
                         bordercolor=BORDER,
                         lightcolor=ACCENT,
                         darkcolor=ACCENT)
        style.configure("TEntry",
                         fieldbackground=BG_CONTENT,
                         foreground=TEXT,
                         bordercolor=BORDER,
                         insertcolor=TEXT)
        style.map("TEntry", fieldbackground=[("focus", BG_CONTENT)])

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_right_pane()

    def _build_sidebar(self):
        sidebar = tk.Frame(self, bg=BG_SIDEBAR, width=140)
        sidebar.grid(row=0, column=0, sticky="ns")
        sidebar.grid_propagate(False)

        # App title
        tk.Label(
            sidebar, text="Auto\nProduction",
            bg=BG_SIDEBAR, fg=TEXT_WHITE,
            font=FONT_TITLE, pady=18, padx=10,
        ).pack(fill="x")

        tk.Frame(sidebar, bg=BORDER, height=1).pack(fill="x", padx=10)

        # Navigation buttons
        self._nav_buttons = {}
        for label, key, _ in MODULES:
            btn = tk.Button(
                sidebar, text=label,
                bg=BG_SIDEBAR, fg=TEXT,
                activebackground=ACCENT, activeforeground=TEXT_WHITE,
                font=FONT_NAV,
                relief="flat", bd=0,
                padx=14, pady=10,
                cursor="hand2",
                anchor="w",
                command=lambda k=key: self._switch_module(k),
            )
            btn.pack(fill="x", padx=0, pady=1)
            self._nav_buttons[key] = btn


    def _build_right_pane(self):
        right = tk.Frame(self, bg=BG_MAIN)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        right.rowconfigure(2, weight=0)

        # Header — shared assembly path
        self._build_header(right)

        # Content area — stacked module frames
        self.content_frame = tk.Frame(right, bg=BG_CONTENT)
        self.content_frame.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        self.content_frame.columnconfigure(0, weight=1)
        self.content_frame.rowconfigure(0, weight=1)

        # Shared log at the bottom
        self._build_log(right)

        # Instantiate modules
        self._module_frames = {}
        for label, key, cls in MODULES:
            frame = cls(
                self.content_frame,
                log_fn=self._log,
                get_asm_path=lambda: self.asm_var.get().strip(),
            )
            frame.grid(row=0, column=0, sticky="nsew")
            self._module_frames[key] = frame

    def _build_header(self, parent):
        header = tk.Frame(parent, bg=BG_HEADER, pady=8)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)

        tk.Label(
            header, text="Assembly (.sldasm):",
            bg=BG_HEADER, fg=TEXT_DIM, font=FONT_LABEL,
        ).grid(row=0, column=0, padx=(14, 6), sticky="e")

        self.asm_var = tk.StringVar()
        asm_entry = tk.Entry(
            header, textvariable=self.asm_var,
            bg=BG_CONTENT, fg=TEXT, insertbackground=TEXT,
            relief="flat", font=FONT_UI,
            highlightthickness=1, highlightbackground=BORDER,
            highlightcolor=ACCENT,
        )
        asm_entry.grid(row=0, column=1, padx=4, pady=2, sticky="ew")

        tk.Button(
            header, text="Browse\u2026",
            command=self._browse_asm,
            bg=BG_CONTENT, fg=TEXT,
            activebackground=ACCENT, activeforeground=TEXT_WHITE,
            relief="flat", font=FONT_LABEL, padx=10, pady=4,
            cursor="hand2",
        ).grid(row=0, column=2, padx=(0, 14))

    def _build_log(self, parent):
        log_frame = tk.Frame(parent, bg=BG_MAIN)
        log_frame.grid(row=2, column=0, sticky="ew", padx=0)
        log_frame.columnconfigure(0, weight=1)

        # Log header row
        log_header = tk.Frame(log_frame, bg=BG_MAIN, pady=4)
        log_header.grid(row=0, column=0, sticky="ew")
        log_header.columnconfigure(0, weight=1)

        tk.Label(
            log_header, text="Log",
            bg=BG_MAIN, fg=TEXT_DIM, font=FONT_LABEL,
        ).grid(row=0, column=0, padx=14, sticky="w")

        tk.Button(
            log_header, text="Limpar",
            command=self._clear_log,
            bg=BG_MAIN, fg=TEXT_DIM,
            activebackground=BG_CONTENT, activeforeground=TEXT,
            relief="flat", font=FONT_LABEL, padx=8, pady=2,
            cursor="hand2",
        ).grid(row=0, column=1, padx=10, sticky="e")

        self.log_widget = scrolledtext.ScrolledText(
            log_frame,
            width=90, height=12,
            state="disabled",
            font=FONT_LOG,
            bg=LOG_BG, fg=TEXT,
            insertbackground=TEXT,
            relief="flat", bd=0,
            selectbackground=ACCENT,
        )
        self.log_widget.grid(row=1, column=0, sticky="ew", padx=0, pady=0)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _switch_module(self, key: str):
        for k, btn in self._nav_buttons.items():
            if k == key:
                btn.configure(bg=ACCENT, fg=TEXT_WHITE)
            else:
                btn.configure(bg=BG_SIDEBAR, fg=TEXT)
        self._module_frames[key].tkraise()

    # ------------------------------------------------------------------
    # Assembly browse
    # ------------------------------------------------------------------

    def _browse_asm(self):
        path = filedialog.askopenfilename(
            title="Seleciona o assembly SolidWorks",
            filetypes=[("SolidWorks Assembly", "*.sldasm"), ("All files", "*.*")],
        )
        if path:
            self.asm_var.set(path)

    # ------------------------------------------------------------------
    # Shared log
    # ------------------------------------------------------------------

    def _log(self, msg: str, level: str = "INFO", tag: str = None):
        entry = LogEntry(msg, level, tag)
        self._log_entries.append(entry)

        self.log_widget.configure(state="normal")
        self.log_widget.insert("end", str(entry) + "\n")
        self.log_widget.see("end")
        self.log_widget.configure(state="disabled")

    def _refresh_log(self, tag: str = None):
        """Repopulates the log widget from stored entries, filtering by tag if provided."""
        self.log_widget.configure(state="normal")
        self.log_widget.delete("1.0", "end")
        for entry in self._log_entries:
            if tag is None or entry.tag == tag:
                self.log_widget.insert("end", str(entry) + "\n")
        self.log_widget.see("end")
        self.log_widget.configure(state="disabled")

    def _clear_log(self):
        self._log_entries = []
        self.log_widget.configure(state="normal")
        self.log_widget.delete("1.0", "end")
        self.log_widget.configure(state="disabled")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Auto Production Unified Exporter")
    parser.add_argument("--path", help="Path to the SolidWorks assembly file")
    args = parser.parse_args()
    
    app = MainWindow(initial_path=args.path)
    app.mainloop()
