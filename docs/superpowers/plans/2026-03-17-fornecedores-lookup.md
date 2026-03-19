# Fornecedores Lookup Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace hardcoded brand frozensets in `bom_writer.py` with a runtime lookup against `Templates/Fornecedores.xlsx`, so all 311 suppliers are recognised and classified correctly.

**Architecture:** `bom_writer.py` loads the Excel at import time into `FORNECEDORES_LOOKUP` (dict of normalized-name → category) and `ALL_KNOWN_BRANDS` (frozenset of normalized names). `classify_commercial` and new `is_known_brand` use this lookup. The 3 callers replace the old `any(b in val for b in ALL_KNOWN_BRANDS)` pattern with `is_known_brand(val)`.

**Tech Stack:** Python 3.x, openpyxl (already a dependency), unittest, unittest.mock

---

## File Map

| Action | File |
|--------|------|
| Modify (1 line) | `tools/fornecedores/categorias.py` |
| Modify (1 line) | `Templates/Fornecedores.txt` |
| Regenerate (run script) | `Templates/Fornecedores.xlsx` |
| Modify (brand section) | `tools/exporter/bom_writer.py` |
| Create | `tools/exporter/tests/test_bom_writer_lookup.py` |
| Modify (import + warning check) | `tools/exporter/modules/bom_module.py` |
| Modify (import + warning check) | `tools/exporter/modules/listas_module.py` |
| Modify (import + warning check) | `tools/exporter/modules/all_module.py` |

---

## Task 1: Fix categorias.py + Fornecedores.txt and regenerate Fornecedores.xlsx

**Files:**
- Modify: `tools/fornecedores/categorias.py:188`
- Modify: `Templates/Fornecedores.txt:181`

> **Why both files?** `generate_fornecedores.py` reads supplier names from `Fornecedores.txt` and looks up categories from `categorias.py`. If only `categorias.py` is updated, the generated Excel will still have a row named "Murr" (from the txt) but with `DEFAULT_CATEGORY` ("Mecânico") because `CATEGORIAS.get("Murr")` now misses.

- [ ] **Step 1: Rename in categorias.py**

In `tools/fornecedores/categorias.py`, change line 188:
```python
# Before
"Murr": "Elétrico",
# After
"Murreletronik": "Elétrico",
```

- [ ] **Step 2: Rename in Fornecedores.txt**

In `Templates/Fornecedores.txt`, change line 181:
```
# Before
Murr
# After
Murreletronik
```

- [ ] **Step 3: Regenerate the Excel**

```bash
cd "C:\Users\Micael\Desktop\Auto Production"
python tools/fornecedores/generate_fornecedores.py
```

Expected output: `Saved 311 suppliers -> ...\Templates\Fornecedores.xlsx`

- [ ] **Step 4: Run existing fornecedores tests to confirm no regression**

```bash
cd "C:\Users\Micael\Desktop\Auto Production"
python -m pytest tools/fornecedores/tests/ -v
```

Expected: all tests pass. The rename is a key rename + txt rename, not a removal — total supplier count stays the same.

- [ ] **Step 5: Commit**

```bash
git add tools/fornecedores/categorias.py Templates/Fornecedores.txt Templates/Fornecedores.xlsx
git commit -m "fix: rename Murr -> Murreletronik in categorias.py + Fornecedores.txt, regenerate Excel"
```

---

## Task 2: Write failing tests for new bom_writer API

**Files:**
- Create: `tools/exporter/tests/test_bom_writer_lookup.py`

- [ ] **Step 1: Create the test file**

Create `tools/exporter/tests/test_bom_writer_lookup.py`:

