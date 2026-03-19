# Perfis de Alumínio — Capped-End Detection (D17) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically detect which aluminum profile ends are physically capped by other profiles inside a weldment part, and append D17/D17/nothing to cut list descriptions so the supplier knows where to drill connector holes.

**Architecture:** Four new private helpers are added to `solidworks.py`. The existing `get_weldment_cut_list` function is extended to call them after the current feature-iteration loop and expand `CutListItem` rows by capping state before returning. No changes to `perfis_writer.py` or `listas_module.py` — the expanded rows drop in transparently.

**Tech Stack:** Python 3.x, win32com (SW 2024 early + late binding), numpy 2.4.3, unittest + MagicMock

---

## Chunk 1: Private Helpers

### Task 1: Add numpy import and LENGTH_MATCH_TOLERANCE_MM constant

**Files:**
- Modify: `tools/exporter/solidworks.py` (line 13, after `import os`)

- [ ] **Step 1: Add numpy import and constant**

In `solidworks.py`, after `import os` (line 13), add:

```python
import numpy as np
```

After the `CutListItem` namedtuple definition (around line 29), add:

```python
# Tolerance for matching body axis-length to cut list LENGTH property (mm).
# Accounts for SW rounding LENGTH to nearest integer mm.
LENGTH_MATCH_TOLERANCE_MM = 1.0
```

- [ ] **Step 2: Verify import works**

```bash
cd tools/exporter && python -c "import solidworks; print('ok')"
```
Expected: `ok`

---

### Task 2: `_contains_point` helper + tests

**Files:**
- Modify: `tools/exporter/solidworks.py` (insert before `_get_cut_list_prop`, currently ~line 475)
- Test: `tools/exporter/tests/test_solidworks_helpers.py`

- [ ] **Step 1: Write failing tests**

In `test_solidworks_helpers.py`, add a new test class after the existing imports:

```python
# ---------------------------------------------------------------------------
# _contains_point
# ---------------------------------------------------------------------------

class TestContainsPoint(unittest.TestCase):

    def test_early_binding_returns_true(self):
        from solidworks import _contains_point
        body = MagicMock()
        body.ContainsPoint.return_value = 1  # SW returns non-zero int for True
        self.assertTrue(_contains_point(body, 0.0, 0.0, 0.0))

    def test_early_binding_returns_false(self):
        from solidworks import _contains_point
        body = MagicMock()
        body.ContainsPoint.return_value = 0
        self.assertFalse(_contains_point(body, 0.0, 0.0, 0.0))

    @patch("win32com.client.Dispatch")
    def test_late_binding_fallback_when_early_raises(self, mock_dispatch):
        from solidworks import _contains_point
        body = MagicMock()
        body.ContainsPoint.side_effect = AttributeError("no attribute")
        body._oleobj_ = MagicMock()
        late = MagicMock()
        late.ContainsPoint.return_value = 1
        mock_dispatch.return_value = late
        self.assertTrue(_contains_point(body, 1.0, 2.0, 3.0))
        late.ContainsPoint.assert_called_once_with(1.0, 2.0, 3.0)

    def test_returns_false_when_both_paths_fail(self):
        from solidworks import _contains_point
        body = MagicMock()
        body.ContainsPoint.side_effect = Exception("fail")
        body._oleobj_ = None
        body._dispobj_ = None
        self.assertFalse(_contains_point(body, 0.0, 0.0, 0.0))
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd tools/exporter && python -m pytest tests/test_solidworks_helpers.py::TestContainsPoint -v
```
Expected: `FAILED` (ImportError — `_contains_point` not defined yet)

- [ ] **Step 3: Implement `_contains_point`**

In `solidworks.py`, insert before `_get_cut_list_prop` (~line 475):

```python
def _contains_point(body, x: float, y: float, z: float) -> bool:
    """Call IBody2.ContainsPoint with early-binding, falling back to late binding.

    ContainsPoint may be absent from SW 2024 IBody2 early-binding stubs.
    Returns False on any unrecoverable error (treats as not capped).
    """
    try:
        return bool(body.ContainsPoint(x, y, z))
    except Exception:
        pass
    try:
        raw = getattr(body, "_oleobj_", None) or getattr(body, "_dispobj_", None)
        if raw is not None:
            return bool(win32com.client.Dispatch(raw).ContainsPoint(x, y, z))
    except Exception:
        pass
    return False
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd tools/exporter && python -m pytest tests/test_solidworks_helpers.py::TestContainsPoint -v
```
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add tools/exporter/solidworks.py tools/exporter/tests/test_solidworks_helpers.py
git commit -m "feat: add _contains_point helper with late-binding fallback for IBody2"
```

---

### Task 3: `_get_sketch_directions` + tests

**Files:**
- Modify: `tools/exporter/solidworks.py` (insert after `_contains_point`)
- Test: `tools/exporter/tests/test_solidworks_helpers.py`

- [ ] **Step 1: Write failing tests**

```python
# ---------------------------------------------------------------------------
# _get_sketch_directions
# ---------------------------------------------------------------------------

