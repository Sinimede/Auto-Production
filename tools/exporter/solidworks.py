"""
solidworks.py — SolidWorks COM API wrapper.

All SolidWorks interactions are isolated here. Requires SolidWorks to be
running. Uses win32com with early-binding stubs generated from sldworks.tlb:

    python -m win32com.client.makepy "C:\\Program Files\\SOLIDWORKS Corp\\SOLIDWORKS\\sldworks.tlb"

Run the above once per machine. The stubs are stored in %TEMP%\\gen_py\\ and
enable correct array marshalling for methods like GetComponents.
"""

import os
import shutil
import numpy as np
import re
import unicodedata
from typing import List, Optional
from collections import namedtuple, Counter

import win32com.client
from win32com.client import gencache

HoleInfo = namedtuple('HoleInfo', ['feature', 'original_diameter_m'])

BomComponent = namedtuple('BomComponent', ['component', 'path', 'comp_type'])
# component: IComponent2
# path:      os.path.normpath(component.GetPathName())
# comp_type: "producao" | "comercial"

CutListItem = namedtuple('CutListItem', ['description', 'length_mm', 'qty'])
# description: str  — profile description from DESCRIPTION cut-list property
# length_mm:   float — length parsed from LENGTH property (already in mm, no conversion)
# qty:         int  — quantity from QUANTITY/QTY property × assembly instance count

# Tolerance for matching body axis-length to cut list LENGTH property (mm).
# Accounts for SW rounding LENGTH to nearest integer mm.
LENGTH_MATCH_TOLERANCE_MM = 1.0


def _select_length_axis(extents_mm: list, raw_items: list) -> tuple:
    """Try each bbox axis; return the one whose extent matches an item length.

    Args:
        extents_mm: list of 3 floats [dx, dy, dz] in millimetres
        raw_items:  list of CutListItem

    Returns:
        (axis_idx, length_mm, cross_dims_mm) where axis_idx is 0/1/2,
        length_mm is the matched extent, and cross_dims_mm is a sorted
        [dim_short, dim_long] list of the two remaining extents.

        Returns (None, None, None) if no axis matches any item length.
        Tiebreak: if multiple axes match, the one with the largest extent wins.
    """
    if not raw_items:
        return (None, None, None)

    candidates = []
    for i, extent in enumerate(extents_mm):
        for item in raw_items:
            if abs(item.length_mm - extent) <= LENGTH_MATCH_TOLERANCE_MM:
                candidates.append((extent, i))
                break  # one item match is enough for this axis

    if not candidates:
        return (None, None, None)

    # tiebreak: largest extent
    _, axis_idx = max(candidates, key=lambda t: t[0])
    length_mm = extents_mm[axis_idx]
    cross = sorted(e for j, e in enumerate(extents_mm) if j != axis_idx)
    return (axis_idx, length_mm, cross)


def _classify_profile_holes(cross_dims_mm: list) -> "int | str":
    """Classify a profile cross-section and return holes-per-end count.

    Args:
        cross_dims_mm: sorted [dim_short, dim_long] in mm (output of _select_length_axis)

    Returns:
        1            — 45×45 profile (both dims 40–50 mm)
        2            — 45×90 profile (short 40–50 mm, long 85–95 mm)
        "VERIFICAR"  — unknown cross-section
    """
    if len(cross_dims_mm) != 2:
        return "VERIFICAR"
    short, long_ = cross_dims_mm
    is_45 = lambda v: 40.0 <= v <= 50.0
    is_90 = lambda v: 85.0 <= v <= 95.0
    if is_45(short) and is_45(long_):
        return 1
    if is_45(short) and is_90(long_):
        return 2
    return "VERIFICAR"


def _holes_per_end_from_description(description: str) -> "int | None":
    """Parse holes-per-end count from a cut list item description.

    Uses the description (the ground truth for profile type) rather than
    body geometry, avoiding misclassification when round-robin assigns a
    45×90 body to a same-length 45×45 item.

    Returns:
        1    — description identifies a 45×45 profile
        2    — description identifies a 45×90 profile
        None — pattern not recognised; caller should fall back to geometry
    """
    import re
    desc = description.upper()
    if re.search(r'45\s*[X×]\s*90|90\s*[X×]\s*45', desc):
        return 2
    if re.search(r'45\s*[X×]\s*45', desc):
        return 1
    return None


def _d17_suffix(capped_ends: int, holes_per_end: "int | str") -> str:
    """Return the D17 annotation suffix string.

    Args:
        capped_ends:  0, 1, or 2 (number of physically capped ends)
        holes_per_end: 1, 2, or "VERIFICAR"

    Returns suffix string to append to the cut list item description.
    """
    if capped_ends == 0:
        return ""
    if holes_per_end == "VERIFICAR":
        return " VERIFICAR FURAÇÕES"
    if holes_per_end == 1:
        return {1: " D17", 2: " D17/D17"}.get(capped_ends, "")
    if holes_per_end == 2:
        return {1: " D17/D17/-/-", 2: " D17/D17/D17/D17"}.get(capped_ends, "")
    return ""


# SolidWorks 2024 type library identifiers (from sldworks.tlb)
_SW_TLB_GUID  = '{83A33D31-27C5-11CE-BFD4-00400513BB57}'
_SW_TLB_MAJOR = 32
_SW_TLB_MINOR = 0


def _sw_module():
    """Return the generated early-binding module for the SolidWorks type library."""
    return gencache.GetModuleForTypelib(_SW_TLB_GUID, 0, _SW_TLB_MAJOR, _SW_TLB_MINOR)


def _wrap(obj, interface_name: str):
    """
    Wrap a COM dispatch object with an early-binding class from the stubs.

    Early-binding constructors (DispatchBaseClass.__init__) need a raw PyIDispatch.
    Python COM wrappers store it under '_oleobj_' (DispatchBaseClass) or '_dispobj_'
    (CoClass). This function peels those layers before constructing the wrapper.

    Strategy: try each stored raw reference in turn; fall back to constructing
    directly from obj (works when obj is already a DispatchBaseClass subclass
    and the DispatchBaseClass constructor can QI for the target interface).
    Returns the wrapped object, or the original obj if all attempts fail.
    """
    try:
        mod = _sw_module()
        cls = getattr(mod, interface_name)
        if isinstance(obj, cls):
            return obj  # Already the correct type

        # Try '_dispobj_' (CoClass wrapper) then '_oleobj_' (DispatchBaseClass).
        # For each, attempt to construct cls(inner) directly — this works when
        # 'inner' is a raw PyIDispatch, bypassing the CLSID/QueryInterface path
        # that fails for pure-interface classes (no CoClass CLSID in the stubs).
        for attr in ('_dispobj_', '_oleobj_'):
            inner = obj.__dict__.get(attr) or getattr(obj, attr, None)
            if inner is not None:
                try:
                    return cls(inner)
                except Exception:
                    pass

        # Last resort: let DispatchBaseClass try QueryInterface itself.
        return cls(obj)
    except Exception:
        return obj



# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def connect_to_solidworks():
    """
    Attach to a running SolidWorks instance via COM.
    Raises RuntimeError if SolidWorks is not running or stubs are missing.
    """
    try:
        # GetActiveObject attaches to a running SolidWorks instance.
        # Dispatch would create a new invisible instance — not what we want.
        raw = win32com.client.GetActiveObject("SldWorks.Application")
        # Wrap with ISldWorks early-binding class via QueryInterface.
        # This gives correct array marshalling without needing GetTypeInfo.
        sw = _wrap(raw, "ISldWorks")
        sw.Visible = True
        return sw
    except Exception as exc:
        raise RuntimeError(
            "Não foi possível conectar ao SolidWorks. "
            "Certifica-te que o SolidWorks está aberto."
        ) from exc


