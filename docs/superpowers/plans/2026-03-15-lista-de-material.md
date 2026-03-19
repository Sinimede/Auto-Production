# Lista de Material (BOM) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate `Lista de materiais.xlsx` from a SolidWorks assembly using a macro template, listing all production parts and commercial items across four categorised sheets.

**Architecture:** Three new files added to `tools/exporter/` — `bom_writer.py` (pure Excel logic, no COM), `modules/bom_module.py` (tkinter panel + background worker), plus additions to `solidworks.py` (BOM traversal helpers). `main.py` registers the new panel. The BOM traversal is selective: group 800 components are recorded as single purchasable items and their children are not recursed into.

**Tech Stack:** Python 3.x, `openpyxl` (Excel read/write), `win32com` (SolidWorks COM, early binding), `tkinter` (GUI), `threading` (background worker)

---

## Chunk 1: File Map + Task 1 (solidworks.py BOM helpers)

### File Map

| File | Action | Responsibility |
|---|---|---|
| `tools/exporter/solidworks.py` | Modify | Add `BomComponent` namedtuple, `get_bom_components`, `_bom_traverse`, `count_bom_instances`, `deduplicate_bom_by_path` |
| `tools/exporter/bom_writer.py` | Create | Brand sets, `classify_commercial`, column definitions, `generate_bom` |
| `tools/exporter/modules/bom_module.py` | Create | tkinter panel + background worker |
| `tools/exporter/main.py` | Modify | Import and register `BomModule` |
| `tools/exporter/tests/test_solidworks_helpers.py` | Modify | Add BOM helper tests |
| `tools/exporter/tests/test_bom_writer.py` | Create | Tests for `bom_writer.py` |

---

### Task 1: solidworks.py — BOM traversal helpers

**Files:**
- Modify: `tools/exporter/solidworks.py` (after `HoleInfo` namedtuple, ~line 22)
- Modify: `tools/exporter/tests/test_solidworks_helpers.py` (append new test classes at the end)

- [ ] **Step 1.1: Write failing tests — append to `test_solidworks_helpers.py`**

Append the following to the end of `tools/exporter/tests/test_solidworks_helpers.py` (before the `if __name__ == "__main__":` block):

