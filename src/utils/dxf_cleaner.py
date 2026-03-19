"""
dxf_cleaner.py — DXF post-processing for laser cutting.

Two cleanup passes:
1. Concentric circles — for each group, keep only the smallest (through-hole);
   exception: if the largest is the outer part contour, keep it and remove only
   the intermediates.
2. Outside contour — remove every entity whose representative point lies outside
   the outer contour of the part (e.g. SolidWorks Educational watermarks).
"""

import math
from collections import defaultdict
from typing import List, Optional, Tuple

import ezdxf

CONCENTRIC_TOLERANCE = 0.1   # mm — centers within this distance are the same point
ENDPOINT_TOLERANCE   = 0.5   # mm — segment endpoints within this distance are joined


def clean_dxf(input_path: str, output_path: str) -> int:
    """
    Load a DXF file, run both cleanup passes, save to output_path.
    Returns the number of concentric circles removed (pass 1).
    """
    doc = ezdxf.readfile(input_path)
    msp = doc.modelspace()
    removed_circles  = _clean_concentric_circles(msp)
    _remove_outside_contour(msp)
    doc.saveas(output_path)
    return removed_circles


# ---------------------------------------------------------------------------
# Pass 1 — concentric circle cleanup
# ---------------------------------------------------------------------------

def _clean_concentric_circles(msp) -> int:
    circles = [e for e in msp if e.dxftype() == "CIRCLE"]

    if len(circles) < 2:
        return 0

    groups = _group_concentric(circles)
    other_entities = [e for e in msp if e.dxftype() != "CIRCLE"]
    to_delete = []

    for group in groups:
        if len(group) < 2:
            continue

        group_sorted   = sorted(group, key=lambda c: c.dxf.radius)
        largest        = group_sorted[-1]
        intermediates  = group_sorted[1:-1]

        # Pass only this group's circles — not all msp circles — so that
        # unrelated circles (e.g. SW Educational watermark) don't prevent
        # correct outer-contour detection.
        if _is_outer_contour(largest, group, other_entities):
            # Largest is the outer cut profile — remove everything else
            # (center-mark rings, thread designators, hole annotations).
            to_delete.extend(group_sorted[:-1])
        else:
            to_delete.extend(group_sorted[1:])

    for circle in to_delete:
        msp.delete_entity(circle)

    return len(to_delete)


def _group_concentric(circles) -> List[List]:
    """Group circles whose centres are within CONCENTRIC_TOLERANCE of each other."""
    n = len(circles)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        parent[find(i)] = find(j)

    for i in range(n):
        cx_i = circles[i].dxf.center.x
        cy_i = circles[i].dxf.center.y
        for j in range(i + 1, n):
            dist = math.hypot(circles[j].dxf.center.x - cx_i,
                              circles[j].dxf.center.y - cy_i)
            if dist <= CONCENTRIC_TOLERANCE:
                union(i, j)

    groups_map = defaultdict(list)
    for i, circle in enumerate(circles):
        groups_map[find(i)].append(circle)

    return list(groups_map.values())


def _is_outer_contour(candidate, all_circles: List, other_entities: List) -> bool:
    cx = candidate.dxf.center.x
    cy = candidate.dxf.center.y
    cr = candidate.dxf.radius

    for c in all_circles:
        if c is candidate:
            continue
        dist = math.hypot(c.dxf.center.x - cx, c.dxf.center.y - cy)
        if dist + c.dxf.radius > cr + CONCENTRIC_TOLERANCE:
            return False

    for px, py in _sample_geometry_points(other_entities):
        if math.hypot(px - cx, py - cy) > cr + CONCENTRIC_TOLERANCE:
            return False

    return True


# ---------------------------------------------------------------------------
# Pass 2 — remove entities outside the outer contour
# ---------------------------------------------------------------------------

# Entity types that form the part boundary (kept unconditionally).
_CONTOUR_TYPES = {"LINE", "ARC", "LWPOLYLINE", "SPLINE"}


def _remove_outside_contour(msp) -> int:
    """
    Build the outer contour polygon from LINE/ARC/LWPOLYLINE entities, then
    delete every other entity whose representative point lies outside it.
    Falls back to the bounding box if a closed polygon cannot be built.
    Returns the number of entities removed.
    """
    all_entities     = list(msp)
    contour_entities = [e for e in all_entities if e.dxftype() in _CONTOUR_TYPES]
    # Circles that survived pass 1 are actual cut profiles — never remove them.
    candidates       = [e for e in all_entities
                        if e.dxftype() not in _CONTOUR_TYPES
                        and e.dxftype() != "CIRCLE"]

    if not contour_entities or not candidates:
        return 0

    polygon = _build_contour_polygon(contour_entities)

    if len(polygon) >= 3:
        def is_inside(px: float, py: float) -> bool:
            return _point_in_polygon(px, py, polygon)
    else:
        # Fallback: axis-aligned bounding box of all contour points.
        pts = _sample_geometry_points(contour_entities)
        if not pts:
            return 0
        min_x = min(p[0] for p in pts)
        max_x = max(p[0] for p in pts)
        min_y = min(p[1] for p in pts)
        max_y = max(p[1] for p in pts)
        tol = 1.0
        def is_inside(px: float, py: float) -> bool:
            return (min_x - tol <= px <= max_x + tol and
                    min_y - tol <= py <= max_y + tol)

    to_delete = []
    for e in candidates:
        pt = _entity_representative_point(e)
        if pt is None:
            continue
        if not is_inside(pt[0], pt[1]):
            to_delete.append(e)

    for e in to_delete:
        msp.delete_entity(e)

    return len(to_delete)


