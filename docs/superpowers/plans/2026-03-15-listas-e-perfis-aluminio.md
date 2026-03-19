# Listas Panel + Perfis de Alumínio Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the "Lista de Material" sidebar tab to "Listas" with checkboxes for 6 report types, and add a new "Perfis de Alumínio" list that reads weldment cut list data directly from SolidWorks part features.

**Architecture:** New `listas_module.py` replaces `bom_module.py` as the nav entry — adds checkboxes + runs selected phases (Laser/Router/CNC/Torno/BOM/Perfis) in one worker. Core weldment logic added to `solidworks.py` (`get_perfis_parts`, `get_weldment_cut_list`). New `perfis_writer.py` handles Excel output. `all_module.py` gains phase 4.

**Tech Stack:** Python 3, win32com (SolidWorks COM API, SW 2024), tkinter, openpyxl, unittest + MagicMock

---

## Chunk 1: Data Layer

### Task 1: Add weldment helpers to solidworks.py

**Files:**
- Modify: `tools/exporter/solidworks.py`

- [ ] **Step 1: Add `unicodedata` to imports**

In `solidworks.py`, the imports block (lines 13–16) currently reads:
```python
import os
import re
from typing import List, Optional
from collections import namedtuple
```
Add `unicodedata`:
```python
import os
import re
import unicodedata
from typing import List, Optional
from collections import namedtuple
```

- [ ] **Step 2: Add `CutListItem` namedtuple after the existing namedtuples (line ~24)**

```python
CutListItem = namedtuple('CutListItem', ['description', 'length_mm', 'qty'])
# description: str  — profile description from DESCRIPTION cut-list property
# length_mm:   float — length parsed from LENGTH property (already in mm, no conversion)
# qty:         int  — quantity from QUANTITY/QTY property × assembly instance count
```

- [ ] **Step 3: Add `_normalize_corte` helper and `is_perfil_aluminio` after `is_step_part` (~line 424)**

```python
def _normalize_corte(val: str) -> str:
    """Strip accents and lowercase — used for Corte_Fabrico accent-insensitive matching."""
    nfkd = unicodedata.normalize("NFD", val.lower())
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


def is_perfil_aluminio(component) -> bool:
    """
    Return True if Corte_Fabrico matches 'PERFIL ALUMINIO' or 'PERFIL ALUMÍNIO'.
    Uses get_corte_fabrico (already lowercased) + NFD accent stripping.
    """
    val = get_corte_fabrico(component)  # already .strip().lower()
    if not val:
        return False
    return "perfil aluminio" in _normalize_corte(val)
```

- [ ] **Step 4: Add `get_perfis_parts` after `is_perfil_aluminio`**

```python
def get_perfis_parts(asm_doc) -> list:
    """
    Return list of (part_path: str, instance_count: int) for all unique
    parts whose Corte_Fabrico matches 'PERFIL ALUMINIO'/'PERFIL ALUMÍNIO'.

    Uses the existing get_all_parts / deduplicate_by_path / count_instances helpers.
    instance_count = number of non-suppressed instances of that .sldprt in the assembly.
    """
    all_parts = get_all_parts(asm_doc)
    perfil_parts = [p for p in all_parts if is_perfil_aluminio(p)]
    unique = deduplicate_by_path(perfil_parts)

    result = []
    for comp in unique:
        try:
            path_ref = comp.GetPathName
            path = path_ref() if callable(path_ref) else path_ref
            if isinstance(path, tuple):
                path = path[0]
            path = os.path.normpath(os.path.abspath(path))
            count = count_instances(all_parts, path)
            result.append((path, count))
        except Exception:
            continue
    return result
```

- [ ] **Step 5: Write failing tests for `get_weldment_cut_list` BEFORE implementing it (TDD)**

Append to `tools/exporter/tests/test_solidworks_helpers.py`:

```python
# ---------------------------------------------------------------------------
# get_weldment_cut_list
# ---------------------------------------------------------------------------
from unittest.mock import patch

class TestGetWeldmentCutList(unittest.TestCase):
    """Mocked COM tests for get_weldment_cut_list. No SW running required."""

    def _make_cut_feat(self, desc="Profile A", length="350.0", qty="2", suppressed=False):
        feat = MagicMock()
        feat.GetTypeName2.return_value = "CutListFolder"
        feat.IsSuppressed = suppressed  # non-callable (property-style, SW 2024 early binding)
        feat.Name = f"CutList<{desc}>"
        feat.GetCustomInfoValue.side_effect = lambda config, prop: {
            "DESCRIPTION": desc, "LENGTH": length, "QUANTITY": qty,
        }.get(prop, "")
        feat.GetNextFeature.return_value = None
        return feat

    def _wrap_side(self, mock_part):
        def side(obj, iface):
            return mock_part if iface == "IPartDoc" else obj
        return side

    @patch("solidworks._open_doc")
    @patch("solidworks._wrap")
    def test_reads_cut_list_item(self, mock_wrap, mock_open_doc):
        from solidworks import get_weldment_cut_list
        feat = self._make_cut_feat("Aluminium profile 40x40", "350.0", "2")
        mock_doc = MagicMock()
        mock_open_doc.return_value = mock_doc
        mock_part = MagicMock()
        mock_part.FirstFeature.return_value = feat
        mock_wrap.side_effect = self._wrap_side(mock_part)
        items, warnings = get_weldment_cut_list(MagicMock(), "C:\\parts\\part.sldprt")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].description, "Aluminium profile 40x40")
        self.assertAlmostEqual(items[0].length_mm, 350.0)
        self.assertEqual(items[0].qty, 2)
        self.assertEqual(warnings, [])

    @patch("solidworks._open_doc")
    @patch("solidworks._wrap")
    def test_skips_suppressed_folder(self, mock_wrap, mock_open_doc):
        from solidworks import get_weldment_cut_list
        feat = self._make_cut_feat(suppressed=True)
        mock_doc = MagicMock()
        mock_open_doc.return_value = mock_doc
        mock_part = MagicMock()
        mock_part.FirstFeature.return_value = feat
        mock_wrap.side_effect = self._wrap_side(mock_part)
        items, _ = get_weldment_cut_list(MagicMock(), "C:\\parts\\part.sldprt")
        self.assertEqual(items, [])

    @patch("solidworks._open_doc")
    @patch("solidworks._wrap")
    def test_quantity_fallback_to_qty_key(self, mock_wrap, mock_open_doc):
        from solidworks import get_weldment_cut_list
        feat = MagicMock()
        feat.GetTypeName2.return_value = "CutListFolder"
        feat.IsSuppressed = False
        feat.Name = "CutList"
        feat.GetCustomInfoValue.side_effect = lambda c, p: {
            "DESCRIPTION": "Profile A", "LENGTH": "100.0",
            "QUANTITY": "", "QTY": "3",
        }.get(p, "")
        feat.GetNextFeature.return_value = None
        mock_doc = MagicMock()
        mock_open_doc.return_value = mock_doc
        mock_part = MagicMock()
        mock_part.FirstFeature.return_value = feat
        mock_wrap.side_effect = self._wrap_side(mock_part)
        items, warnings = get_weldment_cut_list(MagicMock(), "C:\\parts\\part.sldprt")
        self.assertEqual(items[0].qty, 3)
        self.assertEqual(warnings, [])

    @patch("solidworks._open_doc")
    @patch("solidworks._wrap")
    def test_quantity_defaults_to_1_and_warns(self, mock_wrap, mock_open_doc):
        from solidworks import get_weldment_cut_list
        feat = MagicMock()
        feat.GetTypeName2.return_value = "CutListFolder"
        feat.IsSuppressed = False
        feat.Name = "CutListItem1"
        feat.GetCustomInfoValue.side_effect = lambda c, p: {
            "DESCRIPTION": "Profile A", "LENGTH": "100.0",
        }.get(p, "")
        feat.GetNextFeature.return_value = None
        mock_doc = MagicMock()
        mock_open_doc.return_value = mock_doc
        mock_part = MagicMock()
        mock_part.FirstFeature.return_value = feat
        mock_wrap.side_effect = self._wrap_side(mock_part)
        items, warnings = get_weldment_cut_list(MagicMock(), "C:\\parts\\part.sldprt")
        self.assertEqual(items[0].qty, 1)
        self.assertTrue(any("QUANTITY/QTY" in w for w in warnings))

    @patch("solidworks._open_doc")
    @patch("solidworks._wrap")
    def test_close_doc_called_in_finally(self, mock_wrap, mock_open_doc):
        from solidworks import get_weldment_cut_list
        mock_sw = MagicMock()
        mock_doc = MagicMock()
        mock_open_doc.return_value = mock_doc
        mock_part = MagicMock()
        mock_part.FirstFeature.return_value = None
        mock_wrap.side_effect = self._wrap_side(mock_part)
        get_weldment_cut_list(mock_sw, "C:\\parts\\part.sldprt")
        mock_sw.CloseDoc.assert_called_once()
```

