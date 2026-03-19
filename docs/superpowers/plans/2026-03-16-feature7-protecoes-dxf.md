# Feature 7 — DXF Proteções + Per-Process Selection Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add DXF export + Excel list for "Proteções" parts, and add per-process selection checkboxes to the DXF and STEP panels so users can export only the processes they need.

**Architecture:** Six targeted changes across existing files — a new filter function in `solidworks.py`, a new config entry in `excel_writer.py`, a checkbox refactor in `dxf_module.py` and `step_module.py`, a new phase in `listas_module.py`, and an update to `all_module.py` Phase 1. Every change follows the existing pattern of that file — no new files are created.

**Tech Stack:** Python 3.x, win32com (SolidWorks COM API), tkinter, openpyxl.

**Spec:** `docs/superpowers/specs/2026-03-16-feature7-protecoes-dxf-design.md`

**Run tests from:** `tools/exporter/` directory:
```bash
cd "c:/Users/Micael/Desktop/Auto Production/tools/exporter"
python -m pytest tests/ -v
```

---

## Chunk 1: Foundation — `solidworks.py` + `excel_writer.py`

### Task 1: Add `is_protecoes_part()` to `solidworks.py`

**Files:**
- Modify: `tools/exporter/solidworks.py` (after `is_step_part`, around line 434)
- Test: `tools/exporter/tests/test_solidworks_helpers.py`

- [ ] **Step 1: Write failing tests**

Open `tools/exporter/tests/test_solidworks_helpers.py` and add at the end (before `if __name__ == "__main__"`):

```python
# ---------------------------------------------------------------------------
# is_protecoes_part
# ---------------------------------------------------------------------------

class TestIsProtecoesPart(unittest.TestCase):

    def _make_part(self, corte_fabrico_value):
        """Return a mock IComponent2 whose Corte_Fabrico returns the given value."""
        comp = MagicMock()
        model = MagicMock()
        comp.GetModelDoc2.return_value = model
        mgr = MagicMock()
        model.Extension.CustomPropertyManager.return_value = mgr
        mgr.Get.return_value = corte_fabrico_value
        mgr.Get4.side_effect = Exception("not used")
        return comp

    def test_exact_match(self):
        from solidworks import is_protecoes_part
        self.assertTrue(is_protecoes_part(self._make_part("Proteções")))

    def test_exact_match_no_accent(self):
        from solidworks import is_protecoes_part
        self.assertTrue(is_protecoes_part(self._make_part("Protecoes")))

    def test_uppercase(self):
        from solidworks import is_protecoes_part
        self.assertTrue(is_protecoes_part(self._make_part("PROTEÇÕES")))

    def test_laser_part_returns_false(self):
        from solidworks import is_protecoes_part
        self.assertFalse(is_protecoes_part(self._make_part("Laser")))

    def test_empty_returns_false(self):
        from solidworks import is_protecoes_part
        self.assertFalse(is_protecoes_part(self._make_part("")))

    def test_none_model_returns_false(self):
        from solidworks import is_protecoes_part
        comp = MagicMock()
        comp.GetModelDoc2.return_value = None
        self.assertFalse(is_protecoes_part(comp))
```

- [ ] **Step 2: Run tests — confirm they FAIL**

```bash
cd "c:/Users/Micael/Desktop/Auto Production/tools/exporter"
python -m pytest tests/test_solidworks_helpers.py::TestIsProtecoesPart -v
```

Expected: `ImportError` or `AttributeError: module 'solidworks' has no attribute 'is_protecoes_part'`

- [ ] **Step 3: Implement `is_protecoes_part` in `solidworks.py`**

In `tools/exporter/solidworks.py`, after the `is_step_part` function (around line 434), add:

```python
def is_protecoes_part(component) -> bool:
    """
    Return True if Corte_Fabrico contains 'protecoes' (accent/case-insensitive).
    get_corte_fabrico already returns a lowercased, accent-stripped value.
    Matches: 'PROTEÇÕES', 'Proteções', 'Protecoes', etc.
    """
    val = get_corte_fabrico(component)
    return bool(val) and "protecoes" in val
```

- [ ] **Step 4: Run tests — confirm they PASS**

