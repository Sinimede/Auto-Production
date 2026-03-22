
import os
import tkinter as tk
from tkinter import ttk
from src.ui.modules.base_frame import BaseFrame, BG_CONTENT, BG_MAIN, ACCENT, TEXT, TEXT_WHITE, TEXT_DIM, BORDER, FONT_TITLE, FONT_UI, FONT_BTN
from src.ui.components.process_card import ProcessCard
from src.ui.components.hold_button import HoldButton

class DashboardFrame(BaseFrame):
    def __init__(self, parent, dxf_service, step_service, bom_service, job_manager, pdm_service, log_fn, get_asm_path, get_out_path, filter_logs_fn):
        super().__init__(parent, None, log_fn, get_asm_path)
        self.get_out_path = get_out_path
        self.dxf_service = dxf_service
        self.step_service = step_service
        self.bom_service = bom_service
        self.job_manager = job_manager
        self.pdm_service = pdm_service
        self.filter_logs_fn = filter_logs_fn
        
        # Main Options
        self.opt_dxf = tk.BooleanVar(value=True)
        self.opt_step = tk.BooleanVar(value=True)
        self.opt_listas = tk.BooleanVar(value=True)
        self.opt_excel = tk.BooleanVar(value=True)
        
        # Sub-Options
        self.opt_laser = tk.BooleanVar(value=True)
        self.opt_protecoes = tk.BooleanVar(value=True)
        self.opt_router = tk.BooleanVar(value=True)
        self.opt_cnc = tk.BooleanVar(value=True)
        self.opt_torno = tk.BooleanVar(value=True)
        
        self._setup_callbacks()
        self._build_ui()

    def _setup_callbacks(self):
        # ... (unchanged)
        self.dxf_service.set_callbacks(
            on_log=lambda m, l="INFO", t="dxf": self._on_log(m, l, t),
            on_progress=lambda c, t: self._on_progress("dxf", c, t),
            on_status=lambda s: self._on_status("dxf", s),
            on_finish=lambda ok, err: self._on_finish("dxf", ok, err)
        )
        self.step_service.set_callbacks(
            on_log=lambda m, l="INFO", t="step": self._on_log(m, l, t),
            on_progress=lambda c, t: self._on_progress("step", c, t),
            on_status=lambda s: self._on_status("step", s),
            on_finish=lambda ok, err: self._on_finish("step", ok, err)
        )
        self.bom_service.set_callbacks(
            on_log=lambda m, l="INFO", t="listas": self._on_log(m, l, t),
            on_progress=lambda c, t: self._on_progress("listas", c, t),
            on_status=lambda s: self._on_status("listas", s),
            on_finish=lambda ok, err: self._on_finish("listas", ok, err)
        )
        # Job Manager progress
        self.job_manager.set_progress_callback(self._on_global_progress)

    def _build_ui(self):
        # Container
        self.container = tk.Frame(self, bg=BG_CONTENT, padx=20, pady=10)
        self.container.pack(fill="both", expand=True)
        
        # 1. Settings / Filters
        settings = tk.LabelFrame(self.container, text=" Configurações de Processamento ", bg=BG_CONTENT, fg=TEXT_DIM, font=FONT_UI, padx=15, pady=10, relief="flat", highlightthickness=1, highlightbackground=BORDER)
        settings.pack(fill="x", pady=(0, 20))
        
        # PDM Quick Status (Added)
        pdm_status = tk.Frame(self.container, bg=BG_MAIN, padx=15, pady=8, highlightthickness=1, highlightbackground=BORDER)
        pdm_status.pack(fill="x", pady=(0, 15))
        
        tk.Label(pdm_status, text="\ud83d\udd12 Estado do Vault:", bg=BG_MAIN, fg=TEXT_DIM, font=("Segoe UI", 9, "bold")).pack(side="left")
        self.lbl_pdm_quick = tk.Label(pdm_status, text="A carregar...", bg=BG_MAIN, fg=ACCENT, font=("Segoe UI", 9))
        self.lbl_pdm_quick.pack(side="left", padx=5)
        
        tk.Button(pdm_status, text="Ver Bloqueios", command=self._show_all_locks, bg=BG_MAIN, fg=TEXT, font=("Segoe UI", 8), relief="flat", padx=10).pack(side="right")
        
        self.after(500, self._update_pdm_status)

        # Header Row
        header_row = tk.Frame(settings, bg=BG_CONTENT)
        header_row.pack(fill="x")

        # DXF Group
        dxf_grp = tk.Frame(header_row, bg=BG_CONTENT)
        dxf_grp.pack(side="left", padx=10)
        tk.Checkbutton(dxf_grp, text="Exportar DXF", variable=self.opt_dxf, bg=BG_CONTENT, fg=TEXT_WHITE, activebackground=BG_CONTENT, selectcolor=BG_MAIN, font=("Segoe UI", 10, "bold"), command=self._update_button_text).pack(anchor="w")
        sub_dxf = tk.Frame(dxf_grp, bg=BG_CONTENT, padx=20)
        sub_dxf.pack(anchor="w")
        tk.Checkbutton(sub_dxf, text="Laser", variable=self.opt_laser, bg=BG_CONTENT, fg=TEXT, activebackground=BG_CONTENT, selectcolor=BG_MAIN, font=("Segoe UI", 9)).pack(side="left")
        tk.Checkbutton(sub_dxf, text="Proteções", variable=self.opt_protecoes, bg=BG_CONTENT, fg=TEXT, activebackground=BG_CONTENT, selectcolor=BG_MAIN, font=("Segoe UI", 9)).pack(side="left")

        tk.Frame(header_row, width=2, bg=BORDER).pack(side="left", fill="y", padx=15)

        # STEP Group
        step_grp = tk.Frame(header_row, bg=BG_CONTENT)
        step_grp.pack(side="left", padx=10)
        tk.Checkbutton(step_grp, text="Exportar STEP", variable=self.opt_step, bg=BG_CONTENT, fg=TEXT_WHITE, activebackground=BG_CONTENT, selectcolor=BG_MAIN, font=("Segoe UI", 10, "bold"), command=self._update_button_text).pack(anchor="w")
        sub_step = tk.Frame(step_grp, bg=BG_CONTENT, padx=20)
        sub_step.pack(anchor="w")
        tk.Checkbutton(sub_step, text="Router", variable=self.opt_router, bg=BG_CONTENT, fg=TEXT, activebackground=BG_CONTENT, selectcolor=BG_MAIN, font=("Segoe UI", 9)).pack(side="left")
        tk.Checkbutton(sub_step, text="CNC", variable=self.opt_cnc, bg=BG_CONTENT, fg=TEXT, activebackground=BG_CONTENT, selectcolor=BG_MAIN, font=("Segoe UI", 9)).pack(side="left")
        tk.Checkbutton(sub_step, text="Torno", variable=self.opt_torno, bg=BG_CONTENT, fg=TEXT, activebackground=BG_CONTENT, selectcolor=BG_MAIN, font=("Segoe UI", 9)).pack(side="left")

        tk.Frame(header_row, width=2, bg=BORDER).pack(side="left", fill="y", padx=15)

        # BOM & Global
        other_grp = tk.Frame(header_row, bg=BG_CONTENT)
        other_grp.pack(side="left", padx=10)
        tk.Checkbutton(other_grp, text="Listas/BOM", variable=self.opt_listas, bg=BG_CONTENT, fg=TEXT_WHITE, activebackground=BG_CONTENT, selectcolor=BG_MAIN, font=("Segoe UI", 10, "bold"), command=self._update_button_text).pack(anchor="w")
        tk.Checkbutton(other_grp, text="Gerar Excel", variable=self.opt_excel, bg=BG_CONTENT, fg=TEXT, activebackground=BG_CONTENT, selectcolor=BG_MAIN, font=("Segoe UI", 9)).pack(anchor="w", padx=20)

        # ... (rest of _build_ui)

        # 2. Grid layout for cards
        grid = tk.Frame(self.container, bg=BG_CONTENT)
        grid.pack(fill="both", expand=True)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        
        # Cards
        self.cards = {
            "dxf": ProcessCard(grid, "DXF (Laser/Prot.)", "\ud83d\udcc4", lambda: self.filter_logs_fn("dxf")),
            "step": ProcessCard(grid, "STEP (CNC/3D)", "\ud83d\udce6", lambda: self.filter_logs_fn("step")),
            "listas": ProcessCard(grid, "Listas e BOM", "\ud83d\udccb", lambda: self.filter_logs_fn("listas")),
        }
        
        self.cards["dxf"].grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.cards["step"].grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        self.cards["listas"].grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        
        # 3. Global Progress Bar
        self.progress_frame = tk.Frame(self.container, bg=BG_CONTENT, pady=10)
        self.progress_frame.pack(fill="x")
        
        self.lbl_progress = tk.Label(self.progress_frame, text="Progresso Global", bg=BG_CONTENT, fg=TEXT_DIM, font=FONT_UI)
        self.lbl_progress.pack(anchor="w")
        
        prog_row = tk.Frame(self.progress_frame, bg=BG_CONTENT)
        prog_row.pack(fill="x", pady=5)
        
        self.global_progress = ttk.Progressbar(prog_row, orient="horizontal", mode="determinate", style="TProgressbar")
        self.global_progress.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        self.btn_cancel = HoldButton(prog_row, self._cancel_execution, size=46)
        self.btn_cancel.pack(side="right", padx=2)
        self.btn_cancel.set_state("disabled")
        
        # 4. Action Bar (Bottom)
        self.action_bar = tk.Frame(self.container, bg=BG_CONTENT, pady=10)
        self.action_bar.pack(fill="x")
        
        self.btn_all = tk.Button(
            self.action_bar, text="GERAR TUDO", 
            command=self._start_all,
            bg=ACCENT, fg=TEXT_WHITE, font=FONT_BTN,
            padx=40, pady=12, relief="flat", cursor="hand2"
        )
        self.btn_all.pack(side="top")

    def _update_pdm_status(self):
        try:
            locks = self.pdm_service.get_checked_out_files()
            count = len(locks)
            if count == 0:
                self.lbl_pdm_quick.config(text="Tudo disponível no cofre.", fg="#51cf66")
            else:
                self.lbl_pdm_quick.config(text=f"{count} ficheiros bloqueados para edição.", fg="#ff6b6b")
        except:
            self.lbl_pdm_quick.config(text="Erro ao ler base de dados PDM.", fg="#fa5252")
        
        # Refresh every 30 seconds
        self.after(30000, self._update_pdm_status)

    def _show_all_locks(self):
        from tkinter import messagebox
        locks = self.pdm_service.get_checked_out_files()
        if not locks:
            messagebox.showinfo("PDM", "Nenhum ficheiro está bloqueado de momento.")
            return
            
        win = tk.Toplevel(self)
        win.title("Ficheiros em Check-Out")
        win.geometry("600x400")
        win.configure(bg=BG_MAIN)
        
        tree = ttk.Treeview(win, columns=("user", "date", "file"), show="headings")
        tree.heading("user", text="Utilizador")
        tree.heading("date", text="Data Bloqueio")
        tree.heading("file", text="Ficheiro")
        
        tree.column("user", width=100)
        tree.column("date", width=120)
        tree.column("file", width=350)
        tree.pack(fill="both", expand=True, padx=10, pady=10)
        
        for l in locks:
            tree.insert("", "end", values=(l['user'], l['checkout_date'], os.path.basename(l['file_path'])))

    def _update_button_text(self):
        # If any major process is selected, change text to "GERAR"
        if self.opt_dxf.get() or self.opt_step.get() or self.opt_listas.get():
            self.btn_all.config(text="GERAR")
        else:
            self.btn_all.config(text="GERAR TUDO")

    def _start_all(self):
        asm = self._get_asm_path()
        out_dir = self.get_out_path()
        
        if not asm or not os.path.isfile(asm):
            from tkinter import messagebox
            messagebox.showerror("Erro", "Seleciona um ficheiro .sldasm válido.")
            return
            
        if not out_dir:
            from tkinter import messagebox
            messagebox.showerror("Erro", "Seleciona uma pasta de saída válida.")
            return

        # Build config. If none selected, enable all (YOLO mode)
        dxf_en = self.opt_dxf.get()
        step_en = self.opt_step.get()
        listas_en = self.opt_listas.get()
        
        if not (dxf_en or step_en or listas_en):
            dxf_en = step_en = listas_en = True

        config = {
            'dxf': {
                'enabled': dxf_en,
                'selected_processes': {
                    'laser': self.opt_laser.get(), 
                    'protecoes': self.opt_protecoes.get()
                },
                'gen_excel': self.opt_excel.get()
            },
            'step': {
                'enabled': step_en,
                'selected_processes': {
                    'router': self.opt_router.get(), 
                    'cnc': self.opt_cnc.get(), 
                    'torno': self.opt_torno.get()
                },
                'gen_excel': self.opt_excel.get()
            },
            'listas': {
                'enabled': listas_en,
                'include_bom': True,
                'include_perfis': True
            }
        }
        
        # Reset card states and clear old logs filter
        self.filter_logs_fn(None) # Show all logs during process
        
        for tag, card in self.cards.items():
            if config[tag]['enabled']:
                card.set_state("IDLE")
                card.set_progress(0)
            else:
                card.set_state("IDLE") # Or maybe a "SKIPPED" state if implemented
        
        self.global_progress['value'] = 0
        self.lbl_progress.config(text="Progresso Global: 0%")
        self.btn_all.config(state="disabled", bg=BORDER)
        self.btn_cancel.set_state("normal")
            
        def on_finish_all():
            self.after(0, lambda: self.btn_all.config(state="normal", bg=ACCENT))
            self.after(0, lambda: self.btn_cancel.set_state("disabled"))
            self.after(0, lambda: self.lbl_progress.config(text="Concluído."))

        if not os.path.exists(out_dir):
            os.makedirs(out_dir)

        self.job_manager.run_sequence(asm, out_dir, config, on_finish_all)

    def _on_global_progress(self, percent, message):
        self.after(0, lambda: self.global_progress.configure(value=percent))
        self.after(0, lambda: self.lbl_progress.config(text=f"Progresso Global: {int(percent)}% — {message}"))

    def _cancel_execution(self):
        self.job_manager.stop()
        self._log_fn("Cancelamento solicitado...", "WARNING")

    def _on_log(self, message, level="INFO", tag=None):
        self.after(0, lambda: self._log_fn(message, level, tag))

    def _on_progress(self, tag, current, total):
        if tag in self.cards:
            val = (current / total) * 100 if total > 0 else 0
            self.after(0, lambda: self.cards[tag].set_progress(val))

    def _on_status(self, tag, status):
        if tag in self.cards:
            self.after(0, lambda: self.cards[tag].set_state("RUNNING", status))

    def _on_finish(self, tag, ok, err):
        if tag in self.cards:
            state = "SUCCESS" if err == 0 else "ERROR"
            self.after(0, lambda: self.cards[tag].set_state(state))