Run to confirm they fail:
```bash
cd "c:\Users\Micael\Desktop\Auto Production"
python -m pytest tools/exporter/tests/test_solidworks_helpers.py -v -k "TestGetWeldment" 2>&1 | tail -10
```
Expected: FAIL — `ImportError: cannot import name 'get_weldment_cut_list'`

- [ ] **Step 6: Add `get_weldment_cut_list` after `get_perfis_parts`**

```python
def get_weldment_cut_list(sw, part_path: str) -> tuple:
    """
    Open part_path and read its weldment cut list by iterating CutListFolder features.

    Returns (items, warnings):
      items:    list[CutListItem] — one entry per non-suppressed CutListFolder
      warnings: list[str]        — human-readable warnings (QUANTITY missing, etc.)

    Properties are read via IFeature.GetCustomInfoValue("", prop_name) where the
    first argument is the config name (empty string = default/active config).
    LENGTH is a plain mm string — parsed as float, no unit conversion needed.
    QUANTITY primary key is "QUANTITY"; fallback "QTY"; default 1 if neither found.

    SW 2024 quirks applied:
      - IPartDoc.FirstFeature() for iteration (not IModelDoc2.FirstFeature)
      - callable-guard on IsSuppressed (property-as-attribute in SW 2024 stubs)
      - normalised path for CloseDoc
    """
    part_path = os.path.normpath(os.path.abspath(part_path))
    doc = None
    warnings = []

    try:
        doc = _open_doc(sw, part_path, doc_type=1, silent=True)
        part = _wrap(doc, "IPartDoc")

        feat_raw = part.FirstFeature()
        feat = _wrap(feat_raw, "IFeature") if feat_raw is not None else None

        items = []
        while feat is not None:
            type_name_ref = feat.GetTypeName2
            type_name = type_name_ref() if callable(type_name_ref) else str(type_name_ref)

            if type_name == "CutListFolder":
                is_sup_ref = feat.IsSuppressed
                suppressed = is_sup_ref() if callable(is_sup_ref) else bool(is_sup_ref)

                if not suppressed:
                    desc = (feat.GetCustomInfoValue("", "DESCRIPTION") or "").strip()
                    length_str = (feat.GetCustomInfoValue("", "LENGTH") or "").strip()
                    qty_str = (feat.GetCustomInfoValue("", "QUANTITY") or "").strip()
                    if not qty_str:
                        qty_str = (feat.GetCustomInfoValue("", "QTY") or "").strip()

                    # Parse length — skip folder if missing/invalid
                    try:
                        length_mm = float(length_str)
                    except (ValueError, TypeError):
                        next_raw = feat.GetNextFeature()
                        feat = _wrap(next_raw, "IFeature") if next_raw is not None else None
                        continue

                    # Parse qty — warn if neither key found
                    if qty_str:
                        try:
                            qty = int(float(qty_str))
                        except (ValueError, TypeError):
                            qty = 1
                    else:
                        name_ref = feat.Name
                        feat_name = name_ref() if callable(name_ref) else str(name_ref)
                        warnings.append(
                            f"QUANTITY/QTY não encontrado em '{feat_name}' — assumido qty=1"
                        )
                        qty = 1

                    if desc:
                        items.append(CutListItem(desc, length_mm, qty))

            next_raw = feat.GetNextFeature()
            feat = _wrap(next_raw, "IFeature") if next_raw is not None else None

        return items, warnings

    finally:
        if doc is not None:
            try:
                sw.CloseDoc(part_path)
            except Exception:
                pass
```

- [ ] **Step 7: Commit solidworks.py additions**

```bash
git add "tools/exporter/solidworks.py"
git commit -m "feat: add weldment cut list helpers to solidworks.py"
```

---

### Task 2: Tests for new solidworks.py helpers

**Files:**
- Modify: `tools/exporter/tests/test_solidworks_helpers.py`

- [ ] **Step 1: Write failing tests for `_normalize_corte` and `is_perfil_aluminio`**

Append to `test_solidworks_helpers.py`:

```python
# ---------------------------------------------------------------------------
# _normalize_corte
# ---------------------------------------------------------------------------

class TestNormalizeCorte(unittest.TestCase):

    def test_strips_accent_from_i(self):
        from solidworks import _normalize_corte
        self.assertEqual(_normalize_corte("PERFIL ALUMÍNIO"), "perfil aluminio")

    def test_already_unaccented_unchanged(self):
        from solidworks import _normalize_corte
        self.assertEqual(_normalize_corte("PERFIL ALUMINIO"), "perfil aluminio")

    def test_lowercases(self):
        from solidworks import _normalize_corte
        self.assertEqual(_normalize_corte("ABC"), "abc")


# ---------------------------------------------------------------------------
# is_perfil_aluminio
# ---------------------------------------------------------------------------

def _make_perfil_comp(corte_fabrico_value):
    """Create a mock component whose GetModelDoc2 returns a mock model
    with GetCustomPropertyManager("").Get returning corte_fabrico_value."""
    mgr = MagicMock()
    mgr.Get.return_value = corte_fabrico_value
    mgr.Get4.side_effect = Exception("not used")
    model = MagicMock()
    model.Extension.CustomPropertyManager.return_value = mgr
    comp = MagicMock()
    comp.GetModelDoc2.return_value = model
    return comp


class TestIsPerfisAluminio(unittest.TestCase):

    def test_uppercase_no_accent_matches(self):
        from solidworks import is_perfil_aluminio
        comp = _make_perfil_comp("PERFIL ALUMINIO")
        self.assertTrue(is_perfil_aluminio(comp))

    def test_uppercase_with_accent_matches(self):
        from solidworks import is_perfil_aluminio
        comp = _make_perfil_comp("PERFIL ALUMÍNIO")
        self.assertTrue(is_perfil_aluminio(comp))

    def test_mixed_case_matches(self):
        from solidworks import is_perfil_aluminio
        comp = _make_perfil_comp("Perfil Alumínio")
        self.assertTrue(is_perfil_aluminio(comp))

    def test_laser_does_not_match(self):
        from solidworks import is_perfil_aluminio
        comp = _make_perfil_comp("LASER")
        self.assertFalse(is_perfil_aluminio(comp))

    def test_empty_does_not_match(self):
        from solidworks import is_perfil_aluminio
        comp = _make_perfil_comp("")
        self.assertFalse(is_perfil_aluminio(comp))

    def test_none_model_does_not_match(self):
        from solidworks import is_perfil_aluminio
        comp = MagicMock()
        comp.GetModelDoc2.return_value = None
        self.assertFalse(is_perfil_aluminio(comp))
```

Note: `TestGetWeldmentCutList` was written in Task 1 Step 5 (TDD — before implementation). Only `TestNormalizeCorte` and `TestIsPerfisAluminio` are added here.

- [ ] **Step 2: Run all new helper tests**

```bash
cd "c:\Users\Micael\Desktop\Auto Production"
python -m pytest tools/exporter/tests/test_solidworks_helpers.py -v -k "TestNormalize or TestIsPerfis or TestGetWeldment" 2>&1 | tail -20
```
Expected: all pass after Task 1 implementation is complete.

- [ ] **Step 3: Run full test suite to verify nothing broken**

```bash
python -m pytest tools/exporter/tests/ -v 2>&1 | tail -20
```
Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add "tools/exporter/tests/test_solidworks_helpers.py"
git commit -m "test: add tests for is_perfil_aluminio and _normalize_corte"
```

---

### Task 3: Create perfis_writer.py

**Files:**
- Create: `tools/exporter/perfis_writer.py`

- [ ] **Step 1: Write failing test first**

Create `tools/exporter/tests/test_perfis_writer.py`:

```python
"""
Unit tests for perfis_writer.py.
Uses the real Perfis-de-Alumínio_template.xlsx — SolidWorks not needed.
"""
import sys
import os
import tempfile
import unittest
import openpyxl

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))),
    "Templates"
)
TEMPLATE_PATH = os.path.join(TEMPLATES_DIR, "Perfis-de-Alumínio_template.xlsx")