```python
"""
Tests for the Excel-backed brand lookup API in bom_writer.py.
Uses a controlled in-memory fixture Excel — does not depend on the real Fornecedores.xlsx.
"""
import sys
import os
import tempfile
import shutil
import unittest
import unittest.mock
import openpyxl

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def _make_fixture_excel(path: str, rows: list) -> None:
    """
    Write a minimal Fornecedores.xlsx fixture.
    rows: list of (nome, categoria) — e.g. [("Festo", "Pneumático")]
    Column layout: A=Nome, B=Código (ignored by loader), C=Categoria
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Nome", "Código", "Categoria"])  # header row 1
    for nome, categoria in rows:
        ws.append([nome, nome[:3].upper(), categoria])
    wb.save(path)


class TestNormalize(unittest.TestCase):

    def test_lowercase_and_strips_spaces(self):
        from bom_writer import normalize
        self.assertEqual(normalize("Bru y Rubio"), "bruyrubio")

    def test_already_lowercase_no_spaces(self):
        from bom_writer import normalize
        self.assertEqual(normalize("equinotec"), "equinotec")

    def test_all_uppercase(self):
        from bom_writer import normalize
        self.assertEqual(normalize("EQUINOTEC"), "equinotec")

    def test_empty_string(self):
        from bom_writer import normalize
        self.assertEqual(normalize(""), "")

    def test_spaces_only(self):
        from bom_writer import normalize
        self.assertEqual(normalize("   "), "")


class TestLoadFornecedoresLookup(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_loads_all_three_categories(self):
        from bom_writer import load_fornecedores_lookup
        _make_fixture_excel(
            os.path.join(self.tmp, "Fornecedores.xlsx"),
            [("Festo", "Pneumático"), ("Balluf", "Elétrico"), ("SKF", "Mecânico")],
        )
        with unittest.mock.patch("bom_writer.get_templates_dir", return_value=self.tmp):
            lookup = load_fornecedores_lookup()
        self.assertEqual(lookup["festo"], "pneumatico")
        self.assertEqual(lookup["balluf"], "eletrico")
        self.assertEqual(lookup["skf"], "mecanico")

    def test_normalizes_names_with_spaces(self):
        from bom_writer import load_fornecedores_lookup
        _make_fixture_excel(
            os.path.join(self.tmp, "Fornecedores.xlsx"),
            [("Bru y Rubio", "Mecânico")],
        )
        with unittest.mock.patch("bom_writer.get_templates_dir", return_value=self.tmp):
            lookup = load_fornecedores_lookup()
        self.assertIn("bruyrubio", lookup)

    def test_skips_rows_with_no_category(self):
        from bom_writer import load_fornecedores_lookup
        _make_fixture_excel(
            os.path.join(self.tmp, "Fornecedores.xlsx"),
            [("Festo", "Pneumático"), ("NoCategory", "")],
        )
        # Patch the Excel to have an empty category row
        # (fixture helper always fills col C — manually write a None cell)
        wb = openpyxl.load_workbook(os.path.join(self.tmp, "Fornecedores.xlsx"))
        ws = wb.active
        ws.cell(row=3, column=3, value=None)
        wb.save(os.path.join(self.tmp, "Fornecedores.xlsx"))

        with unittest.mock.patch("bom_writer.get_templates_dir", return_value=self.tmp):
            lookup = load_fornecedores_lookup()
        self.assertIn("festo", lookup)
        self.assertNotIn("nocategory", lookup)

    def test_missing_excel_returns_empty_dict(self):
        from bom_writer import load_fornecedores_lookup
        empty_dir = os.path.join(self.tmp, "no_excel_here")
        os.makedirs(empty_dir)
        with unittest.mock.patch("bom_writer.get_templates_dir", return_value=empty_dir):
            lookup = load_fornecedores_lookup()
        self.assertEqual(lookup, {})


_FIXTURE_LOOKUP = {
    "festo":   "pneumatico",
    "smc":     "pneumatico",
    "balluf":  "eletrico",
    "siemens": "eletrico",
    "skf":     "mecanico",
    "bruyrubio": "mecanico",  # "Bru y Rubio" normalized
}


class TestIsKnownBrand(unittest.TestCase):
    """
    Patches bom_writer.FORNECEDORES_LOOKUP directly — no reload needed.
    is_known_brand reads the module-level dict at call time, so patch.dict suffices.
    """

    def test_known_brand_exact_match(self):
        import bom_writer
        with unittest.mock.patch.dict(bom_writer.FORNECEDORES_LOOKUP, _FIXTURE_LOOKUP, clear=True):
            self.assertTrue(bom_writer.is_known_brand("Festo"))

    def test_known_brand_case_insensitive(self):
        import bom_writer
        with unittest.mock.patch.dict(bom_writer.FORNECEDORES_LOOKUP, _FIXTURE_LOOKUP, clear=True):
            self.assertTrue(bom_writer.is_known_brand("FESTO"))

    def test_known_brand_substring_match(self):
        import bom_writer
        with unittest.mock.patch.dict(bom_writer.FORNECEDORES_LOOKUP, _FIXTURE_LOOKUP, clear=True):
            self.assertTrue(bom_writer.is_known_brand("Ref 123 Festo ABC"))

    def test_unknown_brand_returns_false(self):
        import bom_writer
        with unittest.mock.patch.dict(bom_writer.FORNECEDORES_LOOKUP, _FIXTURE_LOOKUP, clear=True):
            self.assertFalse(bom_writer.is_known_brand("XYZ Unknown Corp"))

    def test_empty_string_returns_false(self):
        import bom_writer
        with unittest.mock.patch.dict(bom_writer.FORNECEDORES_LOOKUP, _FIXTURE_LOOKUP, clear=True):
            self.assertFalse(bom_writer.is_known_brand(""))

    def test_tuple_input_unpacked(self):
        import bom_writer
        # SW 2024 can return tuple from get_custom_property_evaluated
        with unittest.mock.patch.dict(bom_writer.FORNECEDORES_LOOKUP, _FIXTURE_LOOKUP, clear=True):
            self.assertTrue(bom_writer.is_known_brand(("Festo", "extra")))

    def test_tuple_empty_returns_false(self):
        import bom_writer
        with unittest.mock.patch.dict(bom_writer.FORNECEDORES_LOOKUP, _FIXTURE_LOOKUP, clear=True):
            self.assertFalse(bom_writer.is_known_brand(()))


class TestClassifyCommercialWithFixture(unittest.TestCase):
    """
    Patches bom_writer.FORNECEDORES_LOOKUP directly — no reload needed.
    classify_commercial reads the module-level dict at call time.
    """

    def test_exact_match_pneumatico(self):
        import bom_writer
        with unittest.mock.patch.dict(bom_writer.FORNECEDORES_LOOKUP, _FIXTURE_LOOKUP, clear=True):
            self.assertEqual(bom_writer.classify_commercial("Festo"), "pneumatico")

    def test_case_insensitive_pneumatico(self):
        import bom_writer
        with unittest.mock.patch.dict(bom_writer.FORNECEDORES_LOOKUP, _FIXTURE_LOOKUP, clear=True):
            self.assertEqual(bom_writer.classify_commercial("FESTO"), "pneumatico")

    def test_space_variation_mecanico(self):
        import bom_writer
        # "Bruyrubio" normalizes to "bruyrubio", same as "Bru y Rubio"
        with unittest.mock.patch.dict(bom_writer.FORNECEDORES_LOOKUP, _FIXTURE_LOOKUP, clear=True):
            self.assertEqual(bom_writer.classify_commercial("Bruyrubio"), "mecanico")

    def test_substring_match_eletrico(self):
        import bom_writer
        with unittest.mock.patch.dict(bom_writer.FORNECEDORES_LOOKUP, _FIXTURE_LOOKUP, clear=True):
            self.assertEqual(bom_writer.classify_commercial("Produto Balluf 123"), "eletrico")

    def test_unknown_brand_defaults_to_mecanico(self):
        import bom_writer
        with unittest.mock.patch.dict(bom_writer.FORNECEDORES_LOOKUP, _FIXTURE_LOOKUP, clear=True):
            self.assertEqual(bom_writer.classify_commercial("Unknown Corp XYZ"), "mecanico")

    def test_empty_string_defaults_to_mecanico(self):
        import bom_writer
        with unittest.mock.patch.dict(bom_writer.FORNECEDORES_LOOKUP, _FIXTURE_LOOKUP, clear=True):
            self.assertEqual(bom_writer.classify_commercial(""), "mecanico")

    def test_tuple_input_unpacked(self):
        import bom_writer
        with unittest.mock.patch.dict(bom_writer.FORNECEDORES_LOOKUP, _FIXTURE_LOOKUP, clear=True):
            self.assertEqual(bom_writer.classify_commercial(("Festo", "extra")), "pneumatico")

    def test_exact_match_wins_over_substring(self):
        """Exact match should return before iterating substrings."""
        import bom_writer
        with unittest.mock.patch.dict(bom_writer.FORNECEDORES_LOOKUP, _FIXTURE_LOOKUP, clear=True):
            self.assertEqual(bom_writer.classify_commercial("SMC"), "pneumatico")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to confirm they all fail (functions don't exist yet)**

```bash
cd "C:\Users\Micael\Desktop\Auto Production"
python -m pytest tools/exporter/tests/test_bom_writer_lookup.py -v 2>&1 | head -40
```

Expected: errors like `ImportError: cannot import name 'normalize'` or `AttributeError`. All tests in `TestNormalize`, `TestLoadFornecedoresLookup`, `TestIsKnownBrand`, `TestClassifyCommercialWithFixture` should fail.

---

## Task 3: Implement new bom_writer API

**Files:**
- Modify: `tools/exporter/bom_writer.py:19-45` (brand classification section)

- [ ] **Step 1: Add `import logging` to the top-level imports block**

In `tools/exporter/bom_writer.py`, add `import logging` to the existing imports block (lines 8–14), after `import zipfile`:
```python
import zipfile
import logging    # ← add this line
```

- [ ] **Step 2: Replace the brand classification section**

In `tools/exporter/bom_writer.py`, replace lines 19–45 (from `# Brand classification` comment through the end of `classify_commercial`) with:

```python
# ---------------------------------------------------------------------------
# Brand classification — backed by Templates/Fornecedores.xlsx
# ---------------------------------------------------------------------------

_CAT_MAP = {
    "Mecânico":   "mecanico",
    "Elétrico":   "eletrico",
    "Pneumático": "pneumatico",
}


def normalize(s: str) -> str:
    return s.lower().replace(" ", "")


def load_fornecedores_lookup() -> dict:
    """
    Load Templates/Fornecedores.xlsx and return {normalize(nome): category}.
    category is one of "mecanico", "eletrico", "pneumatico".
    Returns {} and logs a warning if the file is missing.
    """
    path = os.path.join(get_templates_dir(), "Fornecedores.xlsx")
    if not os.path.isfile(path):
        logging.warning("AVISO: Fornecedores.xlsx não encontrado — classificação por defeito: Mecânico")
        return {}
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    result = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        nome = row[0]
        cat_pt = row[2] if len(row) > 2 else None
        if not nome or not cat_pt:
            continue
        internal = _CAT_MAP.get(str(cat_pt).strip())
        if internal:
            result[normalize(str(nome))] = internal
    wb.close()
    return result


FORNECEDORES_LOOKUP: dict = load_fornecedores_lookup()
ALL_KNOWN_BRANDS: frozenset = frozenset(FORNECEDORES_LOOKUP.keys())


def is_known_brand(corte_fabrico) -> bool:
    if isinstance(corte_fabrico, tuple):
        corte_fabrico = corte_fabrico[0] if corte_fabrico else ""
    corte_fabrico = corte_fabrico or ""
    val = normalize(corte_fabrico)
    if val in FORNECEDORES_LOOKUP:
        return True
    return any(n and n in val for n in FORNECEDORES_LOOKUP)


def classify_commercial(corte_fabrico) -> str:
    """
    Return "pneumatico", "eletrico", or "mecanico".
    Exact match first; then substring scan (alphabetical, first wins).
    Unknown / empty falls back to "mecanico".
    """
    if isinstance(corte_fabrico, tuple):
        corte_fabrico = corte_fabrico[0] if corte_fabrico else ""
    corte_fabrico = corte_fabrico or ""
    val = normalize(corte_fabrico)
    if val in FORNECEDORES_LOOKUP:
        return FORNECEDORES_LOOKUP[val]
    for norm_name in sorted(FORNECEDORES_LOOKUP):
        if norm_name and norm_name in val:
            return FORNECEDORES_LOOKUP[norm_name]
    return "mecanico"
```