```bash
cd "c:/Users/Micael/Desktop/Auto Production/tools/exporter"
python -m pytest tests/test_solidworks_helpers.py::TestIsProtecoesPart -v
```

Expected: 6 tests PASS.

- [ ] **Step 5: Run full test suite — confirm no regressions**

```bash
python -m pytest tests/ -v
```

Expected: all existing tests still pass.

---

### Task 2: Add Proteções config to `excel_writer.py`

**Files:**
- Modify: `tools/exporter/excel_writer.py`
- Test: `tools/exporter/tests/test_excel_writer.py`

- [ ] **Step 1: Write failing tests**

Add to `tools/exporter/tests/test_excel_writer.py` (after the existing test classes, before `if __name__ == "__main__"`):

```python
PROTECOES_TEMPLATE = os.path.join(TEMPLATES_DIR, "Protecoes_template.xlsx")


class TestProtecoesConfig(unittest.TestCase):
    """PROTECOES_COLUMNS and PROCESS_CONFIG['protecoes'] are correctly defined."""

    def test_protecoes_columns_defined(self):
        from excel_writer import PROTECOES_COLUMNS
        self.assertEqual(PROTECOES_COLUMNS,
                         ["qty", "part_number", "Description", "Material"])

    def test_process_config_has_protecoes(self):
        from excel_writer import PROCESS_CONFIG
        self.assertIn("protecoes", PROCESS_CONFIG)

    def test_process_config_protecoes_values(self):
        from excel_writer import PROCESS_CONFIG, PROTECOES_COLUMNS
        tmpl, out, cols, start_row = PROCESS_CONFIG["protecoes"]
        self.assertEqual(tmpl, "Protecoes_template.xlsx")
        self.assertEqual(out, "Protecoes.xlsx")
        self.assertEqual(cols, PROTECOES_COLUMNS)
        self.assertEqual(start_row, 4)


class TestGenerateExcelProtecoes(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_protecoes_data_written_to_correct_columns(self):
        from excel_writer import generate_excel, PROTECOES_COLUMNS
        output = os.path.join(self.tmp, "Protecoes.xlsx")
        rows = [{
            "qty": 3, "part_number": "18026.200.001",
            "Description": "Tampa Proteção", "Material": "S235JR",
        }]
        generate_excel(PROTECOES_TEMPLATE, rows, output,
                       PROTECOES_COLUMNS, data_start_row=4)

        ws = openpyxl.load_workbook(output)["Folha1"]
        self.assertEqual(ws.cell(row=4, column=2).value, 3)
        self.assertEqual(ws.cell(row=4, column=3).value, "18026.200.001")
        self.assertEqual(ws.cell(row=4, column=4).value, "Tampa Proteção")
        self.assertEqual(ws.cell(row=4, column=5).value, "S235JR")

    def test_header_row_preserved(self):
        from excel_writer import generate_excel, PROTECOES_COLUMNS
        output = os.path.join(self.tmp, "Protecoes_hdr.xlsx")
        generate_excel(PROTECOES_TEMPLATE, [], output,
                       PROTECOES_COLUMNS, data_start_row=4)
        ws = openpyxl.load_workbook(output)["Folha1"]
        # Row 3 col B should be the header (QTY.)
        self.assertIsNotNone(ws.cell(row=3, column=2).value)

    def test_original_template_not_modified(self):
        from excel_writer import generate_excel, PROTECOES_COLUMNS
        output = os.path.join(self.tmp, "Protecoes_orig.xlsx")
        hdr_before = openpyxl.load_workbook(
            PROTECOES_TEMPLATE)["Folha1"].cell(row=3, column=2).value
        rows = [{"qty": 1, "part_number": "X", "Description": "X", "Material": "X"}]
        generate_excel(PROTECOES_TEMPLATE, rows, output,
                       PROTECOES_COLUMNS, data_start_row=4)
        hdr_after = openpyxl.load_workbook(
            PROTECOES_TEMPLATE)["Folha1"].cell(row=3, column=2).value
        self.assertEqual(hdr_before, hdr_after)
```

- [ ] **Step 2: Run tests — confirm they FAIL**

