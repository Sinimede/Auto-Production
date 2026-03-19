
import os
import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk
from src.core.solidworks import SolidWorksClient
from src.services.dxf_service import DxfService
from src.services.step_service import StepService
from src.services.bom_service import BomService
from src.ui.modules.dxf_frame import DxfFrame
from src.ui.modules.step_frame import StepFrame
from src.ui.modules.listas_frame import ListasFrame
from src.ui.modules.base_frame import BG_MAIN, BG_SIDEBAR, BG_CONTENT, BG_HEADER, ACCENT, TEXT, TEXT_DIM, TEXT_WHITE, LOG_BG, BORDER, FONT_TITLE, FONT_NAV, FONT_LABEL, FONT_UI, FONT_LOG

class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Auto Production v2")
        self.configure(bg=BG_MAIN)
        self.minsize(850, 600)
        
        # Initialize Core and Services
        self.sw_client = SolidWorksClient()
        self.dxf_service = DxfService(self.sw_client)
        self.step_service = StepService(self.sw_client)
        self.bom_service = BomService(self.sw_client)
        
        self._apply_ttk_theme()
        self._build_ui()
        self._switch_module("dxf")

    def _apply_ttk_theme(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TProgressbar", troughcolor=BG_MAIN, background=ACCENT, bordercolor=BORDER, lightcolor=ACCENT, darkcolor=ACCENT)

    def _build_ui(self):
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        
        # Sidebar
        self.sidebar = tk.Frame(self, bg=BG_SIDEBAR, width=160)
        self.sidebar.grid(row=0, column=0, sticky="ns")
        self.sidebar.grid_propagate(False)
        
        tk.Label(self.sidebar, text="Auto\nProduction", bg=BG_SIDEBAR, fg=TEXT_WHITE, font=FONT_TITLE, pady=18).pack(fill="x")
        tk.Frame(self.sidebar, bg=BORDER, height=1).pack(fill="x", padx=10)
        
        # Navigation
        self._nav_buttons = {}
        modules = [
            ("DXF Export", "dxf"),
            ("STEP Export", "step"),
            ("Listas e BOM", "listas"),
        ]
        for label, key in modules:
            btn = tk.Button(self.sidebar, text=label, bg=BG_SIDEBAR, fg=TEXT, activebackground=ACCENT, activeforeground=TEXT_WHITE,
                            font=FONT_NAV, relief="flat", bd=0, padx=14, pady=10, cursor="hand2", anchor="w",
                            command=lambda k=key: self._switch_module(k))
            btn.pack(fill="x")
            self._nav_buttons[key] = btn

        # Right Pane
        right = tk.Frame(self, bg=BG_MAIN)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        
        # Header
        header = tk.Frame(right, bg=BG_HEADER, pady=8)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)
        
        tk.Label(header, text="Assembly (.sldasm):", bg=BG_HEADER, fg=TEXT_DIM, font=FONT_LABEL).grid(row=0, column=0, padx=(14, 6))
        self.asm_var = tk.StringVar()
        tk.Entry(header, textvariable=self.asm_var, bg=BG_CONTENT, fg=TEXT, insertbackground=TEXT, relief="flat", font=FONT_UI,
                 highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT).grid(row=0, column=1, sticky="ew", padx=4)
        tk.Button(header, text="Browse\u2026", command=self._browse_asm, bg=BG_CONTENT, fg=TEXT, relief="flat", font=FONT_LABEL, padx=10).grid(row=0, column=2, padx=(0, 14))

        # Content
        self.content_frame = tk.Frame(right, bg=BG_CONTENT)
        self.content_frame.grid(row=1, column=0, sticky="nsew")
        self.content_frame.columnconfigure(0, weight=1)
        self.content_frame.rowconfigure(0, weight=1)
        
        # Log
        self.log_widget = scrolledtext.ScrolledText(right, height=12, state="disabled", font=FONT_LOG, bg=LOG_BG, fg=TEXT, relief="flat")
        self.log_widget.grid(row=2, column=0, sticky="ew")
        
        # Frames
        self.frames = {
            "dxf":    DxfFrame(self.content_frame, self.dxf_service, self.log, lambda: self.asm_var.get()),
            "step":   StepFrame(self.content_frame, self.step_service, self.log, lambda: self.asm_var.get()),
            "listas": ListasFrame(self.content_frame, self.bom_service, self.log, lambda: self.asm_var.get()),
        }
        for f in self.frames.values(): f.grid(row=0, column=0, sticky="nsew")

    def _switch_module(self, key):
        for k, btn in self._nav_buttons.items():
            btn.configure(bg=ACCENT if k == key else BG_SIDEBAR, fg=TEXT_WHITE if k == key else TEXT)
        self.frames[key].tkraise()

    def _browse_asm(self):
        path = filedialog.askopenfilename(filetypes=[("SolidWorks Assembly", "*.sldasm")])
        if path: self.asm_var.set(path)

    def log(self, msg):
        self.log_widget.configure(state="normal")
        self.log_widget.insert("end", msg + "\n")
        self.log_widget.see("end")
        self.log_widget.configure(state="disabled")

if __name__ == "__main__":
    app = MainWindow()
    app.mainloop()