- [ ] **Step 3: Run the new lookup tests**

```bash
cd "C:\Users\Micael\Desktop\Auto Production"
python -m pytest tools/exporter/tests/test_bom_writer_lookup.py -v
```

Expected: all tests pass.

- [ ] **Step 4: Run existing bom_writer tests to confirm no regression**

```bash
cd "C:\Users\Micael\Desktop\Auto Production"
python -m pytest tools/exporter/tests/test_bom_writer.py -v
```

Expected: all tests pass. Key ones to watch:
- `test_festo_*` → still "pneumatico" (Festo is in Fornecedores.xlsx as Pneumático)
- `test_siemens_is_eletrico` → still "eletrico"
- `test_skf_is_mecanico` → still "mecanico"
- `test_bosch_rexroth_is_mecanico` → still "mecanico" (either in Excel as Mecânico, or falls through to default)
- `TestAllKnownBrands` tests → still pass because `ALL_KNOWN_BRANDS` is now a frozenset of 311 normalized names, and `any(b in "festo" for b in ALL_KNOWN_BRANDS)` is still True.

- [ ] **Step 5: Commit**

```bash
git add tools/exporter/bom_writer.py tools/exporter/tests/test_bom_writer_lookup.py
git commit -m "feat: replace hardcoded brand frozensets with Fornecedores.xlsx lookup"
```

---

## Task 4: Update the 3 callers

