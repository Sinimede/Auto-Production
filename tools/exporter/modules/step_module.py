"""
step_module.py — STEP Export panel.

Exports STEP AP214 files for all router/cnc/torno parts in the assembly.
Router parts: copies to tmp, reduces dowel hole diameters by 1 mm, exports, deletes tmp.
CNC/torno parts: exports directly, no modifications.
Uses the shared log and assembly path from MainWindow.
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, ttk

BG_CONTENT  = "#2a2a3e"
BG_MAIN     = "#13131f"
ACCENT      = "#0078D4"
BORDER      = "#3a3a5a"
TEXT        = "#e0e0e0"
TEXT_DIM    = "#8888aa"
TEXT_WHITE  = "#ffffff"
FONT_UI     = ("Segoe UI", 10)
FONT_LABEL  = ("Segoe UI", 9)
FONT_BTN    = ("Segoe UI", 10, "bold")


class StepModule(tk.Frame):
    """STEP export panel. Renders inside the shared content frame."""

    def __init__(self, parent, log_fn, get_asm_path):
        super().__init__(parent, bg=BG_CONTENT)
        self._log = log_fn
        self._get_asm_path = get_asm_path
        self.columnconfigure(1, weight=1)
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        pad = {"padx": 14, "pady": 6}

        # Row 0: section title
        tk.Label(
            self, text="STEP Export",
            bg=BG_CONTENT, fg=TEXT_WHITE,
            font=("Segoe UI", 11, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=14, pady=(14, 4))

        # Row 1: separator
        tk.Frame(self, bg=BORDER, height=1).grid(
            row=1, column=0, columnspan=3, sticky="ew", padx=14, pady=(0, 10))

        # Row 2: output folder
        tk.Label(
            self, text="Output folder:",
            bg=BG_CONTENT, fg=TEXT_DIM, font=FONT_LABEL, anchor="e",
        ).grid(row=2, column=0, sticky="e", **pad)

        self.out_var = tk.StringVar()
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

        # Row 3: process checkboxes
        tk.Label(
            self, text="Processos:",
            bg=BG_CONTENT, fg=TEXT_DIM, font=FONT_LABEL, anchor="e",
        ).grid(row=3, column=0, sticky="ne", padx=(14, 6), pady=(8, 4))

        self._check_vars = {}
        checks_frame = tk.Frame(self, bg=BG_CONTENT)
        checks_frame.grid(row=3, column=1, sticky="w", pady=(8, 4))
        for label, key in [("Router", "router"), ("CNC", "cnc"), ("Torno", "torno")]:
            var = tk.BooleanVar(value=True)
            self._check_vars[key] = var
            tk.Checkbutton(
                checks_frame, text=label, variable=var,
                bg=BG_CONTENT, fg=TEXT, activebackground=BG_CONTENT,
                activeforeground=TEXT_WHITE, selectcolor=BG_CONTENT,
                font=FONT_LABEL, cursor="hand2",
            ).pack(anchor="w", pady=1)

        # Row 4: "Gerar Excel" checkbox
        self.excel_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            self, text="Gerar Excel",
            variable=self.excel_var,
            bg=BG_CONTENT, fg=TEXT, selectcolor=BG_CONTENT,
            activebackground=BG_CONTENT, activeforeground=TEXT_WHITE,
            font=FONT_LABEL,
        ).grid(row=4, column=0, columnspan=3, sticky="w", padx=14, pady=(4, 2))

        # Row 5: Export button
        self.btn_export = tk.Button(
            self, text="Export STEP",
            command=self._start_export,
            bg=ACCENT, fg=TEXT_WHITE,
            activebackground="#005fa3", activeforeground=TEXT_WHITE,
            font=FONT_BTN, padx=24, pady=8,
            relief="flat", cursor="hand2",
        )
        self.btn_export.grid(row=5, column=0, columnspan=3, pady=(10, 4))

        # Row 6: "Gerar Excel apenas" button
        self.btn_excel_only = tk.Button(
            self, text="Gerar Excel apenas",
            command=self._start_excel_only,
            bg="#3a3a5a", fg=TEXT_WHITE,
            activebackground="#505070", activeforeground=TEXT_WHITE,
            font=FONT_BTN, padx=24, pady=8,
            relief="flat", cursor="hand2",
        )
        self.btn_excel_only.grid(row=6, column=0, columnspan=3, pady=(0, 6))

        # Row 7: progress bar
        self.progress = ttk.Progressbar(self, length=500, mode="determinate")
        self.progress.grid(row=7, column=0, columnspan=3, padx=14, pady=(4, 0))

        # Row 8: status label
        self.status_var = tk.StringVar(value="Pronto.")
        tk.Label(
            self, textvariable=self.status_var,
            bg=BG_CONTENT, fg=TEXT_DIM, font=FONT_LABEL, anchor="w",
        ).grid(row=8, column=0, columnspan=3, sticky="w", padx=14, pady=(2, 4))

    # ------------------------------------------------------------------
    # Dialog
    # ------------------------------------------------------------------

    def _browse_out(self):
        path = filedialog.askdirectory(title="Seleciona a pasta de output")
        if path:
            self.out_var.set(path)

    # ------------------------------------------------------------------
    # Export pipeline
    # ------------------------------------------------------------------

    def _validate_inputs(self):
        from tkinter import messagebox
        asm = self._get_asm_path()
        out = self.out_var.get().strip()
        if not asm or not os.path.isfile(asm):
            messagebox.showerror("Erro", "Seleciona um ficheiro .sldasm válido.")
            return None, None
        if not out or not os.path.isdir(out):
            messagebox.showerror("Erro", "Seleciona uma pasta de output válida.")
            return None, None
        if not any(v.get() for v in self._check_vars.values()):
            messagebox.showwarning("Aviso", "Seleciona pelo menos um processo.")
            return None, None
        return asm, out

    def _start_export(self):
        asm, out = self._validate_inputs()
        if asm is None:
            return
        self.btn_export.config(state="disabled")
        self.btn_excel_only.config(state="disabled")
        self.progress["value"] = 0
        self._set_status("A iniciar\u2026")
        threading.Thread(target=self._worker, args=(asm, out), daemon=True).start()

    def _start_excel_only(self):
        asm, out = self._validate_inputs()
        if asm is None:
            return
        self.btn_export.config(state="disabled")
        self.btn_excel_only.config(state="disabled")
        self.progress["value"] = 0
        self._set_status("A gerar Excel\u2026")
        threading.Thread(
            target=self._worker_excel_only, args=(asm, out), daemon=True).start()

    def _worker(self, asm_path: str, out_dir: str):
        """Runs in background thread. All UI updates via self.after()."""
        # Normalise path immediately so CloseDoc later uses the exact same format
        # that SolidWorks expects (backslashes, resolved absolute path).
        asm_path = os.path.normpath(os.path.abspath(asm_path))

        sw_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, sw_dir)
        from solidworks import (
            connect_to_solidworks, open_assembly_resolved, get_all_parts,
            deduplicate_by_path, is_step_part, get_corte_fabrico,
            get_part_path, copy_part_to_tmp, get_dowel_holes,
            modify_dowel_diameter, export_part_to_step,
        )

        def ui(fn):
            self.after(0, fn)

        ok_count = skip_count = err_count = 0
        sw = None  # ensure sw is always defined for the finally block
        asm_doc = asm_opened_by_us = None

        try:
            ui(lambda: self._log("\u2550" * 68))
            ui(lambda: self._log("STEP Export"))
            ui(lambda: self._log("A conectar ao SolidWorks\u2026"))
            sw = connect_to_solidworks()

            ui(lambda: self._log(f"A abrir assembly: {os.path.basename(asm_path)}"))
            asm_doc, asm_opened_by_us = open_assembly_resolved(sw, asm_path)

            ui(lambda: self._log("A percorrer componentes\u2026"))
            all_parts    = get_all_parts(asm_doc)
            unique_parts = deduplicate_by_path(all_parts)
            ui(lambda n=len(unique_parts): self._log(f"  Pe\u00e7as \u00fanicas encontradas: {n}"))
            step_parts   = [p for p in unique_parts if is_step_part(p)]

            # Filter by selected process checkboxes
            selected_keywords = [k for k, v in self._check_vars.items() if v.get()]
            step_parts = [
                p for p in step_parts
                if any(kw in get_corte_fabrico(p) for kw in selected_keywords)
            ]

            # Categorise by treatment
            router_parts = [p for p in step_parts
                            if "router" in get_corte_fabrico(p)]
            direct_parts = [p for p in step_parts
                            if "router" not in get_corte_fabrico(p)]

            ui(lambda: self._log(
                f"A exportar STEP: {len(step_parts)} pe\u00e7a(s) \u2014 "
                f"router: {len(router_parts)} | direto (cnc/torno): {len(direct_parts)}"
            ))
            ui(lambda: self._log("\u2500" * 68))

            total = len(step_parts)
            if total == 0:
                ui(lambda: self._log(
                    "Nenhuma peça encontrada para os processos selecionados. "
                    "Verifica as propriedades no SolidWorks."
                ))
                return

            ui(lambda: self._set_progress(0, total))

            # Temporary directory for router part copies (.tmp/ at repo root, gitignored)
            tmp_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                ".tmp"
            )
            os.makedirs(tmp_dir, exist_ok=True)

            try:
                for i, part in enumerate(step_parts):
                    part_path = get_part_path(part)
                    part_name = os.path.basename(part_path)
                    base_name = os.path.splitext(part_name)[0]
                    corte     = get_corte_fabrico(part)
                    is_router = "router" in corte

                    ui(lambda n=part_name, idx=i: (
                        self._set_progress(idx, total),
                        self._set_status(f"A processar {n}\u2026"),
                    ))

                    output_step = os.path.join(out_dir, base_name + ".step")

                    try:
                        if is_router:
                            note = self._export_router_part(
                                sw, part_path, output_step, tmp_dir)
                        else:
                            export_part_to_step(sw, part_path, output_step)
                            note = f"{corte} \u2014 exportado direto"

                        ok_count += 1
                        msg = f"  OK    {base_name}.step  [{note}]"
                        ui(lambda m=msg: self._log(m))

                    except Exception as exc:
                        err_count += 1
                        msg = f"  ERROR {base_name} \u2014 {exc}"
                        ui(lambda m=msg: self._log(m))

                ui(lambda: self._set_progress(total, total))

                # Generate Excel files if checkbox is checked
                if self.excel_var.get():
                    try:
                        generated = self._generate_step_excels(
                            all_parts, unique_parts, step_parts, out_dir)
                        for name in generated:
                            ui(lambda n=name: self._log(f"  OK    {n}"))
                    except Exception as excel_exc:
                        ui(lambda m=str(excel_exc): self._log(f"  ERROR Excel \u2014 {m}"))

            finally:
                # Individual tmp files are deleted inside _export_router_part's finally.
                # The shared .tmp/ directory is NOT deleted — it is a persistent project dir.
                pass

        except Exception as exc:
            err_count += 1
            ui(lambda m=str(exc): self._log(f"ERRO FATAL: {m}"))

        finally:
            if sw is not None and asm_opened_by_us and asm_doc is not None:
                try:
                    sw.CloseDoc(asm_path)
                except Exception:
                    pass

            def _finish():
                self.btn_export.config(state="normal")
                self.btn_excel_only.config(state="normal")
                self._set_status("Conclu\u00eddo.")
                self._log("\u2500" * 68)
                self._log(
                    f"Resultado: {ok_count} exportado(s)  |  "
                    f"{skip_count} ignorado(s)  |  {err_count} erro(s)"
                )

            ui(_finish)

    def _export_router_part(self, sw, part_path: str, output_step: str,
                             tmp_dir: str) -> str:
        """
        Copy part to tmp, reduce dowel holes by 1 mm, export STEP, clean up.
        Returns a human-readable note for the log.
        Raises on any unrecoverable error; always cleans up tmp.
        """
        from solidworks import (
            copy_part_to_tmp, get_dowel_holes, modify_dowel_diameter,
            export_part_to_step, save_silent, _open_doc,  # _open_doc: Python does not enforce underscore privacy
        )

        tmp_path = None
        tmp_doc  = None

        try:
            tmp_path = copy_part_to_tmp(part_path, tmp_dir)

            # Open tmp part silently (options=1 = swOpenDocOptions_Silent)
            tmp_doc = _open_doc(sw, tmp_path, doc_type=1, silent=True)

            # Identify and reduce dowel holes
            holes = get_dowel_holes(tmp_doc)
            dowel_notes = []
            for hole in holes:
                orig_mm = hole.original_diameter_m * 1000
                new_m   = hole.original_diameter_m - 0.001
                new_mm  = new_m * 1000
                modify_dowel_diameter(tmp_doc, hole, new_m)
                dowel_notes.append(f"\u2300{orig_mm:.0f}\u2192\u2300{new_mm:.0f}")

            # Export STEP from the modified (still-open) tmp doc.
            # Pass doc=tmp_doc directly to avoid GetOpenDocumentByName path-matching issues.
            export_part_to_step(sw, tmp_path, output_step, doc=tmp_doc)

            if dowel_notes:
                return f"{len(holes)} dowel(s) reduzido(s): {', '.join(dowel_notes)}"
            return "sem furos de cavilha"

        finally:
            if tmp_doc is not None:
                try:
                    save_silent(tmp_doc)
                    sw.CloseDoc(tmp_path)
                except Exception:
                    pass
            if tmp_path and os.path.isfile(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    def _generate_step_excels(self, all_parts, unique_parts, step_parts, out_dir):
        """
        Generate one Excel file per process category found in step_parts.
        Returns list of generated filenames (e.g. ["Router.xlsx", "CNC.xlsx"]).
        A part with "router+cnc" in Corte_Fabrico appears in both groups.
        """
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from solidworks import get_part_data, get_corte_fabrico
        from excel_writer import generate_excel, PROCESS_CONFIG

        from paths import get_templates_dir
        templates_dir = get_templates_dir()

        # Group parts by process keyword (multi-group allowed)
        groups = {"router": [], "cnc": [], "torno": []}
        for part in step_parts:
            corte = get_corte_fabrico(part)
            for keyword in groups:
                if keyword in corte:
                    groups[keyword].append(part)

        generated = []
        for keyword, parts in groups.items():
            if not parts:
                continue
            template_name, output_name, col_order, data_start_row = PROCESS_CONFIG[keyword]
            template_path = os.path.join(templates_dir, template_name)
            output_path   = os.path.join(out_dir, output_name)
            rows = [get_part_data(p, all_parts) for p in parts]
            generate_excel(template_path, rows, output_path, col_order, data_start_row)
            generated.append(output_name)

        return generated

    def _worker_excel_only(self, asm_path: str, out_dir: str):
        """Background worker for 'Gerar Excel apenas' \u2014 no STEP export."""
        asm_path = os.path.normpath(os.path.abspath(asm_path))
        sw_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, sw_dir)
        from solidworks import (
            connect_to_solidworks, open_assembly_resolved, get_all_parts,
            deduplicate_by_path, is_step_part, get_corte_fabrico,
        )

        def ui(fn):
            self.after(0, fn)

        sw = None
        asm_doc = asm_opened_by_us = None

        try:
            ui(lambda: self._log("\u2550" * 68))
            ui(lambda: self._log("Gerar Excel (Router / CNC / Torno)"))
            ui(lambda: self._log("A conectar ao SolidWorks\u2026"))
            sw = connect_to_solidworks()

            ui(lambda: self._log(f"A abrir assembly: {os.path.basename(asm_path)}"))
            asm_doc, asm_opened_by_us = open_assembly_resolved(sw, asm_path)

            ui(lambda: self._log("A percorrer componentes\u2026"))
            all_parts    = get_all_parts(asm_doc)
            unique_parts = deduplicate_by_path(all_parts)
            step_parts   = [p for p in unique_parts if is_step_part(p)]

            selected_keywords = [k for k, v in self._check_vars.items() if v.get()]
            step_parts = [
                p for p in step_parts
                if any(kw in get_corte_fabrico(p) for kw in selected_keywords)
            ]

            ui(lambda n=len(step_parts): self._log(f"  Pe\u00e7as STEP: {n}"))

            if step_parts:
                try:
                    generated = self._generate_step_excels(
                        all_parts, unique_parts, step_parts, out_dir)
                    for name in generated:
                        ui(lambda n=name: self._log(f"  OK    {n}"))
                except Exception as excel_exc:
                    ui(lambda m=str(excel_exc): self._log(f"  ERROR Excel \u2014 {m}"))
            else:
                ui(lambda: self._log("Nenhuma peça encontrada para os processos selecionados."))

        except Exception as exc:
            ui(lambda m=str(exc): self._log(f"ERRO FATAL: {m}"))

        finally:
            if sw is not None and asm_opened_by_us and asm_doc is not None:
                try:
                    sw.CloseDoc(asm_path)
                except Exception:
                    pass

            def _finish():
                self.btn_export.config(state="normal")
                self.btn_excel_only.config(state="normal")
                self._set_status("Conclu\u00eddo.")
                self._log("\u2500" * 68)

            ui(_finish)

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------

    def _set_status(self, text: str):
        self.status_var.set(text)

    def _set_progress(self, value: int, maximum: int):
        self.progress["maximum"] = maximum or 1
        self.progress["value"]   = value
