# Integrated Exporter GUI Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the existing DXF Exporter into a unified "Auto Production" desktop app with sidebar navigation, and add STEP AP214 export for router/cnc/torno parts with automatic dowel hole diameter reduction.

**Architecture:** A single `MainWindow` (tk.Tk) hosts a sidebar of navigation buttons and a shared content area. Each feature (DXF export, STEP export) is a `tk.Frame` subclass that lives in `tools/exporter/modules/`. The assembly path field and log area are shared across all modules. SolidWorks COM interactions live entirely in `solidworks.py`.

**Tech Stack:** Python 3.11, tkinter (stdlib), pywin32 (win32com), ezdxf. SolidWorks 2024 must be running. No external GUI libraries.

**Note on testing:** This tool drives SolidWorks via COM. Automated unit tests are not feasible. Each task's verification step is a manual smoke test using SolidWorks and the test assembly `18026.100.900.SLDASM`.

---

## Chunk 1: Scaffold + solidworks.py

---

### Task 1: Create tools/exporter/ directory structure

**Files:**
- Create: `tools/exporter/` (directory)
- Create: `tools/exporter/modules/` (directory)

- [ ] **Step 1: Create directories**

```bash
mkdir -p "tools/exporter/modules"
```

From repo root (`c:\Users\Micael\Desktop\Auto Production\`).

- [ ] **Step 2: Create empty placeholder files so Python treats directories as packages**

Create `tools/exporter/modules/__init__.py` with content:
```python
```
(empty file)

- [ ] **Step 3: Commit**

```bash
git add tools/exporter/
git commit -m "chore: scaffold tools/exporter directory structure"
```

---

### Task 2: Copy and update solidworks.py

**Files:**
- Create: `tools/exporter/solidworks.py` (copy from `tools/dxf_exporter/solidworks.py` then modify)

- [ ] **Step 1: Copy solidworks.py from dxf_exporter**

Copy `tools/dxf_exporter/solidworks.py` to `tools/exporter/solidworks.py`.

- [ ] **Step 2: Update `_open_doc` to support a `silent` parameter**

Find the `_open_doc` function (currently at the bottom of solidworks.py). Replace it with:

```python
def _open_doc(sw_app, path: str, doc_type: int, silent: bool = False):
    """
    Open a SolidWorks document.
    doc_type: 1 = part, 2 = assembly, 3 = drawing.
    silent=True  → options=1 (swOpenDocOptions_Silent), suppresses UI prompts.
                   Use for standalone parts (e.g. tmp copies).
    silent=False → options=0 (non-silent), ensures full component tree for assemblies.
    Raises RuntimeError if the document cannot be opened.
    """
    errors   = _byref_long()
    warnings = _byref_long()
    options  = 1 if silent else 0
    doc = sw_app.OpenDoc6(path, doc_type, options, "", errors, warnings)
    if doc is None:
        err_val = errors.value if hasattr(errors, "value") else errors
        raise RuntimeError(
            f"Não foi possível abrir '{path}'. Código de erro: {err_val}"
        )
    return doc
```

- [ ] **Step 3: Verify the existing DXF functions still call `_open_doc` without the `silent` arg**

Check `export_part_to_dxf` and `export_drawing_to_dxf` — they call `_open_doc(sw_app, path, doc_type=1)` and `_open_doc(sw_app, path, doc_type=3)`. Since `silent` defaults to `False`, these calls are unchanged. No edits needed.

---

### Task 3: Add STEP functions to solidworks.py

**Files:**
- Modify: `tools/exporter/solidworks.py`

These functions go at the end of the file, after the existing DXF export section.

- [ ] **Step 1: Add the `HoleInfo` namedtuple and imports**

At the top of the file, after existing imports, add:

```python
from collections import namedtuple

HoleInfo = namedtuple('HoleInfo', ['feature', 'original_diameter_m'])
```

(`original_diameter_m` is the original hole diameter in **metres**, e.g. 0.010 for a 10 mm dowel.)

- [ ] **Step 2: Add `get_corte_fabrico` and `is_step_part`**

```python
# ---------------------------------------------------------------------------
# STEP export — part selection
# ---------------------------------------------------------------------------

def get_corte_fabrico(component) -> str:
    """
    Return the Corte_Fabrico custom property value, stripped and lowercased.
    Returns empty string if the property is missing or inaccessible.
    """
    try:
        model = component.GetModelDoc2()
        if model is None:
            return ""
        mgr = model.Extension.CustomPropertyManager("")
        try:
            val = mgr.Get("Corte_Fabrico")
        except Exception:
            val = None
        if val is None:
            try:
                result = mgr.Get4("Corte_Fabrico", False)
                val = result[1] if isinstance(result, tuple) and len(result) > 1 else result
            except Exception:
                return ""
        if val is None:
            return ""
        return str(val).strip().lower()
    except Exception:
        return ""


def is_step_part(component) -> bool:
    """
    Return True if Corte_Fabrico contains 'router', 'cnc', or 'torno' (case-insensitive).
    Matches combinations: 'router+cnc', 'CNC+TORNO', etc.
    """
    val = get_corte_fabrico(component)
    return bool(val) and any(k in val for k in ("router", "cnc", "torno"))
```

- [ ] **Step 3: Add `copy_part_to_tmp`**

```python
# ---------------------------------------------------------------------------
# STEP export — temporary copy
# ---------------------------------------------------------------------------

def copy_part_to_tmp(sldprt_path: str, tmp_dir: str) -> str:
    """
    Copy a .sldprt file to tmp_dir with a '_step_tmp' suffix.
    Creates tmp_dir if it does not exist.
    Returns the full path of the copy.
    """
    import shutil
    os.makedirs(tmp_dir, exist_ok=True)
    name, ext = os.path.splitext(os.path.basename(sldprt_path))
    tmp_path = os.path.join(tmp_dir, f"{name}_step_tmp{ext}")
    shutil.copy2(sldprt_path, tmp_path)
    return tmp_path
```

- [ ] **Step 4: Add `get_dowel_holes`**

```python
# ---------------------------------------------------------------------------
# STEP export — dowel hole detection
# ---------------------------------------------------------------------------

def get_dowel_holes(part_doc) -> list:
    """
    Return a list of HoleInfo for every Hole Wizard Dowel hole in the part.

    Iterates all IFeature objects, calls GetSpecificFeature2() on each,
    wraps the result with IHoleWizardFeatureData2, and checks Type against
    swHoleType_Dowel. Collects the hole diameter (IHoleWizardFeatureData2.Diameter,
    in metres, SI units).

    Returns an empty list if no dowel holes are found or on any API error.
    """
    results = []
    try:
        mod = _sw_module()
        dowel_type = mod.swHoleType_Dowel
    except Exception:
        return results

    try:
        feat = part_doc.FirstFeature()
        while feat is not None:
            try:
                feat_data_raw = feat.GetSpecificFeature2()
                if feat_data_raw is not None:
                    try:
                        feat_data = _wrap(feat_data_raw, "IHoleWizardFeatureData2")
                        if feat_data.Type == dowel_type:
                            diameter_m = feat_data.Diameter  # metres (SI)
                            results.append(HoleInfo(feature=feat, original_diameter_m=diameter_m))
                    except Exception:
                        pass  # Not a hole wizard feature — skip silently
            except Exception:
                pass
            try:
                feat = feat.GetNextFeature()
            except Exception:
                break
    except Exception:
        pass

    return results
```

- [ ] **Step 5: Add `modify_dowel_diameter`**

```python
# ---------------------------------------------------------------------------
# STEP export — dowel hole modification
# ---------------------------------------------------------------------------

def modify_dowel_diameter(part_doc, hole: HoleInfo, new_diameter_m: float) -> None:
    """
    Change a dowel hole's diameter to new_diameter_m (metres).

    Sequence required by SolidWorks COM:
      1. GetSpecificFeature2()       — fetch current feature data
      2. set IHoleWizardFeatureData2.Diameter  — update value in memory
      3. IFeature.ModifyDefinition(featureData) — commit back to feature
      4. IModelDoc2.EditRebuild3()   — regenerate geometry

    Raises RuntimeError if ModifyDefinition fails.
    """
    feat = hole.feature
    feat_data_raw = feat.GetSpecificFeature2()
    feat_data = _wrap(feat_data_raw, "IHoleWizardFeatureData2")
    feat_data.Diameter = new_diameter_m
    result = feat.ModifyDefinition(feat_data)
    if not result:
        raise RuntimeError(
            f"ModifyDefinition falhou para o furo de cavilha "
            f"(diâmetro original: {hole.original_diameter_m * 1000:.1f} mm)."
        )
    part_doc.EditRebuild3()
```

- [ ] **Step 6: Add `export_part_to_step`**

```python
# ---------------------------------------------------------------------------
# STEP export
# ---------------------------------------------------------------------------

def export_part_to_step(sw_app, sldprt_path: str, output_step_path: str) -> None:
    """
    Export a SolidWorks part (.sldprt) to STEP AP214.

    If the part is already open in SolidWorks (e.g. a modified tmp copy),
    uses the existing open document — preserving any in-memory modifications.
    If not open, opens it silently and closes it after export.

    Raises RuntimeError on failure.
    """
    sldprt_path = os.path.normpath(os.path.abspath(sldprt_path))
    already_open = sw_app.GetOpenDocumentByName(sldprt_path) is not None
    part_doc = None
    opened_by_us = False

    try:
        if already_open:
            part_doc = sw_app.GetOpenDocumentByName(sldprt_path)
        else:
            part_doc = _open_doc(sw_app, sldprt_path, doc_type=1, silent=True)
            opened_by_us = True

        # Configure STEP export options: AP214 schema
        export_data = None
        try:
            export_data_raw = sw_app.GetExportFileData(2)  # 2 = swExportStep
            export_data = _wrap(export_data_raw, "IStepExportOptions")
            mod = _sw_module()
            export_data.ExportAs = mod.swStepAP214
        except Exception:
            export_data = None  # Fallback: IStepExportOptions unavailable in these stubs
            import warnings
            warnings.warn(
                "IStepExportOptions não disponível — o schema STEP depende da configuração "
                "atual do SolidWorks (pode não ser AP214).",
                RuntimeWarning, stacklevel=2
            )

        errors   = _byref_long()
        warnings = _byref_long()
        result = part_doc.SaveAs4(output_step_path, 0, 1, export_data, errors, warnings)
        if not result:
            err_val = errors.value if hasattr(errors, "value") else errors
            raise RuntimeError(f"SaveAs4 falhou (código {err_val}).")

    finally:
        if opened_by_us and part_doc is not None:
            try:
                sw_app.CloseDoc(sldprt_path)
            except Exception:
                pass
```

- [ ] **Step 7: Smoke-test solidworks.py imports**

```bash
cd "c:\Users\Micael\Desktop\Auto Production\tools\exporter"
python -c "import solidworks; print('OK')"
```

Expected: `OK` (no import errors). SolidWorks does not need to be running for this check.

- [ ] **Step 8: Commit**

```bash
git add tools/exporter/solidworks.py
git commit -m "feat: add STEP export functions to solidworks.py"
```

---

### Task 4: Copy dxf_cleaner.py and requirements.txt

**Files:**
- Create: `tools/exporter/dxf_cleaner.py` (copy unchanged)
- Create: `tools/exporter/requirements.txt`

- [ ] **Step 1: Copy dxf_cleaner.py**

Copy `tools/dxf_exporter/dxf_cleaner.py` to `tools/exporter/dxf_cleaner.py`. No changes needed.

- [ ] **Step 2: Create requirements.txt**

```
pywin32>=306
ezdxf>=1.1.0
```

- [ ] **Step 3: Commit**

```bash
git add tools/exporter/dxf_cleaner.py tools/exporter/requirements.txt
git commit -m "chore: copy dxf_cleaner and requirements to tools/exporter"
```

---

## Chunk 2: main.py — sidebar window

---

### Task 5: Create main.py

**Files:**
- Create: `tools/exporter/main.py`

`main.py` is the entry point. It creates the `MainWindow`, builds the sidebar, shared assembly header, stacked content frames (one per module), and shared log area.

- [ ] **Step 1: Create tools/exporter/main.py**

```python
"""
main.py — Auto Production
Unified export tool for SolidWorks assemblies.
Sidebar navigation, shared assembly path, shared log.

Usage:
    python main.py
"""

import os
import sys
import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk

# Ensure sibling modules are importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.dxf_module import DxfModule
from modules.step_module import StepModule

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
    ("DXF Export",  "dxf",  DxfModule),
    ("STEP Export", "step", StepModule),
]


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Auto Production")
        self.configure(bg=BG_MAIN)
        self.minsize(820, 560)
        self.resizable(True, True)

        self._apply_ttk_theme()
        self._build_ui()
        self._switch_module("dxf")  # Show DXF module by default

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
            header, text="Browse…",
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

    def _log(self, msg: str):
        self.log_widget.configure(state="normal")
        self.log_widget.insert("end", msg + "\n")
        self.log_widget.see("end")
        self.log_widget.configure(state="disabled")

    def _clear_log(self):
        self.log_widget.configure(state="normal")
        self.log_widget.delete("1.0", "end")
        self.log_widget.configure(state="disabled")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = MainWindow()
    app.mainloop()
