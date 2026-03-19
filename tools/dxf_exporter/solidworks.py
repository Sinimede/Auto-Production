"""
solidworks.py — SolidWorks COM API wrapper.

All SolidWorks interactions are isolated here. Requires SolidWorks to be
running. Uses win32com with early-binding stubs generated from sldworks.tlb:

    python -m win32com.client.makepy "C:\\Program Files\\SOLIDWORKS Corp\\SOLIDWORKS\\sldworks.tlb"

Run the above once per machine. The stubs are stored in %TEMP%\\gen_py\\ and
enable correct array marshalling for methods like GetComponents.
"""

import os
from typing import List, Optional

import pythoncom
import win32com.client
from win32com.client import gencache

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
    The early-binding constructor (DispatchBaseClass.__init__) requires a raw
    PyIDispatch as input. Python COM wrappers (CoClass, CDispatch, or other
    DispatchBaseClass subclasses) all store it under '_oleobj_' or '_dispobj_'.
    This function peels those layers to reach the raw PyIDispatch before wrapping.
    Returns the wrapped object, or the original if wrapping fails.
    """
    try:
        mod = _sw_module()
        cls = getattr(mod, interface_name)
        if isinstance(obj, cls):
            return obj  # Already early-bound to the correct type

        # CoClass objects (e.g. SldWorks from GetActiveObject) store the
        # interface wrapper under '_dispobj_'.
        inner = obj.__dict__.get('_dispobj_')
        if inner is not None:
            if isinstance(inner, cls):
                return inner
            obj = inner  # descend into the interface wrapper

        # Any remaining Python wrapper (CDispatch, DispatchBaseClass subclass)
        # stores the raw PyIDispatch under '_oleobj_'. Extract it so the
        # DispatchBaseClass constructor receives a proper PyIDispatch.
        raw = obj.__dict__.get('_oleobj_')
        if raw is not None and type(raw).__name__ == 'PyIDispatch':
            obj = raw

        return cls(obj)
    except Exception:
        return obj


def _byref_long(value: int = 0):
    """Create a VARIANT ByRef Long for COM out-parameters (Errors/Warnings)."""
    return win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, value)


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


def get_all_parts(assembly_doc) -> List:
    """
    Return all unique part IComponent2 objects in the assembly, recursively.
    Uses IAssemblyDoc.GetComponents via early-binding cast (CastTo) which fixes
    the array marshalling issue present in late-binding.
    Suppressed or unresolvable parts are skipped.
    """
    # Wrap assembly doc for correct array marshalling in GetComponents.
    asm = _wrap(assembly_doc, "IAssemblyDoc")

    # Resolve lightweight components so their data is accessible
    try:
        asm.ResolveAllLightweightComponents(False)
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
            root = config.GetRootComponent3(True)  # True = resolve
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
                comp.SetComponentState(3)  # swComponentFullyResolved = 3
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
        children = component.GetChildren()
    except Exception:
        return result
    if not children:
        return result
    for child in children:
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
    (case-insensitive). Examples that match: 'LASER', 'Laser', 'LASER+QUINAGEM'.
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
        return "laser" in str(val).strip().lower()
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

        errors   = _byref_long()
        warnings = _byref_long()
        result = drw_doc.SaveAs4(output_dxf_path, 0, 1, None, errors, warnings)
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

def _open_doc(sw_app, path: str, doc_type: int):
    """
    Open a SolidWorks document.
    doc_type: 1 = part, 2 = assembly, 3 = drawing.
    options=0 (non-silent) ensures the full component tree is loaded for assemblies.
    Raises RuntimeError if the document cannot be opened.
    """
    errors   = _byref_long()
    warnings = _byref_long()
    doc = sw_app.OpenDoc6(path, doc_type, 0, "", errors, warnings)
    if doc is None:
        err_val = errors.value if hasattr(errors, "value") else errors
        raise RuntimeError(
            f"Não foi possível abrir '{path}'. Código de erro: {err_val}"
        )
    return doc