```python
# ---------------------------------------------------------------------------
# BomComponent helper: _make_bom_comp
# ---------------------------------------------------------------------------

def _make_bom_comp(path, comp_type="producao"):
    """Build a minimal BomComponent for testing."""
    from solidworks import BomComponent
    comp = MagicMock()
    return BomComponent(comp, path, comp_type)


# ---------------------------------------------------------------------------
# count_bom_instances
# ---------------------------------------------------------------------------

class TestCountBomInstances(unittest.TestCase):

    def test_counts_three_matching(self):
        from solidworks import count_bom_instances
        path = "C:\\parts\\18026.100.001.SLDPRT"
        bom_flat = [_make_bom_comp(path)] * 3 + [_make_bom_comp("C:\\parts\\18026.200.001.SLDPRT")]
        self.assertEqual(count_bom_instances(bom_flat, path), 3)

    def test_case_insensitive(self):
        from solidworks import count_bom_instances
        bom_flat = [_make_bom_comp("C:\\Parts\\Part_A.SLDPRT")]
        self.assertEqual(count_bom_instances(bom_flat, "c:\\parts\\part_a.sldprt"), 1)

    def test_no_match_returns_zero(self):
        from solidworks import count_bom_instances
        bom_flat = [_make_bom_comp("C:\\parts\\18026.200.001.SLDPRT")]
        self.assertEqual(count_bom_instances(bom_flat, "C:\\parts\\18026.100.001.SLDPRT"), 0)

    def test_empty_list(self):
        from solidworks import count_bom_instances
        self.assertEqual(count_bom_instances([], "C:\\parts\\x.SLDPRT"), 0)


# ---------------------------------------------------------------------------
# deduplicate_bom_by_path
# ---------------------------------------------------------------------------

class TestDeduplicateBomByPath(unittest.TestCase):

    def test_five_with_two_dupes_yields_three(self):
        from solidworks import deduplicate_bom_by_path
        path_a = "C:\\parts\\18026.100.001.SLDPRT"
        path_b = "C:\\parts\\18026.100.002.SLDPRT"
        path_c = "C:\\parts\\18026.200.001.SLDPRT"
        bom_flat = [
            _make_bom_comp(path_a),
            _make_bom_comp(path_b),
            _make_bom_comp(path_a),  # dupe
            _make_bom_comp(path_c),
            _make_bom_comp(path_b),  # dupe
        ]
        result = deduplicate_bom_by_path(bom_flat)
        self.assertEqual(len(result), 3)

    def test_preserves_first_occurrence(self):
        from solidworks import deduplicate_bom_by_path
        path = "C:\\parts\\18026.100.001.SLDPRT"
        first  = _make_bom_comp(path, comp_type="producao")
        second = _make_bom_comp(path, comp_type="comercial")
        result = deduplicate_bom_by_path([first, second])
        self.assertEqual(result[0].comp_type, "producao")

    def test_case_insensitive_dedup(self):
        from solidworks import deduplicate_bom_by_path
        result = deduplicate_bom_by_path([
            _make_bom_comp("C:\\Parts\\A.SLDPRT"),
            _make_bom_comp("c:\\parts\\a.sldprt"),
        ])
        self.assertEqual(len(result), 1)

    def test_empty_list(self):
        from solidworks import deduplicate_bom_by_path
        self.assertEqual(deduplicate_bom_by_path([]), [])


# ---------------------------------------------------------------------------
# SW instance suffix strip (pure Python, no mocking)
# ---------------------------------------------------------------------------

class TestSuffixStrip(unittest.TestCase):

    def test_strips_dash_n(self):
        import re
        self.assertEqual(re.sub(r'-\d+$', '', '18026.100.001-3'), '18026.100.001')

    def test_strips_dash_1(self):
        import re
        self.assertEqual(re.sub(r'-\d+$', '', '18026.800.001-1'), '18026.800.001')

    def test_no_suffix_unchanged(self):
        import re
        self.assertEqual(re.sub(r'-\d+$', '', '18026.100.001'), '18026.100.001')

    def test_ignores_non_trailing_number(self):
        import re
        # Hypothetical vendor name — trailing non-digit segment not stripped
        self.assertEqual(re.sub(r'-\d+$', '', 'PART-A'), 'PART-A')


# ---------------------------------------------------------------------------
# _bom_traverse (mocked COM)
# ---------------------------------------------------------------------------

def _make_traversal_comp(path, doc_type, suppressed=False, children=None):
    """
    Build a mock IComponent2 for _bom_traverse tests.
    doc_type: 1=swDocPART, 2=swDocASSEMBLY
    """
    model = MagicMock()
    model.GetType = doc_type   # attribute, not callable
    comp = MagicMock()
    comp.IsSuppressed.return_value = suppressed
    comp.GetModelDoc2.return_value = model
    comp.GetPathName.return_value = path
    comp.GetChildren.return_value = children or []
    return comp


class TestBomTraverse(unittest.TestCase):

    def test_group_100_part_appended_as_producao(self):
        from solidworks import _bom_traverse
        comp = _make_traversal_comp("C:\\parts\\18026.100.001.SLDPRT", doc_type=1)
        bom_flat, warnings = [], []
        _bom_traverse(comp, bom_flat, warnings)
        self.assertEqual(len(bom_flat), 1)
        self.assertEqual(bom_flat[0].comp_type, "producao")
        self.assertEqual(warnings, [])

    def test_group_800_appended_as_comercial_children_not_traversed(self):
        from solidworks import _bom_traverse
        child = _make_traversal_comp("C:\\parts\\18026.800.099.SLDPRT", doc_type=1)
        comp = _make_traversal_comp(
            "C:\\parts\\18026.800.001.SLDASM", doc_type=2, children=[child])
        bom_flat, warnings = [], []
        _bom_traverse(comp, bom_flat, warnings)
        # Only the group-800 top-level component is recorded; child is NOT traversed
        self.assertEqual(len(bom_flat), 1)
        self.assertEqual(bom_flat[0].comp_type, "comercial")

    def test_suppressed_component_skipped(self):
        from solidworks import _bom_traverse
        comp = _make_traversal_comp(
            "C:\\parts\\18026.100.002.SLDPRT", doc_type=1, suppressed=True)
        bom_flat, warnings = [], []
        _bom_traverse(comp, bom_flat, warnings)
        self.assertEqual(bom_flat, [])
        self.assertEqual(warnings, [])

    def test_unrecognized_basename_adds_warning(self):
        from solidworks import _bom_traverse
        comp = _make_traversal_comp("C:\\parts\\VENDOR_PART.SLDPRT", doc_type=1)
        bom_flat, warnings = [], []
        _bom_traverse(comp, bom_flat, warnings)
        self.assertEqual(bom_flat, [])
        self.assertEqual(len(warnings), 1)
        self.assertIn("VENDOR_PART", warnings[0])

    def test_assembly_group_100_recurses_into_children(self):
        from solidworks import _bom_traverse
        child = _make_traversal_comp("C:\\parts\\18026.100.002.SLDPRT", doc_type=1)
        parent = _make_traversal_comp(
            "C:\\parts\\18026.100.001.SLDASM", doc_type=2, children=[child])
        bom_flat, warnings = [], []
        _bom_traverse(parent, bom_flat, warnings)
        # Parent assembly (group 100) is not recorded; child part is
        self.assertEqual(len(bom_flat), 1)
        self.assertEqual(bom_flat[0].comp_type, "producao")

    def test_suffix_stripped_before_group_parse(self):
        from solidworks import _bom_traverse
        # Path has SW instance suffix -3 — must be stripped before group regex
        comp = _make_traversal_comp("C:\\parts\\18026.100.001-3.SLDPRT", doc_type=1)
        bom_flat, warnings = [], []
        _bom_traverse(comp, bom_flat, warnings)
        self.assertEqual(len(bom_flat), 1)
        self.assertEqual(bom_flat[0].comp_type, "producao")
        self.assertEqual(warnings, [])
```