```

- [ ] **Step 2: Verify main.py opens without SolidWorks running**

```bash
cd "c:\Users\Micael\Desktop\Auto Production\tools\exporter"
python main.py
```

Expected: window opens with sidebar showing "DXF Export" and "STEP Export". Assembly Browse works. Log area visible. No errors in terminal.

If `modules.dxf_module` or `modules.step_module` don't exist yet, stub them (see below) or skip this until Task 7+8 are done.

- [ ] **Step 3: Commit**

```bash
git add tools/exporter/main.py
git commit -m "feat: add MainWindow with sidebar navigation"
```

---

## Chunk 3: modules/

---

### Task 6: Create modules/dxf_module.py

**Files:**
- Create: `tools/exporter/modules/dxf_module.py`

This is the DXF export panel, extracted from `tools/dxf_exporter/main.py` and adapted to use the shared log and assembly path callbacks.

- [ ] **Step 1: Create tools/exporter/modules/dxf_module.py**

```python
"""
dxf_module.py — DXF Export panel.

Exports flat-pattern DXFs for all 'corte fabrico = laser' parts in the assembly.
Uses the shared log and assembly path from MainWindow.
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, ttk

# Colour palette (imported from parent via passed references, or defined locally)
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

        # Section title
        tk.Label(
            self, text="DXF Export — Laser",
            bg=BG_CONTENT, fg=TEXT_WHITE,
            font=("Segoe UI", 11, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=14, pady=(14, 4))

        tk.Frame(self, bg=BORDER, height=1).grid(
            row=1, column=0, columnspan=3, sticky="ew", padx=14, pady=(0, 10))

        # Output folder
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
            self, text="Browse…",
            command=self._browse_out,
            bg="#1e1e2e", fg=TEXT,
            activebackground=ACCENT, activeforeground=TEXT_WHITE,
            relief="flat", font=FONT_LABEL, padx=10, pady=4,
            cursor="hand2",
        ).grid(row=2, column=2, padx=(0, 14))

        # Export button
        self.btn_export = tk.Button(
            self, text="Export DXF",
            command=self._start_export,
            bg=ACCENT, fg=TEXT_WHITE,
            activebackground="#005fa3", activeforeground=TEXT_WHITE,
            font=FONT_BTN, padx=24, pady=8,
            relief="flat", cursor="hand2",
        )
        self.btn_export.grid(row=3, column=0, columnspan=3, pady=(10, 6))

        # Progress bar
        self.progress = ttk.Progressbar(self, length=500, mode="determinate")
        self.progress.grid(row=4, column=0, columnspan=3, padx=14, pady=(4, 0))

        # Status label
        self.status_var = tk.StringVar(value="Pronto.")
        tk.Label(
            self, textvariable=self.status_var,
            bg=BG_CONTENT, fg=TEXT_DIM, font=FONT_LABEL, anchor="w",
        ).grid(row=5, column=0, columnspan=3, sticky="w", padx=14, pady=(2, 4))

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

    def _start_export(self):
        from tkinter import messagebox
        asm = self._get_asm_path()
        out = self.out_var.get().strip()

        if not asm or not os.path.isfile(asm):
            messagebox.showerror("Erro", "Seleciona um ficheiro .sldasm válido.")
            return
        if not out or not os.path.isdir(out):
            messagebox.showerror("Erro", "Seleciona uma pasta de output válida.")
            return

        self.btn_export.config(state="disabled")
        self.progress["value"] = 0
        self._set_status("A iniciar…")

        thread = threading.Thread(
            target=self._worker, args=(asm, out), daemon=True)
        thread.start()

    def _worker(self, asm_path: str, out_dir: str):
        """Runs in a background thread. All UI updates go through self.after()."""
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from solidworks import (
            connect_to_solidworks, open_assembly, get_all_parts,
            deduplicate_by_path, is_laser_part, get_part_path,
            export_part_to_dxf,
        )
        from dxf_cleaner import clean_dxf

        def ui(fn):
            self.after(0, fn)

        ok_count = warn_count = err_count = 0
        asm_doc = asm_opened_by_us = None

        try:
            ui(lambda: self._log("═" * 68))
            ui(lambda: self._log("DXF Export"))
            ui(lambda: self._log("A conectar ao SolidWorks…"))
            sw = connect_to_solidworks()

            ui(lambda: self._log(f"A abrir assembly: {os.path.basename(asm_path)}"))
            asm_doc, asm_opened_by_us = open_assembly(sw, asm_path)

            ui(lambda: self._log("A percorrer componentes…"))
            all_parts   = get_all_parts(asm_doc)
            unique_parts = deduplicate_by_path(all_parts)
            laser_parts  = [p for p in unique_parts if is_laser_part(p)]

            ui(lambda: self._log(
                f"Total: {len(all_parts)} | Únicas: {len(unique_parts)} | Laser: {len(laser_parts)}"
            ))
            ui(lambda: self._log("─" * 68))

            total = len(laser_parts)
            if total == 0:
                ui(lambda: self._log(
                    "Nenhuma peça com 'corte fabrico = laser'. "
                    "Verifica as propriedades no SolidWorks."
                ))
                return

            ui(lambda: self._set_progress(0, total))

            for i, part in enumerate(laser_parts):
                part_path = get_part_path(part)
                part_name = os.path.basename(part_path)
                base_name = os.path.splitext(part_name)[0]

                ui(lambda n=part_name, idx=i: (
                    self._set_progress(idx, total),
                    self._set_status(f"A processar {n}…"),
                ))

                raw_dxf   = os.path.join(out_dir, base_name + "_raw.dxf")
                final_dxf = os.path.join(out_dir, base_name + ".dxf")

                try:
                    export_part_to_dxf(sw, part_path, raw_dxf)
                    removed = clean_dxf(raw_dxf, final_dxf)
                    try:
                        os.remove(raw_dxf)
                    except OSError:
                        pass
                    ok_count += 1
                    circles_txt = (
                        f"{removed} círculo(s) removido(s)" if removed else "sem alterações"
                    )
                    msg = f"  OK    {base_name}.dxf  [{circles_txt}]"
                    ui(lambda m=msg: self._log(m))
                except Exception as exc:
                    err_count += 1
                    msg = f"  ERROR {base_name} — {exc}"
                    ui(lambda m=msg: self._log(m))
                    if os.path.isfile(raw_dxf):
                        try:
                            os.remove(raw_dxf)
                        except OSError:
                            pass

            ui(lambda: self._set_progress(total, total))

        except Exception as exc:
            err_count += 1
            ui(lambda m=str(exc): self._log(f"ERRO FATAL: {m}"))

        finally:
            if asm_opened_by_us and asm_doc is not None:
                try:
                    sw.CloseDoc(asm_path)
                except Exception:
                    pass

            def _finish():
                self.btn_export.config(state="normal")
                self._set_status("Concluído.")
                self._log("─" * 68)
                self._log(
                    f"Resultado: {ok_count} exportado(s)  |  "
                    f"{warn_count} aviso(s)  |  {err_count} erro(s)"
                )

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

- [ ] **Step 2: Commit**

```bash
git add tools/exporter/modules/dxf_module.py
git commit -m "feat: add DxfModule panel extracted from old main.py"
```

---

### Task 7: Create modules/step_module.py

**Files:**
- Create: `tools/exporter/modules/step_module.py`

- [ ] **Step 1: Create tools/exporter/modules/step_module.py**

```python
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

        # Section title
        tk.Label(
            self, text="STEP Export — Router / CNC / Torno",
            bg=BG_CONTENT, fg=TEXT_WHITE,
            font=("Segoe UI", 11, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=14, pady=(14, 4))

        tk.Frame(self, bg=BORDER, height=1).grid(
            row=1, column=0, columnspan=3, sticky="ew", padx=14, pady=(0, 10))

        # Output folder
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
            self, text="Browse…",
            command=self._browse_out,
            bg="#1e1e2e", fg=TEXT,
            activebackground=ACCENT, activeforeground=TEXT_WHITE,
            relief="flat", font=FONT_LABEL, padx=10, pady=4,
            cursor="hand2",
        ).grid(row=2, column=2, padx=(0, 14))

        # Export button
        self.btn_export = tk.Button(
            self, text="Export STEP",
            command=self._start_export,
            bg=ACCENT, fg=TEXT_WHITE,
            activebackground="#005fa3", activeforeground=TEXT_WHITE,
            font=FONT_BTN, padx=24, pady=8,
            relief="flat", cursor="hand2",
        )
        self.btn_export.grid(row=3, column=0, columnspan=3, pady=(10, 6))

        # Progress bar
        self.progress = ttk.Progressbar(self, length=500, mode="determinate")
        self.progress.grid(row=4, column=0, columnspan=3, padx=14, pady=(4, 0))

        # Status label
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
    # Export pipeline
    # ------------------------------------------------------------------

    def _start_export(self):
        from tkinter import messagebox
        asm = self._get_asm_path()
        out = self.out_var.get().strip()

        if not asm or not os.path.isfile(asm):
            messagebox.showerror("Erro", "Seleciona um ficheiro .sldasm válido.")
            return
        if not out or not os.path.isdir(out):
            messagebox.showerror("Erro", "Seleciona uma pasta de output válida.")
            return

        self.btn_export.config(state="disabled")
        self.progress["value"] = 0
        self._set_status("A iniciar…")

        thread = threading.Thread(
            target=self._worker, args=(asm, out), daemon=True)
        thread.start()

    def _worker(self, asm_path: str, out_dir: str):
        """Runs in background thread. All UI updates via self.after()."""
        sw_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, sw_dir)
        from solidworks import (
            connect_to_solidworks, open_assembly, get_all_parts,
            deduplicate_by_path, is_step_part, get_corte_fabrico,
            get_part_path, copy_part_to_tmp, get_dowel_holes,
            modify_dowel_diameter, export_part_to_step,
        )

        def ui(fn):
            self.after(0, fn)

        ok_count = skip_count = err_count = 0
        asm_doc = asm_opened_by_us = None

        try:
            ui(lambda: self._log("═" * 68))
            ui(lambda: self._log("STEP Export"))
            ui(lambda: self._log("A conectar ao SolidWorks…"))
            sw = connect_to_solidworks()

            ui(lambda: self._log(f"A abrir assembly: {os.path.basename(asm_path)}"))
            asm_doc, asm_opened_by_us = open_assembly(sw, asm_path)

            ui(lambda: self._log("A percorrer componentes…"))
            all_parts    = get_all_parts(asm_doc)
            unique_parts = deduplicate_by_path(all_parts)
            step_parts   = [p for p in unique_parts if is_step_part(p)]

            # Categorise by treatment
            router_parts = [p for p in step_parts
                            if "router" in get_corte_fabrico(p)]
            direct_parts = [p for p in step_parts
                            if "router" not in get_corte_fabrico(p)]

            ui(lambda: self._log(
                f"A exportar STEP: {len(step_parts)} peça(s) — "
                f"router: {len(router_parts)} | direto (cnc/torno): {len(direct_parts)}"
            ))
            ui(lambda: self._log("─" * 68))

            total = len(step_parts)
            if total == 0:
                ui(lambda: self._log(
                    "Nenhuma peça com corte fabrico router/cnc/torno. "
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
                        self._set_status(f"A processar {n}…"),
                    ))

                    output_step = os.path.join(out_dir, base_name + ".step")

                    try:
                        if is_router:
                            # Check: if part is already open, we can't safely copy it
                            already_open = sw.GetOpenDocumentByName(part_path) is not None
                            if already_open:
                                skip_count += 1
                                msg = (f"  SKIP  {base_name} — "
                                       "ficheiro aberto no SolidWorks; fechar e tentar novamente")
                                ui(lambda m=msg: self._log(m))
                                continue

                            note = self._export_router_part(
                                sw, part_path, output_step, tmp_dir)
                        else:
                            export_part_to_step(sw, part_path, output_step)
                            note = f"{corte} — exportado direto"

                        ok_count += 1
                        msg = f"  OK    {base_name}.step  [{note}]"
                        ui(lambda m=msg: self._log(m))

                    except Exception as exc:
                        err_count += 1
                        msg = f"  ERROR {base_name} — {exc}"
                        ui(lambda m=msg: self._log(m))

                ui(lambda: self._set_progress(total, total))

            finally:
                # Individual tmp files are deleted inside _export_router_part's finally.
                # The shared .tmp/ directory is NOT deleted — it is a persistent project dir.
                pass

        except Exception as exc:
            err_count += 1
            ui(lambda m=str(exc): self._log(f"ERRO FATAL: {m}"))

        finally:
            if asm_opened_by_us and asm_doc is not None:
                try:
                    sw.CloseDoc(asm_path)
                except Exception:
                    pass

            def _finish():
                self.btn_export.config(state="normal")
                self._set_status("Concluído.")
                self._log("─" * 68)
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
            export_part_to_step, _open_doc,  # _open_doc: Python does not enforce underscore privacy
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
                dowel_notes.append(f"⌀{orig_mm:.0f}→⌀{new_mm:.0f}")

            # Export STEP from the modified (still-open) tmp doc
            export_part_to_step(sw, tmp_path, output_step)

            if dowel_notes:
                return f"{len(holes)} dowel(s) reduzido(s): {', '.join(dowel_notes)}"
            return "sem furos de cavilha"

        finally:
            if tmp_doc is not None:
                try:
                    sw.CloseDoc(tmp_path)
                except Exception:
                    pass
            if tmp_path and os.path.isfile(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------

    def _set_status(self, text: str):
        self.status_var.set(text)

    def _set_progress(self, value: int, maximum: int):
        self.progress["maximum"] = maximum or 1
        self.progress["value"]   = value
```

- [ ] **Step 2: Commit**

```bash
git add tools/exporter/modules/step_module.py
git commit -m "feat: add StepModule panel with router dowel modification"
```

---

## Chunk 4: run_dxf.py + verification

---

### Task 8: Create run_dxf.py

**Files:**
- Create: `tools/exporter/run_dxf.py`

Headless runner for the DXF export pipeline (for testing without GUI).

- [ ] **Step 1: Create tools/exporter/run_dxf.py**

```python
"""
run_dxf.py — headless DXF export (no GUI).
Usage: python run_dxf.py [assembly.sldasm] [output_dir]
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from solidworks import (
    connect_to_solidworks, open_assembly, get_all_parts,
    deduplicate_by_path, is_laser_part, get_part_path,
    export_part_to_dxf,
)
from dxf_cleaner import clean_dxf


