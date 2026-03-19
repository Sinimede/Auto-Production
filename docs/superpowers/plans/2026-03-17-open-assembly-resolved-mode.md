# Open Assembly in Resolved Mode — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `open_assembly_resolved()` to `solidworks.py` so the BOM/listas feature always opens the SolidWorks assembly in fully-resolved (non-lightweight) mode, fixing the `Produção: 43` → `Produção: 88` count bug.

**Architecture:** New function `open_assembly_resolved()` closes any already-open instance (after a dirty check), then opens via `OpenDoc6` with `options=66` (`swOpenDocOptions_ReadOnly | swOpenDocOptions_OverrideDefaultLoadLightweight`). `listas_module.py` calls this instead of `open_assembly`. All other callers (DXF, STEP, BOM, All) continue using `open_assembly` unchanged.

**Tech Stack:** Python 3.x, win32com (SW 2024 early binding), unittest.mock

**Spec:** `docs/superpowers/specs/2026-03-17-open-assembly-resolved-mode-design.md`

---

## Chunk 1: Tests + `_is_dirty()` helper

### Task 1: Write failing tests for `_is_dirty()`

**Files:**
- Modify: `tools/exporter/tests/test_solidworks_helpers.py`

- [ ] **Step 1: Add failing tests for `_is_dirty()`**

Add at the bottom of `tools/exporter/tests/test_solidworks_helpers.py`:

```python
# ---------------------------------------------------------------------------
# _is_dirty
# ---------------------------------------------------------------------------

class TestIsDirty(unittest.TestCase):

    def test_returns_true_when_dirty_method(self):
        """GetSaveFlag is a callable returning True (document has unsaved changes)."""
        from solidworks import _is_dirty
        doc = MagicMock()
        doc.GetSaveFlag = MagicMock(return_value=True)
        self.assertTrue(_is_dirty(doc))

    def test_returns_false_when_clean_method(self):
        """GetSaveFlag is a callable returning False (document is clean)."""
        from solidworks import _is_dirty
        doc = MagicMock()
        doc.GetSaveFlag = MagicMock(return_value=False)
        self.assertFalse(_is_dirty(doc))

    def test_returns_true_when_dirty_property(self):
        """GetSaveFlag is a non-callable property (True = dirty)."""
        from solidworks import _is_dirty
        doc = MagicMock()
        doc.GetSaveFlag = True  # property, not method
        self.assertTrue(_is_dirty(doc))

    def test_returns_false_when_clean_property(self):
        """GetSaveFlag is a non-callable property (False = clean)."""
        from solidworks import _is_dirty
        doc = MagicMock()
        doc.GetSaveFlag = False
        self.assertFalse(_is_dirty(doc))

    def test_handles_tuple_return(self):
        """SW 2024 sometimes returns tuple — first element is the value."""
        from solidworks import _is_dirty
        doc = MagicMock()
        doc.GetSaveFlag = MagicMock(return_value=(True, 0))
        self.assertTrue(_is_dirty(doc))

    def test_handles_tuple_clean(self):
        from solidworks import _is_dirty
        doc = MagicMock()
        doc.GetSaveFlag = MagicMock(return_value=(False, 0))
        self.assertFalse(_is_dirty(doc))
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd "c:\Users\Micael\Desktop\Auto Production\tools\exporter"
python -m pytest tests/test_solidworks_helpers.py::TestIsDirty -v
```

Expected: `ImportError` or `AttributeError: module 'solidworks' has no attribute '_is_dirty'`

---

### Task 2: Implement `_is_dirty()`

**Files:**
- Modify: `tools/exporter/solidworks.py` (add helper near `open_assembly`, around line 117)

- [ ] **Step 3: Add `_is_dirty()` just before `open_assembly`**

Insert in `solidworks.py` directly before `def open_assembly(`:

```python
def _is_dirty(doc) -> bool:
    """Return True if the document has unsaved changes (GetSaveFlag == True)."""
    ref = doc.GetSaveFlag
    result = ref() if callable(ref) else ref
    if isinstance(result, tuple):
        result = result[0]
    return bool(result)
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd "c:\Users\Micael\Desktop\Auto Production\tools\exporter"
python -m pytest tests/test_solidworks_helpers.py::TestIsDirty -v
```

Expected: `6 passed`

- [ ] **Step 5: Run full test suite — expect no regressions**

```bash
cd "c:\Users\Micael\Desktop\Auto Production\tools\exporter"
python -m pytest tests/ -v
```

Expected: all previously passing tests still pass.

- [ ] **Step 6: Commit**

```bash
cd "c:\Users\Micael\Desktop\Auto Production"
git add tools/exporter/solidworks.py tools/exporter/tests/test_solidworks_helpers.py
git commit -m "feat: add _is_dirty() helper for SW document modified-flag check"
```

---

## Chunk 2: `open_assembly_resolved()` + caller update

### Task 3: Write failing tests for `open_assembly_resolved()`

**Files:**
- Modify: `tools/exporter/tests/test_solidworks_helpers.py`

- [ ] **Step 1: Add failing tests**

Add at the bottom of `test_solidworks_helpers.py`:

```python
# ---------------------------------------------------------------------------
# open_assembly_resolved
# ---------------------------------------------------------------------------

def _make_sw_app(active_doc=None, open_doc_by_name=None, open_doc6_return=None):
    """Helper: build a mock ISldWorks object."""
    sw = MagicMock()
    sw.ActiveDoc = active_doc
    sw.GetOpenDocumentByName = MagicMock(return_value=open_doc_by_name)
    # OpenDoc6 returns a tuple (doc, errors, warnings) in early binding
    mock_doc = open_doc6_return or MagicMock()
    sw.OpenDoc6 = MagicMock(return_value=(mock_doc, 0, 0))
    return sw, mock_doc


class TestOpenAssemblyResolved(unittest.TestCase):

    def test_opens_with_resolved_readonly_options(self):
        """OpenDoc6 must be called with options=66 (ReadOnly=2 | OverrideLoadLightweight=64)."""
        from solidworks import open_assembly_resolved
        sw, doc = _make_sw_app()
        sw.ActiveDoc = None
        result_doc, opened_by_us = open_assembly_resolved(sw, r"C:\asm\test.SLDASM")
        call_args = sw.OpenDoc6.call_args
        options_arg = call_args[0][2]  # third positional arg
        self.assertEqual(options_arg, 66)
        self.assertTrue(opened_by_us)

    def test_closes_active_doc_if_already_open_and_clean(self):
        """If assembly is the active doc and clean, it is closed with the normalised path."""
        import os
        from solidworks import open_assembly_resolved
        active = MagicMock()
        active.GetPathName = MagicMock(return_value=r"C:\asm\test.SLDASM")
        active.GetSaveFlag = MagicMock(return_value=False)  # clean
        sw, _ = _make_sw_app(active_doc=active)
        open_assembly_resolved(sw, r"C:\asm\test.SLDASM")
        sw.CloseDoc.assert_called_once_with(os.path.normpath(os.path.abspath(r"C:\asm\test.SLDASM")))

    def test_raises_if_active_doc_is_dirty(self):
        """If assembly is the active doc and dirty, raise RuntimeError."""
        from solidworks import open_assembly_resolved
        active = MagicMock()
        active.GetPathName = MagicMock(return_value=r"C:\asm\test.SLDASM")
        active.GetSaveFlag = MagicMock(return_value=True)  # dirty
        sw, _ = _make_sw_app(active_doc=active)
        with self.assertRaises(RuntimeError):
            open_assembly_resolved(sw, r"C:\asm\test.SLDASM")

    def test_closes_background_doc_if_already_open_and_clean(self):
        """If assembly is open in background (not active), it is still closed."""
        import os
        from solidworks import open_assembly_resolved
        bg_doc = MagicMock()
        bg_doc.GetSaveFlag = MagicMock(return_value=False)  # clean
        sw, _ = _make_sw_app(open_doc_by_name=bg_doc)
        sw.ActiveDoc = None  # not the active doc
        open_assembly_resolved(sw, r"C:\asm\test.SLDASM")
        sw.CloseDoc.assert_called_once_with(os.path.normpath(os.path.abspath(r"C:\asm\test.SLDASM")))

    def test_raises_if_background_doc_is_dirty(self):
        """If assembly is open in background and dirty, raise RuntimeError."""
        from solidworks import open_assembly_resolved
        bg_doc = MagicMock()
        bg_doc.GetSaveFlag = MagicMock(return_value=True)  # dirty
        sw, _ = _make_sw_app(open_doc_by_name=bg_doc)
        sw.ActiveDoc = None
        with self.assertRaises(RuntimeError):
            open_assembly_resolved(sw, r"C:\asm\test.SLDASM")

    def test_raises_if_open_doc6_returns_none(self):
        """If OpenDoc6 returns None, raise RuntimeError."""
        from solidworks import open_assembly_resolved
        sw = MagicMock()
        sw.ActiveDoc = None
        sw.GetOpenDocumentByName = MagicMock(return_value=None)
        sw.OpenDoc6 = MagicMock(return_value=(None, 0, 0))
        with self.assertRaises(RuntimeError):
            open_assembly_resolved(sw, r"C:\asm\test.SLDASM")
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd "c:\Users\Micael\Desktop\Auto Production\tools\exporter"
python -m pytest tests/test_solidworks_helpers.py::TestOpenAssemblyResolved -v
```

