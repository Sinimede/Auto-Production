"""
bom_module.py — Lista de Material (BOM) export panel.

Traverses a SolidWorks assembly, classifies components as production or
commercial, and writes Lista de materiais.xlsx using the template.
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


class BomModule(tk.Frame):
    """Lista de Material export panel. Renders inside the shared content frame."""

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
            self, text="Lista de Material \u2014 BOM",
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

        # Row 3: generate button
        self.btn_generate = tk.Button(
            self, text="Gerar Lista de Material",
            command=self._start_generate,
            bg=ACCENT, fg=TEXT_WHITE,
            activebackground="#005fa3", activeforeground=TEXT_WHITE,
            font=FONT_BTN, padx=24, pady=8,
            relief="flat", cursor="hand2",
        )
        self.btn_generate.grid(row=3, column=0, columnspan=3, pady=(10, 4))

        # Row 4: progress bar (indeterminate — no per-component progress)
        self.progress = ttk.Progressbar(self, length=500, mode="indeterminate")
        self.progress.grid(row=4, column=0, columnspan=3, padx=14, pady=(4, 0))

        # Row 5: status label
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
    # Generate pipeline
    # ------------------------------------------------------------------

    def _start_generate(self):
        from tkinter import messagebox
        asm = self._get_asm_path()
        out = self.out_var.get().strip()

        if not asm or not os.path.isfile(asm):
            messagebox.showerror("Erro", "Seleciona um ficheiro .sldasm v\u00e1lido.")
            return
        if not out or not os.path.isdir(out):
            messagebox.showerror("Erro", "Seleciona uma pasta de output v\u00e1lida.")
            return

        self.btn_generate.config(state="disabled")
        self.progress.start()
        self._set_status("A gerar\u2026")

        thread = threading.Thread(
            target=self._worker, args=(asm, out), daemon=True)
        thread.start()

    def _worker(self, asm_path: str, out_dir: str):
        """Runs in background thread. All UI updates via self.after()."""
        asm_path = os.path.normpath(os.path.abspath(asm_path))

        sw_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, sw_dir)
        from solidworks import (
            connect_to_solidworks, open_assembly,
            get_bom_components, deduplicate_bom_by_path, count_bom_instances,
            get_custom_property_evaluated,
        )
        from bom_writer import (
            classify_commercial, generate_bom, is_known_brand,
        )

        def ui(fn):
            self.after(0, fn)

        sw = None
        asm_doc = None
        asm_opened_by_us = False
        error = False

        try:
            ui(lambda: self._log("\u2550" * 68))
            ui(lambda: self._log("Gerar Lista de Material"))
            ui(lambda: self._log("A conectar ao SolidWorks\u2026"))
            sw = connect_to_solidworks()

            ui(lambda: self._log(f"A abrir assembly: {os.path.basename(asm_path)}"))
            asm_doc, asm_opened_by_us = open_assembly(sw, asm_path)

            ui(lambda: self._log("A percorrer componentes\u2026"))
            bom_flat, warnings = get_bom_components(asm_doc)
            for w in warnings:
                ui(lambda m=w: self._log(f"  AVISO {m}"))

            unique = deduplicate_bom_by_path(bom_flat)
            all_raw = [bc.component for bc in bom_flat]
            # all_raw: list[IComponent2] passed to get_part_data for qty counting.
            # get_part_data does NOT open or close any SolidWorks document.
            # The qty it computes is immediately overridden below with count_bom_instances.

            pairs = []
            for bc in unique:
                model_doc_ref = bc.component.GetModelDoc2
                model_doc = model_doc_ref() if callable(model_doc_ref) else model_doc_ref
                if isinstance(model_doc, tuple):
                    model_doc = model_doc[0]
                if model_doc is None:
                    ui(lambda p=bc.path: self._log(f"  AVISO GetModelDoc2() None: {p}"))
                    continue
                # Build row from custom properties only — no geometry/feature access.
                # get_part_data is intentionally NOT used here: it calls
                # get_bounding_box_thickness (feature iteration + GetPartBox) which
                # marks parts as modified in SW. The BOM has no espessura column.
                path_ref = bc.component.GetPathName
                part_path = path_ref() if callable(path_ref) else path_ref
                if isinstance(part_path, tuple):
                    part_path = part_path[0]
                row = {
                    "qty":        count_bom_instances(bom_flat, bc.path),
                    "part_number": os.path.splitext(os.path.basename(part_path))[0],
                }
                for prop in ("Description", "Corte_Fabrico", "Simetria",
                             "Material", "TratSuperficial"):
                    row[prop] = get_custom_property_evaluated(model_doc, prop)
                if bc.comp_type == "producao":
                    row["A_Partir_de"] = get_custom_property_evaluated(
                        model_doc, "A_Partir_de")
                pairs.append((bc, row))

            rows_producao = [row for bc, row in pairs if bc.comp_type == "producao"]
            rows_mecanico, rows_eletrico, rows_pneumatico = [], [], []
            warn_count = len(warnings)

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
                {"mecanico": rows_mecanico,
                 "eletrico": rows_eletrico,
                 "pneumatico": rows_pneumatico}[cat].append(row)

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
            error = True
            ui(lambda m=str(exc): self._log(f"ERRO FATAL: {m}"))

        finally:
            if asm_opened_by_us and asm_doc is not None and sw is not None:
                try:
                    sw.CloseDoc(asm_path)
                except Exception:
                    pass

            def _finish():
                self.btn_generate.config(state="normal")
                self.progress.stop()
                self._set_status(
                    "Conclu\u00eddo." if not error else "Erro \u2014 ver log.")
                self._log("\u2500" * 68)

            ui(_finish)

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------

    def _set_status(self, text: str):
        self.status_var.set(text)