**Files:**
- Modify: `tools/exporter/modules/bom_module.py:145-219`
- Modify: `tools/exporter/modules/listas_module.py:347-405`
- Modify: `tools/exporter/modules/all_module.py:500-549`

All 3 callers have the same two-line change pattern.

### bom_module.py

- [ ] **Step 1: Update import (line 145–147)**

```python
# Before
from bom_writer import (
    classify_commercial, generate_bom, ALL_KNOWN_BRANDS,
)
# After
from bom_writer import (
    classify_commercial, generate_bom, ALL_KNOWN_BRANDS, is_known_brand,
)
```

- [ ] **Step 2: Update warning check (line 213–219)**

```python
# Before
val = (row.get("Corte_Fabrico") or "").strip().lower()
if not any(b in val for b in ALL_KNOWN_BRANDS):
    msg = (f"Fabricante desconhecido: '{row['Corte_Fabrico']}'"
           f" → Material Mecânico")
    ui(lambda m=msg: self._log(f"  AVISO {m}"))
    warn_count += 1
cat = classify_commercial(val)
# After
val = row.get("Corte_Fabrico") or ""
if not is_known_brand(val):
    msg = (f"Fabricante desconhecido: '{row['Corte_Fabrico']}'"
           f" → Material Mecânico")
    ui(lambda m=msg: self._log(f"  AVISO {m}"))
    warn_count += 1
cat = classify_commercial(val)
```

### listas_module.py

- [ ] **Step 3: Update import (line 347)**

```python
# Before
from bom_writer import classify_commercial, generate_bom, ALL_KNOWN_BRANDS
# After
from bom_writer import classify_commercial, generate_bom, ALL_KNOWN_BRANDS, is_known_brand
```

- [ ] **Step 4: Update warning check (line 399–405)**

```python
# Before
val = (row.get("Corte_Fabrico") or "").strip().lower()
if not any(b in val for b in ALL_KNOWN_BRANDS):
    msg = (f"Fabricante desconhecido: '{row['Corte_Fabrico']}'"
           f" → Material Mecânico")
    ui(lambda m=msg: self._log(f"  AVISO {m}"))
    warn_count += 1
cat = classify_commercial(val)
# After
val = row.get("Corte_Fabrico") or ""
if not is_known_brand(val):
    msg = (f"Fabricante desconhecido: '{row['Corte_Fabrico']}'"
           f" → Material Mecânico")
    ui(lambda m=msg: self._log(f"  AVISO {m}"))
    warn_count += 1
cat = classify_commercial(val)
```

### all_module.py

- [ ] **Step 5: Update import (line 500)**

```python
# Before
from bom_writer import classify_commercial, generate_bom, ALL_KNOWN_BRANDS
# After
from bom_writer import classify_commercial, generate_bom, ALL_KNOWN_BRANDS, is_known_brand
```

- [ ] **Step 6: Update warning check (line 543–549)**

```python
# Before
val = (row.get("Corte_Fabrico") or "").strip().lower()
if not any(b in val for b in ALL_KNOWN_BRANDS):
    msg = (f"Fabricante desconhecido: '{row['Corte_Fabrico']}'"
           f" → Material Mecânico")
    ui(lambda m=msg: self._log(f"  AVISO {m}"))
    warn_count += 1
cat = classify_commercial(val)
# After
val = row.get("Corte_Fabrico") or ""
if not is_known_brand(val):
    msg = (f"Fabricante desconhecido: '{row['Corte_Fabrico']}'"
           f" → Material Mecânico")
    ui(lambda m=msg: self._log(f"  AVISO {m}"))
    warn_count += 1
cat = classify_commercial(val)
```

- [ ] **Step 7: Run full test suite**

```bash
cd "C:\Users\Micael\Desktop\Auto Production"
python -m pytest tools/ -v --tb=short 2>&1 | tail -20
```

Expected: all previously-passing tests still pass. The 1 pre-existing failure (`test_lightweight_part_model_none_skipped_silently`) is acceptable.

- [ ] **Step 8: Commit**

```bash
git add tools/exporter/modules/bom_module.py tools/exporter/modules/listas_module.py tools/exporter/modules/all_module.py
git commit -m "refactor: callers use is_known_brand() instead of ALL_KNOWN_BRANDS set scan"
```

---

## Done

All 311 suppliers in `Templates/Fornecedores.xlsx` are now the single source of truth. The "Fabricante desconhecido" warning will only fire for brands genuinely absent from the Excel. To add a new supplier, edit `categorias.py` and re-run `generate_fornecedores.py`.