```bash
cd "c:/Users/Micael/Desktop/Auto Production/tools/exporter"
python -m pytest tests/test_excel_writer.py::TestProtecoesConfig tests/test_excel_writer.py::TestGenerateExcelProtecoes -v
```

Expected: `ImportError: cannot import name 'PROTECOES_COLUMNS'`

- [ ] **Step 3: Add `PROTECOES_COLUMNS` and `"protecoes"` entry to `excel_writer.py`**

In `tools/exporter/excel_writer.py`, after `TORNO_COLUMNS` and before `PROCESS_CONFIG`, add:

```python
PROTECOES_COLUMNS = [
    "qty", "part_number", "Description", "Material",
]
```

Then in `PROCESS_CONFIG`, add the `"protecoes"` entry:

```python
PROCESS_CONFIG = {
    "laser":     ("Laser_template.xlsx",     "Laser.xlsx",     LASER_COLUMNS,     4),
    "router":    ("Router_template.xlsx",    "Router.xlsx",    ROUTER_COLUMNS,    3),
    "cnc":       ("CNC_template.xlsx",       "CNC.xlsx",       CNC_COLUMNS,       4),
    "torno":     ("Torno_template.xlsx",     "Torno.xlsx",     TORNO_COLUMNS,     4),
    "protecoes": ("Protecoes_template.xlsx", "Protecoes.xlsx", PROTECOES_COLUMNS, 4),
}
```

- [ ] **Step 4: Run tests — confirm they PASS**

```bash
python -m pytest tests/test_excel_writer.py::TestProtecoesConfig tests/test_excel_writer.py::TestGenerateExcelProtecoes -v
```

Expected: all new tests PASS.

- [ ] **Step 5: Run full test suite**

```bash
python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
cd "c:/Users/Micael/Desktop/Auto Production"
git add tools/exporter/solidworks.py tools/exporter/excel_writer.py tools/exporter/tests/test_solidworks_helpers.py tools/exporter/tests/test_excel_writer.py
git commit -m "feat: add is_protecoes_part and Protecoes excel config

- solidworks.py: is_protecoes_part() mirrors is_perfil_aluminio pattern
- excel_writer.py: PROTECOES_COLUMNS + PROCESS_CONFIG['protecoes']
  Template: Protecoes_template.xlsx, cols: qty/part_number/Description/Material"
```

---

## Chunk 2: DXF Module refactor

### Task 3: Add Laser/Proteções checkboxes to `dxf_module.py`

**Files:**
- Modify: `tools/exporter/modules/dxf_module.py`

The current panel has one process (Laser). We add a checkbox row so the user can select Laser, Proteções, or both. The existing buttons ("Export DXF" and "Gerar Excel apenas") now iterate over selected processes in one SW session.

Key changes:
- Title: `"DXF Export"` (remove `"— Laser"`)
- Add `self._check_vars` dict with `"laser"` and `"protecoes"` BooleanVars (both `True` by default)
- Guard in `_start_export` and `_start_excel_only`: warn if both unchecked
- `_worker`: `total = len(laser_parts) + len(protecoes_parts)`; loop phases with log label
- `_worker_excel_only`: same selection logic, Excel only
- Rename `_generate_laser_excel` → `_generate_dxf_excel(process_key, parts, all_parts, out_dir)` using `PROCESS_CONFIG`
- Add `is_protecoes_part` to imports

- [ ] **Step 1: Replace `dxf_module.py` with the refactored version**

Replace `tools/exporter/modules/dxf_module.py` entirely with the following:

```python
"""
dxf_module.py — DXF Export panel.

Exports flat-pattern DXFs for selected processes (Laser and/or Proteções).
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

# Ordered list of (label, process_key) for checkboxes
_DXF_PROCESSES = [
    ("Laser",      "laser"),
    ("Proteções",  "protecoes"),
]


class DxfModule(tk.Frame):
    """DXF export panel. Renders inside the shared content frame."""

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
            self, text="DXF Export",
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
        for label, key in _DXF_PROCESSES:
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
            self, text="Export DXF",
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
    # Dialogs
    # ------------------------------------------------------------------

    def _browse_out(self):
        path = filedialog.askdirectory(title="Seleciona a pasta de output")
        if path:
            self.out_var.set(path)

    # ------------------------------------------------------------------
    # Export pipeline
    # ------------------------------------------------------------------

    def _validate_inputs(self):
        """Validate assembly path, output folder, and process selection.
        Returns (asm, out) or (None, None) on failure."""
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
        """Runs in a background thread. All UI updates go through self.after()."""
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from solidworks import (
            connect_to_solidworks, open_assembly, get_all_parts,
            deduplicate_by_path, is_laser_part, is_protecoes_part,
            get_part_path, export_part_to_dxf,
        )
        from dxf_cleaner import clean_dxf

        def ui(fn):
            self.after(0, fn)

        # Snapshot checkbox state before entering background thread
        selected = {k: v.get() for k, v in self._check_vars.items()}

        ok_count = err_count = 0
        asm_doc = asm_opened_by_us = None
        sw = None

        try:
            ui(lambda: self._log("\u2550" * 68))
            ui(lambda: self._log("DXF Export"))
            ui(lambda: self._log("A conectar ao SolidWorks\u2026"))
            sw = connect_to_solidworks()

            ui(lambda: self._log(f"A abrir assembly: {os.path.basename(asm_path)}"))
            asm_doc, asm_opened_by_us = open_assembly(sw, asm_path)

            ui(lambda: self._log("A percorrer componentes\u2026"))
            all_parts    = get_all_parts(asm_doc)
            unique_parts = deduplicate_by_path(all_parts)

            laser_parts     = [p for p in unique_parts if is_laser_part(p)] \
                              if selected.get("laser") else []
            protecoes_parts = [p for p in unique_parts if is_protecoes_part(p)] \
                              if selected.get("protecoes") else []

            total = len(laser_parts) + len(protecoes_parts)
            ui(lambda n=total: self._log(f"  Peças a exportar: {n}"))
            ui(lambda: self._log("\u2500" * 68))

            if total == 0:
                ui(lambda: self._log(
                    "Nenhuma peça encontrada para os processos selecionados. "
                    "Verifica as propriedades no SolidWorks."
                ))
                return

            ui(lambda: self._set_progress(0, total))
            progress_i = 0

            def _export_one(part):
                """Export a single part to DXF. Returns (ok: bool, log_msg: str)."""
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
                        f"{removed} círculo(s) removido(s)" if removed
                        else "sem alterações"
                    )
                    return True, f"  OK    {base_name}.dxf  [{circles_txt}]"
                except Exception as exc:
                    if os.path.isfile(raw_dxf):
                        try:
                            os.remove(raw_dxf)
                        except OSError:
                            pass
                    return False, f"  ERROR {base_name} — {exc}"

            if laser_parts:
                ui(lambda: self._log("  Processo: Laser"))
            for part in laser_parts:
                part_name = os.path.basename(get_part_path(part))
                ui(lambda n=part_name, i=progress_i: (
                    self._set_progress(i, total),
                    self._set_status(f"A processar {n}\u2026"),
                ))
                success, msg = _export_one(part)
                ok_count    += int(success)
                err_count   += int(not success)
                progress_i  += 1
                ui(lambda m=msg: self._log(m))

            if protecoes_parts:
                ui(lambda: self._log("  Processo: Proteções"))
            for part in protecoes_parts:
                part_name = os.path.basename(get_part_path(part))
                ui(lambda n=part_name, i=progress_i: (
                    self._set_progress(i, total),
                    self._set_status(f"A processar {n}\u2026"),
                ))
                success, msg = _export_one(part)
                ok_count    += int(success)
                err_count   += int(not success)
                progress_i  += 1
                ui(lambda m=msg: self._log(m))

            ui(lambda: self._set_progress(total, total))

            # Generate Excel if checkbox is checked
            if self.excel_var.get():
                if laser_parts:
                    ui(lambda: self._log("A gerar Laser.xlsx\u2026"))
                    try:
                        self._generate_dxf_excel("laser", laser_parts, all_parts, out_dir)
                        ui(lambda: self._log("  OK    Laser.xlsx"))
                    except Exception as exc:
                        ui(lambda m=str(exc): self._log(f"  ERROR Laser.xlsx — {m}"))
                if protecoes_parts:
                    ui(lambda: self._log("A gerar Protecoes.xlsx\u2026"))
                    try:
                        self._generate_dxf_excel("protecoes", protecoes_parts,
                                                  all_parts, out_dir)
                        ui(lambda: self._log("  OK    Protecoes.xlsx"))
                    except Exception as exc:
                        ui(lambda m=str(exc): self._log(f"  ERROR Protecoes.xlsx — {m}"))

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
                self._set_status("Concluído.")
                self._log("\u2500" * 68)
                self._log(
                    f"Resultado: {ok_count} exportado(s)  |  {err_count} erro(s)"
                )

            ui(_finish)

    def _generate_dxf_excel(self, process_key: str, parts: list,
                             all_parts: list, out_dir: str) -> None:
        """Generate Excel for a DXF process using PROCESS_CONFIG."""
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from solidworks import get_part_data
        from excel_writer import generate_excel, PROCESS_CONFIG

        template_name, output_name, col_order, data_start_row = PROCESS_CONFIG[process_key]
        template_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))))),
            "Templates", template_name,
        )
        rows = [get_part_data(p, all_parts) for p in parts]
        generate_excel(template_path, rows,
                       os.path.join(out_dir, output_name),
                       col_order, data_start_row)

    def _worker_excel_only(self, asm_path: str, out_dir: str):
        """Background worker for 'Gerar Excel apenas' — no DXF export."""
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from solidworks import (
            connect_to_solidworks, open_assembly, get_all_parts,
            deduplicate_by_path, is_laser_part, is_protecoes_part,
        )

        def ui(fn):
            self.after(0, fn)

        selected = {k: v.get() for k, v in self._check_vars.items()}
        sw = None
        asm_doc = asm_opened_by_us = None

        try:
            ui(lambda: self._log("\u2550" * 68))
            ui(lambda: self._log("Gerar Excel (DXF)"))
            ui(lambda: self._log("A conectar ao SolidWorks\u2026"))
            sw = connect_to_solidworks()

            ui(lambda: self._log(f"A abrir assembly: {os.path.basename(asm_path)}"))
            asm_doc, asm_opened_by_us = open_assembly(sw, asm_path)

            ui(lambda: self._log("A percorrer componentes\u2026"))
            all_parts    = get_all_parts(asm_doc)
            unique_parts = deduplicate_by_path(all_parts)

            laser_parts     = [p for p in unique_parts if is_laser_part(p)] \
                              if selected.get("laser") else []
            protecoes_parts = [p for p in unique_parts if is_protecoes_part(p)] \
                              if selected.get("protecoes") else []

            ui(lambda n=len(laser_parts): self._log(f"  Peças laser: {n}"))
            ui(lambda n=len(protecoes_parts): self._log(f"  Peças proteções: {n}"))

            if laser_parts:
                ui(lambda: self._log("A gerar Laser.xlsx\u2026"))
                try:
                    self._generate_dxf_excel("laser", laser_parts, all_parts, out_dir)
                    ui(lambda: self._log("  OK    Laser.xlsx"))
                except Exception as exc:
                    ui(lambda m=str(exc): self._log(f"  ERROR Laser.xlsx — {m}"))

            if protecoes_parts:
                ui(lambda: self._log("A gerar Protecoes.xlsx\u2026"))
                try:
                    self._generate_dxf_excel("protecoes", protecoes_parts,
                                              all_parts, out_dir)
                    ui(lambda: self._log("  OK    Protecoes.xlsx"))
                except Exception as exc:
                    ui(lambda m=str(exc): self._log(f"  ERROR Protecoes.xlsx — {m}"))

            if not laser_parts and not protecoes_parts:
                ui(lambda: self._log(
                    "Nenhuma peça encontrada para os processos selecionados."))

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
                self._set_status("Concluído.")
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
```