- [ ] **Step 1.2: Run to verify tests FAIL**

```
cd "c:\Users\Micael\Desktop\Auto Production"
pytest tools/exporter/tests/test_solidworks_helpers.py -v -k "CountBom or DeduplicateBom or SuffixStrip or BomTraverse" 2>&1 | tail -15
```

Expected: `ImportError` or `AttributeError` — `BomComponent`, `count_bom_instances`, etc. not yet defined.

- [ ] **Step 1.3: Add `BomComponent` namedtuple to `solidworks.py`**

In `tools/exporter/solidworks.py`, after line 21 (`HoleInfo = namedtuple('HoleInfo', ['feature', 'original_diameter_m'])`), add:

```python
BomComponent = namedtuple('BomComponent', ['component', 'path', 'comp_type'])
# component: IComponent2
# path:      os.path.normpath(component.GetPathName())
# comp_type: "producao" | "comercial"
```

- [ ] **Step 1.4: Add BOM functions to the bottom of `solidworks.py`**

Append the following before any `if __name__` block (or at the very end of the file):

```python
# ---------------------------------------------------------------------------
# BOM traversal
# ---------------------------------------------------------------------------

def get_bom_components(assembly_doc):
    """
    Traverse the top-level assembly and return a flat list of BomComponent.
    assembly_doc: IModelDoc2 (same type returned by open_assembly).
    Returns (bom_flat: list[BomComponent], warnings: list[str]).
    """
    bom_flat = []
    warnings = []
    try:
        config = assembly_doc.ConfigurationManager.ActiveConfiguration
        root = config.GetRootComponent3(True)
        children = root.GetChildren()
    except Exception as e:
        warnings.append(f"Erro ao obter componentes: {e}")
        return bom_flat, warnings
    if children:
        for child in children:
            _bom_traverse(child, bom_flat, warnings)
    return bom_flat, warnings


def _bom_traverse(comp, bom_flat, warnings):
    """Recursive BOM traversal — appends BomComponent entries to bom_flat."""
    path = "(desconhecido)"
    try:
        try:
            suppressed = comp.IsSuppressed()
        except Exception:
            suppressed = True   # on exception, treat as suppressed — skip
        if suppressed:
            return

        model = comp.GetModelDoc2()
        if model is None:
            return

        path = os.path.normpath(comp.GetPathName())
        basename = os.path.splitext(os.path.basename(path))[0]
        basename = re.sub(r'-\d+$', '', basename)   # strip SW instance suffix

        m = re.match(r'^\d+\.(\d+)\.\d+$', basename)
        if not m:
            warnings.append(f"Componente ignorado (nome não reconhecido): {basename}")
            return

        group = int(m.group(1))
        doc_type = model.GetType
        if callable(doc_type):
            doc_type = doc_type()

        if group == 800:
            # Commercial item — record as single purchasable unit, do not recurse
            bom_flat.append(BomComponent(comp, path, "comercial"))
            return

        if doc_type == 1:   # swDocPART
            bom_flat.append(BomComponent(comp, path, "producao"))
        elif doc_type == 2:  # swDocASSEMBLY
            children = comp.GetChildren()
            if children:
                for child in children:
                    _bom_traverse(child, bom_flat, warnings)
        # doc_type 3 (drawing) and others are silently ignored

    except Exception as e:
        warnings.append(f"Erro ao processar componente '{path}': {e}")


def count_bom_instances(bom_flat, part_path):
    """Count entries in bom_flat matching part_path (case-insensitive normpath)."""
    target = os.path.normpath(part_path).lower()
    return sum(1 for bc in bom_flat
               if os.path.normpath(bc.path).lower() == target)


def deduplicate_bom_by_path(bom_components):
    """Return list with duplicate paths removed; first occurrence preserved."""
    seen = set()
    unique = []
    for bc in bom_components:
        key = bc.path.lower()
        if key not in seen:
            seen.add(key)
            unique.append(bc)
    return unique
```