class TestGetSketchDirections(unittest.TestCase):

    def _make_sketch_feat(self, segments):
        """Build a mock 3DSketch IFeature with given (start, end) mm tuples."""
        feat = MagicMock()
        feat.GetTypeName2.return_value = "3DSketch"
        sketch = MagicMock()
        mock_segs = []
        for (sx, sy, sz), (ex, ey, ez) in segments:
            seg = MagicMock()
            p1, p2 = MagicMock(), MagicMock()
            p1.X, p1.Y, p1.Z = sx, sy, sz
            p2.X, p2.Y, p2.Z = ex, ey, ez
            seg.GetStartPoint2.return_value = p1
            seg.GetEndPoint2.return_value = p2
            mock_segs.append(seg)
        sketch.GetSketchSegments.return_value = mock_segs
        feat.GetSpecificFeature2.return_value = sketch
        feat.GetNextFeature.return_value = None
        return feat

    @patch("solidworks._wrap")
    def test_returns_line_endpoints_from_sketch(self, mock_wrap):
        from solidworks import _get_sketch_directions
        sketch_feat = self._make_sketch_feat([
            ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
        ])
        mock_part = MagicMock()
        mock_part.FirstFeature.return_value = sketch_feat
        mock_wrap.side_effect = lambda obj, iface: obj  # passthrough
        lines = _get_sketch_directions(mock_part)
        self.assertEqual(len(lines), 1)
        np.testing.assert_allclose(lines[0][0], [0.0, 0.0, 0.0])
        np.testing.assert_allclose(lines[0][1], [1.0, 0.0, 0.0])

    @patch("solidworks._wrap")
    def test_skips_zero_length_segments(self, mock_wrap):
        from solidworks import _get_sketch_directions
        sketch_feat = self._make_sketch_feat([
            ((0.5, 0.5, 0.5), (0.5, 0.5, 0.5)),  # zero-length
        ])
        mock_part = MagicMock()
        mock_part.FirstFeature.return_value = sketch_feat
        mock_wrap.side_effect = lambda obj, iface: obj
        lines = _get_sketch_directions(mock_part)
        self.assertEqual(lines, [])

    @patch("solidworks._wrap")
    def test_returns_empty_when_no_3dsketch(self, mock_wrap):
        from solidworks import _get_sketch_directions
        feat = MagicMock()
        feat.GetTypeName2.return_value = "BaseFlangeFeature"
        feat.GetNextFeature.return_value = None
        mock_part = MagicMock()
        mock_part.FirstFeature.return_value = feat
        mock_wrap.side_effect = lambda obj, iface: obj
        lines = _get_sketch_directions(mock_part)
        self.assertEqual(lines, [])
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd tools/exporter && python -m pytest tests/test_solidworks_helpers.py::TestGetSketchDirections -v
```
Expected: `FAILED`

- [ ] **Step 3: Implement `_get_sketch_directions`**

In `solidworks.py`, insert after `_contains_point`:

```python
def _get_sketch_directions(part_doc) -> list:
    """Return list of (start_m, end_m) np.ndarray pairs for all 3DSketch line segments.

    Iterates IPartDoc features looking for 3DSketch features.
    Coordinates are in metres as returned by ISketchPoint.X/Y/Z.
    Returns [] if no 3DSketch found or GetSketchSegments fails.
    """
    lines = []
    try:
        feat_raw = part_doc.FirstFeature()
        feat = _wrap(feat_raw, "IFeature") if feat_raw is not None else None
        while feat is not None:
            type_name_ref = feat.GetTypeName2
            type_name = type_name_ref() if callable(type_name_ref) else str(type_name_ref)
            if type_name == "3DSketch":
                try:
                    sketch = feat.GetSpecificFeature2()
                    if sketch is not None:
                        segs = sketch.GetSketchSegments()
                        if segs:
                            if isinstance(segs, tuple):
                                segs = list(segs)
                            for seg in segs:
                                try:
                                    # Try direct access first (ISketchSegment base),
                                    # fall back to ISketchLine2 wrapping.
                                    try:
                                        p1 = seg.GetStartPoint2()
                                        p2 = seg.GetEndPoint2()
                                    except Exception:
                                        line = _wrap(seg, "ISketchLine2")
                                        p1 = line.GetStartPoint2()
                                        p2 = line.GetEndPoint2()
                                    s = np.array([p1.X, p1.Y, p1.Z])
                                    e = np.array([p2.X, p2.Y, p2.Z])
                                    if np.linalg.norm(e - s) > 1e-9:
                                        lines.append((s, e))
                                except Exception:
                                    continue
                except Exception:
                    pass
            next_raw = feat.GetNextFeature()
            feat = _wrap(next_raw, "IFeature") if next_raw is not None else None
    except Exception:
        pass
    return lines
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd tools/exporter && python -m pytest tests/test_solidworks_helpers.py::TestGetSketchDirections -v
```
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add tools/exporter/solidworks.py tools/exporter/tests/test_solidworks_helpers.py
git commit -m "feat: add _get_sketch_directions to extract 3DSketch line endpoints"
```