def run(asm_path: str, out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    asm_path = os.path.abspath(asm_path)

    print("Conectando ao SolidWorks…")
    sw = connect_to_solidworks()

    print(f"A abrir: {os.path.basename(asm_path)}")
    asm_doc, asm_opened = open_assembly(sw, asm_path)

    ok = err = 0
    try:
        all_parts    = get_all_parts(asm_doc)
        unique       = deduplicate_by_path(all_parts)
        laser        = [p for p in unique if is_laser_part(p)]

        print(f"Total: {len(all_parts)} | Únicas: {len(unique)} | Laser: {len(laser)}")
        print("─" * 60)

        for part in laser:
            path      = get_part_path(part)
            name      = os.path.splitext(os.path.basename(path))[0]
            raw       = os.path.join(out_dir, name + "_raw.dxf")
            final     = os.path.join(out_dir, name + ".dxf")
            try:
                export_part_to_dxf(sw, path, raw)
                removed = clean_dxf(raw, final)
                try:
                    os.remove(raw)
                except OSError:
                    pass
                ok += 1
                print(f"  OK    {name}.dxf [{removed} círculo(s) removido(s)]")
            except Exception as exc:
                err += 1
                print(f"  ERROR {name} — {exc}")
                if os.path.isfile(raw):
                    try:
                        os.remove(raw)
                    except OSError:
                        pass
    finally:
        if asm_opened:
            try:
                sw.CloseDoc(asm_path)
            except Exception:
                pass

    print("─" * 60)
    print(f"Resultado: {ok} exportado(s)  |  {err} erro(s)")


if __name__ == "__main__":
    asm = (sys.argv[1] if len(sys.argv) > 1
           else r"c:\Users\Micael\Desktop\Auto Production\18026.100.900.SLDASM")
    out = (sys.argv[2] if len(sys.argv) > 2
           else r"c:\Users\Micael\Desktop\Auto Production\resultados")
    run(asm, out)
```

- [ ] **Step 2: Commit**

```bash
git add tools/exporter/run_dxf.py
git commit -m "feat: add run_dxf.py headless runner for tools/exporter"
```

---

### Task 9: Smoke test — GUI opens correctly

- [ ] **Step 1: Launch the GUI**

With SolidWorks **closed** (not required for this test):

```bash
cd "c:\Users\Micael\Desktop\Auto Production\tools\exporter"
python main.py
```

Expected:
- Window opens titled "Auto Production"
- Sidebar shows "DXF Export" and "STEP Export" buttons
- "DXF Export" button is highlighted in blue (active)
- Assembly browse button works (file dialog opens)
- Log area is visible at the bottom
- Clicking "STEP Export" switches the panel

- [ ] **Step 2: Verify sidebar switching**

Click "STEP Export" in the sidebar.
Expected: panel changes to show "STEP Export — Router / CNC / Torno" title.

Click "DXF Export" in the sidebar.
Expected: panel changes back to show "DXF Export — Laser" title.

- [ ] **Step 3: Verify validation**

Click "Export DXF" without filling in the assembly path.
Expected: error dialog "Seleciona um ficheiro .sldasm válido."

Click "Export STEP" without filling in the assembly path.
Expected: same error dialog.

---

### Task 10: Full integration test — DXF export regression

**Requires:** SolidWorks running with `18026.100.900.SLDASM` open (or available).

- [ ] **Step 1: Run headless DXF export**

```bash
cd "c:\Users\Micael\Desktop\Auto Production\tools\exporter"
python run_dxf.py
```

Expected output:
```
Conectando ao SolidWorks…
A abrir: 18026.100.900.SLDASM
Total: X | Únicas: X | Laser: 3
────────────────────────────────────────────────────
  OK    18026.100.001.dxf [1 círculo(s) removido(s)]
  OK    18026.100.002.dxf [1 círculo(s) removido(s)]
  OK    18026.100.003.dxf [1 círculo(s) removido(s)]
────────────────────────────────────────────────────
Resultado: 3 exportado(s)  |  0 erro(s)
```

Verify DXF files exist in `resultados/` with correct geometry.

- [ ] **Step 2: Verify original parts are unmodified**

Check that the `.sldprt` files in the assembly have not been modified (timestamps unchanged).

---

### Task 11: Full integration test — STEP export

**Requires:** SolidWorks running with `18026.100.900.SLDASM` open.
**Prerequisite:** At least one part with `Corte_Fabrico = router` and at least one Hole Wizard Dowel hole, or `cnc`/`torno`.

- [ ] **Step 1: Run STEP export via GUI**

1. Open `python main.py`
2. Set assembly path to `18026.100.900.SLDASM`
3. Switch to "STEP Export" in sidebar
4. Set output folder to `c:\Users\Micael\Desktop\Auto Production\resultados_step`
5. Click "Export STEP"

Expected log output pattern:
```
═════════════════════════════════════════════════════════════════════
STEP Export
A conectar ao SolidWorks…
A abrir assembly: 18026.100.900.SLDASM
A percorrer componentes…
A exportar STEP: N peça(s) — router: X | direto (cnc/torno): Y
────────────────────────────────────────────────────────────────────
  OK    <part>.step  [N dowel(s) reduzido(s): ⌀10→⌀9, ...]
  ...
────────────────────────────────────────────────────────────────────
Resultado: N exportado(s)  |  0 ignorado(s)  |  0 erro(s)
```

- [ ] **Step 2: Verify STEP files exist and open correctly**

Open each `.step` file in SolidWorks (File → Open → select `.step`).
Verify the geometry loads without errors.

- [ ] **Step 3: Verify router parts — dowel holes reduced by exactly 1 mm**

For each router part's STEP file: open in SolidWorks and measure Hole Wizard Dowel hole diameters.
Expected: each dowel hole diameter is exactly 1 mm smaller than in the original `.sldprt`.
Example: original ⌀10 mm → exported ⌀9 mm.

- [ ] **Step 4: Verify cnc/torno parts — exported unchanged**

For each cnc or torno part (no `router` in `Corte_Fabrico`): open the exported `.step` in SolidWorks.
Expected: all hole diameters are identical to the original `.sldprt` (no modification was applied).

- [ ] **Step 5: Verify router+cnc combination — treated as router**

If the assembly contains a part with `Corte_Fabrico = router+cnc` (or similar combination), verify it was treated as a router part: log should show `dowel(s) reduzido(s)` and dowel diameters should be reduced in the exported STEP.
Skip this step if the test assembly has no router+cnc combination parts.

- [ ] **Step 6: Verify original .sldprt files are unmodified**

Open the original `.sldprt` files in SolidWorks and verify all hole diameters are unchanged (same as before the export).

- [ ] **Step 7: Verify no tmp files left behind**

Check that `c:\Users\Micael\Desktop\Auto Production\.tmp\` contains no `*_step_tmp.sldprt` files after a successful export run.

- [ ] **Step 8: Commit final state**

```bash
git add tools/exporter/
git commit -m "feat: complete integrated exporter GUI with STEP AP214 export"
```

---

## Summary — Files created/modified

| File | Action |
|------|--------|
| `tools/exporter/solidworks.py` | Copied + updated `_open_doc` + added 6 STEP functions |
| `tools/exporter/dxf_cleaner.py` | Copied unchanged |
| `tools/exporter/main.py` | New — MainWindow with sidebar |
| `tools/exporter/modules/__init__.py` | New — empty package marker |
| `tools/exporter/modules/dxf_module.py` | New — DXF export panel |
| `tools/exporter/modules/step_module.py` | New — STEP export panel |
| `tools/exporter/run_dxf.py` | New — headless DXF runner |
| `tools/exporter/requirements.txt` | New — dependencies |
| `tools/dxf_exporter/` | Unchanged — kept for reference |