- [ ] **Step 2: Smoke-test the GUI launches without errors**

```bash
cd "c:/Users/Micael/Desktop/Auto Production/tools/exporter"
python -c "
import tkinter as tk
import sys, os
sys.path.insert(0, '.')
from modules.dxf_module import DxfModule
root = tk.Tk()
m = DxfModule(root, print, lambda: '')
m.pack()
root.after(500, root.destroy)
root.mainloop()
print('DxfModule: OK')
"
```

Expected: prints `DxfModule: OK` without exceptions.

- [ ] **Step 3: Run full test suite**

```bash
python -m pytest tests/ -v
```

Expected: all tests pass (no GUI-specific tests for this module).

- [ ] **Step 4: Commit**

```bash
cd "c:/Users/Micael/Desktop/Auto Production"
git add tools/exporter/modules/dxf_module.py
git commit -m "feat: add process checkboxes to DXF panel (Laser + Proteções)

- Checkboxes: Laser and Proteções, both checked by default
- Guard: showwarning if both unchecked
- Progress bar accumulates across both phases
- _generate_dxf_excel() replaces _generate_laser_excel(), uses PROCESS_CONFIG"
```

---

## Chunk 3: STEP Module refactor + Listas + Gerar Tudo

### Task 4: Add Router/CNC/Torno checkboxes to `step_module.py`