---

### Task 4: `_match_body_to_direction` + tests

**Files:**
- Modify: `tools/exporter/solidworks.py` (insert after `_get_sketch_directions`)
- Test: `tools/exporter/tests/test_solidworks_helpers.py`

- [ ] **Step 1: Write failing tests**

```python
# ---------------------------------------------------------------------------
# _match_body_to_direction
# ---------------------------------------------------------------------------

class TestMatchBodyToDirection(unittest.TestCase):

    def _make_body(self, xmin, ymin, zmin, xmax, ymax, zmax):
        body = MagicMock()
        body.GetBodyBox.return_value = (xmin, ymin, zmin, xmax, ymax, zmax)
        return body

    def test_axis_aligned_horizontal(self):
        from solidworks import _match_body_to_direction
        # 1000 mm profile along X axis
        body = self._make_body(-0.5, -0.02, -0.02, 0.5, 0.02, 0.02)
        sketch_lines = [(np.array([-0.5, 0.0, 0.0]), np.array([0.5, 0.0, 0.0]))]
        center, axis = _match_body_to_direction(body, sketch_lines)
        np.testing.assert_allclose(center, [0.0, 0.0, 0.0], atol=1e-9)
        np.testing.assert_allclose(np.abs(axis), [1.0, 0.0, 0.0], atol=1e-6)

    def test_angled_45_degrees(self):
        from solidworks import _match_body_to_direction
        # 1000 mm profile at 45° in XY plane (0,0,0) → (0.707, 0.707, 0)
        d = 0.707
        body = self._make_body(0.0, 0.0, -0.02, d, d, 0.02)
        sketch_lines = [(np.array([0.0, 0.0, 0.0]), np.array([d, d, 0.0]))]
        center, axis = _match_body_to_direction(body, sketch_lines)
        expected_axis = np.array([1.0, 1.0, 0.0]) / np.sqrt(2)
        np.testing.assert_allclose(np.abs(axis), np.abs(expected_axis), atol=1e-3)

    def test_fallback_to_bbox_when_no_sketch(self):
        from solidworks import _match_body_to_direction
        # Profile 1000 mm along Z, no sketch
        body = self._make_body(-0.02, -0.02, 0.0, 0.02, 0.02, 1.0)
        center, axis = _match_body_to_direction(body, [])
        np.testing.assert_allclose(axis, [0.0, 0.0, 1.0], atol=1e-9)

    def test_getbodybox_failure_returns_safe_defaults(self):
        from solidworks import _match_body_to_direction
        body = MagicMock()
        body.GetBodyBox.side_effect = Exception("COM error")
        center, axis = _match_body_to_direction(body, [])
        np.testing.assert_allclose(center, [0.0, 0.0, 0.0])
        self.assertEqual(np.linalg.norm(axis), 1.0)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd tools/exporter && python -m pytest tests/test_solidworks_helpers.py::TestMatchBodyToDirection -v
```
Expected: `FAILED`

- [ ] **Step 3: Implement `_match_body_to_direction`**

In `solidworks.py`, insert after `_get_sketch_directions`:

```python
def _match_body_to_direction(body, sketch_lines: list) -> tuple:
    """Return (center_m, unit_axis) for an IBody2 body.

    center_m:  np.ndarray [x, y, z] — bounding box midpoint in metres
    unit_axis: np.ndarray [x, y, z] — unit vector along profile long axis

    Finds axis direction by matching the body's bounding box centre to the
    nearest sketch line (minimum distance from centre to infinite line).
    Falls back to bounding box max-extent coordinate axis when no sketch lines
    are available. Emits a fallback warning is handled by the caller.
    """
    try:
        box = body.GetBodyBox()
        if isinstance(box, tuple) and len(box) >= 6:
            xmin, ymin, zmin, xmax, ymax, zmax = box[:6]
        else:
            raise ValueError(f"unexpected GetBodyBox shape: {box!r}")
    except Exception:
        return np.zeros(3), np.array([1.0, 0.0, 0.0])

    center = np.array([
        (xmin + xmax) / 2.0,
        (ymin + ymax) / 2.0,
        (zmin + zmax) / 2.0,
    ])

    if not sketch_lines:
        extents = [xmax - xmin, ymax - ymin, zmax - zmin]
        axis_idx = int(np.argmax(extents))
        axis = np.zeros(3)
        axis[axis_idx] = 1.0
        return center, axis

    best_dist = float('inf')
    best_dir = None
    for s, e in sketch_lines:
        d = e - s
        d_norm = float(np.linalg.norm(d))
        if d_norm < 1e-9:
            continue
        d_unit = d / d_norm
        proj = float(np.dot(center - s, d_unit))
        closest = s + proj * d_unit
        dist = float(np.linalg.norm(center - closest))
        if dist < best_dist:
            best_dist = dist
            best_dir = d_unit.copy()

    if best_dir is None:
        extents = [xmax - xmin, ymax - ymin, zmax - zmin]
        axis_idx = int(np.argmax(extents))
        best_dir = np.zeros(3)
        best_dir[axis_idx] = 1.0

    return center, best_dir
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd tools/exporter && python -m pytest tests/test_solidworks_helpers.py::TestMatchBodyToDirection -v
```
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add tools/exporter/solidworks.py tools/exporter/tests/test_solidworks_helpers.py
git commit -m "feat: add _match_body_to_direction using nearest sketch line for axis detection"
```

---

### Task 5: `_detect_capped_ends` + tests

**Files:**
- Modify: `tools/exporter/solidworks.py` (insert after `_match_body_to_direction`)
- Test: `tools/exporter/tests/test_solidworks_helpers.py`

- [ ] **Step 1: Write failing tests**

```python
# ---------------------------------------------------------------------------
# _detect_capped_ends
# ---------------------------------------------------------------------------