Expected: `ImportError` or `AttributeError: module 'solidworks' has no attribute 'open_assembly_resolved'`

---

### Task 4: Implement `open_assembly_resolved()`

**Files:**
- Modify: `tools/exporter/solidworks.py` (add after `open_assembly`, around line 142)

- [ ] **Step 3: Add `open_assembly_resolved()` after `open_assembly`**

Insert in `solidworks.py` directly after `def open_assembly(...)` (after line 141):

```python
def open_assembly_resolved(sw_app, sldasm_path: str):
    """
    Open the assembly in read-only resolved (non-lightweight) mode.
    Closes any already-open instance first (dirty check — raises if unsaved changes).
    Always returns (doc, True) — caller is responsible for CloseDoc.

    OpenDoc6 options = 66:
      swOpenDocOptions_ReadOnly (2) — no save prompt on close
      swOpenDocOptions_OverrideDefaultLoadLightweight (64) — force resolved, ignore SW setting
      swOpenDocOptions_Silent (1) NOT set — ensures full component tree is loaded
    """
    RESOLVED_READONLY = 2 | 64  # swOpenDocOptions_ReadOnly | swOpenDocOptions_OverrideDefaultLoadLightweight

    sldasm_path = os.path.normpath(os.path.abspath(sldasm_path))

    # Close any already-open instance (active or background).
    # Must close before OpenDoc6 — otherwise SW returns the existing lightweight doc.
    for _candidate in _find_open_doc(sw_app, sldasm_path):
        if _is_dirty(_candidate):
            raise RuntimeError(
                "O assembly tem alterações não guardadas. "
                "Guarda ou descarta as alterações antes de continuar."
            )
        try:
            sw_app.CloseDoc(sldasm_path)
        except Exception as e:
            raise RuntimeError(
                f"Não foi possível fechar o assembly aberto: {e}"
            ) from e
        break  # only one instance expected

    # Open in resolved + read-only mode.
    result = sw_app.OpenDoc6(sldasm_path, 2, RESOLVED_READONLY, "", 0, 0)
    # Early binding returns tuple (IModelDoc2, errors, warnings)
    doc = result[0] if isinstance(result, tuple) else result
    if doc is None:
        raise RuntimeError(f"Não foi possível abrir o assembly: {sldasm_path}")
    return doc, True


def _find_open_doc(sw_app, norm_path: str):
    """
    Yield the IModelDoc2 for norm_path if it is currently open in SW.
    Checks active doc first, then GetOpenDocumentByName.
    Yields at most one result.
    """
    # Tier 1: active document
    try:
        active = sw_app.ActiveDoc
        if active is not None:
            active_path = os.path.normpath(active.GetPathName())
            if active_path.lower() == norm_path.lower():
                yield active
                return
    except Exception:
        pass

    # Tier 2: open but not active
    try:
        existing = sw_app.GetOpenDocumentByName(norm_path)
        if existing is not None:
            yield existing
    except Exception:
        pass
```

