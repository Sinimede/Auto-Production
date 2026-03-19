# Design: Exclude Soldadura Parts from DXF Export

**Date:** 2026-03-16
**Status:** Approved

---

## Problem

Parts with `SOLDADURA` in their `Corte_Fabrico` property (e.g., `LASER+QUINAGEM+SOLDADURA`) were incorrectly included in DXF Laser exports because `is_laser_part` only checked for the presence of `"laser"` without checking for `"soldadura"`. Welded parts are always multi-body assemblies and cannot be exported as DXF.

---

## Scope

- Affects: DXF Laser panel only
- DXF Proteções panel: not affected (proteções parts never have soldadura)
- STEP export: not affected

---

## Change

**File:** `tools/exporter/solidworks.py`
**Function:** `is_laser_part` (line ~269)

```python
# Before
return "laser" in str(val).strip().lower()

# After
normalized = str(val).strip().lower()
return "laser" in normalized and "soldadura" not in normalized
```

---

## Behavior

| Corte_Fabrico              | Before       | After        |
|----------------------------|--------------|--------------|
| `LASER`                    | ✅ exported  | ✅ exported  |
| `LASER+QUINAGEM`           | ✅ exported  | ✅ exported  |
| `LASER+QUINAGEM+SOLDADURA` | ✅ exported (wrong) | ❌ excluded (correct) |
| `SOLDADURA`                | ❌ excluded  | ❌ excluded  |

---

## Tests

Add to existing `is_laser_part` test cases:
- `"LASER+SOLDADURA"` → `False`
- `"LASER+QUINAGEM+SOLDADURA"` → `False`
- `"LASER+QUINAGEM"` → `True` (regression)
