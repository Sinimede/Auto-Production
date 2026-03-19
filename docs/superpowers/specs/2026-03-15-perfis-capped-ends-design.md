# Design: Perfis de Alumínio — Deteção Automática de Pontas Tapadas (D17)

**Date:** 2026-03-15
**Status:** Approved for implementation
**Feature area:** Feature 6 — Listas / Perfis de Alumínio

---

## Problem

When generating the Perfis de Alumínio Excel table, the team manually inspects the 3D model
to identify which profiles have their ends covered ("capped") by other profiles. For each
capped end, "D17" must be appended to the profile description (1 end → `D17`, 2 ends →
`D17/D17`). This is required so the supplier knows to drill holes for the mechanical
connectors that join profiles together.

---

## Constraints and Context

- All profiles in scope are weldment structural members inside a single `.SLDPRT` file.
- Capping is determined by physical 3D geometry, not sketch topology. Multiple bodies can be
  generated from the same sketch segment (offset instances), and each instance may have a
  different capping state.
- When instances of the same cut list group have different capping states, they must become
  **separate rows** in the output table (each with correct qty count).
- The D17 suffix is always the string `"D17"` regardless of connector type.
- Implementation must follow SW 2024 COM conventions documented in `docs/project-guide.md`.
- Must not mark parts as modified in SolidWorks (no geometry writes).

---

## Approach: Sketch Direction + Bounding Box Center + ContainsPoint

Pure sketch topology cannot distinguish instances generated from the same sketch segment.
Working at the individual body (`IBody2`) level is required. Finding the long axis via
the inertia tensor would require `IBody2.GetMassProperties2` whose return format is not
verified for SW 2024. Instead, the **long axis direction is derived from the 3D sketch
segment** that the body was created from; the **body center** is the bounding box midpoint
(accurate for symmetric cross-sections); and the **endpoint positions** follow from center
± half-length × axis.

### Step 1 — Get all solid bodies

```python
bodies_raw = part_doc.GetBodies2(0, False)
# 0 = swSolidBody enum value; False = TopLevelOnly (False = include all bodies)
# SW 2024: result may be a tuple or dispatch array — unwrap safely:
bodies_raw = bodies_raw if bodies_raw is not None else []
if isinstance(bodies_raw, tuple):
    bodies_raw = list(bodies_raw)
# Wrap each body — raw results from GetBodies2 are untyped CDispatch objects.
# Calling ContainsPoint / GetBodyBox without wrapping raises DISP_E_MEMBERNOTFOUND.
bodies = [_wrap(b, "IBody2") for b in bodies_raw if b is not None]
```

### Step 2 — Get 3D sketch segment directions

Iterate features to find "3DSketch" feature(s). For each sketch feature:

```python
# IFeature.GetTypeName2() == "3DSketch"
sketch = feat.GetSpecificFeature2()   # returns ISketch; may need _wrap
segs = sketch.GetSketchSegments()     # returns array of ISketchSegment (dispatch)
for seg in (segs or []):
    line = _wrap(seg, "ISketchLine2")
    p1 = line.GetStartPoint2()        # ISketchPoint — .X .Y .Z in metres
    p2 = line.GetEndPoint2()
    # direction: normalize(p2 - p1)
```

If `GetSketchSegments` returns None or `GetSpecificFeature2` fails for the sketch feature,
skip sketch direction detection and fall back to bounding-box axis (Step 3b below).

### Step 3 — Match each body to a sketch segment (for axis direction)

For each body:
a. Get bounding box center: `IBody2.GetBodyBox()` → (x1,y1,z1,x2,y2,z2); center = midpoint.
b. Find the sketch segment whose **infinite-line distance** to the body center is minimum.
   This correctly handles multiple bodies generated from the same sketch segment (all match
   the same line, getting the same axis direction, but different bounding box centers).
c. Axis direction `d` = `normalize(seg.end − seg.start)`.

**Fallback axis (Step 3b):** if no sketch found, use the bounding box max-extent axis
(X, Y, or Z). This works correctly for all axis-aligned profiles. For diagonal profiles
this gives the wrong axis direction and capping detection will be incorrect — a warning
`"Eixo fallback: perfil não-ortogonal pode ter capping errado em <part_path>"` must be
emitted when this fallback activates.

### Step 4 — Compute endpoint test positions

