# Excel Generation Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-process Excel file generation (Laser/Router/CNC/Torno) to both export panels, using template files and SolidWorks custom properties.

**Architecture:** New `excel_writer.py` handles template copying and data writing. New helper functions in `solidworks.py` gather QTY (instance count), evaluated custom properties, and bounding box thickness. Both GUI modules get a checkbox ("Gerar Excel") and a secondary button ("Gerar Excel apenas").

**Tech Stack:** Python 3, openpyxl, win32com (early binding), tkinter

**Spec:** `docs/superpowers/specs/2026-03-15-excel-generation-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `tools/exporter/requirements.txt` | Modify | Add openpyxl |
| `tools/exporter/solidworks.py` | Modify | Add `count_instances`, `get_custom_property_evaluated`, `get_bounding_box_thickness`, `get_part_data` |
| `tools/exporter/excel_writer.py` | **Create** | Template copy + data row writing, column order constants |
| `tools/exporter/tests/__init__.py` | **Create** | Empty — marks tests as package |
| `tools/exporter/tests/test_solidworks_helpers.py` | **Create** | Unit tests for new solidworks.py functions (COM mocked) |
| `tools/exporter/tests/test_excel_writer.py` | **Create** | Unit tests for generate_excel (uses real template files) |
| `tools/exporter/modules/dxf_module.py` | Modify | Checkbox + "Gerar Excel apenas" button + Excel worker |
| `tools/exporter/modules/step_module.py` | Modify | Same UI changes + multi-process Excel worker |

---

## Chunk 1: Dependencies + solidworks.py helpers

### Task 1: Add openpyxl to requirements and install

**Files:**
- Modify: `tools/exporter/requirements.txt`

- [ ] **Step 1: Add openpyxl to requirements.txt**

Open `tools/exporter/requirements.txt` and add `openpyxl>=3.1.0`:

```
pywin32>=306
ezdxf>=1.1.0
openpyxl>=3.1.0
```

- [ ] **Step 2: Install the dependency**

```bash
pip install openpyxl
```

Expected: `Successfully installed openpyxl-...`

- [ ] **Step 3: Verify import works**

```bash
python -c "import openpyxl; print(openpyxl.__version__)"
```

Expected: prints a version number (3.x.x)

- [ ] **Step 4: Commit**

```bash
git add tools/exporter/requirements.txt
git commit -m "chore: add openpyxl dependency for Excel generation"
```

---

### Task 2: `count_instances` — unit test then implement

**Files:**
- Create: `tools/exporter/tests/__init__.py`
- Create: `tools/exporter/tests/test_solidworks_helpers.py`
- Modify: `tools/exporter/solidworks.py`

- [ ] **Step 1: Create tests package**

Create `tools/exporter/tests/__init__.py` as an empty file.

- [ ] **Step 2: Write the failing tests for `count_instances`**

Create `tools/exporter/tests/test_solidworks_helpers.py`:

```python
"""
Unit tests for new solidworks.py helper functions.
COM objects are mocked — SolidWorks does not need to be running.
"""
import sys
import os
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ---------------------------------------------------------------------------
# count_instances
# ---------------------------------------------------------------------------

def _make_comp(path, suppressed=False):
    comp = MagicMock()
    comp.GetPathName.return_value = path
    comp.IsSuppressed.return_value = suppressed
    return comp