def _build_contour_polygon(
        contour_entities) -> List[Tuple[float, float]]:
    """
    Chain LINE/ARC/LWPOLYLINE segments into an ordered list of (x, y) vertices.
    Returns an empty list if fewer than 3 vertices can be chained.
    """
    # Collect directed micro-segments: (start_xy, end_xy)
    segments: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []

    for e in contour_entities:
        t = e.dxftype()
        if t == "LINE":
            segments.append(
                ((e.dxf.start.x, e.dxf.start.y),
                 (e.dxf.end.x,   e.dxf.end.y)))
        elif t == "ARC":
            pts = _sample_arc(e)
            for i in range(len(pts) - 1):
                segments.append((pts[i], pts[i + 1]))
        elif t == "LWPOLYLINE":
            pts = [(v[0], v[1]) for v in e.get_points()]
            for i in range(len(pts) - 1):
                segments.append((pts[i], pts[i + 1]))
            if getattr(e.dxf, "flags", 0) & 1:   # closed flag
                segments.append((pts[-1], pts[0]))

    if not segments:
        return []

    # Greedily chain segments by matching endpoints.
    chain = [segments[0][0], segments[0][1]]
    used  = {0}

    for _ in range(len(segments) - 1):
        last = chain[-1]
        found = False
        for i, (a, b) in enumerate(segments):
            if i in used:
                continue
            if math.hypot(a[0] - last[0], a[1] - last[1]) <= ENDPOINT_TOLERANCE:
                chain.append(b)
                used.add(i)
                found = True
                break
            if math.hypot(b[0] - last[0], b[1] - last[1]) <= ENDPOINT_TOLERANCE:
                chain.append(a)
                used.add(i)
                found = True
                break
        if not found:
            break

    return chain if len(chain) >= 3 else []


def _point_in_polygon(px: float, py: float,
                      polygon: List[Tuple[float, float]]) -> bool:
    """Ray-casting point-in-polygon test."""
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > py) != (yj > py) and
                px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _entity_representative_point(
        entity) -> Optional[Tuple[float, float]]:
    """Return a single representative (x, y) for any entity type."""
    t = entity.dxftype()
    if t in ("CIRCLE", "ARC"):
        return entity.dxf.center.x, entity.dxf.center.y
    if t in ("MTEXT", "TEXT"):
        return entity.dxf.insert.x, entity.dxf.insert.y
    if t == "INSERT":
        return entity.dxf.insert.x, entity.dxf.insert.y
    if t == "POINT":
        return entity.dxf.location.x, entity.dxf.location.y
    return None


# ---------------------------------------------------------------------------
# Shared geometry helpers
# ---------------------------------------------------------------------------

def _sample_arc(arc, step_deg: float = 5.0) -> List[Tuple[float, float]]:
    """Sample an ARC entity into a polyline of (x, y) points."""
    cx, cy, r = arc.dxf.center.x, arc.dxf.center.y, arc.dxf.radius
    sa = arc.dxf.start_angle % 360
    ea = arc.dxf.end_angle   % 360
    if ea <= sa:
        ea += 360
    pts = []
    angle = sa
    while angle <= ea + 1e-6:
        rad = math.radians(angle % 360)
        pts.append((cx + r * math.cos(rad), cy + r * math.sin(rad)))
        angle += step_deg
    return pts


def _sample_geometry_points(entities) -> List[Tuple[float, float]]:
    """Extract representative points from a list of entities."""
    points: List[Tuple[float, float]] = []
    for e in entities:
        t = e.dxftype()
        if t == "LINE":
            points.append((e.dxf.start.x, e.dxf.start.y))
            points.append((e.dxf.end.x,   e.dxf.end.y))
        elif t == "ARC":
            points.extend(_sample_arc(e))
        elif t == "LWPOLYLINE":
            for v in e.get_points():
                points.append((v[0], v[1]))
        elif t == "SPLINE":
            for cp in e.control_points:
                points.append((cp[0], cp[1]))
    return points