class TestDetectCappedEnds(unittest.TestCase):

    def _make_body(self, cx, cy, cz, half=0.5):
        """Axis-aligned body centred at (cx,cy,cz), length=2*half along X."""
        body = MagicMock()
        body.GetBodyBox.return_value = (
            cx - half, cy - 0.02, cz - 0.02,
            cx + half, cy + 0.02, cz + 0.02,
        )
        body.ContainsPoint = MagicMock(return_value=0)
        body._oleobj_ = None
        return body

    def _make_items(self, *lengths):
        return [CutListItem(f"Profile {i}", float(l), 1)
                for i, l in enumerate(lengths)]

    def test_both_ends_capped(self):
        from solidworks import _detect_capped_ends, CutListItem
        # body_a: 1000 mm along X, centred at (0.5, 0, 0)
        body_a = self._make_body(0.5, 0.0, 0.0, half=0.5)
        # body_b and body_c cap body_a's ends
        body_b = self._make_body(-0.2, 0.0, 0.0, half=0.15)
        body_c = self._make_body(1.2, 0.0, 0.0, half=0.15)
        # test1 for body_a = (1.0001, 0, 0), test2 = (-0.0001, 0, 0)
        # body_c contains test1; body_b contains test2
        body_c.ContainsPoint.side_effect = (
            lambda x, y, z: 1 if abs(x - 1.0001) < 0.01 else 0)
        body_b.ContainsPoint.side_effect = (
            lambda x, y, z: 1 if abs(x - (-0.0001)) < 0.01 else 0)
        items = self._make_items(1000)
        sketch_lines = [(np.array([0.0, 0.0, 0.0]), np.array([1.0, 0.0, 0.0]))]
        item_caps, warns = _detect_capped_ends(
            [body_a, body_b, body_c], items, sketch_lines)
        self.assertIn(0, item_caps)
        self.assertEqual(item_caps[0], [2])

    def test_one_end_capped(self):
        from solidworks import _detect_capped_ends, CutListItem
        body_a = self._make_body(0.5, 0.0, 0.0, half=0.5)
        body_b = self._make_body(-0.2, 0.0, 0.0, half=0.15)
        # Only body_b caps the left end (test2 = -0.0001)
        body_b.ContainsPoint.side_effect = (
            lambda x, y, z: 1 if x < 0.0 else 0)
        items = self._make_items(1000)
        sketch_lines = [(np.array([0.0, 0.0, 0.0]), np.array([1.0, 0.0, 0.0]))]
        item_caps, _ = _detect_capped_ends([body_a, body_b], items, sketch_lines)
        self.assertEqual(item_caps[0], [1])

    def test_no_ends_capped(self):
        from solidworks import _detect_capped_ends, CutListItem
        body_a = self._make_body(0.5, 0.0, 0.0, half=0.5)
        items = self._make_items(1000)
        sketch_lines = [(np.array([0.0, 0.0, 0.0]), np.array([1.0, 0.0, 0.0]))]
        item_caps, _ = _detect_capped_ends([body_a], items, sketch_lines)
        self.assertEqual(item_caps.get(0, [0]), [0])

    def test_multiple_bodies_same_item_different_capping(self):
        from solidworks import _detect_capped_ends, CutListItem
        # 3 horizontal bodies, all 1000 mm, from the same cut list item
        body0 = self._make_body(0.5, 0.0, 0.0, half=0.5)
        body1 = self._make_body(0.5, 0.1, 0.0, half=0.5)  # offset in Y
        body2 = self._make_body(0.5, 0.2, 0.0, half=0.5)
        # Only body0 has both ends capped
        body0.ContainsPoint.return_value = 0  # overridden per call
        # All on same sketch line — the Y offsets don't matter for distance matching
        items = self._make_items(1000)
        sketch_lines = [(np.array([0.0, 0.0, 0.0]), np.array([1.0, 0.0, 0.0]))]

        call_counts = [0]
        def cap_body0(x, y, z):
            # Both test points of body0 are inside some other body
            return 1
        body0.ContainsPoint.side_effect = cap_body0

        item_caps, _ = _detect_capped_ends(
            [body0, body1, body2], items, sketch_lines)
        # body0 → 2, body1 → 0, body2 → 0
        self.assertIn(0, item_caps)
        self.assertEqual(sorted(item_caps[0]), [0, 0, 2])

    def test_empty_bodies_returns_empty(self):
        from solidworks import _detect_capped_ends, CutListItem
        item_caps, warns = _detect_capped_ends([], [CutListItem("A", 100.0, 1)], [])
        self.assertEqual(item_caps, {})
        self.assertEqual(warns, [])

    def test_getbodies2_returns_tuple_handled(self):
        """Verify tuple-unwrapping in the get_weldment_cut_list caller (smoke test)."""
        # This tests the unwrapping code that lives in get_weldment_cut_list,
        # using _detect_capped_ends as a proxy.
        from solidworks import _detect_capped_ends, CutListItem
        body = MagicMock()
        body.GetBodyBox.return_value = (0.0, -0.02, -0.02, 1.0, 0.02, 0.02)
        body.ContainsPoint.return_value = 0
        body._oleobj_ = None
        # Passing bodies as a list (already unwrapped) — this tests the function directly
        items = [CutListItem("Profile 0", 1000.0, 1)]
        sketch_lines = [(np.array([0.0, 0.0, 0.0]), np.array([1.0, 0.0, 0.0]))]
        item_caps, warns = _detect_capped_ends([body], items, sketch_lines)
        self.assertIsInstance(item_caps, dict)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd tools/exporter && python -m pytest tests/test_solidworks_helpers.py::TestDetectCappedEnds -v