- [ ] **Step 1.5: Run tests to verify PASS**

```
cd "c:\Users\Micael\Desktop\Auto Production"
pytest tools/exporter/tests/test_solidworks_helpers.py -v -k "CountBom or DeduplicateBom or SuffixStrip or BomTraverse" 2>&1 | tail -20
```

Expected: all new tests PASS.

Then run the full file to confirm no regressions:

```
cd "c:\Users\Micael\Desktop\Auto Production"
pytest tools/exporter/tests/test_solidworks_helpers.py -v 2>&1 | tail -10
```

Expected: all tests PASS.

- [ ] **Step 1.6: Commit**

```bash
cd "c:\Users\Micael\Desktop\Auto Production"
git add tools/exporter/solidworks.py tools/exporter/tests/test_solidworks_helpers.py
git commit -m "feat: add BOM traversal helpers to solidworks.py"
```

---

## Chunk 2: Task 2 — bom_writer.py (TDD)

### Task 2: Create `bom_writer.py`

**Files:**
- Create: `tools/exporter/bom_writer.py`
- Create: `tools/exporter/tests/test_bom_writer.py`

- [ ] **Step 2.1: Write failing tests — create `test_bom_writer.py`**

Create `tools/exporter/tests/test_bom_writer.py`:

```python
"""
Unit tests for bom_writer.py.
Uses the real template file from Templates/ — SolidWorks does not need to be running.
"""
import sys
import os
import shutil
import tempfile
import unittest
import openpyxl

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))),
    "Templates"
)
BOM_TEMPLATE = os.path.join(TEMPLATES_DIR, "Lista-de-Material_template.xlsm")


# ---------------------------------------------------------------------------
# classify_commercial
# ---------------------------------------------------------------------------

class TestClassifyCommercial(unittest.TestCase):

    def test_festo_uppercase_is_pneumatico(self):
        from bom_writer import classify_commercial
        self.assertEqual(classify_commercial("FESTO"), "pneumatico")

    def test_festo_lowercase_is_pneumatico(self):
        from bom_writer import classify_commercial
        self.assertEqual(classify_commercial("festo"), "pneumatico")

    def test_festo_mixed_case_is_pneumatico(self):
        from bom_writer import classify_commercial
        self.assertEqual(classify_commercial("Festo"), "pneumatico")

    def test_smc_is_pneumatico(self):
        from bom_writer import classify_commercial
        self.assertEqual(classify_commercial("SMC"), "pneumatico")

    def test_siemens_is_eletrico(self):
        from bom_writer import classify_commercial
        self.assertEqual(classify_commercial("Siemens"), "eletrico")

    def test_balluf_is_eletrico(self):
        from bom_writer import classify_commercial
        self.assertEqual(classify_commercial("Balluf"), "eletrico")

    def test_skf_is_mecanico(self):
        from bom_writer import classify_commercial
        self.assertEqual(classify_commercial("SKF"), "mecanico")

    def test_bosch_rexroth_is_mecanico(self):
        from bom_writer import classify_commercial
        self.assertEqual(classify_commercial("Bosch Rexroth"), "mecanico")

    def test_empty_string_is_mecanico(self):
        from bom_writer import classify_commercial
        self.assertEqual(classify_commercial(""), "mecanico")

    def test_completely_unknown_brand_is_mecanico(self):
        from bom_writer import classify_commercial
        self.assertEqual(classify_commercial("XYZ Unknown Corp"), "mecanico")


# ---------------------------------------------------------------------------
# ALL_KNOWN_BRANDS — unknown brand detection
# ---------------------------------------------------------------------------

class TestAllKnownBrands(unittest.TestCase):

    def test_xyz_not_in_all_known_brands(self):
        from bom_writer import ALL_KNOWN_BRANDS
        val = "xyz"
        self.assertFalse(any(b in val for b in ALL_KNOWN_BRANDS))

    def test_festo_in_all_known_brands(self):
        from bom_writer import ALL_KNOWN_BRANDS
        val = "festo"
        self.assertTrue(any(b in val for b in ALL_KNOWN_BRANDS))

    def test_skf_in_all_known_brands(self):
        from bom_writer import ALL_KNOWN_BRANDS
        val = "skf"
        self.assertTrue(any(b in val for b in ALL_KNOWN_BRANDS))


# ---------------------------------------------------------------------------
# generate_bom — uses real template
# ---------------------------------------------------------------------------

class TestGenerateBom(unittest.TestCase):

    def setUp(self):
        if not os.path.isfile(BOM_TEMPLATE):
            self.skipTest(f"Template not found: {BOM_TEMPLATE}")
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _output(self, name="Lista de materiais.xlsx"):
        return os.path.join(self.tmp, name)

    def test_output_file_is_openable_xlsx(self):
        from bom_writer import generate_bom
        out = self._output()
        generate_bom([], [], [], [], out)
        # openpyxl must open without keep_vba (VBA stripped)
        wb = openpyxl.load_workbook(out)
        wb.close()

    def test_producao_columns_written_correctly(self):
        from bom_writer import generate_bom
        out = self._output()
        rows_prod = [{
            "qty": 3,
            "part_number": "18026.100.001",
            "Description": "Chapa Base",
            "Corte_Fabrico": "LASER",
            "Simetria": "S",
            "Material": "S235JR",
            "TratSuperficial": "Pintar RAL 9002",
            "A_Partir_de": "Chapa 3mm",
        }]
        generate_bom(rows_prod, [], [], [], out)
        wb = openpyxl.load_workbook(out)
        ws = wb["Produção"]
        # Data starts at row 3
        self.assertEqual(ws.cell(3, 1).value, 3)                  # qty
        self.assertEqual(ws.cell(3, 2).value, "18026.100.001")    # part_number
        self.assertEqual(ws.cell(3, 3).value, "")                 # Rev (always empty)
        self.assertEqual(ws.cell(3, 4).value, "Chapa Base")       # Description
        self.assertEqual(ws.cell(3, 5).value, "LASER")            # Corte_Fabrico
        self.assertEqual(ws.cell(3, 6).value, "S")                # Simetria
        self.assertEqual(ws.cell(3, 7).value, "S235JR")           # Material
        self.assertEqual(ws.cell(3, 8).value, "Pintar RAL 9002")  # TratSuperficial
        self.assertEqual(ws.cell(3, 9).value, "Chapa 3mm")        # A_Partir_de
        wb.close()

    def test_comercial_mecanico_columns_written_correctly(self):
        from bom_writer import generate_bom
        out = self._output()
        rows_mec = [{
            "qty": 2,
            "part_number": "18026.800.001",
            "Description": "REF-123",
            "Corte_Fabrico": "SKF",
        }]
        generate_bom([], rows_mec, [], [], out)
        wb = openpyxl.load_workbook(out)
        ws = wb["Material Mecânico"]
        self.assertEqual(ws.cell(3, 1).value, 2)                # qty
        self.assertEqual(ws.cell(3, 2).value, "18026.800.001")  # part_number
        self.assertEqual(ws.cell(3, 3).value, "")               # Coluna1 (always empty)
        self.assertEqual(ws.cell(3, 4).value, "REF-123")        # Description/Referência
        self.assertEqual(ws.cell(3, 5).value, "SKF")            # Corte_Fabrico/Marca
        self.assertEqual(ws.cell(3, 6).value, "")               # Descrição (always empty)
        wb.close()

    def test_none_value_written_as_empty_string(self):
        from bom_writer import generate_bom
        out = self._output()
        rows_prod = [{
            "qty": 1,
            "part_number": "18026.100.002",
            "Description": None,
            "Corte_Fabrico": "CNC",
            "Simetria": None,
            "Material": "S235JR",
            "TratSuperficial": None,
            "A_Partir_de": None,
        }]
        generate_bom(rows_prod, [], [], [], out)
        wb = openpyxl.load_workbook(out)
        ws = wb["Produção"]
        self.assertEqual(ws.cell(3, 4).value, "")  # Description → ""
        self.assertEqual(ws.cell(3, 6).value, "")  # Simetria → ""
        self.assertEqual(ws.cell(3, 8).value, "")  # TratSuperficial → ""
        self.assertEqual(ws.cell(3, 9).value, "")  # A_Partir_de → ""
        wb.close()

    def test_empty_producao_removes_template_blanks(self):
        from bom_writer import generate_bom
        out = self._output()
        generate_bom([], [], [], [], out)
        wb = openpyxl.load_workbook(out)
        ws = wb["Produção"]
        # No data rows → all rows from row 3 deleted → max_row = 2
        self.assertEqual(ws.max_row, 2)
        wb.close()

    def test_table_ref_header_only_when_no_data(self):
        from bom_writer import generate_bom
        out = self._output()
        generate_bom([], [], [], [], out)
        wb = openpyxl.load_workbook(out)
        ws = wb["Produção"]
        for tbl in ws.tables.values():
            # header_row=2, no data → last_row=2 → ref ends with "2"
            self.assertTrue(
                tbl.ref.endswith("2"),
                f"Expected ref ending in '2', got {tbl.ref}"
            )
        wb.close()

    def test_table_ref_updated_with_two_data_rows(self):
        from bom_writer import generate_bom
        out = self._output()
        row_template = {
            "qty": 1, "part_number": "18026.100.001", "Description": "A",
            "Corte_Fabrico": "LASER", "Simetria": "", "Material": "S235JR",
            "TratSuperficial": "", "A_Partir_de": "",
        }
        rows_prod = [dict(row_template), dict(row_template, part_number="18026.100.002")]
        generate_bom(rows_prod, [], [], [], out)
        wb = openpyxl.load_workbook(out)
        ws = wb["Produção"]
        # 2 data rows → last_row = data_start_row(3) + 2 - 1 = 4
        for tbl in ws.tables.values():
            self.assertTrue(
                tbl.ref.endswith("4"),
                f"Expected ref ending in '4', got {tbl.ref}"
            )
        wb.close()

    def test_missing_key_in_row_dict_written_as_empty(self):
        from bom_writer import generate_bom
        out = self._output()
        # Minimal dict — optional keys missing
        rows_prod = [{"qty": 1, "part_number": "18026.100.001"}]
        generate_bom(rows_prod, [], [], [], out)
        wb = openpyxl.load_workbook(out)
        ws = wb["Produção"]
        # Description (col D = 4) should be "" when key absent
        self.assertEqual(ws.cell(3, 4).value, "")
        wb.close()

    def test_template_missing_raises_file_not_found(self):
        from bom_writer import generate_bom
        import unittest.mock as mock
        out = self._output()
        with mock.patch("bom_writer.TEMPLATES_DIR", "/nonexistent/path"):
            with self.assertRaises(FileNotFoundError):
                generate_bom([], [], [], [], out)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2.2: Run to verify tests FAIL**

```
cd "c:\Users\Micael\Desktop\Auto Production"
pytest tools/exporter/tests/test_bom_writer.py -v 2>&1 | tail -10
```

Expected: `ModuleNotFoundError: No module named 'bom_writer'`

- [ ] **Step 2.3: Create `tools/exporter/bom_writer.py`**

```python
"""
bom_writer.py — BOM (Lista de Material) Excel generation.

Copies the macro template (.xlsm), writes a plain workbook (.xlsx).
VBA is intentionally stripped via keep_vba=False — no macros needed in output.
No SolidWorks COM dependency — pure openpyxl + stdlib.
"""
import os
import re
import shutil