def _is_dirty(doc) -> bool:
    """Return True if the document has unsaved changes (GetSaveFlag == True)."""
    ref = doc.GetSaveFlag
    result = ref() if callable(ref) else ref
    if isinstance(result, tuple):
        result = result[0]
    return bool(result)


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def open_assembly(sw_app, sldasm_path: str):
    """
    Return the IModelDoc2 for the assembly. Returns (doc, opened_by_us).
    Three-tier lookup to handle path format differences between tkinter and SolidWorks.
    """
    sldasm_path = os.path.normpath(os.path.abspath(sldasm_path))

    # 1. Check active document first (most common case — user has it open)
    try:
        active = sw_app.ActiveDoc
        if active is not None:
            active_path = os.path.normpath(active.GetPathName())
            if active_path.lower() == sldasm_path.lower():
                return active, False
    except Exception:
        pass

    # 2. Try GetOpenDocumentByName with normalized path
    existing = sw_app.GetOpenDocumentByName(sldasm_path)
    if existing is not None:
        return existing, False

    # 3. Open non-silently (options=0 ensures full component tree is loaded)
    doc = _open_doc(sw_app, sldasm_path, doc_type=2)  # swDocASSEMBLY = 2
    return doc, True


def open_assembly_resolved(sw_app, sldasm_path: str):
    """
    Open the assembly so that ResolveAllLightweightComponents can work.
    Closes any already-open instance first (dirty check — raises if unsaved changes).
    Always returns (doc, True) — caller is responsible for CloseDoc.

    Opens with options=0 (SW default, no ReadOnly flag) because ReadOnly prevents
    ResolveAllLightweightComponents(False) and SetComponentState(4) from working —
    both raise COM errors that are silently swallowed, leaving all components
    lightweight and GetModelDoc2() returning None.
    Since we never modify the assembly, CloseDoc closes without a save prompt.
    """
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
            # Verify CloseDoc succeeded (it silently no-ops if path format doesn't match SW's internal registration)
            try:
                still_open = sw_app.GetOpenDocumentByName(sldasm_path)
                if still_open is not None:
                    raise RuntimeError(
                        "Não foi possível fechar o assembly (CloseDoc não teve efeito). "
                        "Fecha manualmente o assembly antes de continuar."
                    )
            except RuntimeError:
                raise
            except Exception:
                pass  # GetOpenDocumentByName failure is not actionable here
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(
                f"Não foi possível fechar o assembly aberto: {e}"
            ) from e
        break  # only one instance expected

    # Open with default options (0) — no ReadOnly, no lightweight override.
    # ReadOnly blocks ResolveAllLightweightComponents and SetComponentState.
    result = sw_app.OpenDoc6(sldasm_path, 2, 0, "", 0, 0)
    # Early binding returns tuple (IModelDoc2, errors, warnings)
    doc = result[0] if isinstance(result, tuple) else result
    if doc is None:
        raise RuntimeError(f"Não foi possível abrir o assembly: {sldasm_path}")
    return doc, True


def _find_open_doc(sw_app, path: str):
    """
    Yield the IModelDoc2 for path if it is currently open in SW.
    Normalises path internally. Checks active doc first, then GetOpenDocumentByName.
    Yields at most one result.
    """
    path = os.path.normpath(os.path.abspath(path))

    # Tier 1: active document
    try:
        active = sw_app.ActiveDoc
        if active is not None:
            active_path = os.path.normpath(active.GetPathName())
            if active_path.lower() == path.lower():
                yield active
                return
    except Exception:
        pass

    # Tier 2: open but not active
    try:
        existing = sw_app.GetOpenDocumentByName(path)
        if existing is not None:
            yield existing
    except Exception:
        pass  # GetOpenDocumentByName failure is not actionable — proceed without background check


def get_all_parts(assembly_doc) -> List:
    """
    Return all unique part IComponent2 objects in the assembly, recursively.
    Uses IAssemblyDoc.GetComponents via early-binding cast (CastTo) which fixes
    the array marshalling issue present in late-binding.
    Suppressed or unresolvable parts are skipped.
    """
    # Wrap assembly doc for correct array marshalling in GetComponents.
    asm = _wrap(assembly_doc, "IAssemblyDoc")

    # Resolve lightweight components via late binding — early binding silently no-ops in SW 2024.
    # Same pattern used by get_bom_components.
    try:
        asm_raw = getattr(asm, "_dispobj_", None) or getattr(asm, "_oleobj_", None) or asm
        win32com.client.Dispatch(asm_raw).ResolveAllLightweightComponents(False)
    except Exception:
        pass

    # Get components via IAssemblyDoc (known dispatch IDs from stubs)
    components = None
    try:
        components = asm.GetComponents(False)  # False = all levels recursively
    except Exception:
        pass

    # Fallback: use IConfiguration.GetRootComponent3 tree traversal
    if not components:
        try:
            config = assembly_doc.ConfigurationManager.ActiveConfiguration
            root_ref = config.GetRootComponent3
            root_raw = root_ref(True) if callable(root_ref) else root_ref
            if isinstance(root_raw, tuple):
                root_raw = root_raw[0]
            root = root_raw
            components = _collect_children(root)
        except Exception:
            return []

    if not components:
        return []

    parts = []
    for comp in components:
        # Wrap each component with IComponent2 for correct method dispatch
        comp = _wrap(comp, "IComponent2")
        try:
            model = comp.GetModelDoc2()
        except Exception:
            continue

        if model is None:
            try:
                comp.SetComponentState(4)  # swComponentFullyResolved = 4
                model = comp.GetModelDoc2()
            except Exception:
                pass

        if model is None:
            continue

        # GetType is a property in late-binding (CDispatch) — don't call it
        doc_type = model.GetType
        if callable(doc_type):
            doc_type = doc_type()
        if doc_type == 1:  # swDocPART = 1
            parts.append(comp)

    return parts


def _collect_children(component) -> list:
    """Recursively collect all descendant IComponent2 objects via GetChildren."""
    result = []
    if component is None:
        return result
    try:
        children_ref = component.GetChildren
        children = children_ref() if callable(children_ref) else children_ref
        if isinstance(children, tuple):
            children = list(children)
    except Exception:
        return result
    if not children:
        return result
    for child in children:
        child = _wrap(child, "IComponent2")
        result.append(child)
        result.extend(_collect_children(child))
    return result


def deduplicate_by_path(components: List) -> List:
    """Remove duplicate components that refer to the same .sldprt file."""
    seen = set()
    unique = []
    for comp in components:
        try:
            path = comp.GetPathName().lower()
        except Exception:
            continue
        if path not in seen:
            seen.add(path)
            unique.append(comp)
    return unique


# ---------------------------------------------------------------------------
# Part properties
# ---------------------------------------------------------------------------

def is_laser_part(component) -> bool:
    """
    Return True if the part's custom property 'Corte_Fabrico' contains 'laser'
    (case-insensitive) but does NOT contain 'soldadura'.
    Examples that match: 'LASER', 'Laser', 'LASER+QUINAGEM'.
    Excluded (returns False): 'LASER+QUINAGEM+SOLDADURA' — welded parts are never DXF-exported.
    Missing property → False.
    """
    try:
        model = component.GetModelDoc2()
        if model is None:
            return False
        mgr = model.Extension.CustomPropertyManager("")
        # Try Get() first (simpler, consistent across SW versions)
        try:
            val = mgr.Get("Corte_Fabrico")
        except Exception:
            val = None
        # Fallback to Get4 if Get() returned None
        if val is None:
            try:
                result = mgr.Get4("Corte_Fabrico", False)
                val = result[1] if isinstance(result, tuple) and len(result) > 1 else result
            except Exception:
                return False
        if val is None:
            return False
        normalized = str(val).strip().lower()
        return "laser" in normalized and "soldadura" not in normalized
    except Exception:
        return False