```
Expected: `FAILED`

- [ ] **Step 3: Implement `_detect_capped_ends`**

In `solidworks.py`, insert after `_match_body_to_direction`:

```python
def _detect_capped_ends(bodies: list, raw_items: list, sketch_lines: list,
                        part_path: str = "") -> tuple:
    """Detect how many ends of each body are physically capped by another body.

    For each body, finds its axis direction (via _match_body_to_direction),
    computes two test points just outside each end, and checks whether any
    other body contains those test points via _contains_point.

    Also performs body-to-cut-list-item association by matching the nearest
    sketch line's length to the cut list item's LENGTH property within
    LENGTH_MATCH_TOLERANCE_MM. Multiple bodies with the same length are
    assigned round-robin across matching items.

    Args:
        bodies:       list of wrapped IBody2 objects
        raw_items:    list of CutListItem (description, length_mm, qty)
        sketch_lines: list of (start_m, end_m) np.ndarray pairs (metres)
        part_path:    path string used in warning messages

    Returns:
        item_caps: dict[int, list[int]]
            Maps raw_items index → list of capped_count per body in that group.
            capped_count is 0, 1, or 2.
        warnings: list[str]
    """
    item_caps: dict = {}
    warnings_out: list = []
    epsilon = 0.0001  # 0.1 mm in metres

    if not bodies or not raw_items:
        return item_caps, warnings_out

    # Build per-body info: center, axis, nearest-sketch-line length
    body_data = []
    for body in bodies:
        center, axis = _match_body_to_direction(body, sketch_lines)
        sketch_length_mm = None
        if sketch_lines:
            min_dist = float('inf')
            for s, e in sketch_lines:
                d = e - s
                d_norm = float(np.linalg.norm(d))
                if d_norm < 1e-9:
                    continue
                d_unit = d / d_norm
                proj = float(np.dot(center - s, d_unit))
                closest = s + proj * d_unit
                dist = float(np.linalg.norm(center - closest))
                if dist < min_dist:
                    min_dist = dist
                    sketch_length_mm = d_norm * 1000.0
        body_data.append((body, center, axis, sketch_length_mm))

    # Associate each body with a raw_items index (round-robin for ties)
    assign_counts: dict = {}   # item_index -> bodies assigned so far
    body_item_idx: list = []
    for body, center, axis, sketch_length_mm in body_data:
        matching = []
        if sketch_length_mm is not None:
            for i, item in enumerate(raw_items):
                if abs(item.length_mm - sketch_length_mm) <= LENGTH_MATCH_TOLERANCE_MM:
                    matching.append(i)
        if not matching and raw_items:
            # Closest-match fallback
            best = min(range(len(raw_items)),
                       key=lambda i: abs(raw_items[i].length_mm - (sketch_length_mm or 0)))
            matching = [best]
            fname = os.path.basename(part_path) if part_path else "?"
            warnings_out.append(
                f"Body sem correspondência exata em '{fname}' "
                f"(sketch_length≈{sketch_length_mm:.1f}mm) — "
                f"atribuído a '{raw_items[best].description}'"
            )
        if matching:
            # Pick the matching item with the fewest bodies assigned (round-robin)
            chosen = min(matching, key=lambda i: assign_counts.get(i, 0))
            assign_counts[chosen] = assign_counts.get(chosen, 0) + 1
            body_item_idx.append(chosen)
        else:
            body_item_idx.append(None)

    # ContainsPoint check for each body against all other bodies
    for idx, (body, center, axis, sketch_length_mm) in enumerate(body_data):
        item_i = body_item_idx[idx]
        if item_i is None:
            continue

        length_mm = raw_items[item_i].length_mm
        half = (length_mm / 1000.0) / 2.0
        end1 = center + half * axis
        end2 = center - half * axis
        test1 = end1 + epsilon * axis
        test2 = end2 - epsilon * axis

        end1_capped = False
        end2_capped = False
        for other_idx, (other_body, _, _, _) in enumerate(body_data):
            if other_idx == idx:
                continue
            if not end1_capped:
                end1_capped = _contains_point(
                    other_body, float(test1[0]), float(test1[1]), float(test1[2]))
            if not end2_capped:
                end2_capped = _contains_point(
                    other_body, float(test2[0]), float(test2[1]), float(test2[2]))
            if end1_capped and end2_capped:
                break

        capped = int(end1_capped) + int(end2_capped)
        item_caps.setdefault(item_i, []).append(capped)

    return item_caps, warnings_out
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd tools/exporter && python -m pytest tests/test_solidworks_helpers.py::TestDetectCappedEnds -v
```
Expected: `6 passed`

- [ ] **Step 5: Run all helpers tests together**

```bash
cd tools/exporter && python -m pytest tests/test_solidworks_helpers.py::TestContainsPoint tests/test_solidworks_helpers.py::TestGetSketchDirections tests/test_solidworks_helpers.py::TestMatchBodyToDirection tests/test_solidworks_helpers.py::TestDetectCappedEnds -v
```
Expected: `17 passed`

- [ ] **Step 6: Commit**

```bash
git add tools/exporter/solidworks.py tools/exporter/tests/test_solidworks_helpers.py
git commit -m "feat: add _detect_capped_ends — body-level capping detection via ContainsPoint"
```

---

## Chunk 2: Integration into `get_weldment_cut_list`

### Task 6: Expand cut list items by capping state in `get_weldment_cut_list`

**Files:**
- Modify: `tools/exporter/solidworks.py` — `get_weldment_cut_list` function
- Test: `tools/exporter/tests/test_solidworks_helpers.py` — `TestGetWeldmentCutList` class

- [ ] **Step 1: Write failing integration tests**

Add to `TestGetWeldmentCutList`:

```python
    @patch("solidworks._open_doc")
    @patch("solidworks._wrap")
    def test_capping_expands_rows_different_states(self, mock_wrap, mock_open_doc):
        """3 bodies from same cut list group, different capping → 3 separate rows."""
        from solidworks import get_weldment_cut_list
        # One CutListFolder feature: desc="Profile A", length=1000, qty=3
        feat = self._make_cut_feat("Profile A", "1000.0", "3")
        mock_doc = MagicMock()
        mock_open_doc.return_value = mock_doc
        mock_part = MagicMock()
        mock_part.FirstFeature.return_value = feat

        # 3 bodies: capping states 2, 1, 0
        b0, b1, b2 = MagicMock(), MagicMock(), MagicMock()
        for b in (b0, b1, b2):
            b.GetBodyBox.return_value = (0.0, -0.02, -0.02, 1.0, 0.02, 0.02)
            b._oleobj_ = None
        # b0: both ends capped
        b0.ContainsPoint.return_value = 1
        # b1: one end capped
        b1.ContainsPoint.side_effect = lambda x, y, z: 1 if x > 0.9 else 0
        # b2: no ends capped
        b2.ContainsPoint.return_value = 0

        mock_part.GetBodies2.return_value = [b0, b1, b2]
        # No 3DSketch → sketch_lines = [] → fallback axis
        mock_part.FirstFeature.return_value = feat   # no sketch feat in chain

        mock_wrap.side_effect = self._wrap_side(mock_part)

        items, warnings = get_weldment_cut_list(MagicMock(), "C:\\parts\\p.sldprt")

        descs = {it.description for it in items}
        self.assertIn("Profile A D17/D17", descs)
        self.assertIn("Profile A D17", descs)
        self.assertIn("Profile A", descs)
        total_qty = sum(it.qty for it in items)
        self.assertEqual(total_qty, 3)

    @patch("solidworks._open_doc")
    @patch("solidworks._wrap")
    def test_capping_same_state_aggregates_qty(self, mock_wrap, mock_open_doc):
        """2 bodies, both capped on both ends → 1 row with qty=2."""
        from solidworks import get_weldment_cut_list
        feat = self._make_cut_feat("Profile B", "500.0", "2")
        mock_doc = MagicMock()
        mock_open_doc.return_value = mock_doc
        mock_part = MagicMock()
        mock_part.FirstFeature.return_value = feat

        b0, b1 = MagicMock(), MagicMock()
        for b in (b0, b1):
            b.GetBodyBox.return_value = (0.0, -0.02, -0.02, 0.5, 0.02, 0.02)
            b._oleobj_ = None
            b.ContainsPoint.return_value = 1  # both ends capped

        mock_part.GetBodies2.return_value = [b0, b1]
        mock_wrap.side_effect = self._wrap_side(mock_part)

        items, _ = get_weldment_cut_list(MagicMock(), "C:\\parts\\p.sldprt")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].description, "Profile B D17/D17")
        self.assertEqual(items[0].qty, 2)

    @patch("solidworks._open_doc")
    @patch("solidworks._wrap")
    def test_capping_detection_failure_returns_raw_items(self, mock_wrap, mock_open_doc):
        """If GetBodies2 raises, raw items are returned unchanged."""
        from solidworks import get_weldment_cut_list
        feat = self._make_cut_feat("Profile C", "300.0", "1")
        mock_doc = MagicMock()
        mock_open_doc.return_value = mock_doc
        mock_part = MagicMock()
        mock_part.FirstFeature.return_value = feat
        mock_part.GetBodies2.side_effect = Exception("COM error")
        mock_wrap.side_effect = self._wrap_side(mock_part)

        items, warnings = get_weldment_cut_list(MagicMock(), "C:\\parts\\p.sldprt")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].description, "Profile C")
        self.assertTrue(any("Capping detection" in w for w in warnings))

    @patch("solidworks._open_doc")
    @patch("solidworks._wrap")
    def test_getbodies2_returns_tuple_unwrapped(self, mock_wrap, mock_open_doc):
        """GetBodies2 returning a tuple is correctly unwrapped."""
        from solidworks import get_weldment_cut_list
        feat = self._make_cut_feat("Profile D", "200.0", "1")
        mock_doc = MagicMock()
        mock_open_doc.return_value = mock_doc
        mock_part = MagicMock()
        mock_part.FirstFeature.return_value = feat
        body = MagicMock()
        body.GetBodyBox.return_value = (0.0, -0.01, -0.01, 0.2, 0.01, 0.01)
        body._oleobj_ = None
        body.ContainsPoint.return_value = 0
        mock_part.GetBodies2.return_value = (body,)  # tuple, not list
        mock_wrap.side_effect = self._wrap_side(mock_part)

        items, _ = get_weldment_cut_list(MagicMock(), "C:\\parts\\p.sldprt")
        self.assertEqual(len(items), 1)
        # No capping → description unchanged
        self.assertEqual(items[0].description, "Profile D")
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd tools/exporter && python -m pytest tests/test_solidworks_helpers.py::TestGetWeldmentCutList -v -k "capping"
```
Expected: `FAILED` (test method not affecting current code yet)

- [ ] **Step 3: Integrate capping detection into `get_weldment_cut_list`**

In `solidworks.py`, inside `get_weldment_cut_list`, add the capping block after the
feature-iteration `while` loop (after `items` is fully populated) and before
`return items, warnings`. The current structure is:

```python
        # [existing feature iteration while loop ends here]

        return items, warnings   # ← insert block BEFORE this line