import openpyxl

# ---------------------------------------------------------------------------
# Template location
# ---------------------------------------------------------------------------

# bom_writer.py → tools/exporter/ → tools/ → project root
TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "Templates"
)

# ---------------------------------------------------------------------------
# Brand classification
# ---------------------------------------------------------------------------

PNEUMATICO_BRANDS = frozenset({"festo", "smc"})
ELETRICO_BRANDS = frozenset({
    "balluf", "ifm", "datalogic", "sick", "siemens", "pepperl+fuchs",
    "rittal", "schneider-eletric", "nord", "banner", "datasensing", "efectoled"
})
MECANICO_BRANDS = frozenset({
    "norelem", "misumi", "rolisa", "item", "igus", "bosch", "bosch rexroth",
    "lanema", "boteco", "skf", "gayner"
})
ALL_KNOWN_BRANDS = PNEUMATICO_BRANDS | ELETRICO_BRANDS | MECANICO_BRANDS


def classify_commercial(corte_fabrico: str) -> str:
    """
    Return "pneumatico", "eletrico", or "mecanico".
    Unknown brands fall back to "mecanico" — caller detects unknowns via ALL_KNOWN_BRANDS.
    Check priority: pneumatico → eletrico → mecanico (unconditional else).
    """
    val = corte_fabrico.strip().lower()
    if any(b in val for b in PNEUMATICO_BRANDS):
        return "pneumatico"
    if any(b in val for b in ELETRICO_BRANDS):
        return "eletrico"
    return "mecanico"

