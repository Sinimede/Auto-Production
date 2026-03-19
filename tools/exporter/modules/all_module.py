"""
all_module.py — Gerar Tudo panel.

Runs DXF export + STEP export + Lista de Material in sequence using a
single SolidWorks connection and a single assembly open/close cycle.
All outputs go to one folder. Partial failures are logged; remaining
phases always run.
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, ttk

BG_CONTENT = "#2a2a3e"
ACCENT     = "#0078D4"
BORDER     = "#3a3a5a"
TEXT       = "#e0e0e0"
TEXT_DIM   = "#8888aa"
TEXT_WHITE = "#ffffff"
FONT_UI    = ("Segoe UI", 10)
FONT_LABEL = ("Segoe UI", 9)
FONT_BTN   = ("Segoe UI", 10, "bold")


class AllModule(tk.Frame):
    """Gerar Tudo panel. Renders inside the shared content frame."""

    def __init__(self, parent, log_fn, get_asm_path):
        super().__init__(parent, bg=BG_CONTENT)
        self._log = log_fn
        self._get_asm_path = get_asm_path
        self._cancel = threading.Event()
        self.columnconfigure(1, weight=1)
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        pad = {"padx": 14, "pady": 6}

        tk.Label(
            self, text="Gerar Tudo \u2014 DXF + STEP + BOM + Perfis de Alum\u00ednio",
            bg=BG_CONTENT, fg=TEXT_WHITE,
            font=("Segoe UI", 11, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=14, pady=(14, 4))

        tk.Frame(self, bg=BORDER, height=1).grid(
            row=1, column=0, columnspan=3, sticky="ew", padx=14, pady=(0, 10))

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

        self.btn_run = tk.Button(
            self, text="Gerar Tudo",
            command=self._start,
            bg=ACCENT, fg=TEXT_WHITE,
            activebackground="#005fa3", activeforeground=TEXT_WHITE,
            font=FONT_BTN, padx=24, pady=8,
            relief="flat", cursor="hand2",
        )
        self.btn_run.grid(row=3, column=0, columnspan=3, pady=(10, 4))

        self.progress = ttk.Progressbar(self, mode="indeterminate")
        self.progress.grid(row=4, column=0, columnspan=2, padx=(14, 4), pady=(4, 0), sticky="ew")

        self.btn_cancel = tk.Button(
            self, text="Cancelar",
            command=self._cancel_op,
            bg="#2a1a1a", fg="#cc4444",
            activebackground="#3a2020", activeforeground="#ff6b6b",
            font=FONT_LABEL, padx=10, pady=4,
            relief="flat", cursor="hand2",
            state="disabled",
        )
        self.btn_cancel.grid(row=4, column=2, padx=(0, 14), pady=(4, 0))

        self.status_var = tk.StringVar(value="Pronto.")
        tk.Label(
            self, textvariable=self.status_var,
            bg=BG_CONTENT, fg=TEXT_DIM, font=FONT_LABEL, anchor="w",
        ).grid(row=5, column=0, columnspan=3, sticky="w", padx=14, pady=(2, 4))

    # ------------------------------------------------------------------
    # Dialog
    # ------------------------------------------------------------------

    def _browse_out(self):
        path = filedialog.askdirectory(title="Seleciona a pasta de output")
        if path:
            self.out_var.set(path)

    # ------------------------------------------------------------------
    # Pipeline entry point
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
        self._cancel.clear()
        self.btn_run.config(state="disabled")
        self.btn_cancel.config(state="normal")
        self.progress.start()
        self._set_status("A iniciar\u2026")
        threading.Thread(target=self._worker, args=(asm, out), daemon=True).start()

    # ------------------------------------------------------------------
    # Main background worker
    # ------------------------------------------------------------------

    def _worker(self, asm_path: str, out_dir: str):
        """Runs in a background thread. All UI updates via self.after()."""
        asm_path = os.path.normpath(os.path.abspath(asm_path))
        sw_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, sw_dir)

        def ui(fn):
            self.after(0, fn)

        sw = None
        asm_doc = asm_opened_by_us = None
        all_errors = []

        try:
            ui(lambda: self._log("\u2550" * 68))
            ui(lambda: self._log("Gerar Tudo"))
            ui(lambda: self._log("A conectar ao SolidWorks\u2026"))

            from solidworks import connect_to_solidworks, open_assembly_resolved
            sw = connect_to_solidworks()

            ui(lambda: self._log(f"A abrir assembly: {os.path.basename(asm_path)}"))
            asm_doc, asm_opened_by_us = open_assembly_resolved(sw, asm_path)

            # --- Phase 1: DXF ---
            ui(lambda: self._log("\u2500" * 68))
            ui(lambda: self._log("[1/4] DXF Export \u2014 Laser + Prote\u00e7\u00f5es"))
            ui(lambda: self._set_status("[1/4] DXF Export\u2026"))
            dxf_errors = self._run_dxf(sw, asm_doc, out_dir, ui)
            all_errors.extend(dxf_errors)

            if self._cancel.is_set():
                return

            # --- Phase 2: STEP ---
            ui(lambda: self._log("\u2500" * 68))
            ui(lambda: self._log("[2/4] STEP Export \u2014 Router / CNC / Torno"))
            ui(lambda: self._set_status("[2/4] STEP Export\u2026"))
            step_errors = self._run_step(sw, asm_doc, out_dir, ui)
            all_errors.extend(step_errors)

            if self._cancel.is_set():
                return

            # --- Phase 3: BOM ---
            ui(lambda: self._log("\u2500" * 68))
            ui(lambda: self._log("[3/4] Lista de Material"))
            ui(lambda: self._set_status("[3/4] Lista de Material\u2026"))
            bom_errors = self._run_bom(sw, asm_doc, asm_path, out_dir, ui)
            all_errors.extend(bom_errors)

            if self._cancel.is_set():
                return

            # --- Phase 4: Perfis de Alumínio ---
            ui(lambda: self._log("\u2500" * 68))
            ui(lambda: self._log("[4/4] Perfis de Alum\u00ednio"))
            ui(lambda: self._set_status("[4/4] Perfis de Alum\u00ednio\u2026"))
            perfis_errors = self._run_perfis(sw, asm_doc, out_dir, ui)
            all_errors.extend(perfis_errors)

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

            cancelled = self._cancel.is_set()

            def _finish():
                self.btn_run.config(state="normal")
                self.btn_cancel.config(state="disabled")
                self.progress.stop()
                if cancelled:
                    self._set_status("Cancelado.")
                elif n_err == 0:
                    self._set_status("Conclu\u00eddo.")
                else:
                    self._set_status(f"Conclu\u00eddo com {n_err} erro(s) \u2014 ver log.")
                self._log("\u2500" * 68)
                if cancelled:
                    self._log("Gerar Tudo cancelado pelo utilizador.")
                else:
                    self._log(f"Gerar Tudo conclu\u00eddo. Erros: {n_err}")

            ui(_finish)

    # ------------------------------------------------------------------
    # Phase 1 — DXF
    # ------------------------------------------------------------------

    def _run_dxf(self, sw, asm_doc, out_dir: str, ui) -> list:
        from solidworks import (
            get_all_parts, deduplicate_by_path, is_laser_part, is_protecoes_part,
            get_part_path, export_part_to_dxf, get_part_data,
        )
        from dxf_cleaner import clean_dxf
        from excel_writer import generate_excel, LASER_COLUMNS, PROCESS_CONFIG

        errors = []
        try:
            all_parts    = get_all_parts(asm_doc)
            unique_parts = deduplicate_by_path(all_parts)
            ui(lambda n=len(unique_parts): self._log(f"  Total pe\u00e7as \u00fanicas: {n}"))

            from paths import get_templates_dir
            templates_dir = get_templates_dir()

            laser_parts     = [p for p in unique_parts if is_laser_part(p)]
            protecoes_parts = [p for p in unique_parts if is_protecoes_part(p)]
            ui(lambda n=len(laser_parts): self._log(f"  Pe\u00e7as laser: {n}"))
            ui(lambda n=len(protecoes_parts): self._log(f"  Pe\u00e7as prote\u00e7\u00f5es: {n}"))

            if not laser_parts and not protecoes_parts:
                ui(lambda: self._log("  Nenhuma pe\u00e7a laser/prote\u00e7\u00f5es encontrada."))
                return errors

            for part in laser_parts:
                if self._cancel.is_set():
                    return errors
                part_path = get_part_path(part)
                part_name = os.path.basename(part_path)
                base_name = os.path.splitext(part_name)[0]
                raw_dxf   = os.path.join(out_dir, base_name + "_raw.dxf")
                final_dxf = os.path.join(out_dir, base_name + ".dxf")
                try:
                    export_part_to_dxf(sw, part_path, raw_dxf)
                    removed = clean_dxf(raw_dxf, final_dxf)
                    try:
                        os.remove(raw_dxf)
                    except OSError:
                        pass
                    circles_txt = (
                        f"{removed} c\u00edrculo(s) removido(s)" if removed
                        else "sem altera\u00e7\u00f5es"
                    )
                    msg = f"  OK    {base_name}.dxf  [{circles_txt}]"
                    ui(lambda m=msg: self._log(m))
                except Exception as exc:
                    err_msg = f"DXF {base_name}: {exc}"
                    errors.append(err_msg)
                    ui(lambda m=f"  ERROR {base_name} \u2014 {exc}": self._log(m))
                    if os.path.isfile(raw_dxf):
                        try:
                            os.remove(raw_dxf)
                        except OSError:
                            pass

            # Laser.xlsx
            if laser_parts:
                try:
                    template_name, output_name, _, data_start_row = PROCESS_CONFIG["laser"]
                    rows = [get_part_data(p, all_parts) for p in laser_parts]
                    generate_excel(
                        os.path.join(templates_dir, template_name),
                        rows,
                        os.path.join(out_dir, output_name),
                        LASER_COLUMNS, data_start_row,
                    )
                    ui(lambda n=output_name: self._log(f"  OK    {n}"))
                except Exception as exc:
                    errors.append(f"Laser.xlsx: {exc}")
                    ui(lambda m=str(exc): self._log(f"  ERROR Laser.xlsx \u2014 {m}"))

            # Proteções DXF
            if self._cancel.is_set():
                return errors
            for part in protecoes_parts:
                if self._cancel.is_set():
                    return errors
                part_path = get_part_path(part)
                part_name = os.path.basename(part_path)
                base_name = os.path.splitext(part_name)[0]
                raw_dxf   = os.path.join(out_dir, base_name + "_raw.dxf")
                final_dxf = os.path.join(out_dir, base_name + ".dxf")
                try:
                    export_part_to_dxf(sw, part_path, raw_dxf)
                    removed = clean_dxf(raw_dxf, final_dxf)
                    try:
                        os.remove(raw_dxf)
                    except OSError:
                        pass
                    circles_txt = (
                        f"{removed} c\u00edrculo(s) removido(s)" if removed
                        else "sem altera\u00e7\u00f5es"
                    )
                    msg = f"  OK    {base_name}.dxf  [{circles_txt}]"
                    ui(lambda m=msg: self._log(m))
                except Exception as exc:
                    err_msg = f"DXF {base_name}: {exc}"
                    errors.append(err_msg)
                    ui(lambda m=f"  ERROR {base_name} \u2014 {exc}": self._log(m))
                    if os.path.isfile(raw_dxf):
                        try:
                            os.remove(raw_dxf)
                        except OSError:
                            pass

            # Protecoes.xlsx
            if protecoes_parts:
                try:
                    template_name, output_name, col_order, data_start_row = \
                        PROCESS_CONFIG["protecoes"]
                    rows = [get_part_data(p, all_parts) for p in protecoes_parts]
                    generate_excel(
                        os.path.join(templates_dir, template_name),
                        rows,
                        os.path.join(out_dir, output_name),
                        col_order, data_start_row,
                    )
                    ui(lambda n=output_name: self._log(f"  OK    {n}"))
                except Exception as exc:
                    errors.append(f"Protecoes.xlsx: {exc}")
                    ui(lambda m=str(exc): self._log(f"  ERROR Protecoes.xlsx \u2014 {m}"))

        except Exception as exc:
            errors.append(f"DXF fase: {exc}")
            ui(lambda m=str(exc): self._log(f"  ERRO DXF: {m}"))

        return errors

    # ------------------------------------------------------------------
    # Phase 2 — STEP
    # ------------------------------------------------------------------

    def _run_step(self, sw, asm_doc, out_dir: str, ui) -> list:
        from solidworks import (
            get_all_parts, deduplicate_by_path, is_step_part,
            get_corte_fabrico, get_part_path, export_part_to_step,
            copy_part_to_tmp, get_dowel_holes, modify_dowel_diameter,
            save_silent, _open_doc, get_part_data,
        )
        from excel_writer import generate_excel, PROCESS_CONFIG

        errors = []
        try:
            all_parts    = get_all_parts(asm_doc)
            unique_parts = deduplicate_by_path(all_parts)
            ui(lambda n=len(unique_parts): self._log(f"  Total pe\u00e7as \u00fanicas: {n}"))
            step_parts   = [p for p in unique_parts if is_step_part(p)]
            ui(lambda n=len(step_parts): self._log(f"  Pe\u00e7as STEP: {n}"))

            if not step_parts:
                ui(lambda: self._log("  Nenhuma pe\u00e7a router/cnc/torno encontrada."))
                return errors

            tmp_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(
                    os.path.abspath(__file__)))),
                ".tmp",
            )
            os.makedirs(tmp_dir, exist_ok=True)

            for part in step_parts:
                if self._cancel.is_set():
                    return errors
                part_path   = get_part_path(part)
                part_name   = os.path.basename(part_path)
                base_name   = os.path.splitext(part_name)[0]
                corte       = get_corte_fabrico(part)
                is_router   = "router" in corte
                output_step = os.path.join(out_dir, base_name + ".step")
                try:
                    if is_router:
                        note = self._export_router_part(
                            sw, part_path, output_step, tmp_dir,
                            copy_part_to_tmp, get_dowel_holes,
                            modify_dowel_diameter, export_part_to_step,
                            save_silent, _open_doc,
                        )
                    else:
                        export_part_to_step(sw, part_path, output_step)
                        note = f"{corte} \u2014 exportado direto"
                    msg = f"  OK    {base_name}.step  [{note}]"
                    ui(lambda m=msg: self._log(m))
                except Exception as exc:
                    errors.append(f"STEP {base_name}: {exc}")
                    ui(lambda m=f"  ERROR {base_name} \u2014 {exc}": self._log(m))

            # Excel per process category
            groups = {"router": [], "cnc": [], "torno": []}
            for part in step_parts:
                corte = get_corte_fabrico(part)
                for kw in groups:
                    if kw in corte:
                        groups[kw].append(part)

            from paths import get_templates_dir
            templates_dir = get_templates_dir()
            for kw, parts in groups.items():
                if not parts:
                    continue
                template_name, output_name, col_order, data_start_row = PROCESS_CONFIG[kw]
                try:
                    rows = [get_part_data(p, all_parts) for p in parts]
                    generate_excel(
                        os.path.join(templates_dir, template_name),
                        rows,
                        os.path.join(out_dir, output_name),
                        col_order, data_start_row,
                    )
                    ui(lambda n=output_name: self._log(f"  OK    {n}"))
                except Exception as exc:
                    errors.append(f"{output_name}: {exc}")
                    ui(lambda m=str(exc): self._log(f"  ERROR {output_name} \u2014 {m}"))

        except Exception as exc:
            errors.append(f"STEP fase: {exc}")
            ui(lambda m=str(exc): self._log(f"  ERRO STEP: {m}"))

        return errors

    def _export_router_part(self, sw, part_path, output_step, tmp_dir,
                             copy_part_to_tmp, get_dowel_holes,
                             modify_dowel_diameter, export_part_to_step,
                             save_silent, _open_doc) -> str:
        """Copy to tmp, reduce dowel holes by 1 mm, export STEP, clean up."""
        tmp_path = tmp_doc = None
        try:
            tmp_path = copy_part_to_tmp(part_path, tmp_dir)
            tmp_doc  = _open_doc(sw, tmp_path, doc_type=1, silent=True)
            holes    = get_dowel_holes(tmp_doc)
            dowel_notes = []
            for hole in holes:
                orig_mm = hole.original_diameter_m * 1000
                new_m   = hole.original_diameter_m - 0.001
                modify_dowel_diameter(tmp_doc, hole, new_m)
                dowel_notes.append(f"\u2300{orig_mm:.0f}\u2192\u2300{new_m * 1000:.0f}")
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

    # ------------------------------------------------------------------
    # Phase 3 — BOM
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

            rows_producao  = [row for bc, row in pairs if bc.comp_type == "producao"]
            rows_mecanico  = []
            rows_eletrico  = []
            rows_pneumatico = []
            warn_count     = len(warnings)

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
    # Phase 4 — Perfis de Alumínio
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

            totals: dict = defaultdict(int)
            for desc, length_mm, qty in all_raw:
                totals[(desc, length_mm)] += qty

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

    def _cancel_op(self):
        self._cancel.set()
        self.btn_cancel.config(state="disabled")
        self._set_status("A cancelar\u2026")

    def _set_status(self, text: str):
        self.status_var.set(text)
