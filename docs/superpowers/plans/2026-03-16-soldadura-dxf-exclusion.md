# Soldadura DXF Exclusion Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure parts with `SOLDADURA` in `Corte_Fabrico` are never exported as DXF, even if they also contain `LASER`.

**Architecture:** Single-line logic change in `is_laser_part` (already applied). This plan adds test coverage to lock the behavior in.

**Tech Stack:** Python, unittest, MagicMock

**Spec:** `docs/superpowers/specs/2026-03-16-soldadura-dxf-exclusion-design.md`

---

## Chunk 1: Tests for is_laser_part soldadura exclusion

**Files:**
- Modify: `tools/exporter/solidworks.py` — `is_laser_part` function (already done)
- Modify: `tools/exporter/tests/test_solidworks_helpers.py` — add `TestIsLaserPart` class at end of file (before `if __name__ == "__main__":`)

### Task 1: Add TestIsLaserPart test class

- [ ] **Step 1: Add the test class to test_solidworks_helpers.py**

Insert before the `if __name__ == "__main__":` line at the bottom of the file:

```python
# ---------------------------------------------------------------------------
# is_laser_part
# ---------------------------------------------------------------------------

class TestIsLaserPart(unittest.TestCase):

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

    def test_laser_only_returns_true(self):
        from solidworks import is_laser_part
        self.assertTrue(is_laser_part(self._make_part("LASER")))

    def test_laser_quinagem_returns_true(self):
        from solidworks import is_laser_part
        self.assertTrue(is_laser_part(self._make_part("LASER+QUINAGEM")))

    def test_laser_soldadura_returns_false(self):
        from solidworks import is_laser_part
        self.assertFalse(is_laser_part(self._make_part("LASER+SOLDADURA")))

    def test_laser_quinagem_soldadura_returns_false(self):
        from solidworks import is_laser_part
        self.assertFalse(is_laser_part(self._make_part("LASER+QUINAGEM+SOLDADURA")))

    def test_soldadura_only_returns_false(self):
        from solidworks import is_laser_part
        self.assertFalse(is_laser_part(self._make_part("SOLDADURA")))

    def test_empty_returns_false(self):
        from solidworks import is_laser_part
        self.assertFalse(is_laser_part(self._make_part("")))

    def test_none_model_returns_false(self):
        from solidworks import is_laser_part
        comp = MagicMock()
        comp.GetModelDoc2.return_value = None
        self.assertFalse(is_laser_part(comp))
```

- [ ] **Step 2: Run the new tests**

```bash
cd "c:/Users/Micael/Desktop/Auto Production/tools/exporter"
python -m pytest tests/test_solidworks_helpers.py::TestIsLaserPart -v
```

Expected: 7 tests PASS

- [ ] **Step 3: Run the full test suite to check for regressions**

```bash
cd "c:/Users/Micael/Desktop/Auto Production/tools/exporter"
python -m pytest tests/ -v
```

Expected: all previously passing tests still pass (149+7 total)