# ---------------------------------------------------------------------------
# Column definitions
# ---------------------------------------------------------------------------

# None entries → write "" for that column
PRODUCAO_COLUMNS = [
    "qty",             # col 1 (A) — Quant.
    "part_number",     # col 2 (B) — Número Interno
    None,              # col 3 (C) — Rev. (always empty — dept. convention)
    "Description",     # col 4 (D) — Descrição
    "Corte_Fabrico",   # col 5 (E) — Corte/Fabrico
    "Simetria",        # col 6 (F) — Simetria
    "Material",        # col 7 (G) — Material
    "TratSuperficial", # col 8 (H) — Tratamento Superficial
    "A_Partir_de",     # col 9 (I) — A partir de
]

COMERCIAL_COLUMNS = [
    "qty",           # col 1 (A) — Quant.
    "part_number",   # col 2 (B) — Número Interno
    None,            # col 3 (C) — Coluna1 (Excel auto-name, no business meaning, always empty)
    "Description",   # col 4 (D) — Referência/nº Proposta
    "Corte_Fabrico", # col 5 (E) — Marca/Fabricante
    None,            # col 6 (F) — Descrição (always empty — dept. convention)
]

# ---------------------------------------------------------------------------
# Excel generation
# ---------------------------------------------------------------------------

