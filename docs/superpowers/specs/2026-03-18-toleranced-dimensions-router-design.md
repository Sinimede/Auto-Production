# Design Spec: Toleranced Dimension Reduction for Router STEP Export

**Date:** 2026-03-18
**Status:** Approved

---

## Context

Router parts are exported to STEP with pre-modifications because the router is a low-precision machine. Dimensions that require tight tolerances are machined undersized on the router and then finished to the correct size on a CNC (or other precise machine).

This already exists for dowel holes (HoleWzd features): diameters are reduced by 1mm before export. The goal of this feature is to generalise that concept: any sketch dimension that carries a tolerance annotation (any tolerance type) should also be reduced before export.

---

## Problem

Sketch dimensions with tolerances (H7, ±0.01, bilateral limits, etc.) indicate precision requirements that the router cannot meet. Currently, only dowel hole diameters are handled. All other toleranced dimensions (extrude depths, pocket widths, revolve radii, etc.) are exported at nominal value, which may be too large or too small for the CNC finish pass.

---

## Solution

In `_export_router_part()`, after the existing dowel hole modification, scan all display dimensions of the tmp part for any dimension that has a non-NONE tolerance. For each such dimension:

- **Linear/diametral:** reduce by **1 mm** (0.001 m in SI)
- **Angular:** reduce by **1°** (converted to radians internally)

Skip driven (reference) dimensions — they are controlled by geometry and cannot be set.

---

## Why Not Double-Modify Dowel Holes

The existing `modify_dowel_diameter()` operates on `IWizardHoleFeatureData2.Diameter` — a wizard parameter, not a sketch dimension. `GetDisplayDimensions()` does not return wizard parameters as `IDimension` objects. These two mechanisms are orthogonal and cannot interfere with each other.

In the future, if dowel holes are redefined as Cut-Extrude sketches with Ø H7 dimensions, the new code would cover them and the old dowel code would become obsolete. That decision is deferred.

---

## API Approach

Use `IModelDoc2.GetDisplayDimensions()` to retrieve all display dimensions from the part in a single call. This is simpler and faster than traversing the feature tree (no sub-feature iteration needed). For a tmp part file (not a drawing), this returns sketch dimensions only — DimXpert/PMI annotations are a separate subsystem.

### Key API objects

| Object | Purpose |
|---|---|
| `IModelDoc2.GetDisplayDimensions()` | Returns all display dimensions in the model |
| `IDisplayDimension.GetDimension2(0)` | Returns the underlying `IDimension` |
| `IDimension.Tolerance.Type` | `swTolType_e` integer — 0 = no tolerance |
| `IDimension.DrivenState` | Skip if driven (reference dimension) |
| `IDimension.GetType` | Distinguish angular from linear/diametral |
| `IDimension.SystemValue` | Current value in SI (metres or radians) |
| `IDimension.SetSystemValue3(val, 0, "")` | Set value in active configuration |

### SW 2024 quirks to handle

- `GetDisplayDimensions()` may return a tuple — convert to list
- `IDimension.Tolerance` may be `None` if the dimension object is malformed — guard with try/except
- `GetType` may be a callable property — use the standard callable-guard pattern
- `SetSystemValue3` returns a bool — if `False`, log warning and continue (do not abort export)
- `DrivenState` returns an int — value `1` means driven/reference

---

## New Functions in `solidworks.py`

### `DimensionInfo` namedtuple

```python
DimensionInfo = namedtuple('DimensionInfo', [
    'dim_obj',          # IDimension object
    'current_value',    # float, SI units (metres or radians)
    'is_angular',       # bool
])
```

### `get_toleranced_dimensions(part_doc) -> list[DimensionInfo]`

1. Call `part_doc.GetDisplayDimensions()` — handle tuple result
2. For each display dimension:
   a. `GetDimension2(0)` → `IDimension`; skip if None
   b. Check `DrivenState` — skip if driven
   c. Read `Tolerance.Type`; skip if `== 0` (swTolNONE)
   d. Determine `is_angular` via `GetType`
   e. Read `SystemValue`
   f. Append `DimensionInfo` to result
3. Return list (empty if none found)

### `modify_toleranced_dimension(dim_info: DimensionInfo) -> bool`

1. Compute `new_value`:
   - Linear: `current_value - 0.001`
   - Angular: `current_value - math.radians(1.0)`
2. Call `dim_info.dim_obj.SetSystemValue3(new_value, 0, "")` → returns bool
3. Return bool (caller logs warning on False)

---

## Integration in `_export_router_part()` (`step_module.py`)

```
copy_part_to_tmp()
    ↓
_open_doc(silent=True)
    ↓
[EXISTING] get_dowel_holes() + modify_dowel_diameter() × N
    ↓
[NEW] get_toleranced_dimensions() → dims
    ↓
[NEW] modify_toleranced_dimension(d) × N  (log warnings on False)
    ↓
EditRebuild3()
    ↓
export_part_to_step(doc=tmp_doc)
    ↓
CloseDoc + delete tmp file [finally]
```

The `EditRebuild3()` call already present covers both the dowel modifications and the new dimension modifications — no additional rebuild needed.

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| `GetDimension2` returns None | Skip, continue |
| `Tolerance` is None | Skip, continue |
| `SetSystemValue3` returns False | Log warning with dimension name, continue |
| `GetDisplayDimensions` returns None/empty | Return empty list, no modifications |
| Exception anywhere in a dimension | Swallow, log, continue — never abort export |

Failures in individual dimensions do not cancel the export. The router operator can review the log.

---

## Tests

New unit tests in `test_solidworks_helpers.py` using existing mock patterns:

| Test | Validates |
|---|---|
| `test_get_toleranced_dimensions_empty_when_no_dims` | Returns `[]` when model has no display dimensions |
| `test_get_toleranced_dimensions_empty_when_no_tolerance` | Returns `[]` when all dims have `swTolNONE` |
| `test_get_toleranced_dimensions_skips_driven` | Excludes driven/reference dimensions |
| `test_get_toleranced_dimensions_detects_symmetric` | Detects `swTolSYMMETRIC` (Type=4) |
| `test_get_toleranced_dimensions_detects_fit` | Detects `swTolFIT` (Type=7) |
| `test_get_toleranced_dimensions_detects_all_types` | Types 1–9 all trigger detection |
| `test_get_toleranced_dimensions_angular_flag` | `is_angular=True` for angular dimensions |
| `test_modify_toleranced_dimension_linear_reduces_1mm` | `new = current - 0.001` |
| `test_modify_toleranced_dimension_angular_reduces_1deg` | `new = current - radians(1)` |
| `test_modify_toleranced_dimension_returns_false_on_failure` | Returns `False` when `SetSystemValue3` returns `False` |

---

## Files Changed

| File | Change |
|---|---|
| `tools/exporter/solidworks.py` | Add `DimensionInfo` namedtuple, `get_toleranced_dimensions()`, `modify_toleranced_dimension()` |
| `tools/exporter/modules/step_module.py` | Call new functions in `_export_router_part()`, log results |
| `tools/exporter/tests/test_solidworks_helpers.py` | Add 10 new unit tests |

No new files. No changes to workflows (no new failure modes that require SOP updates).