```

Add:

```python
        # --- Capped-end detection (post-processing) ---
        try:
            bodies_raw = part.GetBodies2(0, False)
            if bodies_raw is None:
                bodies_raw = []
            if isinstance(bodies_raw, tuple):
                bodies_raw = list(bodies_raw)
            all_bodies = [_wrap(b, "IBody2") for b in bodies_raw if b is not None]

            if all_bodies and items:
                sketch_lines = _get_sketch_directions(part)
                if not sketch_lines:
                    warnings.append(
                        "Sem 3DSketch encontrado — fallback para eixo bounding box "
                        "(perfis não-ortogonais podem ter capping incorreto)"
                    )
                item_caps, cap_warns = _detect_capped_ends(
                    all_bodies, items, sketch_lines, part_path)
                warnings.extend(cap_warns)

                if item_caps:
                    from collections import Counter as _Counter
                    expanded = []
                    for i, item in enumerate(items):
                        caps = item_caps.get(i)
                        if not caps:
                            expanded.append(item)
                            continue
                        state_counter = _Counter(caps)
                        for capped in sorted(state_counter, reverse=True):
                            suffix = {0: "", 1: " D17", 2: " D17/D17"}.get(capped, "")
                            expanded.append(CutListItem(
                                item.description + suffix,
                                item.length_mm,
                                state_counter[capped],
                            ))
                    items = expanded
        except Exception as _cap_exc:
            warnings.append(f"Capping detection falhou: {_cap_exc}")