def get_part_path(component) -> str:
    """Return the full path to the .sldprt file."""
    return component.GetPathName()


# ---------------------------------------------------------------------------
# Drawing lookup
# ---------------------------------------------------------------------------

def find_drawing(part_path: str) -> Optional[str]:
    """
    Look for a .slddrw file with the same base name as the .sldprt in the
    same folder. Returns the path or None if not found.
    """
    base = os.path.splitext(part_path)[0]
    for ext in (".SLDDRW", ".slddrw", ".SldDrw"):
        candidate = base + ext
        if os.path.isfile(candidate):
            return candidate
    return None


# ---------------------------------------------------------------------------
# DXF export
# ---------------------------------------------------------------------------

def export_part_to_dxf(sw_app, sldprt_path: str, output_dxf_path: str) -> None:
    """
    Export a SolidWorks sheet metal part (.sldprt) flat pattern to DXF.
    Uses IPartDoc.ExportFlatPatternView — no .slddrw needed.
    Opens the part if not already open; closes it if we opened it.
    Raises RuntimeError on failure.
    """
    sldprt_path = os.path.normpath(os.path.abspath(sldprt_path))
    already_open = sw_app.GetOpenDocumentByName(sldprt_path) is not None
    part_doc = None
    opened_by_us = False

    try:
        if already_open:
            part_doc = sw_app.GetOpenDocumentByName(sldprt_path)
        else:
            part_doc = _open_doc(sw_app, sldprt_path, doc_type=1)  # swDocPART = 1
            opened_by_us = True

        # Wrap as IPartDoc to access ExportFlatPatternView
        part = _wrap(part_doc, "IPartDoc")
        # Options = 1 → swExportFlatPatternViewOptions_Geometry (geometry only)
        result = part.ExportFlatPatternView(output_dxf_path, 1)
        if not result:
            raise RuntimeError(
                f"ExportFlatPatternView falhou para '{sldprt_path}'. "
                "Verifica se a peça é de chapa (sheet metal) com flat pattern ativo."
            )
    finally:
        if opened_by_us and part_doc is not None:
            try:
                sw_app.CloseDoc(sldprt_path)
            except Exception:
                pass


def export_drawing_to_dxf(sw_app, slddrw_path: str, output_dxf_path: str) -> None:
    """
    Export a SolidWorks drawing to DXF.
    - Checks if the drawing is already open; only closes it if we opened it.
    - Uses SaveAs4 with silent options; SolidWorks infers DXF from the extension.
    - Raises RuntimeError on failure.
    """
    already_open = sw_app.GetOpenDocumentByName(slddrw_path) is not None
    drw_doc = None
    opened_by_us = False

    try:
        if already_open:
            drw_doc = sw_app.GetOpenDocumentByName(slddrw_path)
        else:
            drw_doc = _open_doc(sw_app, slddrw_path, doc_type=3)  # swDocDRAWING = 3
            opened_by_us = True

        import pythoncom as _pycom
        byref_i4 = lambda: win32com.client.VARIANT(_pycom.VT_BYREF | _pycom.VT_I4, 0)
        late = win32com.client.Dispatch(
            drw_doc._oleobj_ if hasattr(drw_doc, '_oleobj_') else drw_doc
        )
        raw = late.SaveAs4(output_dxf_path, 0, 1, byref_i4(), byref_i4())
        result = raw[0] if isinstance(raw, tuple) else raw
        if not result:
            raise RuntimeError(
                f"SaveAs4 falhou para '{slddrw_path}'. "
                "Verifica se o desenho tem uma folha ativa."
            )
    finally:
        if opened_by_us and drw_doc is not None:
            try:
                sw_app.CloseDoc(slddrw_path)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Internal utilities
# ---------------------------------------------------------------------------

def _open_doc(sw_app, path: str, doc_type: int, silent: bool = False):
    """
    Open a SolidWorks document.
    doc_type: 1 = part, 2 = assembly, 3 = drawing.
    silent=True  → options=1 (swOpenDocOptions_Silent), suppresses UI prompts.
                   Use for standalone parts (e.g. tmp copies).
    silent=False → options=0 (non-silent), ensures full component tree for assemblies.
    Raises RuntimeError if the document cannot be opened.
    """
    options  = 1 if silent else 0
    result = sw_app.OpenDoc6(path, doc_type, options, "", 0, 0)
    # With early binding, BYREF out-params are appended to the return value as a
    # tuple: (IModelDoc2, errors_int, warnings_int).  Extract the first element.
    doc = result[0] if isinstance(result, tuple) else result
    if doc is None:
        raise RuntimeError(
            f"Não foi possível abrir '{path}'."
        )
    return doc


# ---------------------------------------------------------------------------
# STEP export — part selection
# ---------------------------------------------------------------------------

def get_corte_fabrico(component) -> str:
    """
    Return the Corte_Fabrico custom property value, stripped and lowercased.
    Returns empty string if the property is missing or inaccessible.
    """
    try:
        model = component.GetModelDoc2()
        if model is None:
            return ""
        mgr = model.Extension.CustomPropertyManager("")
        try:
            val = mgr.Get("Corte_Fabrico")
        except Exception:
            val = None
        if val is None:
            try:
                result = mgr.Get4("Corte_Fabrico", False)
                val = result[1] if isinstance(result, tuple) and len(result) > 1 else result
            except Exception:
                return ""
        if val is None:
            return ""
        return _normalize_corte(str(val).strip())
    except Exception:
        return ""


def is_step_part(component) -> bool:
    """
    Return True if Corte_Fabrico contains 'router', 'cnc', or 'torno' (case-insensitive).
    Matches combinations: 'router+cnc', 'CNC+TORNO', etc.
    """
    val = get_corte_fabrico(component)
    return bool(val) and any(k in val for k in ("router", "cnc", "torno"))


def is_protecoes_part(component) -> bool:
    """
    Return True if Corte_Fabrico contains 'protecoes' (accent/case-insensitive).
    get_corte_fabrico already returns a lowercased, accent-stripped value.
    Matches: 'PROTEÇÕES', 'Proteções', 'Protecoes', etc.
    """
    val = get_corte_fabrico(component)
    return bool(val) and "protecoes" in val


def _normalize_corte(val: str) -> str:
    """Strip accents and lowercase — used for Corte_Fabrico accent-insensitive matching."""
    nfkd = unicodedata.normalize("NFD", val.lower())
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


def is_perfil_aluminio(component) -> bool:
    """
    Return True if Corte_Fabrico contains 'perfil aluminio' (accent/case-insensitive).
    get_corte_fabrico already returns a lowercased, accent-stripped value.
    Matches: 'PERFIL ALUMINIO', 'PERFIL ALUMÍNIO', 'Perfil Alumínio', etc.
    """
    val = get_corte_fabrico(component)
    return bool(val) and "perfil aluminio" in val


def get_perfis_parts(asm_doc) -> list:
    """
    Return list of (part_path: str, instance_count: int) for all unique
    parts whose Corte_Fabrico matches 'PERFIL ALUMINIO'/'PERFIL ALUMÍNIO'.

    Uses the existing get_all_parts / deduplicate_by_path / count_instances helpers.
    instance_count = number of non-suppressed instances of that .sldprt in the assembly.
    """
    all_parts = get_all_parts(asm_doc)
    perfil_parts = [p for p in all_parts if is_perfil_aluminio(p)]
    unique = deduplicate_by_path(perfil_parts)

    result = []
    for comp in unique:
        try:
            path_ref = comp.GetPathName
            path = path_ref() if callable(path_ref) else path_ref
            if isinstance(path, tuple):
                path = path[0]
            path = os.path.normpath(os.path.abspath(path))
            count = count_instances(all_parts, path)
            result.append((path, count))
        except Exception:
            continue
    return result