```python
center = array([cx, cy, cz])           # bounding box midpoint (metres)
half = (length_mm / 1000.0) / 2.0     # half-length in metres
end1 = center + half * d               # one end face centroid (approx)
end2 = center - half * d               # other end face centroid (approx)

epsilon = 0.0001  # 0.1 mm — small enough to avoid false positives on thin cross-sections
test1 = end1 + epsilon * d             # test point slightly outside body at end1
test2 = end2 - epsilon * d             # test point slightly outside body at end2
```

Epsilon is 0.1 mm. Using 1 mm risks false positives for thin cross-section profiles
(e.g. 20×20 series with 1.8 mm slot wall thickness). 0.1 mm is a tunable constant.

### Step 5 — ContainsPoint check

```python
for other in bodies:
    if other is body:          # identity check — same COM object
        continue
    if other.ContainsPoint(*test1):
        end1_capped = True
    if other.ContainsPoint(*test2):
        end2_capped = True
```

**Risk:** `ContainsPoint` may not be in the SW 2024 early-binding stubs for `IBody2`.
If it raises `AttributeError` or `DISP_E_MEMBERNOTFOUND`, use late binding:

```python
import win32com.client
other_late = win32com.client.Dispatch(other._oleobj_)
result = other_late.ContainsPoint(x, y, z)
```

Wrap this in try/except and log a warning if neither works — treat as not capped.

### Step 6 — Associate bodies with cut list items

**Primary path:** for each `CutListFolder` feature, call `GetSpecificFeature2()`. If it
returns a non-None object, cast to `IWeldmentCutListItem2` and call `GetBodies()` to get
the `IBody2` list for that group.

**Fallback path (likely needed in SW 2024):** match each body to a cut list item by
computing the body's axis-projected extent (using the sketch direction from Step 3) and
comparing to the item's `LENGTH` property within `LENGTH_MATCH_TOLERANCE_MM = 1.0` mm.
The 1 mm tolerance accounts for SW reporting `LENGTH` as a rounded integer mm value while
the body's projected extent is a continuous float. If two items share the same length,
assign bodies round-robin across matching groups and log a warning with the part path and
the ambiguous length value. Note: round-robin order depends on `GetBodies2` return order,
which may vary across SW sessions — this is a known limitation of the fallback path.

`_detect_capped_ends(bodies, cut_list_items)` performs body-to-item association
**internally** (it does not assume association has already been done). The function
receives the full `raw_items` list so it can resolve lengths and run `ContainsPoint` in
a single pass. Steps 3–6 in `get_weldment_cut_list`'s internal flow are sequential at
the outer level, but Steps 3 and 5 both happen inside `_detect_capped_ends`.

The fallback key is the `IBody2` object itself (identity), not a list index, to remain
stable across any reordering.

### Step 7 — Expand cut list items by capping state

Within each cut list group, bodies are grouped by `capped_count` (0, 1, or 2):

```python
from collections import Counter
state_counts = Counter(capped_count_per_body)  # e.g. {2: 1, 1: 1, 0: 1}
```

Each unique state produces a separate `CutListItem`:

| capped_count | suffix | qty |
|---|---|---|
| 2 | ` D17/D17` | count of bodies with this state |
| 1 | ` D17` | count of bodies with this state |
| 0 | *(none)* | count of bodies with this state |

The suffix is appended to the `description` field of `CutListItem`. This means the
description field encodes both the profile type and the capping state. This is a deliberate
design choice: downstream consumers (`perfis_writer`) write the description directly to
Excel without parsing it, so the encoding is transparent. Any future code that needs the
base description without the suffix must strip ` D17` or ` D17/D17` from the end.

---

## Integration with `listas_module.py`

`_run_perfis` multiplies `item.qty × instance_count` (number of assembly instances of the
weldment part). With expanded rows, `item.qty` is "number of bodies with this capping state
within one part instance". Multiplying by `instance_count` is correct: each assembly
instance of the weldment part has the same internal geometry and the same capping pattern.
**No changes to `listas_module.py` are required.**

---

## Data Model

`CutListItem` namedtuple is unchanged: `(description, length_mm, qty)`.

The change is that `get_weldment_cut_list` may now return **more rows** than the number of
`CutListFolder` features — one row per unique `(description, length_mm, capped_count)`.

Example — 3 identical profiles with different capping:

| Before | After |
|--------|-------|
| `CutListItem("Perfil 40x40", 1000.0, 3)` | `CutListItem("Perfil 40x40 D17/D17", 1000.0, 1)` |
| | `CutListItem("Perfil 40x40 D17", 1000.0, 1)` |
| | `CutListItem("Perfil 40x40", 1000.0, 1)` |

---