def generate_bom(rows_producao, rows_mecanico, rows_eletrico, rows_pneumatico,
                 output_path):
    """
    Write Lista de materiais.xlsx from the macro template.
    All row list args are list[dict]. Empty lists are allowed.
    Raises FileNotFoundError if template is missing.
    """
    template_path = os.path.join(TEMPLATES_DIR, "Lista-de-Material_template.xlsm")
    shutil.copy2(template_path, output_path)   # raises FileNotFoundError if missing
    wb = openpyxl.load_workbook(output_path, keep_vba=False)

    sheet_config = [
        ("Produção",            rows_producao,   PRODUCAO_COLUMNS),
        ("Material Mecânico",   rows_mecanico,   COMERCIAL_COLUMNS),
        ("Material Elétrico",   rows_eletrico,   COMERCIAL_COLUMNS),
        ("Material Pneumático", rows_pneumatico, COMERCIAL_COLUMNS),
    ]

    for sheet_name, rows, col_keys in sheet_config:
        ws = wb[sheet_name]
        data_start_row = 3
        header_row = 2   # invariant for all 4 sheets

        for row_offset, row_dict in enumerate(rows):
            row_idx = data_start_row + row_offset
            for col_offset, key in enumerate(col_keys):
                value = row_dict.get(key, "") if key else ""
                ws.cell(row=row_idx, column=1 + col_offset).value = value or ""

        # Remove trailing blank template rows
        first_blank = data_start_row + len(rows)
        if first_blank <= ws.max_row:
            ws.delete_rows(first_blank, ws.max_row - first_blank + 1)

        # Update Excel Table refs to match actual data range.
        # Column letters are preserved from the template (e.g. "A2:I1098" → "A2:I7").
        # Column bounds are NOT hardcoded — extracted via regex from existing ref.
        last_row = header_row if not rows else data_start_row + len(rows) - 1
        for tbl in ws.tables.values():
            m = re.match(r'([A-Z]+)\d+:([A-Z]+)\d+', tbl.ref)
            if m:
                tbl.ref = f"{m.group(1)}{header_row}:{m.group(2)}{last_row}"
        # If a sheet has no Excel Table the loop is a no-op.

    wb.save(output_path)