def _contains_point(body, x: float, y: float, z: float) -> bool:
    """Call IBody2.ContainsPoint with early-binding, falling back to late binding.

    NOTE: IBody2.ContainsPoint does NOT exist in the SW 2024 dispatch interface.
    Both early and late binding raise AttributeError — this function always
    returns False in SW 2024.  It is kept here for reference and future SW
    versions; the capping detection uses _bbox_contains_point instead.
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


def _bbox_contains_point(bbox: tuple, x: float, y: float, z: float) -> bool:
    """Check if point (x, y, z) is inside bounding box (xmin, ymin, zmin, xmax, ymax, zmax).

    This is the primary capping-end detection method (IBody2.ContainsPoint is
    unavailable in SW 2024 — see _contains_point).

    Why this works for aluminum profiles:
        Extruded profiles are rectilinear, so their bounding box ≈ their body.
        A test point placed 0.1 mm past an end face will land inside the bbox of
        any perpendicular profile that physically caps that end.

    Limitation — false positives if two profiles run in parallel with overlapping
    bounding boxes (e.g. two profiles side by side with less than 0.1 mm gap).
    In practice this does not occur in typical weldment frames.

    Returns False if bbox is None (body whose GetBodyBox failed).
    """
    if bbox is None:
        return False
    xmin, ymin, zmin, xmax, ymax, zmax = bbox
    return xmin <= x <= xmax and ymin <= y <= ymax and zmin <= z <= zmax


def _get_sketch_directions(part_doc) -> list:
    """Return list of (start_m, end_m) np.ndarray pairs for all 3DSketch line segments.

    Iterates IPartDoc features looking for '3DSketch' features.
    Coordinates are in metres as returned by ISketchPoint.X/Y/Z.
    Returns [] if no 3DSketch feature is found or GetSketchSegments fails.

    NOTE: In practice, SolidWorks 2024 weldments do NOT expose standalone sketch
    features — structural members are built via WeldMemberFeat / 3DProfileFeature /
    ProfileFeature, and the sketch geometry is embedded in those features rather
    than appearing as a separate '3DSketch' or 'Sketch' feature in the tree.
    This function therefore returns [] for all current weldment parts, and
    _match_body_to_direction falls back to the bounding-box axis method.

    If future part types do contain a standalone 3DSketch (e.g. mixed weldments),
    this function will pick it up automatically.
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


def _match_body_to_direction(body, sketch_lines: list) -> tuple:
    """Return (center_m, unit_axis) for an IBody2 body.

    center_m:  np.ndarray [x, y, z] — bounding box midpoint in metres
    unit_axis: np.ndarray [x, y, z] — unit vector along the profile's long axis

    Primary path (sketch_lines available):
        Finds the sketch segment whose infinite line is closest to the body's
        bounding box centre.  This correctly handles multiple bodies generated
        from the same sketch segment (offset instances on the same line).

    Fallback path (sketch_lines == []):
        Uses the bounding box max-extent coordinate axis (X, Y, or Z).
        This is the path taken for all SW 2024 weldment parts (see
        _get_sketch_directions for why sketch_lines is always empty).

    LIMITATION — non-square cross-sections (e.g. future 45×90 profiles):
        The max-extent fallback assumes the longest bounding box dimension is
        the profile's length axis.  This is safe when length >> cross-section,
        but breaks for short profiles where the cross-section height (90 mm)
        exceeds the profile length (e.g. a 80 mm piece of 45×90).
        In that case argmax would return the 90 mm cross-section axis instead
        of the actual 80 mm length axis, producing wrong test points and wrong
        body-to-item matching.

        Fix path: pass raw_items to _match_body_to_direction (or to
        _detect_capped_ends) and try all three bbox axes, choosing the axis
        whose extent matches a cut list item length within the tolerance.
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


def _detect_capped_ends(bodies: list, raw_items: list, sketch_lines: list,
                        part_path: str = "") -> tuple:
    """Detect how many ends of each body are physically capped by another body.

    Overview
    --------
    For each body:
      1. Find its long axis and bbox centre (_match_body_to_direction).
      2. Compute two test points — one just outside each end face (epsilon=0.1mm).
      3. Check every other body's bounding box: if a test point falls inside
         another body's bbox, that end is capped.
      4. Associate the body with a cut list item (by length match) so the
         result maps to the correct row index in raw_items.

    Capping detection method
    ------------------------
    Uses _bbox_contains_point (bounding box containment) rather than
    IBody2.ContainsPoint, which does not exist in the SW 2024 dispatch
    interface.  Bbox containment is reliable for rectilinear extruded profiles
    whose bboxes closely match their physical bodies.

    Body ↔ cut list item association
    ---------------------------------
    Uses the body's bounding-box max-extent as its "length" and matches it
    against raw_items[i].length_mm within LENGTH_MATCH_TOLERANCE_MM (1 mm).
    Bodies that don't match any item length (e.g. end caps, plates) are
    assigned None and act only as potential cappers for other bodies.
    When two or more items share the same length, bodies are distributed
    round-robin (relies on GetBodies2 return order, which may vary between
    SW sessions).

    LIMITATION — non-square cross-sections (e.g. 45×90 profiles):
        body_length_mm = max(bbox extents) works correctly only when the
        profile length is greater than the largest cross-section dimension.
        For a 80 mm piece of 45×90 profile, max extent = 90 mm (cross-section
        height) → wrong length → body not matched to its cut list item →
        D17 state not computed for that body.

        To support 45×90, replace the single max(extents) call with a loop
        that tries each of the three bbox axes and picks the axis whose extent
        matches an item length.  The same chosen axis should also be used as
        the profile's unit_axis (currently computed separately in
        _match_body_to_direction, which has the same limitation).

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
    item_cross_dims: dict = {}
    warnings_out: list = []
    epsilon = 0.0001  # 0.1 mm in metres

    if not bodies or not raw_items:
        return item_caps, item_cross_dims, warnings_out

    # Build per-body info
    body_data = []
    for body in bodies:
        center = np.zeros(3)
        axis = np.array([1.0, 0.0, 0.0])
        body_length_mm = None
        body_bbox = None
        cross_dims_mm = None
        try:
            box = body.GetBodyBox()
            if isinstance(box, tuple) and len(box) >= 6:
                xmin, ymin, zmin, xmax, ymax, zmax = box[:6]
                body_bbox = (xmin, ymin, zmin, xmax, ymax, zmax)
                center = np.array([
                    (xmin + xmax) / 2.0,
                    (ymin + ymax) / 2.0,
                    (zmin + zmax) / 2.0,
                ])
                extents_mm = [
                    (xmax - xmin) * 1000.0,
                    (ymax - ymin) * 1000.0,
                    (zmax - zmin) * 1000.0,
                ]
                axis_idx, length_mm_sel, cross = _select_length_axis(extents_mm, raw_items)
                if axis_idx is not None:
                    body_length_mm = length_mm_sel
                    cross_dims_mm = cross
                    axis = np.zeros(3)
                    axis[axis_idx] = 1.0
                else:
                    # Capper body — axis irrelevant; keep argmax fallback for completeness
                    _, axis = _match_body_to_direction(body, sketch_lines)
        except Exception:
            pass
        body_data.append((body, center, axis, body_length_mm, body_bbox, cross_dims_mm))

    # Associate each body with a raw_items index
    assign_counts: dict = {}
    body_item_idx: list = []
    for body, center, axis, body_length_mm, body_bbox, cross_dims_mm in body_data:
        matching = []
        if body_length_mm is not None:
            for i, item in enumerate(raw_items):
                if abs(item.length_mm - body_length_mm) <= LENGTH_MATCH_TOLERANCE_MM:
                    matching.append(i)
        if matching:
            chosen = min(matching, key=lambda i: assign_counts.get(i, 0))
            assign_counts[chosen] = assign_counts.get(chosen, 0) + 1
            body_item_idx.append(chosen)
            if cross_dims_mm is not None:
                item_cross_dims.setdefault(chosen, []).append(cross_dims_mm)
        else:
            if body_length_mm is not None and raw_items:
                fname = os.path.basename(part_path) if part_path else "?"
                warnings_out.append(
                    f"Body sem correspondência exata em '{fname}' "
                    f"(body_length≈{body_length_mm:.1f}mm) — ignorado como tampo"
                )
            body_item_idx.append(None)

    # Bounding-box containment check
    for idx, (body, center, axis, body_length_mm, body_bbox, cross_dims_mm) in enumerate(body_data):
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
        for other_idx, (_, _, _, _, other_bbox, _) in enumerate(body_data):
            if other_idx == idx:
                continue
            if not end1_capped:
                end1_capped = _bbox_contains_point(
                    other_bbox, float(test1[0]), float(test1[1]), float(test1[2]))
            if not end2_capped:
                end2_capped = _bbox_contains_point(
                    other_bbox, float(test2[0]), float(test2[1]), float(test2[2]))
            if end1_capped and end2_capped:
                break

        capped = int(end1_capped) + int(end2_capped)
        item_caps.setdefault(item_i, []).append(capped)

    return item_caps, item_cross_dims, warnings_out