## Components

### `solidworks.py` — new private helpers

**`_get_sketch_directions(part_doc) -> list[tuple[np.ndarray, np.ndarray]]`**
Returns list of `(start_m, end_m)` pairs (numpy arrays) for all 3DSketch line segments.
Returns `[]` if no 3DSketch feature is found or if `GetSketchSegments` fails.

**`_match_body_to_direction(body, sketch_lines) -> np.ndarray`**
Returns unit axis vector for a body by finding the sketch line with minimum distance
from body bounding box center to the infinite line. Falls back to max bounding box
extent axis if `sketch_lines` is empty.

**`_detect_capped_ends(bodies, cut_list_items) -> dict[IBody2, int]`**
Returns a dict mapping `IBody2 object → capped_count` (0, 1, or 2).
Uses body identity as dict key for stability. Internally calls `_match_body_to_direction`
and `ContainsPoint` (with late-binding fallback).

### `solidworks.py` — modified `get_weldment_cut_list`

After collecting raw `CutListItem` entries (current logic), runs body-level capping
detection and expands items by capping state. Returns the same `(items, warnings)`
signature — callers are unaffected.

New internal flow:
1. Read cut list features → raw items (current logic, unchanged)
2. Get all bodies: `GetBodies2(0, False)` + wrap
3. Get sketch directions: `_get_sketch_directions(part_doc)`
4. `_detect_capped_ends(bodies, raw_items)` → per-body capping map
5. Associate bodies to cut list groups (primary: `IWeldmentCutListItem2.GetBodies()`; fallback: length-match)
6. Group by `(description, length_mm, capped_count)` → expand rows
7. Return expanded items + accumulated warnings

### `perfis_writer.py` — no changes

### `listas_module.py` — no changes

---

## Error Handling

| Failure | Behaviour |
|---------|-----------|
| `GetBodies2` returns None / empty | Skip capping detection, use raw cut list items, add warning |
| No 3DSketch feature found | Use bounding box max-extent axis fallback; emit warning for non-axis-aligned profiles |
| `GetSpecificFeature2` returns None for sketch | Skip sketch direction for that feature, continue |
| `ContainsPoint` not in SW 2024 stubs | Retry via late binding; if still fails, treat as not capped, log warning |
| `GetSpecificFeature2` returns None for CutListFolder | Use length-match fallback |
| Length-match fallback ambiguous (two groups same length) | Round-robin assignment; log warning with part path and ambiguous length value |
| `GetBodyBox` fails for a body | Skip that body, log warning |

All warnings are returned in the existing `warnings: list[str]` return value.

---

## Testing

New unit tests in `tests/test_solidworks_helpers.py` (no SW running required).
All COM objects mocked with `MagicMock`; `ContainsPoint` stubbed via `side_effect`.

1. `test_match_body_to_direction_axis_aligned` — body centered on horizontal line → returns (1,0,0)
2. `test_match_body_to_direction_angled` — body centered on 45° line → returns (1/√2, 1/√2, 0)
3. `test_capped_ends_both` — both test-points inside another body → 2
4. `test_capped_ends_one` — one test-point inside, one outside → 1
5. `test_capped_ends_none` — no test-points inside any other body → 0
6. `test_contains_point_late_binding_fallback` — mock early-bound `ContainsPoint` to raise `AttributeError`; verify late-binding `Dispatch` path is called and returns correct capped count
7. `test_get_bodies2_returns_tuple` — mock `GetBodies2` returning a tuple instead of a list; verify all bodies are correctly unwrapped and processed
8. `test_expand_same_group_different_capping` — 3 bodies, states (2,1,0) → 3 separate rows
9. `test_expand_same_capping_aggregates` — 2 bodies same state → 1 row qty=2
10. `test_fallback_when_get_specific_feature_fails` — length-match fallback path
11. `test_no_bodies_returns_raw_items` — GetBodies2 returns None → raw items unchanged

---

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| `GetSpecificFeature2` returns None for CutListFolder in SW 2024 | Medium | Length-match fallback (primary in practice) |
| `ContainsPoint` not in SW 2024 early-binding stubs | Medium | Late-binding fallback via `_oleobj_` |
| `GetSketchSegments` fails or returns None in SW 2024 | Low | Bounding box axis fallback |
| Profiles at identical length cause ambiguous body↔item matching | Low | Round-robin assignment + warning with part path |
| Endpoint slightly off-center for non-symmetric cross-sections | Very low | Epsilon offset ensures test point exits body; ContainsPoint handles |