```

- [ ] **Step 2.4: Run tests to verify PASS**

```
cd "c:\Users\Micael\Desktop\Auto Production"
pytest tools/exporter/tests/test_bom_writer.py -v 2>&1 | tail -20
```

Expected: all tests PASS.

- [ ] **Step 2.5: Commit**

```bash
cd "c:\Users\Micael\Desktop\Auto Production"
git add tools/exporter/bom_writer.py tools/exporter/tests/test_bom_writer.py
git commit -m "feat: add bom_writer.py with brand classification and Excel generation"
```

---

## Chunk 3: Task 3 (bom_module.py) + Task 4 (main.py registration)

### Task 3: Create `modules/bom_module.py`

**Files:**
- Create: `tools/exporter/modules/bom_module.py`
- No unit tests — tkinter + threading (verified by smoke-check import and manual run)

- [ ] **Step 3.1: Create `tools/exporter/modules/bom_module.py`**

```python
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
            get_part_data, get_custom_property_evaluated,
        )
        from bom_writer import (
            classify_commercial, generate_bom, ALL_KNOWN_BRANDS,
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
                model_doc = bc.component.GetModelDoc2()
                if model_doc is None:
                    ui(lambda p=bc.path: self._log(f"  AVISO GetModelDoc2() None: {p}"))
                    continue
                row = get_part_data(bc.component, all_raw)
                row["qty"] = count_bom_instances(bom_flat, bc.path)
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
                val = row["Corte_Fabrico"].strip().lower()
                if not any(b in val for b in ALL_KNOWN_BRANDS):
                    msg = (f"Fabricante desconhecido: '{row['Corte_Fabrico']}'"
                           f" \u2192 Material Mec\u00e2nico")
                    ui(lambda m=msg: self._log(f"  AVISO {m}"))
                    warn_count += 1
                cat = classify_commercial(row["Corte_Fabrico"])
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
```

- [ ] **Step 3.2: Smoke-check import (no GUI, no COM)**

```
cd "c:\Users\Micael\Desktop\Auto Production"
python -c "import sys; sys.path.insert(0, 'tools/exporter'); from modules.bom_module import BomModule; print('import OK')"
```

Expected output: `import OK`

- [ ] **Step 3.3: Commit**

```bash
cd "c:\Users\Micael\Desktop\Auto Production"
git add tools/exporter/modules/bom_module.py
git commit -m "feat: add bom_module.py GUI panel for Lista de Material"
```

---

### Task 4: Register `BomModule` in `main.py`

**Files:**
- Modify: `tools/exporter/main.py`

- [ ] **Step 4.1: Add import to `main.py`**

In `tools/exporter/main.py`, after the existing import on line 19 (`from modules.step_module import StepModule`), add:

```python
from modules.bom_module import BomModule
```

- [ ] **Step 4.2: Update `MODULES` list in `main.py`**

Replace the existing `MODULES` list (lines 48-51):

```python
MODULES = [
    ("DXF Export",  "dxf",  DxfModule),
    ("STEP Export", "step", StepModule),
]
```

With:

```python
MODULES = [
    ("DXF Export",        "dxf",  DxfModule),
    ("STEP Export",       "step", StepModule),
    ("Lista de Material", "bom",  BomModule),
]
```

- [ ] **Step 4.3: Smoke-check `main.py` import**

```
cd "c:\Users\Micael\Desktop\Auto Production"
python -c "import sys; sys.path.insert(0, 'tools/exporter'); import main; print('import OK')"
```

Expected output: `import OK` (no GUI launched — no `mainloop()` called)

- [ ] **Step 4.4: Run full test suite — confirm no regressions**

```
cd "c:\Users\Micael\Desktop\Auto Production"
pytest tools/exporter/tests/ -v 2>&1 | tail -20
```

Expected: all tests PASS.

- [ ] **Step 4.5: Commit**

```bash
cd "c:\Users\Micael\Desktop\Auto Production"
git add tools/exporter/main.py
git commit -m "feat: register BomModule in main.py — Lista de Material tab live"
```