def _get_cut_list_prop(feat, prop_name: str) -> str:
    """Read a custom property from a CutListFolder IFeature via CustomPropertyManager.

    IFeature.GetCustomInfoValue does not exist in SW 2024 early-bound stubs.
    Uses Get4 (returns tuple) with fallback to Get().
    """
    try:
        mgr = feat.CustomPropertyManager
        try:
            result = mgr.Get4(prop_name, False)
            if isinstance(result, tuple) and len(result) > 1:
                val = result[2] if (len(result) > 2 and result[2]) else result[1]
                return str(val).strip() if val is not None else ""
        except Exception:
            pass
        val = mgr.Get(prop_name)
        return str(val).strip() if val is not None else ""
    except Exception:
        return ""


def get_weldment_cut_list(sw, part_path: str) -> tuple:
    """
    Open part_path and read its weldment cut list by iterating CutListFolder features.

    Returns (items, warnings):
      items:    list[CutListItem] — one entry per non-suppressed CutListFolder
      warnings: list[str]        — human-readable warnings (QUANTITY missing, etc.)

    Properties are read via feat.CustomPropertyManager (ICustomPropertyManager),
    using Get4 with useCached=False, falling back to Get().
    GetCustomInfoValue does NOT exist on IFeature in SW 2024 early-bound stubs.
    LENGTH is a plain mm string — parsed as float, no unit conversion needed.
    QUANTITY primary key is "QUANTITY"; fallback "QTY"; default 1 if neither found.

    SW 2024 quirks applied:
      - IPartDoc.FirstFeature() for iteration (not IModelDoc2.FirstFeature)
      - callable-guard on IsSuppressed (property-as-attribute in SW 2024 stubs)
      - normalised path for CloseDoc
      - feat.CustomPropertyManager instead of feat.GetCustomInfoValue (missing in stubs)
    """
    part_path = os.path.normpath(os.path.abspath(part_path))
    doc = None
    warnings = []

    try:
        doc = _open_doc(sw, part_path, doc_type=1, silent=True)
        part = _wrap(doc, "IPartDoc")

        feat_raw = part.FirstFeature()
        feat = _wrap(feat_raw, "IFeature") if feat_raw is not None else None

        items = []
        while feat is not None:
            type_name_ref = feat.GetTypeName2
            type_name = type_name_ref() if callable(type_name_ref) else str(type_name_ref)

            if type_name == "CutListFolder":
                is_sup_ref = feat.IsSuppressed
                suppressed = is_sup_ref() if callable(is_sup_ref) else bool(is_sup_ref)

                if not suppressed:
                    desc = _get_cut_list_prop(feat, "DESCRIPTION")
                    length_str = _get_cut_list_prop(feat, "LENGTH")
                    qty_str = _get_cut_list_prop(feat, "QUANTITY")
                    if not qty_str:
                        qty_str = _get_cut_list_prop(feat, "QTY")

                    # Parse length — skip folder if missing/invalid
                    try:
                        length_mm = float(length_str)
                    except (ValueError, TypeError):
                        next_raw = feat.GetNextFeature()
                        feat = _wrap(next_raw, "IFeature") if next_raw is not None else None
                        continue

                    # Parse qty — warn if neither key found
                    if qty_str:
                        try:
                            qty = int(float(qty_str))
                        except (ValueError, TypeError):
                            qty = 1
                    else:
                        name_ref = feat.Name
                        feat_name = name_ref() if callable(name_ref) else str(name_ref)
                        warnings.append(
                            f"QUANTITY/QTY não encontrado em '{feat_name}' — assumido qty=1"
                        )
                        qty = 1

                    if desc:
                        items.append(CutListItem(desc, length_mm, qty))

            next_raw = feat.GetNextFeature()
            feat = _wrap(next_raw, "IFeature") if next_raw is not None else None

        # --- Capped-end detection (post-processing) ---
        try:
            bodies_raw = part.GetBodies2(0, False)
            if bodies_raw is None:
                bodies_raw = []
            if isinstance(bodies_raw, tuple):
                bodies_raw = list(bodies_raw)
            if not isinstance(bodies_raw, list):
                bodies_raw = []
            all_bodies = [_wrap(b, "IBody2") for b in bodies_raw if b is not None]

            if all_bodies and items:
                sketch_lines = _get_sketch_directions(part)
                if not sketch_lines:
                    warnings.append(
                        "Sem 3DSketch encontrado — fallback para eixo bounding box "
                        "(perfis não-ortogonais podem ter capping incorreto)"
                    )
                item_caps, item_cross_dims, cap_warns = _detect_capped_ends(
                    all_bodies, items, sketch_lines, part_path)
                warnings.extend(cap_warns)

                if item_caps:
                    expanded = []
                    for i, item in enumerate(items):
                        caps = item_caps.get(i)
                        if caps is None:
                            expanded.append(item)
                            continue
                        holes_per_end = _holes_per_end_from_description(item.description)
                        if holes_per_end is None:
                            cross_list = item_cross_dims.get(i)
                            cross_dims = cross_list[0] if cross_list else []
                            holes_per_end = _classify_profile_holes(cross_dims) if cross_dims else "VERIFICAR"
                        state_counter = Counter(caps)
                        for capped in sorted(state_counter, reverse=True):
                            suffix = _d17_suffix(capped, holes_per_end)
                            expanded.append(CutListItem(
                                item.description + suffix,
                                item.length_mm,
                                state_counter[capped],
                            ))
                    items = expanded
        except Exception as _cap_exc:
            warnings.append(f"Capping detection falhou: {_cap_exc}")

        return items, warnings

    finally:
        if doc is not None:
            try:
                sw.CloseDoc(part_path)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# STEP export — temporary copy
# ---------------------------------------------------------------------------