**Files:**
- Modify: `tools/exporter/modules/step_module.py`

Key changes:
- Title: `"STEP Export"` (remove `"— Router / CNC / Torno"`)
- Add `self._check_vars` with `"router"`, `"cnc"`, `"torno"` BooleanVars (all `True`)
- Guard: warn if all unchecked
- `_worker`: filter `step_parts` to only selected keywords; `selected_keywords = [k for k, v in self._check_vars.items() if v.get()]`
- `_worker_excel_only`: same filter
- `_generate_step_excels` already only iterates non-empty groups — no change needed there

- [ ] **Step 1: Update `_build_ui` — title and checkboxes**

In `tools/exporter/modules/step_module.py`:

1. Change the title label text from `"STEP Export \u2014 Router / CNC / Torno"` to `"STEP Export"`.

2. After the existing `self.excel_var` Checkbutton (currently Row 3), shift all subsequent `.grid(row=N...)` calls up by +1 (new checkbox row inserts before the existing "Gerar Excel" checkbox), or simply add the new process-checkboxes row at Row 3 and push "Gerar Excel" to Row 4.

Insert after the separator (Row 1) and output folder (Row 2), a new Row 3:

```python
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
```

Then renumber: old Row 3 (Gerar Excel) → Row 4, old Row 4 (btn_export) → Row 5, old Row 5 (btn_excel_only) → Row 6, old Row 6 (progress) → Row 7, old Row 7 (status) → Row 8.

- [ ] **Step 2: Add `_validate_inputs` + update `_start_export` and `_start_excel_only`**

Add this method to `StepModule`:

```python
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
```

Replace the validation block in `_start_export` with:

```python
    def _start_export(self):
        asm, out = self._validate_inputs()
        if asm is None:
            return
        self.btn_export.config(state="disabled")
        self.btn_excel_only.config(state="disabled")
        self.progress["value"] = 0
        self._set_status("A iniciar\u2026")
        threading.Thread(target=self._worker, args=(asm, out), daemon=True).start()
```

Replace `_start_excel_only` similarly:

```python
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
```

- [ ] **Step 3: Filter `step_parts` by selected keywords in `_worker`**

In `_worker`, after `step_parts = [p for p in unique_parts if is_step_part(p)]`, add:

```python
            # Snapshot checkbox state in background thread
            selected_keywords = [k for k, v in self._check_vars.items() if v.get()]
            step_parts = [
                p for p in step_parts
                if any(kw in get_corte_fabrico(p) for kw in selected_keywords)
            ]
```

Also update the "0 parts found" message to reference the selection:

```python
            if total == 0:
                ui(lambda: self._log(
                    "Nenhuma peça encontrada para os processos selecionados. "
                    "Verifica as propriedades no SolidWorks."
                ))
                return
```

- [ ] **Step 4: Filter in `_worker_excel_only`**

First, add `get_corte_fabrico` to the `_worker_excel_only` import (it is not currently there):

```python
        from solidworks import (
            connect_to_solidworks, open_assembly, get_all_parts,
            deduplicate_by_path, is_step_part, get_corte_fabrico,
        )
```

Then, after `step_parts = [p for p in unique_parts if is_step_part(p)]`, add:

```python
            selected_keywords = [k for k, v in self._check_vars.items() if v.get()]
            step_parts = [
                p for p in step_parts
                if any(kw in get_corte_fabrico(p) for kw in selected_keywords)
            ]
```

Update the "no parts" message similarly.

- [ ] **Step 5: Smoke-test**

```bash
cd "c:/Users/Micael/Desktop/Auto Production/tools/exporter"
python -c "
import tkinter as tk
import sys, os
sys.path.insert(0, '.')
from modules.step_module import StepModule
root = tk.Tk()
m = StepModule(root, print, lambda: '')
m.pack()
root.after(500, root.destroy)
root.mainloop()
print('StepModule: OK')
"
```

Expected: prints `StepModule: OK` without exceptions.

- [ ] **Step 6: Run full test suite**

```bash
python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
cd "c:/Users/Micael/Desktop/Auto Production"
git add tools/exporter/modules/step_module.py
git commit -m "feat: add process checkboxes to STEP panel (Router, CNC, Torno)

- Checkboxes: Router, CNC, Torno — all checked by default
- Guard: showwarning if all unchecked
- _worker and _worker_excel_only filter step_parts by selected keywords"
```

---

### Task 5: Add Proteções to `listas_module.py`

**Files:**
- Modify: `tools/exporter/modules/listas_module.py`

Two changes:
1. Add `("Proteções", "protecoes")` to `_LISTS` between Laser and Router
2. Add `if selected.get("protecoes"):` block in `_worker` between the Laser and Router blocks

- [ ] **Step 1: Update `_LISTS`**

In `tools/exporter/modules/listas_module.py`, change:

```python
_LISTS = [
    ("Laser",              "laser"),
    ("Router",             "router"),
```

to:

```python
_LISTS = [
    ("Laser",              "laser"),
    ("Proteções",          "protecoes"),
    ("Router",             "router"),
```

- [ ] **Step 2: Add the `protecoes` phase block in `_worker`**

In the `_worker` method, after the Laser phase block and before the Router phase block, insert:

```python
            # ── Phase: Proteções ──────────────────────────────────────────────────
            if selected.get("protecoes"):
                phase_n += 1
                ui(lambda n=phase_n, t=phase_total: self._log("─" * 68))
                ui(lambda n=phase_n, t=phase_total: self._log(f"[{n}/{t}] Proteções"))
                ui(lambda n=phase_n, t=phase_total: self._set_status(f"[{n}/{t}] Proteções…"))
                errs = self._run_excel_list(sw, asm_doc, out_dir, "protecoes", ui)
                all_errors.extend(errs)
```

- [ ] **Step 3: Smoke-test**

```bash
cd "c:/Users/Micael/Desktop/Auto Production/tools/exporter"
python -c "
import tkinter as tk
import sys, os
sys.path.insert(0, '.')
from modules.listas_module import ListasModule
root = tk.Tk()
m = ListasModule(root, print, lambda: '')
m.pack()
root.after(500, root.destroy)
root.mainloop()
print('ListasModule: OK')
"
```

Expected: prints `ListasModule: OK` without exceptions.

- [ ] **Step 4: Run full test suite**

```bash
python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
cd "c:/Users/Micael/Desktop/Auto Production"
git add tools/exporter/modules/listas_module.py
git commit -m "feat: add Proteções checkbox to Listas panel

- _LISTS: ('Proteções', 'protecoes') between Laser and Router
- _worker: new protecoes phase block between Laser and Router phases
- _run_excel_list else-branch already handles 'protecoes' via substring match"
```

---

### Task 6: Add Proteções DXF to `all_module.py` Phase 1

**Files:**
- Modify: `tools/exporter/modules/all_module.py`

Changes:
- Phase 1 label: `"[1/4] DXF Export — Laser + Proteções"`
- After exporting all Laser DXFs + `Laser.xlsx`, also export all Proteções DXFs + `Protecoes.xlsx`

- [ ] **Step 1: Update Phase 1 label**

In `all_module.py` `_worker`, change:

```python
            ui(lambda: self._log("[1/4] DXF Export \u2014 Laser"))
            ui(lambda: self._set_status("[1/4] DXF Export\u2026"))
```

