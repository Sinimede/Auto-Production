
import os
import json
import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk, messagebox
from src.core.solidworks import SolidWorksClient
from src.services.pdm_service import PdmService
from src.services.dxf_service import DxfService
from src.services.step_service import StepService
from src.services.bom_service import BomService
from src.ui.modules.dxf_frame import DxfFrame
from src.ui.modules.step_frame import StepFrame
from src.ui.modules.listas_frame import ListasFrame
from src.ui.modules.pdm_frame import PdmFrame
from src.ui.modules.dashboard_frame import DashboardFrame
from src.ui.modules.base_frame import BG_MAIN, BG_SIDEBAR, BG_CONTENT, BG_HEADER, ACCENT, TEXT, TEXT_DIM, TEXT_WHITE, LOG_BG, BORDER, FONT_TITLE, FONT_NAV, FONT_LABEL, FONT_UI, FONT_LOG
from src.utils.logger import LogManager
from src.services.job_manager import JobManager

class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Auto Production v2")
        self.configure(bg=BG_MAIN)
        self.minsize(850, 600)
        
        self.settings_file = "settings.json"
        
        # Initialize Core, Services and Utils
        self.log_manager = LogManager()
        self.current_filter_tag = None
        self.sw_client = SolidWorksClient()
        
        # Services
        self.pdm_service = PdmService(self.sw_client)
        self.dxf_service = DxfService(self.sw_client)
        self.step_service = StepService(self.sw_client)
        self.bom_service = BomService(self.sw_client)
        
        self.job_manager = JobManager({
            "dxf": self.dxf_service,
            "step": self.step_service,
            "listas": self.bom_service
        })
        
        self._apply_ttk_theme()
        self._build_ui()
        self._load_settings()

    def _apply_ttk_theme(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TProgressbar", troughcolor=BG_MAIN, background=ACCENT, bordercolor=BORDER, lightcolor=ACCENT, darkcolor=ACCENT)

    def _load_settings(self):
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, "r") as f:
                    data = json.load(f)
                    if data.get("last_asm"): self.asm_var.set(data["last_asm"])
                    if data.get("last_out"): self.out_var.set(data["last_out"])
            except:
                pass

    def _save_settings(self):
        data = {
            "last_asm": self.asm_var.get(),
            "last_out": self.out_var.get()
        }
        try:
            with open(self.settings_file, "w") as f:
                json.dump(data, f)
        except:
            pass

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
            ("Dashboard", "dashboard"),
            ("Gestão PDM", "pdm"),
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
        
        # Row 0: Assembly Path
        tk.Label(header, text="Assembly (.sldasm):", bg=BG_HEADER, fg=TEXT_DIM, font=FONT_LABEL).grid(row=0, column=0, padx=(14, 6))
        self.asm_var = tk.StringVar()
        tk.Entry(header, textvariable=self.asm_var, bg=BG_CONTENT, fg=TEXT, insertbackground=TEXT, relief="flat", font=FONT_UI,
                 highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT).grid(row=0, column=1, sticky="ew", padx=4)
        tk.Button(header, text="Browse\u2026", command=self._browse_asm, bg=BG_CONTENT, fg=TEXT, relief="flat", font=FONT_LABEL, padx=10).grid(row=0, column=2, padx=(0, 14))

        # Row 1: Output Directory
        tk.Label(header, text="Pasta de Saída:", bg=BG_HEADER, fg=TEXT_DIM, font=FONT_LABEL).grid(row=1, column=0, padx=(14, 6), pady=(4, 0))
        self.out_var = tk.StringVar()
        tk.Entry(header, textvariable=self.out_var, bg=BG_CONTENT, fg=TEXT, insertbackground=TEXT, relief="flat", font=FONT_UI,
                 highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT).grid(row=1, column=1, sticky="ew", padx=4, pady=(4, 0))
        tk.Button(header, text="Browse\u2026", command=self._browse_out, bg=BG_CONTENT, fg=TEXT, relief="flat", font=FONT_LABEL, padx=10).grid(row=1, column=2, padx=(0, 14), pady=(4, 0))

        # Content
        self.content_frame = tk.Frame(right, bg=BG_CONTENT)
        self.content_frame.grid(row=1, column=0, sticky="nsew")
        self.content_frame.columnconfigure(0, weight=1)
        self.content_frame.rowconfigure(0, weight=1)
        
        # Log Section
        log_container = tk.Frame(right, bg=LOG_BG, highlightthickness=1, highlightbackground=BORDER)
        log_container.grid(row=2, column=0, sticky="ew")
        
        log_header = tk.Frame(log_container, bg=BG_SIDEBAR, pady=2)
        log_header.pack(fill="x")
        tk.Label(log_header, text=" LOGS DO SISTEMA", bg=BG_SIDEBAR, fg=TEXT_DIM, font=("Segoe UI", 8, "bold")).pack(side="left", padx=5)
        tk.Button(log_header, text="Limpar", bg=BG_SIDEBAR, fg=TEXT_DIM, font=("Segoe UI", 8), relief="flat", padx=5, 
                  command=lambda: self.log_manager.clear() or self.filter_logs(self.current_filter_tag)).pack(side="right")

        self.log_widget = scrolledtext.ScrolledText(log_container, height=10, state="disabled", font=FONT_LOG, bg=LOG_BG, fg=TEXT, relief="flat", padx=10, pady=5)
        self.log_widget.pack(fill="x")
        
        # Frames
        self.frames = {
            "dashboard": DashboardFrame(self.content_frame, self.dxf_service, self.step_service, self.bom_service, self.job_manager, self.pdm_service, self.log, lambda: self.asm_var.get(), lambda: self.out_var.get(), self.filter_logs),
            "pdm":       PdmFrame(self.content_frame, self.pdm_service, self.log, lambda: self.asm_var.get()),
            "dxf":       DxfFrame(self.content_frame, self.dxf_service, self.log, lambda: self.asm_var.get(), lambda: self.out_var.get()),
            "step":      StepFrame(self.content_frame, self.step_service, self.log, lambda: self.asm_var.get(), lambda: self.out_var.get()),
            "listas":    ListasFrame(self.content_frame, self.bom_service, self.log, lambda: self.asm_var.get(), lambda: self.out_var.get()),
        }
        for f in self.frames.values(): f.grid(row=0, column=0, sticky="nsew")

        # Set default module
        self._switch_module("dashboard")

    def _switch_module(self, key):
        for k, btn in self._nav_buttons.items():
            btn.configure(bg=ACCENT if k == key else BG_SIDEBAR, fg=TEXT_WHITE if k == key else TEXT)
        self.frames[key].tkraise()

    def _browse_asm(self):
        path = filedialog.askopenfilename(filetypes=[("SolidWorks Assembly", "*.sldasm")])
        if path: 
            # Rule 4: Protection Check
            is_locked, owner = self.pdm_service.is_locked(path)
            current_user = os.getlogin()
            if is_locked and owner != current_user:
                messagebox.showwarning("Ficheiro Bloqueado", f"O ficheiro está em Check-Out por: {owner}.\nNão pode abrir para edição.")

            self.asm_var.set(path)
            # Auto-suggest output dir if empty
            if not self.out_var.get():
                self.out_var.set(os.path.join(os.path.dirname(path), "Resultados"))
            self._save_settings()

    def _browse_out(self):
        path = filedialog.askdirectory()
        if path: 
            self.out_var.set(path)
            self._save_settings()

    def log(self, message: str, level: str = "INFO", tag: str = None):
        """Adds a log entry and updates the display if it matches current filter."""
        entry = self.log_manager.add_entry(message, level, tag)
        
        # If no filter or tag matches filter, show in log widget
        if getattr(self, "current_filter_tag", None) is None or tag == self.current_filter_tag:
            self._append_to_log_widget(entry.timestamp, entry.message, entry.level)

    def _append_to_log_widget(self, timestamp, message, level):
        self.log_widget.configure(state="normal")
        
        # Color coding based on level
        tag_name = f"level_{level}"
        if tag_name not in self.log_widget.tag_names():
            color = TEXT
            if level == "ERROR": color = "#ff6b6b"
            elif level == "WARNING": color = "#fcc419"
            elif level == "SUCCESS": color = "#51cf66"
            self.log_widget.tag_config(tag_name, foreground=color)
        
        # Dim tag for timestamp
        if "dim" not in self.log_widget.tag_names():
            self.log_widget.tag_config("dim", foreground=TEXT_DIM)

        prefix = f"[{timestamp}] "
        self.log_widget.insert("end", prefix, "dim")
        self.log_widget.insert("end", f"{message}\n", tag_name)
        self.log_widget.see("end")
        self.log_widget.configure(state="disabled")

    def filter_logs(self, tag: str = None):
        """Refresh log widget with filtered entries."""
        self.current_filter_tag = tag
        self.log_widget.configure(state="normal")
        self.log_widget.delete("1.0", "end")
        self.log_widget.configure(state="disabled")
        
        entries = self.log_manager.get_filtered(tag=tag)
        for entry in entries:
            self._append_to_log_widget(entry.timestamp, entry.message, entry.level)

if __name__ == "__main__":
    app = MainWindow()
    app.mainloop()
