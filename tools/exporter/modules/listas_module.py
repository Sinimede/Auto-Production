"""
listas_module.py — Listas (Excel reports) panel.

Replaces bom_module.py as the sidebar "Listas" entry.
Shows checkboxes for 6 report types; runs selected phases in one
SolidWorks session. Each phase is try/except resilient.

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


# Labels and internal keys for each checkbox
_LISTS = [
    ("Laser",              "laser"),
    ("Proteções",          "protecoes"),
    ("Router",             "router"),
    ("CNC",                "cnc"),
    ("Torno",              "torno"),
    ("BOM",                "bom"),
    ("Perfis de Alumínio", "perfis"),
]


class ListasModule(tk.Frame):
    """Listas (Excel reports) panel. Renders inside the shared content frame."""

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

        # Title
        tk.Label(
            self, text="Listas — Relatórios Excel",
            bg=BG_CONTENT, fg=TEXT_WHITE,
            font=("Segoe UI", 11, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=14, pady=(14, 4))

        # Separator
        tk.Frame(self, bg=BORDER, height=1).grid(
            row=1, column=0, columnspan=3, sticky="ew", padx=14, pady=(0, 10))

        # Output folder row
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

        # Checkboxes (all checked by default)
        self._check_vars = {}
        tk.Label(
            self, text="Gerar:",
            bg=BG_CONTENT, fg=TEXT_DIM, font=FONT_LABEL, anchor="e",
        ).grid(row=3, column=0, sticky="ne", padx=(14, 6), pady=(8, 4))

        checks_frame = tk.Frame(self, bg=BG_CONTENT)
        checks_frame.grid(row=3, column=1, sticky="w", pady=(8, 4))
        for label, key in _LISTS:
            var = tk.BooleanVar(value=True)
            self._check_vars[key] = var
            tk.Checkbutton(
                checks_frame, text=label, variable=var,
                bg=BG_CONTENT, fg=TEXT, activebackground=BG_CONTENT,
                activeforeground=TEXT_WHITE, selectcolor=BG_CONTENT,
                font=FONT_LABEL, cursor="hand2",
            ).pack(anchor="w", pady=1)

        # Generate button
        self.btn_generate = tk.Button(
            self, text="Gerar Selecionadas",
            command=self._start,
            bg=ACCENT, fg=TEXT_WHITE,
            activebackground="#005fa3", activeforeground=TEXT_WHITE,
            font=FONT_BTN, padx=24, pady=8,
            relief="flat", cursor="hand2",
        )
        self.btn_generate.grid(row=4, column=0, columnspan=3, pady=(10, 4))

        # Progress bar
        self.progress = ttk.Progressbar(self, length=500, mode="indeterminate")
        self.progress.grid(row=5, column=0, columnspan=3, padx=14, pady=(4, 0))

        # Status label
        self.status_var = tk.StringVar(value="Pronto.")
        tk.Label(
            self, textvariable=self.status_var,
            bg=BG_CONTENT, fg=TEXT_DIM, font=FONT_LABEL, anchor="w",
        ).grid(row=6, column=0, columnspan=3, sticky="w", padx=14, pady=(2, 4))

    # ------------------------------------------------------------------
    # Dialog
    # ------------------------------------------------------------------

    def _browse_out(self):
        path = filedialog.askdirectory(title="Seleciona a pasta de output")
        if path:
            self.out_var.set(path)

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def _start(self):
        from tkinter import messagebox
        asm = self._get_asm_path()
        out = self.out_var.get().strip()

        if not asm or not os.path.isfile(asm):
            messagebox.showerror("Erro", "Seleciona um ficheiro .sldasm v\u00e1lido.")
            return
        if not out or not os.path.isdir(out):
            messagebox.showerror("Erro", "Seleciona uma pasta de output v\u00e1lida.")
            return

        selected = {k: v.get() for k, v in self._check_vars.items()}
        if not any(selected.values()):
            messagebox.showwarning("Aviso", "Seleciona pelo menos uma lista.")
            return

        self.btn_generate.config(state="disabled")
        self.progress.start()
        self._set_status("A iniciar\u2026")
        threading.Thread(
            target=self._worker, args=(asm, out, selected), daemon=True
        ).start()

    # ------------------------------------------------------------------
    # Background worker
    # ------------------------------------------------------------------

    def _worker(self, asm_path: str, out_dir: str, selected: dict):
        asm_path = os.path.normpath(os.path.abspath(asm_path))
        sw_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, sw_dir)

        def ui(fn):
            self.after(0, fn)

        sw = None
        asm_doc = None
        asm_opened_by_us = False
        all_errors = []

        try:
            ui(lambda: self._log("\u2550" * 68))
            ui(lambda: self._log("Gerar Listas Selecionadas"))
            ui(lambda: self._log("A conectar ao SolidWorks\u2026"))

            from solidworks import connect_to_solidworks, open_assembly_resolved
            sw = connect_to_solidworks()

            ui(lambda: self._log(f"A abrir assembly: {os.path.basename(asm_path)}"))
            asm_doc, asm_opened_by_us = open_assembly_resolved(sw, asm_path)

            phase_n = 0
            phase_total = sum(1 for v in selected.values() if v)

            # Pre-load parts once if any excel-list phase is selected.
            # Avoids calling get_all_parts + ResolveAllLightweightComponents 5× separately.
            excel_phases = {"laser", "protecoes", "router", "cnc", "torno"}
            all_parts = unique_parts = None
            if any(selected.get(k) for k in excel_phases):
                from solidworks import get_all_parts, deduplicate_by_path
                all_parts    = get_all_parts(asm_doc)
                unique_parts = deduplicate_by_path(all_parts)
                ui(lambda n=len(unique_parts): self._log(f"  Total pe\u00e7as \u00fanicas: {n}"))

            # \u2500\u2500 Phase: Laser \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
            if selected.get("laser"):
                phase_n += 1
                ui(lambda n=phase_n, t=phase_total: self._log("\u2500" * 68))
                ui(lambda n=phase_n, t=phase_total: self._log(f"[{n}/{t}] Laser"))
                ui(lambda n=phase_n, t=phase_total: self._set_status(f"[{n}/{t}] Laser\u2026"))
                errs = self._run_excel_list(all_parts, unique_parts, out_dir,"laser", ui)
                all_errors.extend(errs)

            # \u2500\u2500 Phase: Proteções \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
            if selected.get("protecoes"):
                phase_n += 1
                ui(lambda n=phase_n, t=phase_total: self._log("\u2500" * 68))
                ui(lambda n=phase_n, t=phase_total: self._log(f"[{n}/{t}] Prote\u00e7\u00f5es"))
                ui(lambda n=phase_n, t=phase_total: self._set_status(f"[{n}/{t}] Prote\u00e7\u00f5es\u2026"))
                errs = self._run_excel_list(all_parts, unique_parts, out_dir,"protecoes", ui)
                all_errors.extend(errs)

            # \u2500\u2500 Phase: Router \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
            if selected.get("router"):
                phase_n += 1
                ui(lambda n=phase_n, t=phase_total: self._log("\u2500" * 68))
                ui(lambda n=phase_n, t=phase_total: self._log(f"[{n}/{t}] Router"))
                ui(lambda n=phase_n, t=phase_total: self._set_status(f"[{n}/{t}] Router\u2026"))
                errs = self._run_excel_list(all_parts, unique_parts, out_dir,"router", ui)
                all_errors.extend(errs)

            # \u2500\u2500 Phase: CNC \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
            if selected.get("cnc"):
                phase_n += 1
                ui(lambda n=phase_n, t=phase_total: self._log("\u2500" * 68))
                ui(lambda n=phase_n, t=phase_total: self._log(f"[{n}/{t}] CNC"))
                ui(lambda n=phase_n, t=phase_total: self._set_status(f"[{n}/{t}] CNC\u2026"))
                errs = self._run_excel_list(all_parts, unique_parts, out_dir,"cnc", ui)
                all_errors.extend(errs)

            # \u2500\u2500 Phase: Torno \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
            if selected.get("torno"):
                phase_n += 1
                ui(lambda n=phase_n, t=phase_total: self._log("\u2500" * 68))
                ui(lambda n=phase_n, t=phase_total: self._log(f"[{n}/{t}] Torno"))
                ui(lambda n=phase_n, t=phase_total: self._set_status(f"[{n}/{t}] Torno\u2026"))
                errs = self._run_excel_list(all_parts, unique_parts, out_dir,"torno", ui)
                all_errors.extend(errs)

            # \u2500\u2500 Phase: BOM \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
            if selected.get("bom"):
                phase_n += 1
                ui(lambda n=phase_n, t=phase_total: self._log("\u2500" * 68))
                ui(lambda n=phase_n, t=phase_total: self._log(f"[{n}/{t}] Lista de Material"))
                ui(lambda n=phase_n, t=phase_total: self._set_status(f"[{n}/{t}] BOM\u2026"))
                errs = self._run_bom(sw, asm_doc, asm_path, out_dir, ui)
                all_errors.extend(errs)

            # \u2500\u2500 Phase: Perfis de Alum\u00ednio \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
            if selected.get("perfis"):
                phase_n += 1
                ui(lambda n=phase_n, t=phase_total: self._log("\u2500" * 68))
                ui(lambda n=phase_n, t=phase_total: self._log(f"[{n}/{t}] Perfis de Alum\u00ednio"))
                ui(lambda n=phase_n, t=phase_total: self._set_status(f"[{n}/{t}] Perfis\u2026"))
                errs = self._run_perfis(sw, asm_doc, out_dir, ui)
                all_errors.extend(errs)

        except Exception as exc:
            all_errors.append(str(exc))
            ui(lambda m=str(exc): self._log(f"ERRO FATAL: {m}"))

        finally:
            if sw is not None and asm_opened_by_us and asm_doc is not None:
                try:
                    sw.CloseDoc(asm_path)
                except Exception:
                    pass

            n_err = len(all_errors)

            def _finish():
                self.btn_generate.config(state="normal")
                self.progress.stop()
                if n_err == 0:
                    self._set_status("Conclu\u00eddo.")
                else:
                    self._set_status(f"Conclu\u00eddo com {n_err} erro(s) \u2014 ver log.")
                self._log("\u2500" * 68)
                self._log(f"Gerar Listas conclu\u00eddo. Erros: {n_err}")

            ui(_finish)

    # ------------------------------------------------------------------
    # Laser / Router / CNC / Torno — Excel only
    # ------------------------------------------------------------------

    def _run_excel_list(self, all_parts: list, unique_parts: list,
                        out_dir: str, process_key: str, ui) -> list:
        """Generate the Excel report for a given process keyword (laser/router/cnc/torno)."""
        from solidworks import is_laser_part, get_corte_fabrico, get_part_data
        from excel_writer import generate_excel, PROCESS_CONFIG

        errors = []
        try:
            from paths import get_templates_dir
            templates_dir = get_templates_dir()

            if process_key == "laser":
                parts = [p for p in unique_parts if is_laser_part(p)]
            else:
                parts = [p for p in unique_parts
                         if process_key in get_corte_fabrico(p)]

            template_name, output_name, col_order, data_start_row = PROCESS_CONFIG[process_key]
            ui(lambda n=len(parts), k=process_key: self._log(f"  Pe\u00e7as {k}: {n}"))

            if not parts:
                ui(lambda k=process_key: self._log(f"  Nenhuma pe\u00e7a {k} encontrada."))
                return errors

            rows = [get_part_data(p, all_parts) for p in parts]
            generate_excel(
                os.path.join(templates_dir, template_name),
                rows,
                os.path.join(out_dir, output_name),
                col_order, data_start_row,
            )
            ui(lambda n=output_name: self._log(f"  OK    {n}"))

        except Exception as exc:
            errors.append(f"{process_key}.xlsx: {exc}")
            ui(lambda m=str(exc), k=process_key: self._log(f"  ERROR {k}.xlsx \u2014 {m}"))

        return errors

    # ------------------------------------------------------------------
    # BOM
    # ------------------------------------------------------------------

    def _run_bom(self, sw, asm_doc, asm_path: str, out_dir: str, ui) -> list:
        from solidworks import (
            get_bom_components, deduplicate_bom_by_path,
            count_bom_instances, get_custom_property_evaluated,
        )
        from bom_writer import classify_commercial, generate_bom, is_known_brand

        errors = []
        try:
            bom_flat, warnings = get_bom_components(asm_doc)
            for w in warnings:
                ui(lambda m=w: self._log(f"  AVISO {m}"))

            unique = deduplicate_bom_by_path(bom_flat)
            pairs  = []
            for bc in unique:
                model_doc_ref = bc.component.GetModelDoc2
                model_doc = model_doc_ref() if callable(model_doc_ref) else model_doc_ref
                if isinstance(model_doc, tuple):
                    model_doc = model_doc[0]
                if model_doc is None:
                    try:
                        bc.component.SetComponentState(4)  # swComponentFullyResolved = 4
                        model_doc_ref2 = bc.component.GetModelDoc2
                        model_doc = model_doc_ref2() if callable(model_doc_ref2) else model_doc_ref2
                        if isinstance(model_doc, tuple):
                            model_doc = model_doc[0]
                    except Exception:
                        pass
                if model_doc is None:
                    ui(lambda p=bc.path: self._log(f"  AVISO GetModelDoc2() None após SetComponentState: {p}"))
                    continue
                path_ref  = bc.component.GetPathName
                part_path = path_ref() if callable(path_ref) else path_ref
                if isinstance(part_path, tuple):
                    part_path = part_path[0]
                row = {
                    "qty":         count_bom_instances(bom_flat, bc.path),
                    "part_number": os.path.splitext(os.path.basename(part_path))[0],
                }
                for prop in ("Description", "Corte_Fabrico", "Simetria",
                             "Material", "TratSuperficial"):
                    row[prop] = get_custom_property_evaluated(model_doc, prop)
                if bc.comp_type == "producao":
                    row["A_Partir_de"] = get_custom_property_evaluated(
                        model_doc, "A_Partir_de")
                pairs.append((bc, row))

            rows_producao   = [row for bc, row in pairs if bc.comp_type == "producao"]
            rows_mecanico   = []
            rows_eletrico   = []
            rows_pneumatico = []
            warn_count      = len(warnings)

            for bc, row in pairs:
                if bc.comp_type != "comercial":
                    continue
                val = row.get("Corte_Fabrico") or ""
                if not is_known_brand(val):
                    msg = (f"Fabricante desconhecido: '{row['Corte_Fabrico']}'"
                           f" \u2192 Material Mec\u00e2nico")
                    ui(lambda m=msg: self._log(f"  AVISO {m}"))
                    warn_count += 1
                cat = classify_commercial(val)
                {
                    "mecanico":   rows_mecanico,
                    "eletrico":   rows_eletrico,
                    "pneumatico": rows_pneumatico,
                }[cat].append(row)

            output_path = os.path.join(out_dir, "Lista de materiais.xlsx")
            generate_bom(rows_producao, rows_mecanico, rows_eletrico,
                         rows_pneumatico, output_path)
            ui(lambda: self._log("  OK    Lista de materiais.xlsx"))
            summary = (
                f"Produ\u00e7\u00e3o: {len(rows_producao)} | "
                f"Mec\u00e2nico: {len(rows_mecanico)} | "
                f"El\u00e9trico: {len(rows_eletrico)} | "
                f"Pneum\u00e1tico: {len(rows_pneumatico)} | "
                f"Avisos: {warn_count}"
            )
            ui(lambda s=summary: self._log(s))

        except Exception as exc:
            errors.append(f"BOM: {exc}")
            ui(lambda m=str(exc): self._log(f"  ERRO BOM: {m}"))

        return errors

    # ------------------------------------------------------------------
    # Perfis de Alumínio
    # ------------------------------------------------------------------

    def _run_perfis(self, sw, asm_doc, out_dir: str, ui) -> list:
        from collections import defaultdict
        from solidworks import get_perfis_parts, get_weldment_cut_list
        from perfis_writer import generate_perfis

        errors = []
        try:
            perfis_parts = get_perfis_parts(asm_doc)
            ui(lambda n=len(perfis_parts): self._log(f"  Pe\u00e7as Perfil Alum\u00ednio: {n}"))

            if not perfis_parts:
                ui(lambda: self._log("  Nenhuma pe\u00e7a Perfil Alum\u00ednio encontrada."))
                return errors

            # Collect all cut list items, multiplying qty by instance count
            all_raw = []
            for part_path, instance_count in perfis_parts:
                ui(lambda p=part_path: self._log(
                    f"  A ler cut list: {os.path.basename(p)}"))
                try:
                    items, warns = get_weldment_cut_list(sw, part_path)
                    for w in warns:
                        ui(lambda m=w: self._log(f"  AVISO {m}"))
                    for item in items:
                        all_raw.append((item.description, item.length_mm,
                                        item.qty * instance_count))
                except Exception as exc:
                    p = part_path
                    ui(lambda m=str(exc), p=p: self._log(
                        f"  AVISO cut list falhou para {os.path.basename(p)}: {m}"))

            if not all_raw:
                ui(lambda: self._log("  Nenhum membro de perfil encontrado."))
                return errors

            # Aggregate: same (description, length_mm) → sum qty
            totals: dict = defaultdict(int)
            for desc, length_mm, qty in all_raw:
                totals[(desc, length_mm)] += qty

            # Sort by length_mm ascending
            rows = [
                {"qty": totals[k], "description": k[0], "length_mm": k[1]}
                for k in sorted(totals, key=lambda x: x[1])
            ]

            output_path = os.path.join(out_dir, "Perfis de Alum\u00ednio.xlsx")
            generate_perfis(rows, output_path)
            ui(lambda: self._log(
                f"  OK    Perfis de Alum\u00ednio.xlsx  [{len(rows)} linha(s)]"))

        except Exception as exc:
            errors.append(f"Perfis: {exc}")
            ui(lambda m=str(exc): self._log(f"  ERRO Perfis: {m}"))

        return errors

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------

    def _set_status(self, text: str):
        self.status_var.set(text)