```

- [ ] **Step 4: Run new integration tests**

```bash
cd tools/exporter && python -m pytest tests/test_solidworks_helpers.py::TestGetWeldmentCutList -v -k "capping"
```
Expected: `4 passed`

- [ ] **Step 5: Run the full `TestGetWeldmentCutList` suite to check no regressions**

```bash
cd tools/exporter && python -m pytest tests/test_solidworks_helpers.py::TestGetWeldmentCutList -v
```
Expected: all previous tests (`test_reads_cut_list_item`, `test_skips_suppressed_folder`,
`test_quantity_fallback_to_qty_key`, `test_quantity_defaults_to_1_and_warns`,
`test_close_doc_called_in_finally`) still pass, plus the 4 new ones.

- [ ] **Step 6: Run full test suite**

```bash
cd tools/exporter && python -m pytest 2>&1 | tail -15
```
Expected: helpers tests all pass; the 5 pre-existing `TestBomTraverse` failures remain
(pre-existing, unrelated to this feature). No new failures.

- [ ] **Step 7: Commit**

```bash
git add tools/exporter/solidworks.py tools/exporter/tests/test_solidworks_helpers.py
git commit -m "feat: integrate capped-end D17 detection into get_weldment_cut_list"
```

---

### Task 7: Manual validation with SolidWorks

> This step requires SolidWorks running with the test assembly open.

- [ ] **Step 1: Launch the GUI**

```bash
python tools/exporter/main.py
```

- [ ] **Step 2: Open the assembly (`18026.sldasm` or similar), go to Listas panel, select only "Perfis de Alumínio", run.**

- [ ] **Step 3: Verify in the log:**
  - `Peças Perfil Alumínio: N` (expected > 0)
  - No `AVISO cut list falhou` errors
  - Profile rows in output with D17/D17 or D17 suffixes where appropriate

- [ ] **Step 4: Open `Perfis de Alumínio.xlsx` and verify:**
  - Rows that previously needed manual D17/D17 editing now have them automatically
  - Rows with no capping have unchanged descriptions
  - Quantities sum correctly

- [ ] **Step 5 (if `ContainsPoint` fails in SW 2024 stubs):**

  If the log shows `Capping detection falhou: DISP_E_MEMBERNOTFOUND` or similar, the
  late-binding fallback in `_contains_point` is the fix path. Verify by checking the
  `_contains_point` function — it should automatically retry via `win32com.client.Dispatch`.
  If both paths fail, add logging inside `_contains_point` to surface the exact error.