def copy_part_to_tmp(sldprt_path: str, tmp_dir: str) -> str:
    """
    Copy a .sldprt file to tmp_dir with a '_step_tmp' suffix.
    Creates tmp_dir if it does not exist.
    Returns the full path of the copy.
    """
    os.makedirs(tmp_dir, exist_ok=True)
    name, ext = os.path.splitext(os.path.basename(sldprt_path))
    tmp_path = os.path.join(tmp_dir, f"{name}_step_tmp{ext}")
    shutil.copy2(sldprt_path, tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# STEP export — dowel hole detection
# ---------------------------------------------------------------------------

# Dowel hole constants — swWzdHoleStandardFastenerTypes_e
# Every Dowel Hole standard maps to one of these FastenerType2 values.
_DOWEL_FASTENER_TYPES = frozenset({
    703,  # swStandardAnsiInchDowelHole
    706,  # swStandardBSIDowelHole
    707,  # swStandardDINDowelHole
    710,  # swStandardISODowelHole  ← most common in EU projects
    711,  # swStandardJISDowelHole
})


def get_dowel_holes(part_doc) -> list:
    """
    Return a list of HoleInfo for every Hole Wizard Dowel hole in the part.

    SW 2024: GetSpecificFeature2() returns None for HoleWzd features.
    Correct approach:
      1. Filter by GetTypeName2() == "HoleWzd"
      2. GetDefinition() → IWizardHoleFeatureData2
      3. AccessSelections(doc, None) before reading properties
      4. Check FastenerType2 in _DOWEL_FASTENER_TYPES (703/706/707/710/711)
         — ALL HoleWzd features share type "HoleWzd"; FastenerType2 is the
           only reliable discriminator for Dowel vs Clearance/Tapped/CHole.
      5. Parse FastenerSize string (e.g. 'Ø20.0') — Diameter getter returns 0.0
      6. ReleaseSelectionAccess() in finally

    Returns an empty list if no dowel holes are found or on any API error.
    """
    results = []
    try:
        # IModelDoc2.FirstFeature() is MEMBERNOTFOUND in SW 2024 — must use IPartDoc.
        part = _wrap(part_doc, "IPartDoc")
        feat_raw = part.FirstFeature()
        while feat_raw is not None:
            feat = _wrap(feat_raw, "IFeature")
            try:
                type_name_ref = feat.GetTypeName2
                type_name = type_name_ref() if callable(type_name_ref) else str(type_name_ref)
                if type_name == "HoleWzd":
                    defn_raw = feat.GetDefinition()
                    feat_data = _wrap(defn_raw, "IWizardHoleFeatureData2")
                    try:
                        feat_data.AccessSelections(part_doc, None)
                        # Distinguish Dowel from Clearance/Tapped/CHole via FastenerType2.
                        # SW 2024 early binding may return a tuple — unpack if needed.
                        ft2 = feat_data.FastenerType2
                        if isinstance(ft2, tuple):
                            ft2 = ft2[0]
                        if int(ft2) in _DOWEL_FASTENER_TYPES:
                            size_str = feat_data.FastenerSize  # e.g. 'Ø20.0'
                            m = re.search(r'[\d.]+', size_str)
                            if m:
                                diameter_m = float(m.group()) / 1000.0
                                results.append(HoleInfo(feature=feat, original_diameter_m=diameter_m))
                    finally:
                        try:
                            feat_data.ReleaseSelectionAccess()
                        except Exception:
                            pass
            except Exception:
                pass
            try:
                feat_raw = feat.GetNextFeature()
            except Exception:
                break
    except Exception:
        pass

    return results


# ---------------------------------------------------------------------------
# STEP export — dowel hole modification
# ---------------------------------------------------------------------------

def modify_dowel_diameter(part_doc, hole: HoleInfo, new_diameter_m: float) -> None:
    """
    Change a dowel hole's diameter to new_diameter_m (metres).

    SW 2024 sequence:
      1. GetDefinition() → IWizardHoleFeatureData2
      2. AccessSelections(doc, None)
      3. set Diameter
      4. IFeature.ModifyDefinition(feat_data, top_doc, component) — 3 args
      5. ReleaseSelectionAccess() in finally
      6. EditRebuild3()

    Raises RuntimeError if ModifyDefinition fails.
    """
    feat = hole.feature
    defn_raw = feat.GetDefinition()
    feat_data = _wrap(defn_raw, "IWizardHoleFeatureData2")
    feat_data.AccessSelections(part_doc, None)
    result = False
    try:
        # Type=0 (swHoleType_Simple) uncouples the hole from the ISO standard table.
        # Without this, Diameter setter is silently ignored (geometry driven by table lookup).
        feat_data.Type = 0
        feat_data.Diameter = new_diameter_m
        result = feat.ModifyDefinition(defn_raw, part_doc, None)
    finally:
        try:
            feat_data.ReleaseSelectionAccess()
        except Exception:
            pass
    if not result:
        raise RuntimeError(
            f"ModifyDefinition falhou para o furo de cavilha "
            f"(diâmetro original: {hole.original_diameter_m * 1000:.1f} mm)."
        )
    part_doc.EditRebuild3()


# ---------------------------------------------------------------------------
# STEP export
# ---------------------------------------------------------------------------

def save_silent(doc) -> None:
    """
    Save a SolidWorks document silently (no dialogs) to its current path.

    Use before CloseDoc on modified tmp copies to clear the dirty flag —
    without this, SW shows a "Save changes to <file>?" dialog on close.

    Uses late binding + Save3(swSaveAsOptions_Silent=1) because early-bound
    Save3 has BYREF out-params that cause type errors.
    Errors are silently swallowed — the close will still happen, worst case
    SW shows the dialog.
    """
    try:
        import pythoncom as _pycom
        raw = getattr(doc, "_dispobj_", None) or getattr(doc, "_oleobj_", None) or doc
        late = win32com.client.Dispatch(raw)
        byref_i4 = lambda: win32com.client.VARIANT(_pycom.VT_BYREF | _pycom.VT_I4, 0)
        late.Save3(1, byref_i4(), byref_i4())  # 1 = swSaveAsOptions_Silent
    except Exception:
        pass


def export_part_to_step(sw_app, sldprt_path: str, output_step_path: str,
                        doc=None) -> None:
    """
    Export a SolidWorks part (.sldprt) to STEP AP214.

    doc: if provided, use this already-open IModelDoc2 directly (e.g. a modified
         tmp copy). Skips GetOpenDocumentByName lookup — avoids path-matching
         issues where the open doc's registered path differs from sldprt_path.
    If doc is None, looks up by path; opens silently if not found.

    Raises RuntimeError on failure.
    """
    sldprt_path = os.path.normpath(os.path.abspath(sldprt_path))
    part_doc = doc
    opened_by_us = False

    try:
        if part_doc is None:
            already_open = sw_app.GetOpenDocumentByName(sldprt_path) is not None
            if already_open:
                part_doc = sw_app.GetOpenDocumentByName(sldprt_path)
            else:
                part_doc = _open_doc(sw_app, sldprt_path, doc_type=1, silent=True)
                opened_by_us = True

        # Use late binding for SaveAs4: the type library's SaveAs4 signature is
        # (Name, Version, Options, Errors, Warnings) — no ExportData parameter.
        # Errors and Warnings must be VT_BYREF|VT_I4; late binding is required
        # because early-bound IModelDoc2 raises DISP_E_TYPEMISMATCH on BYREF params.
        import pythoncom as _pycom
        late = win32com.client.Dispatch(
            part_doc._oleobj_ if hasattr(part_doc, '_oleobj_') else part_doc
        )
        byref_i4 = lambda: win32com.client.VARIANT(_pycom.VT_BYREF | _pycom.VT_I4, 0)
        raw = late.SaveAs4(output_step_path, 0, 1, byref_i4(), byref_i4())
        result = raw[0] if isinstance(raw, tuple) else raw
        if not result:
            raise RuntimeError("SaveAs4 falhou ao exportar STEP.")

    finally:
        if opened_by_us and part_doc is not None:
            try:
                sw_app.CloseDoc(sldprt_path)
            except Exception:
                pass


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
            state_ref = comp.GetSuppression
            state = state_ref() if callable(state_ref) else state_ref
            if isinstance(state, tuple):
                state = state[0]
            if int(state) == 0:  # swComponentSuppressed=0 only
                continue
            if os.path.normpath(comp.GetPathName()).lower() == target:
                count += 1
        except Exception:
            continue
    return count


def get_custom_property_evaluated(model_doc, prop_name: str) -> str:
    """
    Return the best available value for a custom property.

    Strategy (mirrors is_laser_part which is proven to work in SW 2024):
      1. Try Get4 for the resolved/evaluated value (needed for SW expression-linked
         properties, e.g. Material linked to SW-Material expression).
         Get4 returns (retval, val, resolvedVal, wasResolved).
         Prefer result[2] (resolved); fall back to result[1] (raw).
      2. If Get4 yields nothing, fall back to the simpler Get() — more reliable
         for plain-text properties (Description, Simetria, etc.) across SW versions.
      3. If the value is still a raw SW expression (e.g. "SW-Material@part.SLDPRT"),
         Get4 did not resolve it. For Material, read directly from IPartDoc instead.

    Returns "" on any error or missing property.
    """
    try:
        mgr = model_doc.Extension.CustomPropertyManager("")
        # Step 1: Get4 with useCached=True — handles expression-linked properties.
        # useCached=False forces recalculation which fails in assembly component context;
        # True returns the pre-computed cached value (what SW displays in the property dialog).
        value = ""
        try:
            result = mgr.Get4(prop_name, True)
            if isinstance(result, tuple) and len(result) > 2:
                resolved = str(result[2]).strip() if result[2] is not None else ""
                raw      = str(result[1]).strip() if result[1] is not None else ""
                value = resolved if resolved else raw
        except Exception:
            pass
        # Step 2: simpler Get() — reliable for plain-text props across SW versions
        if not value:
            val = mgr.Get(prop_name)
            value = str(val).strip() if val is not None else ""
        # Step 3: strip literal quotes SW sometimes wraps around raw expressions,
        # then resolve Material expression via IPartDoc when Get4/Get() did not evaluate it.
        if value:
            value = value.strip('"\'')
            if prop_name == "Material" and _SW_EXPR_RE.match(value):
                # Raw SW expression — try to resolve via IPartDoc.
                # If the part has no material assigned, return "" (empty cell).
                value = _get_part_material(model_doc)
        return value
    except Exception:
        return ""


_SW_EXPR_RE = re.compile(
    r'^SW-[A-Za-z]+@.+\.(SLDPRT|SLDASM|SLDDRW)$', re.IGNORECASE
)


def _get_part_material(model_doc) -> str:
    """
    Get the assigned material name directly from IPartDoc, bypassing the custom
    property expression indirection ("SW-Material@part.SLDPRT").
    Returns "" on any error or if no material is assigned.

    SW 2024: IPartDoc.GetMaterialPropertyName2(configName) returns a tuple
    (material_name, database_name) via early binding — extract index [0].
    IPartDoc2 fails with BADPARAMCOUNT; use IPartDoc only.
    """
    try:
        part = _wrap(model_doc, "IPartDoc")
        mat = part.GetMaterialPropertyName2("")
        # Early binding returns (name, database) tuple in SW 2024
        if isinstance(mat, tuple):
            mat = mat[0]
        if mat:
            return str(mat).strip()
    except Exception:
        pass
    return ""


def _get_sheet_metal_thickness(model_doc) -> "float | None":
    """
    Return the material thickness for a sheet metal part in mm by reading the
    SheetMetal feature data (GetTypeName2() == "SheetMetal").

    Mirrors the HoleWzd pattern from CLAUDE.md: GetDefinition() → wrap interface
    → AccessSelections → read property → ReleaseSelectionAccess.
    ISheetMetalFeatureData2.Thickness is in metres.
    Returns None if not a sheet metal part or on any error.

    SW 2024: FirstFeature()/GetNextFeature() are not accessible via early-binding
    IModelDoc2 stubs (MEMBERNOTFOUND). Use late binding for feature iteration,
    consistent with the SaveAs4 pattern documented in CLAUDE.md.
    """
    try:
        # FirstFeature() is on IPartDoc (not IModelDoc2) in the SW type library stubs.
        # Cast model_doc → IPartDoc for iteration; use IFeature for type/definition calls.
        # Thickness property is absent from ISheetMetalFeatureData stubs → late binding.
        import win32com.client
        part = _wrap(model_doc, "IPartDoc")
        feat = _wrap(part.FirstFeature(), "IFeature")
        while feat is not None:
            try:
                type_name_ref = feat.GetTypeName2
                type_name = type_name_ref() if callable(type_name_ref) else str(type_name_ref)
                if type_name == "SheetMetal":
                    defn = feat.GetDefinition()
                    if defn is not None:
                        defn_raw = (getattr(defn, "_dispobj_", None)
                                    or getattr(defn, "_oleobj_", None)
                                    or defn)
                        thickness_m = win32com.client.Dispatch(defn_raw).Thickness
                        if thickness_m and thickness_m > 0:
                            return round(thickness_m * 1000, 2)
            except Exception:
                pass
            next_feat = feat.GetNextFeature()
            feat = _wrap(next_feat, "IFeature") if next_feat is not None else None
    except Exception:
        pass
    return None


def get_bounding_box_thickness(model_doc) -> "float | None":
    """
    Return the part thickness in mm (2 d.p.).

    For sheet metal parts, reads the SheetMetal feature thickness directly —
    more reliable than bounding box for bent/formed parts where the bounding
    box minimum may not equal the material thickness.

    Falls back to the bounding box minimum dimension for non-sheet-metal parts.
    GetPartBox(True) returns (xmin, ymin, zmin, xmax, ymax, zmax) in metres.
    Returns None on any error.
    """
    try:
        sm_thickness = _get_sheet_metal_thickness(model_doc)
        if sm_thickness is not None:
            return sm_thickness
        part = _wrap(model_doc, "IPartDoc")
        box = part.GetPartBox(True)
        dx = abs(box[3] - box[0])
        dy = abs(box[4] - box[1])
        dz = abs(box[5] - box[2])
        return round(min(dx, dy, dz) * 1000, 2)
    except Exception:
        return None


def get_part_data(component, all_components: list) -> dict:
    """
    Collect all display-quality data for one part component.
    Call chain: component.GetPathName() → count_instances
                component.GetModelDoc2() → custom properties + bounding box

    Returns a dict with keys: qty, part_number, Description, Corte_Fabrico,
    Simetria, Material, TratSuperficial, espessura.
    These keys match the column_order lists in excel_writer.py.
    """
    path_ref = component.GetPathName
    part_path = path_ref() if callable(path_ref) else path_ref
    if isinstance(part_path, tuple):
        part_path = part_path[0]
    model_ref = component.GetModelDoc2
    model_doc = model_ref() if callable(model_ref) else model_ref
    if isinstance(model_doc, tuple):
        model_doc = model_doc[0]

    data = {}
    data["qty"]         = count_instances(all_components, part_path)
    data["part_number"] = os.path.splitext(os.path.basename(part_path))[0]
    data["espessura"]   = get_bounding_box_thickness(model_doc)

    for prop in ("Description", "Corte_Fabrico", "Simetria", "Material", "TratSuperficial"):
        val = get_custom_property_evaluated(model_doc, prop)
        # SW sometimes wraps the raw expression in literal quote characters
        # e.g. '"SW-Material@part.SLDPRT"' — strip them before matching.
        val = val.strip('"\'')
        # If the value is a SW expression reference (e.g. SW-Material@part.SLDPRT),
        # Get4 did not resolve it. For Material, read directly from IPartDoc instead.
        if _SW_EXPR_RE.match(val):
            if prop == "Material":
                val = _get_part_material(model_doc) or val
            else:
                val = ""  # Other SW expressions shouldn't appear; return empty
        data[prop] = val

    return data


# ---------------------------------------------------------------------------
# BOM traversal
# ---------------------------------------------------------------------------

def get_bom_components(assembly_doc) -> tuple:
    """
    Traverse the top-level assembly and return a flat list of BomComponent.
    assembly_doc: IModelDoc2 (same type returned by open_assembly).
    Returns (bom_flat: list[BomComponent], warnings: list[str]).
    """
    bom_flat = []
    warnings = []

    # Resolve lightweight components before traversal so GetModelDoc2() works.
    # ResolveAllLightweightComponents is NOT in SW 2024 early-binding IAssemblyDoc stubs
    # → use late binding (same pattern as SaveAs4 and Thickness in project-guide).
    try:
        asm = _wrap(assembly_doc, "IAssemblyDoc")
        asm_raw = getattr(asm, "_dispobj_", None) or getattr(asm, "_oleobj_", None) or asm
        win32com.client.Dispatch(asm_raw).ResolveAllLightweightComponents(False)
    except Exception as _resolve_ex:
        warnings.append(f"AVISO ResolveAllLightweightComponents falhou: {_resolve_ex}")

    try:
        config = assembly_doc.ConfigurationManager.ActiveConfiguration
    except Exception as e:
        warnings.append(f"Erro ao obter componentes [ConfigurationManager]: {e}")
        return bom_flat, warnings
    try:
        root_ref = config.GetRootComponent3
        root_raw = root_ref(True) if callable(root_ref) else root_ref
        if isinstance(root_raw, tuple):
            root_raw = root_raw[0]
        root = root_raw
    except Exception as e:
        warnings.append(f"Erro ao obter componentes [GetRootComponent3]: {e}")
        return bom_flat, warnings
    try:
        children_ref = root.GetChildren
        children = children_ref() if callable(children_ref) else children_ref
        if isinstance(children, tuple):
            children = list(children)
    except Exception as e:
        warnings.append(f"Erro ao obter componentes [GetChildren]: {e}")
        return bom_flat, warnings
    if children:
        for child in children:
            _bom_traverse(child, bom_flat, warnings)
    return bom_flat, warnings


def _bom_traverse(comp, bom_flat, warnings, _dbg=False):
    """Recursive BOM traversal — appends BomComponent entries to bom_flat."""
    path = "(desconhecido)"
    try:
        comp = _wrap(comp, "IComponent2")
        try:
            # Use GetSuppression() instead of IsSuppressed: in SW 2024, IsSuppressed
            # returns True for lightweight components (state=1) which appear active in
            # the Feature Tree. GetSuppression() returns swComponentSuppressed=0 only
            # for truly suppressed components; lightweight=1, resolved=4 are active.
            state_ref = comp.GetSuppression
            state = state_ref() if callable(state_ref) else state_ref
            if isinstance(state, tuple):
                state = state[0]
            suppressed = (int(state) == 0)  # swComponentSuppressed = 0
        except Exception as _sup_ex:
            if _dbg:
                warnings.append(f"DBG GetSuppression EXCECAO: {_sup_ex}")
            suppressed = True   # on exception, treat as suppressed — skip
        if suppressed:
            if _dbg:
                warnings.append(f"DBG SUPRIMIDO: {path}")
            return

        path_ref = comp.GetPathName
        path_val = path_ref() if callable(path_ref) else path_ref
        if isinstance(path_val, tuple):
            path_val = path_val[0]
        path = os.path.normpath(path_val)
        basename = os.path.splitext(os.path.basename(path))[0]
        basename = re.sub(r'-\d+$', '', basename)   # strip SW instance suffix

        if _dbg:
            warnings.append(f"DBG VISITA: {basename} | path={path}")

        model_ref = comp.GetModelDoc2
        model = model_ref() if callable(model_ref) else model_ref
        if isinstance(model, tuple):
            model = model[0]
        if model is None:
            # Model doc not loaded — sub-assembly is lightweight or not yet resolved.
            # GetChildren() works via the parent assembly's component tree even when
            # the sub-assembly model file isn't loaded, so recurse into children.
            ext = os.path.splitext(path)[1].lower()
            if _dbg:
                warnings.append(f"DBG MODEL_NONE: {basename} | ext={ext}")
            if ext == '.sldasm':
                children_ref = comp.GetChildren
                children = children_ref() if callable(children_ref) else children_ref
                n = len(children) if children else 0
                if _dbg:
                    warnings.append(f"DBG MODEL_NONE filhos: {basename} | n={n}")
                if children:
                    for child in children:
                        _bom_traverse(child, bom_flat, warnings, _dbg=_dbg)
            elif ext == '.sldprt':
                # Lightweight part — model not loaded but path/basename are available.
                # Classify by name the same way as the normal (model loaded) path.
                m2 = re.match(r'^\d+\.(\d+)\.\d+$', basename)
                if m2:
                    group = int(m2.group(1))
                    if group == 800:
                        bom_flat.append(BomComponent(comp, path, "comercial"))
                    else:
                        bom_flat.append(BomComponent(comp, path, "producao"))
                elif re.match(r'^[A-Za-z]{3}\.', basename):
                    bom_flat.append(BomComponent(comp, path, "comercial"))
                else:
                    warnings.append(f"Componente ignorado (nome não reconhecido): {basename}")
            return

        doc_type = model.GetType
        if callable(doc_type):
            doc_type = doc_type()

        m = re.match(r'^\d+\.(\d+)\.\d+$', basename)
        if not m:
            # 3-letter prefix names (e.g. BOS.040.001, IFM.010.007, SIC.050.001) → comercial
            if re.match(r'^[A-Za-z]{3}\.', basename):
                bom_flat.append(BomComponent(comp, path, "comercial"))
                return
            # Organizer sub-assembly with non-standard name → still recurse into children
            if doc_type == 2:
                children_ref = comp.GetChildren
                children = children_ref() if callable(children_ref) else children_ref
                if children:
                    for child in children:
                        _bom_traverse(child, bom_flat, warnings, _dbg=_dbg)
                return
            # Unrecognized part name → warn and skip
            warnings.append(f"Componente ignorado (nome não reconhecido): {basename}")
            return

        group = int(m.group(1))

        if group == 800:
            # Commercial item — record as single purchasable unit, do not recurse
            bom_flat.append(BomComponent(comp, path, "comercial"))
            return

        if doc_type == 1:   # swDocPART
            bom_flat.append(BomComponent(comp, path, "producao"))
        elif doc_type == 2:  # swDocASSEMBLY
            children_ref = comp.GetChildren
            children = children_ref() if callable(children_ref) else children_ref
            if children:
                for child in children:
                    _bom_traverse(child, bom_flat, warnings, _dbg=_dbg)
        # doc_type 3 (drawing) and others are silently ignored

    except Exception as e:
        warnings.append(f"Erro ao processar componente '{path}': {e}")


def count_bom_instances(bom_flat: list, part_path: str) -> int:
    """Count entries in bom_flat matching part_path (case-insensitive normpath)."""
    target = os.path.normpath(part_path).lower()
    return sum(1 for bc in bom_flat
               if os.path.normpath(bc.path).lower() == target)


def deduplicate_bom_by_path(bom_components: list) -> list:
    """Return list with duplicate paths removed; first occurrence preserved."""
    seen = set()
    unique = []
    for bc in bom_components:
        key = os.path.normpath(bc.path).lower()
        if key not in seen:
            seen.add(key)
            unique.append(bc)
    return unique