class TestGeneratePerfis(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        self.tmp.close()
        self.out_path = self.tmp.name

    def tearDown(self):
        try:
            os.unlink(self.out_path)
        except OSError:
            pass

    def _load(self):
        return openpyxl.load_workbook(self.out_path)

    def test_creates_output_file(self):
        from perfis_writer import generate_perfis
        generate_perfis([], self.out_path)
        self.assertTrue(os.path.isfile(self.out_path))

    def test_item_no_header_written(self):
        from perfis_writer import generate_perfis
        generate_perfis([], self.out_path)
        wb = self._load()
        ws = wb.active
        self.assertEqual(ws["A2"].value, "ITEM NO.")

    def test_writes_data_row_columns(self):
        from perfis_writer import generate_perfis
        rows = [{"qty": 2, "description": "Aluminium profile 40x40", "length_mm": 350.0}]
        generate_perfis(rows, self.out_path)
        wb = self._load()
        ws = wb.active
        self.assertEqual(ws["A3"].value, 1)          # ITEM NO
        self.assertEqual(ws["B3"].value, 2)          # qty
        self.assertEqual(ws["C3"].value, "Aluminium profile 40x40")
        self.assertEqual(ws["D3"].value, 350.0)      # length_mm

    def test_item_no_sequential(self):
        from perfis_writer import generate_perfis
        rows = [
            {"qty": 1, "description": "Profile A", "length_mm": 100.0},
            {"qty": 3, "description": "Profile B", "length_mm": 200.0},
        ]
        generate_perfis(rows, self.out_path)
        wb = self._load()
        ws = wb.active
        self.assertEqual(ws["A3"].value, 1)
        self.assertEqual(ws["A4"].value, 2)

    def test_length_rounded_to_2dp(self):
        from perfis_writer import generate_perfis
        rows = [{"qty": 1, "description": "Profile A", "length_mm": 566.4285}]
        generate_perfis(rows, self.out_path)
        wb = self._load()
        ws = wb.active
        self.assertAlmostEqual(ws["D3"].value, 566.43, places=2)

    def test_table_ref_updated_when_overflow(self):
        """More than 22 data rows → table ref must grow beyond D24."""
        from perfis_writer import generate_perfis
        rows = [{"qty": 1, "description": f"Profile {i}", "length_mm": float(i * 10)}
                for i in range(1, 30)]  # 29 rows — beyond template's 22
        generate_perfis(rows, self.out_path)
        wb = self._load()
        ws = wb.active
        for tbl in ws.tables.values():
            # last data row = 3 + 29 - 1 = 31
            self.assertIn("31", tbl.ref)

    def test_empty_rows_table_ref_collapses_to_header(self):
        """Empty input → table ref shrinks to just the header row."""
        from perfis_writer import generate_perfis
        generate_perfis([], self.out_path)
        wb = self._load()
        ws = wb.active
        for tbl in ws.tables.values():
            # last_row = HEADER_ROW = 2 when no data
            self.assertTrue(tbl.ref.endswith("2"), msg=f"ref={tbl.ref}")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail (perfis_writer doesn't exist yet)**

```bash
cd "c:\Users\Micael\Desktop\Auto Production"
python -m pytest tools/exporter/tests/test_perfis_writer.py -v 2>&1 | tail -10
```
Expected: FAIL — `ModuleNotFoundError: No module named 'perfis_writer'`

- [ ] **Step 3: Create `tools/exporter/perfis_writer.py`**

```python
"""
perfis_writer.py — Perfis de Alumínio Excel generation.

Copies the Perfis-de-Alumínio_template.xlsx, writes weldment cut list rows.
No SolidWorks COM dependency — pure openpyxl + stdlib.

Template structure:
  Sheet "Folha1", Excel Table "Tabela1" ref B2:D24
  Row 2 (header): B2=QTY., C2=DESCRIPTION, D2=LENGTH
  Column A is not in the template — ITEM NO. header and values written at output time.
  Data rows start at row 3.
"""
import os
import re
import shutil

import openpyxl

# perfis_writer.py → tools/exporter/ → tools/ → project root
TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "Templates"
)

TEMPLATE_NAME  = "Perfis-de-Alumínio_template.xlsx"
HEADER_ROW     = 2
DATA_START_ROW = 3


def generate_perfis(rows: list, output_path: str) -> None:
    """
    Write Perfis de Alumínio Excel from the template.

    Args:
        rows:        List of dicts {"qty": int, "description": str, "length_mm": float}.
                     Must be pre-sorted (caller is responsible for sort order).
        output_path: Destination .xlsx path (overwritten if it exists).
    """
    template_path = os.path.join(TEMPLATES_DIR, TEMPLATE_NAME)
    shutil.copy2(template_path, output_path)

    wb = openpyxl.load_workbook(output_path)
    ws = wb.active

    # Write ITEM NO. header in column A (not pre-defined in template)
    ws.cell(row=HEADER_ROW, column=1).value = "ITEM NO."

    # Write data rows
    for i, row in enumerate(rows):
        r = DATA_START_ROW + i
        ws.cell(row=r, column=1).value = i + 1                          # ITEM NO
        ws.cell(row=r, column=2).value = row["qty"]                     # QTY
        ws.cell(row=r, column=3).value = row["description"]             # DESCRIPTION
        ws.cell(row=r, column=4).value = round(row["length_mm"], 2)     # LENGTH

    # Update Excel Table ref to cover actual data range (same pattern as bom_writer.py)
    last_row = HEADER_ROW if not rows else DATA_START_ROW + len(rows) - 1
    for tbl in ws.tables.values():
        m = re.match(r'([A-Z]+)\d+:([A-Z]+)\d+', tbl.ref)
        if m:
            tbl.ref = f"{m.group(1)}{HEADER_ROW}:{m.group(2)}{last_row}"

    wb.save(output_path)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tools/exporter/tests/test_perfis_writer.py -v 2>&1 | tail -15
```
Expected: all 7 tests PASS.

- [ ] **Step 5: Run full test suite**

```bash
python -m pytest tools/exporter/tests/ -v 2>&1 | tail -10
```
Expected: all tests pass, no regressions.

- [ ] **Step 6: Commit**

```bash
git add "tools/exporter/perfis_writer.py" "tools/exporter/tests/test_perfis_writer.py"
git commit -m "feat: add perfis_writer.py + tests for Perfis de Alumínio Excel generation"
```

---

## Chunk 2: UI Layer

### Task 4: Create listas_module.py

**Files:**
- Create: `tools/exporter/modules/listas_module.py`

- [ ] **Step 1: Create `tools/exporter/modules/listas_module.py`**

```python
"""
listas_module.py — Listas (Excel reports) panel.

Replaces bom_module.py as the sidebar "Listas" entry.
Shows checkboxes for 6 report types; runs selected phases in one
SolidWorks session. Each phase is try/except resilient.

NOTE: bom_module.py is kept unchanged — AllModule still uses it directly.
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
            self, text="Browse…",
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
            messagebox.showerror("Erro", "Seleciona um ficheiro .sldasm válido.")
            return
        if not out or not os.path.isdir(out):
            messagebox.showerror("Erro", "Seleciona uma pasta de output válida.")
            return

        selected = {k: v.get() for k, v in self._check_vars.items()}
        if not any(selected.values()):
            messagebox.showwarning("Aviso", "Seleciona pelo menos uma lista.")
            return

        self.btn_generate.config(state="disabled")
        self.progress.start()
        self._set_status("A iniciar…")
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
            ui(lambda: self._log("═" * 68))
            ui(lambda: self._log("Gerar Listas Selecionadas"))
            ui(lambda: self._log("A conectar ao SolidWorks…"))

            from solidworks import connect_to_solidworks, open_assembly
            sw = connect_to_solidworks()

            ui(lambda: self._log(f"A abrir assembly: {os.path.basename(asm_path)}"))
            asm_doc, asm_opened_by_us = open_assembly(sw, asm_path)

            phase_n = 0
            phase_total = sum(1 for v in selected.values() if v)

            # ── Phase: Laser ──────────────────────────────────────────
            if selected.get("laser"):
                phase_n += 1
                ui(lambda n=phase_n, t=phase_total: self._log("─" * 68))
                ui(lambda n=phase_n, t=phase_total: self._log(f"[{n}/{t}] Laser"))
                ui(lambda n=phase_n, t=phase_total: self._set_status(f"[{n}/{t}] Laser…"))
                errs = self._run_excel_list(sw, asm_doc, out_dir, "laser", ui)
                all_errors.extend(errs)

            # ── Phase: Router ─────────────────────────────────────────
            if selected.get("router"):
                phase_n += 1
                ui(lambda n=phase_n, t=phase_total: self._log("─" * 68))
                ui(lambda n=phase_n, t=phase_total: self._log(f"[{n}/{t}] Router"))
                ui(lambda n=phase_n, t=phase_total: self._set_status(f"[{n}/{t}] Router…"))
                errs = self._run_excel_list(sw, asm_doc, out_dir, "router", ui)
                all_errors.extend(errs)

            # ── Phase: CNC ────────────────────────────────────────────
            if selected.get("cnc"):
                phase_n += 1
                ui(lambda n=phase_n, t=phase_total: self._log("─" * 68))
                ui(lambda n=phase_n, t=phase_total: self._log(f"[{n}/{t}] CNC"))
                ui(lambda n=phase_n, t=phase_total: self._set_status(f"[{n}/{t}] CNC…"))
                errs = self._run_excel_list(sw, asm_doc, out_dir, "cnc", ui)
                all_errors.extend(errs)

            # ── Phase: Torno ──────────────────────────────────────────
            if selected.get("torno"):
                phase_n += 1
                ui(lambda n=phase_n, t=phase_total: self._log("─" * 68))
                ui(lambda n=phase_n, t=phase_total: self._log(f"[{n}/{t}] Torno"))
                ui(lambda n=phase_n, t=phase_total: self._set_status(f"[{n}/{t}] Torno…"))
                errs = self._run_excel_list(sw, asm_doc, out_dir, "torno", ui)
                all_errors.extend(errs)

            # ── Phase: BOM ────────────────────────────────────────────
            if selected.get("bom"):
                phase_n += 1
                ui(lambda n=phase_n, t=phase_total: self._log("─" * 68))
                ui(lambda n=phase_n, t=phase_total: self._log(f"[{n}/{t}] Lista de Material"))
                ui(lambda n=phase_n, t=phase_total: self._set_status(f"[{n}/{t}] BOM…"))
                errs = self._run_bom(sw, asm_doc, asm_path, out_dir, ui)
                all_errors.extend(errs)

            # ── Phase: Perfis de Alumínio ─────────────────────────────
            if selected.get("perfis"):
                phase_n += 1
                ui(lambda n=phase_n, t=phase_total: self._log("─" * 68))
                ui(lambda n=phase_n, t=phase_total: self._log(f"[{n}/{t}] Perfis de Alumínio"))
                ui(lambda n=phase_n, t=phase_total: self._set_status(f"[{n}/{t}] Perfis…"))
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
                    self._set_status("Concluído.")
                else:
                    self._set_status(f"Concluído com {n_err} erro(s) — ver log.")
                self._log("─" * 68)
                self._log(f"Gerar Listas concluído. Erros: {n_err}")

            ui(_finish)

    # ------------------------------------------------------------------
    # Laser / Router / CNC / Torno — Excel only
    # ------------------------------------------------------------------

    def _run_excel_list(self, sw, asm_doc, out_dir: str, process_key: str, ui) -> list:
        """Generate the Excel report for a given process keyword (laser/router/cnc/torno)."""
        from solidworks import (
            get_all_parts, deduplicate_by_path,
            is_laser_part, get_corte_fabrico, get_part_data,
        )
        from excel_writer import generate_excel, PROCESS_CONFIG

        errors = []
        try:
            templates_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(
                    os.path.dirname(os.path.abspath(__file__))))),
                "Templates",
            )

            all_parts    = get_all_parts(asm_doc)
            unique_parts = deduplicate_by_path(all_parts)

            if process_key == "laser":
                parts = [p for p in unique_parts if is_laser_part(p)]
            else:
                parts = [p for p in unique_parts
                         if process_key in get_corte_fabrico(p)]

            template_name, output_name, col_order, data_start_row = PROCESS_CONFIG[process_key]
            ui(lambda n=len(parts), k=process_key: self._log(f"  Peças {k}: {n}"))

            if not parts:
                ui(lambda k=process_key: self._log(f"  Nenhuma peça {k} encontrada."))
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
            ui(lambda m=str(exc), k=process_key: self._log(f"  ERROR {k}.xlsx — {m}"))

        return errors

    # ------------------------------------------------------------------
    # BOM
    # ------------------------------------------------------------------

    def _run_bom(self, sw, asm_doc, asm_path: str, out_dir: str, ui) -> list:
        from solidworks import (
            get_bom_components, deduplicate_bom_by_path,
            count_bom_instances, get_custom_property_evaluated,
        )
        from bom_writer import classify_commercial, generate_bom, ALL_KNOWN_BRANDS

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
                    ui(lambda p=bc.path: self._log(f"  AVISO GetModelDoc2() None: {p}"))
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
                val = (row.get("Corte_Fabrico") or "").strip().lower()
                if not any(b in val for b in ALL_KNOWN_BRANDS):
                    msg = (f"Fabricante desconhecido: '{row['Corte_Fabrico']}'"
                           f" → Material Mecânico")
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
                f"Produção: {len(rows_producao)} | "
                f"Mecânico: {len(rows_mecanico)} | "
                f"Elétrico: {len(rows_eletrico)} | "
                f"Pneumático: {len(rows_pneumatico)} | "
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
            ui(lambda n=len(perfis_parts): self._log(f"  Peças Perfil Alumínio: {n}"))

            if not perfis_parts:
                ui(lambda: self._log("  Nenhuma peça Perfil Alumínio encontrada."))
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

            output_path = os.path.join(out_dir, "Perfis de Alumínio.xlsx")
            generate_perfis(rows, output_path)
            ui(lambda: self._log(
                f"  OK    Perfis de Alumínio.xlsx  [{len(rows)} linha(s)]"))

        except Exception as exc:
            errors.append(f"Perfis: {exc}")
            ui(lambda m=str(exc): self._log(f"  ERRO Perfis: {m}"))

        return errors

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------

    def _set_status(self, text: str):
        self.status_var.set(text)
```

- [ ] **Step 2: Commit**

```bash
git add "tools/exporter/modules/listas_module.py"
git commit -m "feat: add ListasModule with checkboxes for 6 Excel report types"
```

---

### Task 5: Update main.py

**Files:**
- Modify: `tools/exporter/main.py`

- [ ] **Step 1: Swap the BomModule import and MODULES entry**

In `main.py`, change line 21:
```python
# Before:
from modules.bom_module import BomModule
# After:
from modules.listas_module import ListasModule
```

Change line 54 in the MODULES list:
```python
# Before:
    ("Lista de Material", "bom",    BomModule),
# After:
    ("Listas",            "listas", ListasModule),
```

- [ ] **Step 2: Launch the app visually and verify the sidebar shows "Listas" and the checkboxes render correctly**

```bash
python "tools/exporter/main.py"
```
Expected: sidebar shows "Listas" entry; clicking it shows 6 checkboxes all pre-checked.

- [ ] **Step 3: Commit**

```bash
git add "tools/exporter/main.py"
git commit -m "feat: rename 'Lista de Material' nav entry to 'Listas', wire ListasModule"
```

---

### Task 6: Update all_module.py

**Files:**
- Modify: `tools/exporter/modules/all_module.py`

- [ ] **Step 1: Update title label and phase counters**

In `all_module.py`, change:
```python
# Before (line ~45):
    tk.Label(
        self, text="Gerar Tudo \u2014 DXF + STEP + Lista de Material",
# After:
    tk.Label(
        self, text="Gerar Tudo \u2014 DXF + STEP + BOM + Perfis de Alum\u00ednio",
```

Change phase log lines in `_worker`:
```python
# Before:
            ui(lambda: self._log("[1/3] DXF Export \u2014 Laser"))
            ui(lambda: self._set_status("[1/3] DXF Export\u2026"))
# After:
            ui(lambda: self._log("[1/4] DXF Export \u2014 Laser"))
            ui(lambda: self._set_status("[1/4] DXF Export\u2026"))

# Before:
            ui(lambda: self._log("[2/3] STEP Export \u2014 Router / CNC / Torno"))
            ui(lambda: self._set_status("[2/3] STEP Export\u2026"))
# After:
            ui(lambda: self._log("[2/4] STEP Export \u2014 Router / CNC / Torno"))
            ui(lambda: self._set_status("[2/4] STEP Export\u2026"))

# Before:
            ui(lambda: self._log("[3/3] Lista de Material"))
            ui(lambda: self._set_status("[3/3] Lista de Material\u2026"))
# After:
            ui(lambda: self._log("[3/4] Lista de Material"))
            ui(lambda: self._set_status("[3/4] Lista de Material\u2026"))
```

- [ ] **Step 2: Add phase 4 call after BOM in `_worker`**

After the BOM phase block (after `bom_errors = self._run_bom(...)`):
```python
            # --- Phase 4: Perfis de Alumínio ---
            ui(lambda: self._log("\u2500" * 68))
            ui(lambda: self._log("[4/4] Perfis de Alum\u00ednio"))
            ui(lambda: self._set_status("[4/4] Perfis de Alum\u00ednio\u2026"))
            perfis_errors = self._run_perfis(sw, asm_doc, out_dir, ui)
            all_errors.extend(perfis_errors)
```

- [ ] **Step 3: Add `_run_perfis` method to `AllModule`**

Add after `_run_bom`:
```python
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
```

- [ ] **Step 4: Run full test suite to confirm no regressions**

```bash
python -m pytest tools/exporter/tests/ -v 2>&1 | tail -15
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add "tools/exporter/modules/all_module.py"
git commit -m "feat: add Perfis de Alumínio phase [4/4] to Gerar Tudo"
```

---

## ⚠️ Pre-flight note for implementation

**Verify QUANTITY property name before running against a real assembly:**

The `get_weldment_cut_list` function tries `"QUANTITY"` then `"QTY"`. Before the first real test run, open a known weldment `.sldprt` in SolidWorks, open its cut list properties (right-click cut list folder → Properties), and confirm the exact property name shown. If it differs (e.g. `"Quantidade"`), update the call in `get_weldment_cut_list` accordingly and document it in `docs/project-guide.md`.