class TestCountInstances(unittest.TestCase):

    def test_counts_matching_non_suppressed(self):
        from solidworks import count_instances
        comps = [
            _make_comp("C:\\parts\\part_a.sldprt"),
            _make_comp("C:\\parts\\part_a.sldprt"),
            _make_comp("C:\\parts\\part_b.sldprt"),
        ]
        self.assertEqual(count_instances(comps, "C:\\parts\\part_a.sldprt"), 2)

    def test_skips_suppressed(self):
        from solidworks import count_instances
        comps = [
            _make_comp("C:\\parts\\part_a.sldprt"),
            _make_comp("C:\\parts\\part_a.sldprt", suppressed=True),
        ]
        self.assertEqual(count_instances(comps, "C:\\parts\\part_a.sldprt"), 1)

    def test_case_insensitive_path_match(self):
        from solidworks import count_instances
        comps = [_make_comp("C:\\Parts\\Part_A.SLDPRT")]
        self.assertEqual(count_instances(comps, "c:\\parts\\part_a.sldprt"), 1)

    def test_normpath_handles_mixed_separators(self):
        from solidworks import count_instances
        # COM may return backslashes; caller may pass forward slashes
        comps = [_make_comp("C:\\parts\\part_a.sldprt")]
        self.assertEqual(count_instances(comps, "C:/parts/part_a.sldprt"), 1)

    def test_returns_zero_no_match(self):
        from solidworks import count_instances
        comps = [_make_comp("C:\\parts\\part_b.sldprt")]
        self.assertEqual(count_instances(comps, "C:\\parts\\part_a.sldprt"), 0)

    def test_empty_components(self):
        from solidworks import count_instances
        self.assertEqual(count_instances([], "C:\\parts\\part_a.sldprt"), 0)

    def test_getpathname_exception_skipped(self):
        from solidworks import count_instances
        bad = MagicMock()
        bad.IsSuppressed.return_value = False
        bad.GetPathName.side_effect = Exception("COM error")
        good = _make_comp("C:\\parts\\part_a.sldprt")
        self.assertEqual(count_instances([bad, good], "C:\\parts\\part_a.sldprt"), 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests to confirm they fail**

```bash
cd "c:\Users\Micael\Desktop\Auto Production"
python -m pytest tools/exporter/tests/test_solidworks_helpers.py::TestCountInstances -v
```

Expected: `ImportError` or `AttributeError` — `count_instances` does not exist yet.

- [ ] **Step 4: Implement `count_instances` in `solidworks.py`**

Append at the end of `tools/exporter/solidworks.py`, after the `export_part_to_step` function:

```python
# ---------------------------------------------------------------------------
# Excel data gathering
# ---------------------------------------------------------------------------

def count_instances(all_components: list, part_path: str) -> int:
    """
    Count non-suppressed instances of part_path in all_components (before dedup).
    Comparison is case-insensitive. Errors on individual components are skipped.
    """
    target = os.path.normpath(part_path).lower()
    count = 0
    for comp in all_components:
        try:
            if comp.IsSuppressed():
                continue
            if os.path.normpath(comp.GetPathName()).lower() == target:
                count += 1
        except Exception:
            continue
    return count
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
python -m pytest tools/exporter/tests/test_solidworks_helpers.py::TestCountInstances -v
```

Expected: 6 PASSED

- [ ] **Step 6: Commit**

```bash
git add tools/exporter/solidworks.py tools/exporter/tests/
git commit -m "feat: add count_instances helper to solidworks.py"
```

---

### Task 3: `get_custom_property_evaluated` — test then implement

**Files:**
- Modify: `tools/exporter/tests/test_solidworks_helpers.py`
- Modify: `tools/exporter/solidworks.py`

- [ ] **Step 1: Add failing tests to `test_solidworks_helpers.py`**

Append to `tools/exporter/tests/test_solidworks_helpers.py` (before `if __name__ == "__main__"`):

```python
# ---------------------------------------------------------------------------
# get_custom_property_evaluated
# ---------------------------------------------------------------------------

def _make_model_doc_with_props(props: dict):
    """props: {prop_name: resolved_value_str}"""
    mgr = MagicMock()
    def _get4(name, flag):
        if name in props:
            return (0, f"raw_{name}", props[name], True)
        return (0, None, None, False)
    mgr.Get4.side_effect = _get4
    ext = MagicMock()
    ext.CustomPropertyManager.return_value = mgr
    doc = MagicMock()
    doc.Extension = ext
    return doc


class TestGetCustomPropertyEvaluated(unittest.TestCase):

    def test_returns_resolved_value(self):
        from solidworks import get_custom_property_evaluated
        doc = _make_model_doc_with_props({"Material": "Cast Alloy Steel"})
        self.assertEqual(get_custom_property_evaluated(doc, "Material"), "Cast Alloy Steel")

    def test_returns_empty_string_for_missing_property(self):
        from solidworks import get_custom_property_evaluated
        doc = _make_model_doc_with_props({})
        self.assertEqual(get_custom_property_evaluated(doc, "Material"), "")

    def test_returns_empty_string_on_exception(self):
        from solidworks import get_custom_property_evaluated
        doc = MagicMock()
        doc.Extension.CustomPropertyManager.side_effect = Exception("COM error")
        self.assertEqual(get_custom_property_evaluated(doc, "Material"), "")

    def test_resolved_val_none_returns_empty(self):
        from solidworks import get_custom_property_evaluated
        mgr = MagicMock()
        mgr.Get4.return_value = (0, "raw", None, False)
        ext = MagicMock()
        ext.CustomPropertyManager.return_value = mgr
        doc = MagicMock()
        doc.Extension = ext
        self.assertEqual(get_custom_property_evaluated(doc, "Simetria"), "")

    def test_strips_whitespace(self):
        from solidworks import get_custom_property_evaluated
        doc = _make_model_doc_with_props({"TratSuperficial": "  Pintar RAL 9002  "})
        self.assertEqual(get_custom_property_evaluated(doc, "TratSuperficial"),
                         "Pintar RAL 9002")
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest tools/exporter/tests/test_solidworks_helpers.py::TestGetCustomPropertyEvaluated -v
```

Expected: `AttributeError` — function not defined yet.

- [ ] **Step 3: Implement `get_custom_property_evaluated` in `solidworks.py`**

Append after `count_instances`:

```python
def get_custom_property_evaluated(model_doc, prop_name: str) -> str:
    """
    Return the Evaluated Value (resolvedVal, index 2) of a custom property.
    Get4 returns (retval, val, resolvedVal, wasResolved).
    Index 2 is the configuration-evaluated result (e.g. "Cast Alloy Steel"
    instead of "SW-Material@part.SLDPRT").
    Returns "" on any error or missing property.

    Note: existing helpers (get_corte_fabrico, is_laser_part) use index 1 for
    filtering — that is intentional. This function uses index 2 for display output.
    """
    try:
        mgr = model_doc.Extension.CustomPropertyManager("")
        result = mgr.Get4(prop_name, False)
        if isinstance(result, tuple) and len(result) > 2:
            val = result[2]
        else:
            val = result
        return str(val).strip() if val is not None else ""
    except Exception:
        return ""
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python -m pytest tools/exporter/tests/test_solidworks_helpers.py::TestGetCustomPropertyEvaluated -v
```

Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add tools/exporter/solidworks.py tools/exporter/tests/test_solidworks_helpers.py
git commit -m "feat: add get_custom_property_evaluated helper to solidworks.py"
```

---

### Task 4: `get_bounding_box_thickness` — test then implement

**Files:**
- Modify: `tools/exporter/tests/test_solidworks_helpers.py`
- Modify: `tools/exporter/solidworks.py`

- [ ] **Step 1: Add failing tests**

Append to `test_solidworks_helpers.py`:

```python
# ---------------------------------------------------------------------------
# get_bounding_box_thickness
# ---------------------------------------------------------------------------

class TestGetBoundingBoxThickness(unittest.TestCase):

    def _run(self, box_metres):
        from solidworks import get_bounding_box_thickness
        model_doc = MagicMock()
        part_mock = MagicMock()
        part_mock.GetPartBox.return_value = box_metres
        with patch("solidworks._wrap", return_value=part_mock):
            return get_bounding_box_thickness(model_doc)

    def test_returns_smallest_dimension_mm(self):
        # 200 x 100 x 5 mm box
        result = self._run((0.0, 0.0, 0.0, 0.200, 0.100, 0.005))
        self.assertEqual(result, 5.0)

    def test_rounds_to_2_decimal_places(self):
        # 3.33333... mm thin
        result = self._run((0.0, 0.0, 0.0, 0.200, 0.100, 0.00333333))
        self.assertEqual(result, 3.33)

    def test_square_box_returns_side(self):
        # 50 x 50 x 50 mm cube → min = 50
        result = self._run((0.0, 0.0, 0.0, 0.05, 0.05, 0.05))
        self.assertEqual(result, 50.0)

    def test_returns_none_on_exception(self):
        from solidworks import get_bounding_box_thickness
        model_doc = MagicMock()
        with patch("solidworks._wrap", side_effect=Exception("COM error")):
            result = get_bounding_box_thickness(model_doc)
        self.assertIsNone(result)

    def test_wrap_called_with_ipartdoc(self):
        from solidworks import get_bounding_box_thickness
        model_doc = MagicMock()
        part_mock = MagicMock()
        part_mock.GetPartBox.return_value = (0.0, 0.0, 0.0, 0.1, 0.1, 0.005)
        with patch("solidworks._wrap", return_value=part_mock) as mock_wrap:
            get_bounding_box_thickness(model_doc)
        mock_wrap.assert_called_once_with(model_doc, "IPartDoc")
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tools/exporter/tests/test_solidworks_helpers.py::TestGetBoundingBoxThickness -v
```

Expected: `AttributeError` — function not defined yet.

- [ ] **Step 3: Implement `get_bounding_box_thickness` in `solidworks.py`**

Append after `get_custom_property_evaluated`:

```python
def get_bounding_box_thickness(model_doc) -> "float | None":
    """
    Return the smallest dimension of the part's bounding box in mm (2 d.p.).
    _wrap to IPartDoc is required — IModelDoc2 does not expose GetPartBox.
    GetPartBox(True) returns (xmin, ymin, zmin, xmax, ymax, zmax) in metres.
    Returns None on any error.
    """
    try:
        part = _wrap(model_doc, "IPartDoc")
        box = part.GetPartBox(True)
        dx = box[3] - box[0]
        dy = box[4] - box[1]
        dz = box[5] - box[2]
        return round(min(dx, dy, dz) * 1000, 2)
    except Exception:
        return None
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python -m pytest tools/exporter/tests/test_solidworks_helpers.py::TestGetBoundingBoxThickness -v
```

Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add tools/exporter/solidworks.py tools/exporter/tests/test_solidworks_helpers.py
git commit -m "feat: add get_bounding_box_thickness helper to solidworks.py"
```

---

### Task 5: `get_part_data` — test then implement

**Files:**
- Modify: `tools/exporter/tests/test_solidworks_helpers.py`
- Modify: `tools/exporter/solidworks.py`

- [ ] **Step 1: Add failing tests**

Append to `test_solidworks_helpers.py`:

```python
# ---------------------------------------------------------------------------
# get_part_data
# ---------------------------------------------------------------------------

class TestGetPartData(unittest.TestCase):

    def _make_component(self, path, props):
        mgr = MagicMock()
        def _get4(name, flag):
            return (0, f"raw_{name}", props.get(name, ""), True)
        mgr.Get4.side_effect = _get4
        ext = MagicMock()
        ext.CustomPropertyManager.return_value = mgr
        doc = MagicMock()
        doc.Extension = ext
        comp = MagicMock()
        comp.GetPathName.return_value = path
        comp.IsSuppressed.return_value = False
        comp.GetModelDoc2.return_value = doc
        return comp

    def test_returns_all_expected_keys(self):
        from solidworks import get_part_data
        comp = self._make_component("C:\\parts\\12624.100.001.SLDPRT", {
            "Description": "Chapa Base", "Corte_Fabrico": "LASER",
            "Simetria": "", "Material": "S235JR", "TratSuperficial": "Pintar"
        })
        with patch("solidworks.get_bounding_box_thickness", return_value=3.0):
            result = get_part_data(comp, [comp])
        expected_keys = {"qty", "part_number", "Description", "Corte_Fabrico",
                         "Simetria", "Material", "TratSuperficial", "espessura"}
        self.assertEqual(set(result.keys()), expected_keys)

    def test_qty_counts_instances(self):
        from solidworks import get_part_data
        path = "C:\\parts\\12624.100.001.SLDPRT"
        comp = self._make_component(path, {})
        comp2 = self._make_component(path, {})
        comp2.GetModelDoc2.return_value = comp.GetModelDoc2()
        with patch("solidworks.get_bounding_box_thickness", return_value=None):
            result = get_part_data(comp, [comp, comp2])
        self.assertEqual(result["qty"], 2)

    def test_part_number_strips_extension(self):
        from solidworks import get_part_data
        comp = self._make_component("C:\\parts\\12624.100.001.SLDPRT", {})
        with patch("solidworks.get_bounding_box_thickness", return_value=None):
            result = get_part_data(comp, [comp])
        self.assertEqual(result["part_number"], "12624.100.001")

    def test_espessura_none_when_bbox_unavailable(self):
        from solidworks import get_part_data
        comp = self._make_component("C:\\parts\\part.SLDPRT", {})
        with patch("solidworks.get_bounding_box_thickness", return_value=None):
            result = get_part_data(comp, [comp])
        self.assertIsNone(result["espessura"])

    def test_properties_populated_from_evaluated_values(self):
        from solidworks import get_part_data
        comp = self._make_component("C:\\parts\\part.SLDPRT", {
            "Material": "Cast Alloy Steel",
            "TratSuperficial": "Anodizar",
        })
        with patch("solidworks.get_bounding_box_thickness", return_value=5.0):
            result = get_part_data(comp, [comp])
        self.assertEqual(result["Material"], "Cast Alloy Steel")
        self.assertEqual(result["TratSuperficial"], "Anodizar")
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tools/exporter/tests/test_solidworks_helpers.py::TestGetPartData -v
```

Expected: `AttributeError` — function not defined yet.

- [ ] **Step 3: Implement `get_part_data` in `solidworks.py`**

Append after `get_bounding_box_thickness`:

```python
def get_part_data(component, all_components: list) -> dict:
    """
    Collect all display-quality data for one part component.
    Call chain: component.GetPathName() → count_instances
                component.GetModelDoc2() → custom properties + bounding box

    Returns a dict with keys: qty, part_number, Description, Corte_Fabrico,
    Simetria, Material, TratSuperficial, espessura.
    These keys match the column_order lists in excel_writer.py.
    """
    part_path = component.GetPathName()
    model_doc = component.GetModelDoc2()

    prop_names = ("Description", "Corte_Fabrico", "Simetria", "Material", "TratSuperficial")
    data = {p: get_custom_property_evaluated(model_doc, p) for p in prop_names}

    data["qty"]         = count_instances(all_components, part_path)
    data["part_number"] = os.path.splitext(os.path.basename(part_path))[0]
    data["espessura"]   = get_bounding_box_thickness(model_doc)

    return data
```

- [ ] **Step 4: Run all solidworks helper tests**

```bash
python -m pytest tools/exporter/tests/test_solidworks_helpers.py -v
```

Expected: all tests PASSED

- [ ] **Step 5: Commit**

```bash
git add tools/exporter/solidworks.py tools/exporter/tests/test_solidworks_helpers.py
git commit -m "feat: add get_part_data helper to solidworks.py"
```

---

## Chunk 2: excel_writer.py

### Task 6: `generate_excel` — test then implement

**Files:**
- Create: `tools/exporter/tests/test_excel_writer.py`
- Create: `tools/exporter/excel_writer.py`

- [ ] **Step 1: Write the failing tests**

Create `tools/exporter/tests/test_excel_writer.py`:

```python
"""
Unit tests for excel_writer.generate_excel.
Uses the real template files from Templates/ — no COM required.
"""
import sys
import os
import shutil
import tempfile
import unittest
import openpyxl

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Templates are at repo root / Templates/
TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))),
    "Templates"
)

LASER_TEMPLATE  = os.path.join(TEMPLATES_DIR, "Laser_template.xlsx")
ROUTER_TEMPLATE = os.path.join(TEMPLATES_DIR, "Router_template.xlsx")
CNC_TEMPLATE    = os.path.join(TEMPLATES_DIR, "CNC_template.xlsx")
TORNO_TEMPLATE  = os.path.join(TEMPLATES_DIR, "Torno_template.xlsx")


class TestGenerateExcel(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    # --- Laser ---

    def test_laser_data_written_to_correct_columns(self):
        from excel_writer import generate_excel, LASER_COLUMNS
        output = os.path.join(self.tmp, "Laser.xlsx")
        rows = [{
            "qty": 2, "part_number": "12624.100.001",
            "Description": "Chapa Base", "Corte_Fabrico": "LASER",
            "Simetria": "", "Material": "S235JR",
            "TratSuperficial": "Pintar RAL 9002", "espessura": 3.0,
        }]
        generate_excel(LASER_TEMPLATE, rows, output, LASER_COLUMNS)

        ws = openpyxl.load_workbook(output)["Folha1"]
        self.assertEqual(ws.cell(row=2, column=2).value, 2)               # qty → B
        self.assertEqual(ws.cell(row=2, column=3).value, "12624.100.001") # part_number → C
        self.assertEqual(ws.cell(row=2, column=4).value, "Chapa Base")    # Description → D
        self.assertEqual(ws.cell(row=2, column=5).value, "LASER")         # Corte_Fabrico → E
        self.assertEqual(ws.cell(row=2, column=6).value, "")              # Simetria → F
        self.assertEqual(ws.cell(row=2, column=7).value, "S235JR")        # Material → G
        self.assertEqual(ws.cell(row=2, column=8).value, "Pintar RAL 9002") # TratSuperficial → H
        self.assertEqual(ws.cell(row=2, column=9).value, 3.0)             # espessura → I

    def test_header_row_preserved(self):
        from excel_writer import generate_excel, LASER_COLUMNS
        output = os.path.join(self.tmp, "Laser.xlsx")
        generate_excel(LASER_TEMPLATE, [], output, LASER_COLUMNS)
        ws = openpyxl.load_workbook(output)["Folha1"]
        # Header must still be present
        self.assertIsNotNone(ws.cell(row=1, column=2).value)

    def test_original_template_not_modified(self):
        from excel_writer import generate_excel, LASER_COLUMNS
        output = os.path.join(self.tmp, "Laser.xlsx")
        wb_before = openpyxl.load_workbook(LASER_TEMPLATE)
        header_before = wb_before["Folha1"].cell(row=1, column=2).value

        rows = [{"qty": 99, "part_number": "X", "Description": "X",
                 "Corte_Fabrico": "X", "Simetria": "X", "Material": "X",
                 "TratSuperficial": "X", "espessura": 1.0}]
        generate_excel(LASER_TEMPLATE, rows, output, LASER_COLUMNS)

        wb_after = openpyxl.load_workbook(LASER_TEMPLATE)
        self.assertEqual(wb_after["Folha1"].cell(row=1, column=2).value, header_before)

    def test_espessura_none_written_as_empty_string(self):
        from excel_writer import generate_excel, LASER_COLUMNS
        output = os.path.join(self.tmp, "Laser.xlsx")
        rows = [{"qty": 1, "part_number": "X", "Description": "", "Corte_Fabrico": "",
                 "Simetria": "", "Material": "", "TratSuperficial": "", "espessura": None}]
        generate_excel(LASER_TEMPLATE, rows, output, LASER_COLUMNS)
        ws = openpyxl.load_workbook(output)["Folha1"]
        self.assertEqual(ws.cell(row=2, column=9).value, "")  # espessura col I

    def test_multiple_rows_written_in_order(self):
        from excel_writer import generate_excel, LASER_COLUMNS
        output = os.path.join(self.tmp, "Laser.xlsx")
        rows = [
            {"qty": 1, "part_number": "P1", "Description": "", "Corte_Fabrico": "",
             "Simetria": "", "Material": "", "TratSuperficial": "", "espessura": None},
            {"qty": 2, "part_number": "P2", "Description": "", "Corte_Fabrico": "",
             "Simetria": "", "Material": "", "TratSuperficial": "", "espessura": None},
        ]
        generate_excel(LASER_TEMPLATE, rows, output, LASER_COLUMNS)
        ws = openpyxl.load_workbook(output)["Folha1"]
        self.assertEqual(ws.cell(row=2, column=3).value, "P1")
        self.assertEqual(ws.cell(row=3, column=3).value, "P2")

    def test_overwrites_existing_file(self):
        from excel_writer import generate_excel, LASER_COLUMNS
        output = os.path.join(self.tmp, "Laser.xlsx")
        rows_v1 = [{"qty": 1, "part_number": "OLD", "Description": "", "Corte_Fabrico": "",
                    "Simetria": "", "Material": "", "TratSuperficial": "", "espessura": None}]
        generate_excel(LASER_TEMPLATE, rows_v1, output, LASER_COLUMNS)
        rows_v2 = [{"qty": 2, "part_number": "NEW", "Description": "", "Corte_Fabrico": "",
                    "Simetria": "", "Material": "", "TratSuperficial": "", "espessura": None}]
        generate_excel(LASER_TEMPLATE, rows_v2, output, LASER_COLUMNS)
        ws = openpyxl.load_workbook(output)["Folha1"]
        self.assertEqual(ws.cell(row=2, column=3).value, "NEW")

    # --- Router ---

    def test_router_columns_espessura_at_col_f(self):
        from excel_writer import generate_excel, ROUTER_COLUMNS
        output = os.path.join(self.tmp, "Router.xlsx")
        rows = [{"qty": 1, "part_number": "P", "Description": "D",
                 "Corte_Fabrico": "Router", "espessura": 15.0,
                 "Material": "Aluminio", "Simetria": "P_mirror"}]
        generate_excel(ROUTER_TEMPLATE, rows, output, ROUTER_COLUMNS)
        ws = openpyxl.load_workbook(output)["Folha1"]
        self.assertEqual(ws.cell(row=2, column=6).value, 15.0)       # espessura → F
        self.assertEqual(ws.cell(row=2, column=8).value, "P_mirror") # Simetria → H

    # --- CNC ---

    def test_cnc_columns_no_espessura(self):
        from excel_writer import generate_excel, CNC_COLUMNS
        output = os.path.join(self.tmp, "CNC.xlsx")
        rows = [{"qty": 2, "part_number": "C1", "Description": "Block",
                 "Corte_Fabrico": "CNC", "Material": "AL5083",
                 "TratSuperficial": "Anodizar", "Simetria": ""}]
        generate_excel(CNC_TEMPLATE, rows, output, CNC_COLUMNS)
        ws = openpyxl.load_workbook(output)["Folha1"]
        self.assertEqual(ws.cell(row=2, column=2).value, 2)       # qty → B
        self.assertEqual(ws.cell(row=2, column=6).value, "AL5083") # Material → F
        self.assertEqual(ws.cell(row=2, column=7).value, "Anodizar") # TratSuperficial → G

    # --- Torno ---

    def test_torno_same_column_order_as_cnc(self):
        from excel_writer import generate_excel, TORNO_COLUMNS, CNC_COLUMNS
        self.assertEqual(TORNO_COLUMNS, CNC_COLUMNS)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest tools/exporter/tests/test_excel_writer.py -v
```

Expected: `ImportError` — `excel_writer` does not exist yet.

- [ ] **Step 3: Create `tools/exporter/excel_writer.py`**

```python
"""
excel_writer.py — Excel generation from templates.

Copies a template xlsx, fills part data rows, and saves to output_path.
Never modifies the original template. Overwrites output_path if it exists.
"""

import os
import shutil
import openpyxl

# Templates directory: repo_root/Templates/
# This file lives at tools/exporter/ — 3 dirname calls reach repo root.
TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "Templates"
)

# Column orders per process.
# Each list maps to openpyxl columns starting at B (index 2).
# Keys must match the dict returned by solidworks.get_part_data().

LASER_COLUMNS = [
    "qty", "part_number", "Description", "Corte_Fabrico",
    "Simetria", "Material", "TratSuperficial", "espessura",
]

ROUTER_COLUMNS = [
    "qty", "part_number", "Description", "Corte_Fabrico",
    "espessura", "Material", "Simetria",
]

CNC_COLUMNS = [
    "qty", "part_number", "Description", "Corte_Fabrico",
    "Material", "TratSuperficial", "Simetria",
]

TORNO_COLUMNS = [
    "qty", "part_number", "Description", "Corte_Fabrico",
    "Material", "TratSuperficial", "Simetria",
]

# Maps process keyword → (template filename, output filename, column order)
PROCESS_CONFIG = {
    "laser":  ("Laser_template.xlsx",  "Laser.xlsx",  LASER_COLUMNS),
    "router": ("Router_template.xlsx", "Router.xlsx", ROUTER_COLUMNS),
    "cnc":    ("CNC_template.xlsx",    "CNC.xlsx",    CNC_COLUMNS),
    "torno":  ("Torno_template.xlsx",  "Torno.xlsx",  TORNO_COLUMNS),
}


def generate_excel(template_path: str, rows: list, output_path: str,
                   column_order: list) -> None:
    """
    Copy template_path to output_path, then write part data rows.

    Layout:
      - Row 1 (header) is preserved from the template.
      - Data starts at row 2, column B (openpyxl index 2).
      - column_order[0] → col B (index 2), column_order[1] → col C (index 3), etc.
      - espessura None → written as empty string "".
      - Overwrites output_path silently if it already exists.

    Raises: OSError on copy failure; openpyxl errors on workbook save.
    """
    shutil.copy2(template_path, output_path)
    wb = openpyxl.load_workbook(output_path)
    ws = wb["Folha1"]

    for row_offset, row_dict in enumerate(rows):
        row_idx = 2 + row_offset
        for col_offset, key in enumerate(column_order):
            value = row_dict.get(key, "")
            if value is None:
                value = ""
            ws.cell(row=row_idx, column=2 + col_offset).value = value

    wb.save(output_path)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python -m pytest tools/exporter/tests/test_excel_writer.py -v
```

Expected: all tests PASSED

- [ ] **Step 5: Run full test suite**

```bash
python -m pytest tools/exporter/tests/ -v
```

Expected: all tests PASSED

- [ ] **Step 6: Commit**

```bash
git add tools/exporter/excel_writer.py tools/exporter/tests/test_excel_writer.py
git commit -m "feat: add excel_writer.py with generate_excel and column order constants"
```

---

## Chunk 3: dxf_module.py UI + Excel worker

### Task 7: Update `dxf_module.py`

**Files:**
- Modify: `tools/exporter/modules/dxf_module.py`

This task is UI-heavy; manual testing against a live SolidWorks assembly is the verification step.

- [ ] **Step 1: Replace `_build_ui` — add checkbox and "Gerar Excel apenas" button**

In `tools/exporter/modules/dxf_module.py`, replace the `_build_ui` method:

```python
def _build_ui(self):
    pad = {"padx": 14, "pady": 6}

    # Row 0: section title
    tk.Label(
        self, text="DXF Export \u2014 Laser",
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

    # Row 3: "Gerar Excel" checkbox
    self.excel_var = tk.BooleanVar(value=False)
    tk.Checkbutton(
        self, text="Gerar Excel",
        variable=self.excel_var,
        bg=BG_CONTENT, fg=TEXT, selectcolor=BG_CONTENT,
        activebackground=BG_CONTENT, activeforeground=TEXT_WHITE,
        font=FONT_LABEL,
    ).grid(row=3, column=0, columnspan=3, sticky="w", padx=14, pady=(4, 2))

    # Row 4: Export button
    self.btn_export = tk.Button(
        self, text="Export DXF",
        command=self._start_export,
        bg=ACCENT, fg=TEXT_WHITE,
        activebackground="#005fa3", activeforeground=TEXT_WHITE,
        font=FONT_BTN, padx=24, pady=8,
        relief="flat", cursor="hand2",
    )
    self.btn_export.grid(row=4, column=0, columnspan=3, pady=(10, 4))

    # Row 5: "Gerar Excel apenas" button
    self.btn_excel_only = tk.Button(
        self, text="Gerar Excel apenas",
        command=self._start_excel_only,
        bg="#3a3a5a", fg=TEXT_WHITE,
        activebackground="#505070", activeforeground=TEXT_WHITE,
        font=FONT_BTN, padx=24, pady=8,
        relief="flat", cursor="hand2",
    )
    self.btn_excel_only.grid(row=5, column=0, columnspan=3, pady=(0, 6))

    # Row 6: progress bar
    self.progress = ttk.Progressbar(self, length=500, mode="determinate")
    self.progress.grid(row=6, column=0, columnspan=3, padx=14, pady=(4, 0))

    # Row 7: status label
    self.status_var = tk.StringVar(value="Pronto.")
    tk.Label(
        self, textvariable=self.status_var,
        bg=BG_CONTENT, fg=TEXT_DIM, font=FONT_LABEL, anchor="w",
    ).grid(row=7, column=0, columnspan=3, sticky="w", padx=14, pady=(2, 4))
```

- [ ] **Step 2: Add `_start_excel_only` method and update `_start_export` + `_finish`**

Add the `_start_excel_only` method after `_start_export`:

```python
def _start_excel_only(self):
    from tkinter import messagebox
    asm = self._get_asm_path()
    out = self.out_var.get().strip()

    if not asm or not os.path.isfile(asm):
        messagebox.showerror("Erro", "Seleciona um ficheiro .sldasm v\u00e1lido.")
        return
    if not out or not os.path.isdir(out):
        messagebox.showerror("Erro", "Seleciona uma pasta de output v\u00e1lida.")
        return

    self.btn_export.config(state="disabled")
    self.btn_excel_only.config(state="disabled")
    self.progress["value"] = 0
    self._set_status("A gerar Excel\u2026")

    thread = threading.Thread(
        target=self._worker_excel_only, args=(asm, out), daemon=True)
    thread.start()
```

- [ ] **Step 3: Update `_start_export` to disable both buttons**

In `_start_export`, replace:
```python
self.btn_export.config(state="disabled")
```
with:
```python
self.btn_export.config(state="disabled")
self.btn_excel_only.config(state="disabled")
```

- [ ] **Step 4: Update `_finish` closure inside `_worker` to re-enable both buttons**

Inside `_worker`, locate the `_finish` inner function and replace:
```python
def _finish():
    self.btn_export.config(state="normal")
    self._set_status("Conclu\u00eddo.")
    self._log("\u2500" * 68)
    self._log(
        f"Resultado: {ok_count} exportado(s)  |  "
        f"{warn_count} aviso(s)  |  {err_count} erro(s)"
    )
```
with:
```python
def _finish():
    self.btn_export.config(state="normal")
    self.btn_excel_only.config(state="normal")
    self._set_status("Conclu\u00eddo.")
    self._log("\u2500" * 68)
    self._log(
        f"Resultado: {ok_count} exportado(s)  |  "
        f"{warn_count} aviso(s)  |  {err_count} erro(s)"
    )
```

- [ ] **Step 5: Add Excel generation at the end of `_worker`**

In `_worker`, add the following block **inside the `try` block, immediately after `ui(lambda: self._set_progress(total, total))`**, at the same indentation level as that call. This placement is after the per-part loop completes and after the `if total == 0: return` guard — so it only runs when there were parts to export. Do not place it after the `except` or `finally` clause.

```python
            # Generate Excel if checkbox is checked
            if self.excel_var.get():
                ui(lambda: self._log("A gerar Laser.xlsx\u2026"))
                try:
                    self._generate_laser_excel(
                        all_parts, laser_parts, out_dir)
                    ui(lambda: self._log("  OK    Laser.xlsx"))
                except Exception as exc:
                    ui(lambda m=str(exc): self._log(f"  ERROR Excel \u2014 {m}"))
```

- [ ] **Step 6: Add `_generate_laser_excel` and `_worker_excel_only` methods**

Add after `_worker`:

```python
def _generate_laser_excel(self, all_parts, laser_parts, out_dir):
    """
    Build Laser.xlsx from the already-collected part lists.
    Called from _worker (after export) and from _worker_excel_only.
    all_parts must be the pre-dedup full list so count_instances is correct.
    """
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from solidworks import get_part_data
    from excel_writer import generate_excel, LASER_COLUMNS, PROCESS_CONFIG

    rows = [get_part_data(p, all_parts) for p in laser_parts]
    template_name, output_name, _ = PROCESS_CONFIG["laser"]
    template_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))))),
        "Templates", template_name
    )
    output_path = os.path.join(out_dir, output_name)
    generate_excel(template_path, rows, output_path, LASER_COLUMNS)


def _worker_excel_only(self, asm_path: str, out_dir: str):
    """Background worker for 'Gerar Excel apenas' — no DXF export."""
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from solidworks import (
        connect_to_solidworks, open_assembly, get_all_parts,
        deduplicate_by_path, is_laser_part,
    )

    def ui(fn):
        self.after(0, fn)

    sw = None  # must be defined before try so finally block is safe
    asm_doc = asm_opened_by_us = None

    try:
        ui(lambda: self._log("\u2550" * 68))
        ui(lambda: self._log("Gerar Excel (Laser)"))
        ui(lambda: self._log("A conectar ao SolidWorks\u2026"))
        sw = connect_to_solidworks()

        ui(lambda: self._log(f"A abrir assembly: {os.path.basename(asm_path)}"))
        asm_doc, asm_opened_by_us = open_assembly(sw, asm_path)

        ui(lambda: self._log("A percorrer componentes\u2026"))
        all_parts    = get_all_parts(asm_doc)
        unique_parts = deduplicate_by_path(all_parts)
        laser_parts  = [p for p in unique_parts if is_laser_part(p)]

        ui(lambda n=len(laser_parts): self._log(f"  Pe\u00e7as laser: {n}"))

        if laser_parts:
            ui(lambda: self._log("A gerar Laser.xlsx\u2026"))
            try:
                self._generate_laser_excel(all_parts, laser_parts, out_dir)
                ui(lambda: self._log("  OK    Laser.xlsx"))
            except Exception as exc:
                ui(lambda m=str(exc): self._log(f"  ERROR Excel \u2014 {m}"))
        else:
            ui(lambda: self._log("Nenhuma pe\u00e7a laser encontrada."))

    except Exception as exc:
        ui(lambda m=str(exc): self._log(f"ERRO FATAL: {m}"))

    finally:
        if asm_opened_by_us and asm_doc is not None:
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
```

- [ ] **Step 7: Manual verification**

Launch the GUI and verify:
```bash
python tools/exporter/main.py
```
- Both buttons visible in the DXF panel
- Checkbox toggles correctly
- Both buttons disable when either operation starts
- Both buttons re-enable on completion
- With checkbox checked: exporting DXF also produces `Laser.xlsx` in the output folder
- "Gerar Excel apenas": produces `Laser.xlsx` without any DXF files

- [ ] **Step 8: Commit**

```bash
git add tools/exporter/modules/dxf_module.py
git commit -m "feat: add Excel checkbox and 'Gerar Excel apenas' button to DXF panel"
```

---

## Chunk 4: step_module.py UI + Excel worker

### Task 8: Update `step_module.py`

**Files:**
- Modify: `tools/exporter/modules/step_module.py`

- [ ] **Step 1: Replace `_build_ui` — same layout as DXF panel**

In `tools/exporter/modules/step_module.py`, replace the `_build_ui` method:

```python
def _build_ui(self):
    pad = {"padx": 14, "pady": 6}

    # Row 0: section title
    tk.Label(
        self, text="STEP Export \u2014 Router / CNC / Torno",
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

    # Row 3: "Gerar Excel" checkbox
    self.excel_var = tk.BooleanVar(value=False)
    tk.Checkbutton(
        self, text="Gerar Excel",
        variable=self.excel_var,
        bg=BG_CONTENT, fg=TEXT, selectcolor=BG_CONTENT,
        activebackground=BG_CONTENT, activeforeground=TEXT_WHITE,
        font=FONT_LABEL,
    ).grid(row=3, column=0, columnspan=3, sticky="w", padx=14, pady=(4, 2))

    # Row 4: Export button
    self.btn_export = tk.Button(
        self, text="Export STEP",
        command=self._start_export,
        bg=ACCENT, fg=TEXT_WHITE,
        activebackground="#005fa3", activeforeground=TEXT_WHITE,
        font=FONT_BTN, padx=24, pady=8,
        relief="flat", cursor="hand2",
    )
    self.btn_export.grid(row=4, column=0, columnspan=3, pady=(10, 4))

    # Row 5: "Gerar Excel apenas" button
    self.btn_excel_only = tk.Button(
        self, text="Gerar Excel apenas",
        command=self._start_excel_only,
        bg="#3a3a5a", fg=TEXT_WHITE,
        activebackground="#505070", activeforeground=TEXT_WHITE,
        font=FONT_BTN, padx=24, pady=8,
        relief="flat", cursor="hand2",
    )
    self.btn_excel_only.grid(row=5, column=0, columnspan=3, pady=(0, 6))

    # Row 6: progress bar
    self.progress = ttk.Progressbar(self, length=500, mode="determinate")
    self.progress.grid(row=6, column=0, columnspan=3, padx=14, pady=(4, 0))

    # Row 7: status label
    self.status_var = tk.StringVar(value="Pronto.")
    tk.Label(
        self, textvariable=self.status_var,
        bg=BG_CONTENT, fg=TEXT_DIM, font=FONT_LABEL, anchor="w",
    ).grid(row=7, column=0, columnspan=3, sticky="w", padx=14, pady=(2, 4))
```

- [ ] **Step 2: Add `_start_excel_only` and update `_start_export`**

Add `_start_excel_only` after `_start_export`:

```python
def _start_excel_only(self):
    from tkinter import messagebox
    asm = self._get_asm_path()
    out = self.out_var.get().strip()

    if not asm or not os.path.isfile(asm):
        messagebox.showerror("Erro", "Seleciona um ficheiro .sldasm v\u00e1lido.")
        return
    if not out or not os.path.isdir(out):
        messagebox.showerror("Erro", "Seleciona uma pasta de output v\u00e1lida.")
        return

    self.btn_export.config(state="disabled")
    self.btn_excel_only.config(state="disabled")
    self.progress["value"] = 0
    self._set_status("A gerar Excel\u2026")

    thread = threading.Thread(
        target=self._worker_excel_only, args=(asm, out), daemon=True)
    thread.start()
```

In `_start_export`, replace:
```python
self.btn_export.config(state="disabled")
```
with:
```python
self.btn_export.config(state="disabled")
self.btn_excel_only.config(state="disabled")
```

- [ ] **Step 3: Update `_finish` in `_worker` to re-enable both buttons**

Inside `_worker`, in the `_finish` closure, replace:
```python
def _finish():
    self.btn_export.config(state="normal")
    self._set_status("Conclu\u00eddo.")
    self._log("\u2500" * 68)
    self._log(
        f"Resultado: {ok_count} exportado(s)  |  "
        f"{skip_count} ignorado(s)  |  {err_count} erro(s)"
    )
```
with:
```python
def _finish():
    self.btn_export.config(state="normal")
    self.btn_excel_only.config(state="normal")
    self._set_status("Conclu\u00eddo.")
    self._log("\u2500" * 68)
    self._log(
        f"Resultado: {ok_count} exportado(s)  |  "
        f"{skip_count} ignorado(s)  |  {err_count} erro(s)"
    )
```

- [ ] **Step 4: Add Excel generation at the end of `_worker`**

In `_worker`, the per-part loop is wrapped in an **inner** `try/finally` block (the `finally: pass` placeholder for tmp dir cleanup). Add the Excel generation block **inside this inner `try` block, immediately after `ui(lambda: self._set_progress(total, total))`**, before the inner `finally`. This ensures Excel is generated even when individual part exports failed (per-part errors are caught individually), and is skipped only if the loop itself aborted via exception.

```python
            # Generate Excel files if checkbox is checked
            if self.excel_var.get():
                try:
                    generated = self._generate_step_excels(
                        all_parts, unique_parts, step_parts, out_dir)
                    for name in generated:
                        ui(lambda n=name: self._log(f"  OK    {n}"))
                except Exception as exc:
                    ui(lambda m=str(exc): self._log(f"  ERROR Excel \u2014 {m}"))
```

- [ ] **Step 5: Add `_generate_step_excels`, `_worker_excel_only` methods**

Add after `_export_router_part`:

```python
def _generate_step_excels(self, all_parts, unique_parts, step_parts, out_dir):
    """
    Generate one Excel file per process category found in step_parts.
    Returns list of generated filenames (e.g. ["Router.xlsx", "CNC.xlsx"]).
    A part with "router+cnc" in Corte_Fabrico appears in both groups.
    """
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from solidworks import get_part_data, get_corte_fabrico
    from excel_writer import generate_excel, PROCESS_CONFIG

    templates_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))))),
        "Templates"
    )

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
        template_name, output_name, col_order = PROCESS_CONFIG[keyword]
        template_path = os.path.join(templates_dir, template_name)
        output_path   = os.path.join(out_dir, output_name)
        rows = [get_part_data(p, all_parts) for p in parts]
        generate_excel(template_path, rows, output_path, col_order)
        generated.append(output_name)

    return generated


def _worker_excel_only(self, asm_path: str, out_dir: str):
    """Background worker for 'Gerar Excel apenas' — no STEP export."""
    asm_path = os.path.normpath(os.path.abspath(asm_path))
    sw_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, sw_dir)
    from solidworks import (
        connect_to_solidworks, open_assembly, get_all_parts,
        deduplicate_by_path, is_step_part,
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
        asm_doc, asm_opened_by_us = open_assembly(sw, asm_path)

        ui(lambda: self._log("A percorrer componentes\u2026"))
        all_parts    = get_all_parts(asm_doc)
        unique_parts = deduplicate_by_path(all_parts)
        step_parts   = [p for p in unique_parts if is_step_part(p)]

        ui(lambda n=len(step_parts): self._log(f"  Pe\u00e7as STEP: {n}"))

        if step_parts:
            try:
                generated = self._generate_step_excels(
                    all_parts, unique_parts, step_parts, out_dir)
                for name in generated:
                    ui(lambda n=name: self._log(f"  OK    {n}"))
            except Exception as exc:
                ui(lambda m=str(exc): self._log(f"  ERROR Excel \u2014 {m}"))
        else:
            ui(lambda: self._log("Nenhuma pe\u00e7a router/cnc/torno encontrada."))

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
```

- [ ] **Step 6: Manual verification**

```bash
python tools/exporter/main.py
```
- Both buttons visible in the STEP panel
- Both buttons disable/re-enable correctly
- With checkbox checked and exporting: Router.xlsx / CNC.xlsx / Torno.xlsx generated for the process types present in the assembly
- "Gerar Excel apenas": generates Excel files without exporting any STEP files
- Parts with combined Corte_Fabrico (e.g. "router+cnc") appear in both Router.xlsx and CNC.xlsx

- [ ] **Step 7: Run full test suite one final time**

```bash
python -m pytest tools/exporter/tests/ -v
```

Expected: all tests PASSED

- [ ] **Step 8: Commit**

```bash
git add tools/exporter/modules/step_module.py
git commit -m "feat: add Excel checkbox and 'Gerar Excel apenas' button to STEP panel"
```