- [ ] **Step 4: Run new tests — expect PASS**

```bash
cd "c:\Users\Micael\Desktop\Auto Production\tools\exporter"
python -m pytest tests/test_solidworks_helpers.py::TestOpenAssemblyResolved -v
```

Expected: `6 passed`

- [ ] **Step 5: Run full test suite — expect no regressions**

```bash
cd "c:\Users\Micael\Desktop\Auto Production\tools\exporter"
python -m pytest tests/ -v
```

Expected: all previously passing tests still pass.

- [ ] **Step 6: Commit**

```bash
cd "c:\Users\Micael\Desktop\Auto Production"
git add tools/exporter/solidworks.py tools/exporter/tests/test_solidworks_helpers.py
git commit -m "feat: add open_assembly_resolved() — opens SW assembly in resolved+read-only mode"
```

---

### Task 5: Update `listas_module.py` to use `open_assembly_resolved`

**Files:**
- Modify: `tools/exporter/modules/listas_module.py` (line ~193-197)

- [ ] **Step 1: Replace import and call site**

In `listas_module.py`, find the import line:
```python
from solidworks import connect_to_solidworks, open_assembly
```

Change to:
```python
from solidworks import connect_to_solidworks, open_assembly_resolved
```

Then find:
```python
asm_doc, asm_opened_by_us = open_assembly(sw, asm_path)
```

Change to:
```python
asm_doc, asm_opened_by_us = open_assembly_resolved(sw, asm_path)
```

- [ ] **Step 2: Run full test suite — expect no regressions**

```bash
cd "c:\Users\Micael\Desktop\Auto Production\tools\exporter"
python -m pytest tests/ -v
```

Expected: all tests still pass.

- [ ] **Step 3: Commit**

```bash
cd "c:\Users\Micael\Desktop\Auto Production"
git add tools/exporter/modules/listas_module.py
git commit -m "feat: listas_module uses open_assembly_resolved to fix lightweight BOM bug"
```

---

### Task 6: Integration test (requires SolidWorks running)

**No SolidWorks needed for this step's test suite — this is a manual verification.**

- [ ] **Step 1: Close the assembly in SW (if open)**

Ensure `15024 - Pack and Go conj 100` assembly is closed in SolidWorks.

- [ ] **Step 2: Run Gerar Listas from the GUI**

Launch: `python tools/exporter/main.py`
Select the assembly, run "Gerar Listas Selecionadas".

- [ ] **Step 3: Verify result**

Expected output:
```
Produção: 88 | Mecânico: XX | Elétrico: XX | Pneumático: XX | Avisos: <much lower than 1777>
```

- [ ] **Step 4: Test with assembly already open in Lightweight**

Open the assembly in SW in Lightweight mode (default). Run Gerar Listas again.
Expected: same result — `Produção: 88` (tool closes and reopens in resolved mode).

- [ ] **Step 5: Remove `_dbg=True` from `_bom_traverse` after confirming results**

In `solidworks.py`, find:
```python
_bom_traverse(child, bom_flat, warnings, _dbg=True)
```
Change to:
```python
_bom_traverse(child, bom_flat, warnings)
```

- [ ] **Step 6: Final commit**

```bash
cd "c:\Users\Micael\Desktop\Auto Production"
git add tools/exporter/solidworks.py
git commit -m "chore: remove BOM debug logging (_dbg=True) after fix validated"
```
