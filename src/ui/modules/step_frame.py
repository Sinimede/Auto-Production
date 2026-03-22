
import os
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
from .base_frame import BaseFrame, BG_CONTENT, TEXT_WHITE, TEXT, TEXT_DIM, BORDER, ACCENT, FONT_LABEL, FONT_UI, FONT_BTN

class StepFrame(BaseFrame):
    def __init__(self, parent, service, log_fn, get_asm_path, get_out_path):
        super().__init__(parent, service, log_fn, get_asm_path)
        self.get_out_path = get_out_path
        self._build_ui()

    def _build_ui(self):
        pad = {"padx": 14, "pady": 6}

        # Title
        tk.Label(
            self, text="STEP Export (Router / CNC / Torno)",
            bg=BG_CONTENT, fg=TEXT_WHITE,
            font=("Segoe UI", 11, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=14, pady=(14, 4))

        # Separator
        tk.Frame(self, bg=BORDER, height=1).grid(
            row=1, column=0, columnspan=3, sticky="ew", padx=14, pady=(0, 10))

        # Output folder
        tk.Label(
            self, text="Pasta de Saída:",
            bg=BG_CONTENT, fg=TEXT_DIM, font=FONT_LABEL, anchor="e",
        ).grid(row=2, column=0, sticky="e", **pad)

        self.out_var = tk.StringVar()
        if self.get_out_path():
            self.out_var.set(self.get_out_path())

        tk.Entry(
            self, textvariable=self.out_var,
            bg="#1e1e2e", fg=TEXT, insertbackground=TEXT,
            relief="flat", font=FONT_UI,
            highlightthickness=1, highlightbackground=BORDER,
            highlightcolor=ACCENT,
        ).grid(row=2, column=1, padx=4, pady=6, sticky="ew")

        tk.Button(
            self, text="Browse\u2026",
            command=self._browse_out,
            bg="#1e1e2e", fg=TEXT,
            activebackground=ACCENT, activeforeground=TEXT_WHITE,
            relief="flat", font=FONT_LABEL, padx=10, pady=4,
            cursor="hand2",
        ).grid(row=2, column=2, padx=(0, 14))

        # Checkboxes
        tk.Label(
            self, text="Processos:",
            bg=BG_CONTENT, fg=TEXT_DIM, font=FONT_LABEL, anchor="e",
        ).grid(row=3, column=0, sticky="ne", padx=(14, 6), pady=(8, 4))

        self._check_vars = {
            "router": tk.BooleanVar(value=True),
            "cnc":    tk.BooleanVar(value=True),
            "torno":  tk.BooleanVar(value=True)
        }
        
        checks_frame = tk.Frame(self, bg=BG_CONTENT)
        checks_frame.grid(row=3, column=1, sticky="w", pady=(8, 4))
        
        for key, label in [("router", "Router (c/ furos piloto)"), ("cnc", "CNC"), ("torno", "Torno")]:
            tk.Checkbutton(
                checks_frame, text=label, variable=self._check_vars[key],
                bg=BG_CONTENT, fg=TEXT, activebackground=BG_CONTENT,
                activeforeground=TEXT_WHITE, selectcolor=BG_CONTENT,
                font=FONT_LABEL, cursor="hand2",
            ).pack(anchor="w", pady=1)

        # Excel toggle
        self.excel_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            self, text="Gerar Excels de acompanhamento",
            variable=self.excel_var,
            bg=BG_CONTENT, fg=TEXT, selectcolor=BG_CONTENT,
            activebackground=BG_CONTENT, activeforeground=TEXT_WHITE,
            font=FONT_LABEL,
        ).grid(row=4, column=0, columnspan=3, sticky="w", padx=14, pady=(4, 2))

        # Buttons
        self.btn_export = tk.Button(
            self, text="Export STEP",
            command=self._start_export,
            bg=ACCENT, fg=TEXT_WHITE,
            activebackground="#005fa3", activeforeground=TEXT_WHITE,
            font=FONT_BTN, padx=24, pady=8,
            relief="flat", cursor="hand2",
        )
        self.btn_export.grid(row=5, column=0, columnspan=3, pady=(10, 4))

        # Progress
        self.progress = ttk.Progressbar(self, variable=self.progress_var, length=500, mode="determinate")
        self.progress.grid(row=7, column=0, columnspan=3, padx=14, pady=(4, 0))

        # Status
        tk.Label(
            self, textvariable=self.status_var,
            bg=BG_CONTENT, fg=TEXT_DIM, font=FONT_LABEL, anchor="w",
        ).grid(row=8, column=0, columnspan=3, sticky="w", padx=14, pady=(2, 4))

    def _browse_out(self):
        path = filedialog.askdirectory(title="Seleciona a pasta de output")
        if path:
            self.out_var.set(path)

    def _start_export(self):
        asm = self._get_asm_path()
        out = self.out_var.get().strip()
        
        if not asm or not os.path.isfile(asm):
            messagebox.showerror("Erro", "Seleciona um ficheiro .sldasm válido.")
            return
        if not out or not os.path.isdir(out):
            messagebox.showerror("Erro", "Seleciona uma pasta de output válida.")
            return
            
        selected = {k: v.get() for k, v in self._check_vars.items()}
        if not any(selected.values()):
            messagebox.showwarning("Aviso", "Seleciona pelo menos um processo.")
            return

        self.set_state("disabled")
        self.service.run_export(asm, out, selected, self.excel_var.get())

    def set_state(self, state: str):
        self.btn_export.config(state=state)