to:

```python
            ui(lambda: self._log("[1/4] DXF Export \u2014 Laser + Prote\u00e7\u00f5es"))
            ui(lambda: self._set_status("[1/4] DXF Export\u2026"))
```

- [ ] **Step 2: Add Proteções DXF export to `_run_dxf`**

In `_run_dxf`, add `is_protecoes_part` to the import:

```python
        from solidworks import (
            get_all_parts, deduplicate_by_path, is_laser_part, is_protecoes_part,
            get_part_path, export_part_to_dxf, get_part_data,
        )
```

**Important — remove the early-exit guard for Laser:** The current `_run_dxf` has `if not laser_parts: return errors` right after filtering laser parts. This guard must be removed (or changed to check both laser and protecoes), otherwise an assembly with only Proteções parts and no Laser parts will skip the entire Proteções export. Replace the guard with:

```python
            if not laser_parts and not protecoes_parts:
                ui(lambda: self._log("  Nenhuma peça laser/proteções encontrada."))
                return errors
```

(Move this check to after both `laser_parts` and `protecoes_parts` are collected.)

**Important:** `templates_dir` does NOT exist as a variable in the current `_run_dxf` — the existing Laser block builds `template_path` inline with a 4-level `dirname` call. You must introduce `templates_dir` at the top of `_run_dxf` (before the Laser block) so both Laser and Proteções can share it.

First, add at the very start of `_run_dxf` (right after the imports, before `all_parts = ...`):

```python
        templates_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))))),
            "Templates",
        )
```

Then replace the existing Laser `template_path` inline construction with `os.path.join(templates_dir, template_name)`.

After the existing Laser DXF loop + `Laser.xlsx` generation block, add the Proteções block:

```python
            # Proteções DXF
            protecoes_parts = [p for p in unique_parts if is_protecoes_part(p)]
            ui(lambda n=len(protecoes_parts): self._log(f"  Peças proteções: {n}"))

            for part in protecoes_parts:
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
                        f"{removed} círculo(s) removido(s)" if removed
                        else "sem alterações"
                    )
                    msg = f"  OK    {base_name}.dxf  [{circles_txt}]"
                    ui(lambda m=msg: self._log(m))
                except Exception as exc:
                    err_msg = f"DXF {base_name}: {exc}"
                    errors.append(err_msg)
                    ui(lambda m=f"  ERROR {base_name} — {exc}": self._log(m))
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
                    ui(lambda m=str(exc): self._log(f"  ERROR Protecoes.xlsx — {m}"))
```

`PROCESS_CONFIG` is already imported in `_run_dxf` via `from excel_writer import generate_excel, LASER_COLUMNS, PROCESS_CONFIG`.

- [ ] **Step 3: Smoke-test**

```bash
cd "c:/Users/Micael/Desktop/Auto Production/tools/exporter"
python -c "
import tkinter as tk
import sys, os
sys.path.insert(0, '.')
from modules.all_module import AllModule
root = tk.Tk()
m = AllModule(root, print, lambda: '')
m.pack()
root.after(500, root.destroy)
root.mainloop()
print('AllModule: OK')
"
```

Expected: prints `AllModule: OK` without exceptions.

- [ ] **Step 4: Run full test suite**

```bash
python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
cd "c:/Users/Micael/Desktop/Auto Production"
git add tools/exporter/modules/all_module.py
git commit -m "feat: add Proteções DXF to Gerar Tudo Phase 1

Phase 1 now exports Laser DXFs + Laser.xlsx, then Proteções DXFs + Protecoes.xlsx
in the same SolidWorks session. Phase count stays at 4."
```

---

## Final Smoke Test

- [ ] **Launch the full GUI and verify all panels load correctly**

```bash
cd "c:/Users/Micael/Desktop/Auto Production/tools/exporter"
python main.py
```

Verify:
1. **DXF Export** panel shows two checkboxes: `Laser` and `Proteções` (both checked)
2. **STEP Export** panel shows three checkboxes: `Router`, `CNC`, `Torno` (all checked)
3. **Listas** panel shows `Proteções` checkbox between Laser and Router
4. **Gerar Tudo** panel loads without error
