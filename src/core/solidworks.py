import win32api
import win32con
import subprocess
import pythoncom
import win32com.client
from win32com.client import gencache
import hashlib
import olefile
import os
import shutil
import numpy as np
import re
import unicodedata
from typing import List, Optional, Tuple, Dict, Any
from collections import namedtuple, Counter

# --- NamedTuples ---
HoleInfo = namedtuple('HoleInfo', ['feature', 'original_diameter_m'])
BomComponent = namedtuple('BomComponent', ['component', 'path', 'comp_type'])
CutListItem = namedtuple('CutListItem', ['description', 'length_mm', 'qty'])

# --- Constants ---
LENGTH_MATCH_TOLERANCE_MM = 1.0
_SW_TLB_GUID = '{83A33D31-27C5-11CE-BFD4-00400513BB57}'
_SW_TLB_MAJOR = 32
_SW_TLB_MINOR = 0
_SW_EXPR_RE = re.compile(r'^SW-[A-Za-z]+@.+\.(SLDPRT|SLDASM|SLDDRW)$', re.IGNORECASE)

_DOWEL_FASTENER_TYPES = frozenset({703, 706, 707, 710, 711})

# --- Decorator ---
def ensure_sw_connection(func):
    """
    Decorator that ensures a connection to SolidWorks exists before executing a method.
    Automatically attempts to reconnect if a 'disconnected' COM error occurs.
    """
    def wrapper(self, *args, **kwargs):
        if not self.sw or not self._is_alive():
            self.connect()
        try:
            return func(self, *args, **kwargs)
        except Exception as e:
            # RPC_E_DISCONNECTED or similar COM errors
            err_msg = str(e).lower()
            if "disconnected" in err_msg or "-2147417848" in err_msg:
                self.connect()
                return func(self, *args, **kwargs)
            raise
    return wrapper

class SolidWorksClient:
    """
    Unified client for interacting with SolidWorks COM API and Process management.
    Encapsulates SW 2024 quirks like early/late binding and callable-guards.
    """
    def __init__(self):
        self.sw = None
        self._mod = None
        self._sw_exe_path = self._find_sw_exe()

    def _find_sw_exe(self) -> str:
        """Locates the SOLIDWORKS executable in common installation paths."""
        common_paths = [
            r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\SLDWORKS.exe",
            r"C:\Program Files\SOLIDWORKS 2024\SOLIDWORKS\SLDWORKS.exe",
            r"C:\Program Files\SOLIDWORKS 2023\SOLIDWORKS\SLDWORKS.exe",
        ]
        for path in common_paths:
            if os.path.exists(path):
                return path
        return ""

    def connect(self):
        """Connects to the active SolidWorks instance with aggressive retry."""
        if self.sw and self._is_alive():
            return True
            
        print("DEBUG: SW Client - connect() called", flush=True)
        try:
            # Clean up thread state
            try: 
                print("DEBUG: SW Client - CoUninitialize", flush=True)
                pythoncom.CoUninitialize()
            except: 
                pass
            print("DEBUG: SW Client - CoInitialize", flush=True)
            pythoncom.CoInitialize()
            
            # Try to get active object
            try:
                print("DEBUG: SW Client - GetActiveObject", flush=True)
                raw = win32com.client.GetActiveObject("SldWorks.Application")
            except Exception as e:
                print(f"DEBUG: SW Client - GetActiveObject failed ({e}), trying Dispatch", flush=True)
                # Fallback to Dispatch (sometimes works when GetActiveObject fails)
                raw = win32com.client.Dispatch("SldWorks.Application")
            
            if not raw:
                print("DEBUG: SW Client - raw object is None", flush=True)
                raise RuntimeError("SolidWorks não está a correr.")
                
            print("DEBUG: SW Client - Wrapping object", flush=True)
            self.sw = self._wrap(raw, "ISldWorks")
            # Try a simple call to verify responsiveness
            print("DEBUG: SW Client - Checking RevisionNumber", flush=True)
            self.sw.RevisionNumber()
            print("DEBUG: SW Client - Connected successfully", flush=True)
            return True
        except Exception as e:
            print(f"DEBUG: SW Client - Exception in connect: {e}", flush=True)
            err_msg = str(e)
            if "-2147221021" in err_msg:
                raise RuntimeError("SolidWorks está ocupado ou com um diálogo aberto. Feche todas as janelas no SolidWorks e tente novamente.")
            return False

    def _is_alive(self) -> bool:
        """Checks if the SW COM object is still responsive."""
        try:
            self.sw.RevisionNumber()
            return True
        except:
            return False

    def _get_mod(self):
        """Loads and caches the early-binding module."""
        if not self._mod:
            self._mod = gencache.GetModuleForTypelib(_SW_TLB_GUID, 0, _SW_TLB_MAJOR, _SW_TLB_MINOR)
        return self._mod

    def _wrap(self, obj, interface_name: str):
        """Wraps a raw COM object with its early-binding interface."""
        try:
            mod = self._get_mod()
            cls = getattr(mod, interface_name)
            if isinstance(obj, cls):
                return obj
            for attr in ('_dispobj_', '_oleobj_'):
                inner = obj.__dict__.get(attr) or getattr(obj, attr, None)
                if inner is not None:
                    try:
                        return cls(inner)
                    except:
                        pass
            return cls(obj)
        except:
            return obj

    def _safe_call(self, obj, attr_name: str, *args):
        """Helper to handle SW 2024 callable-guards and extract values from VARIANTs recursively."""
        try:
            ref = getattr(obj, attr_name)
            val = ref(*args) if callable(ref) else ref
            
            # Recursively unwrap VARIANTs and single-element tuples
            for _ in range(5): # Limit recursion to avoid infinite loops
                if hasattr(val, "value"): # win32com VARIANT
                    val = val.value
                elif isinstance(val, (tuple, list)) and len(val) == 1:
                    val = val[0]
                else:
                    break
            return val
        except:
            return None

    def set_read_only(self, path: str, read_only: bool):
        """Sets or removes the Read-Only file attribute using win32api."""
        path = os.path.normpath(os.path.abspath(path))
        if not os.path.exists(path): return
        
        attrs = win32api.GetFileAttributes(path)
        if read_only:
            attrs |= win32con.FILE_ATTRIBUTE_READONLY
        else:
            attrs &= ~win32con.FILE_ATTRIBUTE_READONLY
        win32api.SetFileAttributes(path, attrs)

    def launch_sw_with_file(self, file_path: str):
        """
        PDM-style launch: 
        1. Tries to connect to an active instance via COM.
        2. If fails or not alive, launches the process via subprocess.
        """
        file_path = os.path.normpath(os.path.abspath(file_path))
        
        # 1. Try COM (Fastest if open)
        try:
            if self.connect():
                self.open_doc(file_path)
                return True
        except:
            pass
            
        # 2. Try Process Launch (If closed)
        if self._sw_exe_path and os.path.exists(self._sw_exe_path):
            print(f"DEBUG: Launching SW process: {self._sw_exe_path}")
            subprocess.Popen([self._sw_exe_path, file_path])
            return True
        
        # 3. Last Resort: OS Association
        print("DEBUG: SW Exe not found, using OS association")
        os.startfile(file_path)
        return True

    @ensure_sw_connection
    def get_dependencies(self, path: str) -> List[str]:
        """Returns a list of immediate dependencies for a SolidWorks document."""
        path = os.path.normpath(os.path.abspath(path))
        deps = self.sw.GetDocumentDependencies2(path, True, False, False)
        if not deps:
            return []
        
        paths = []
        if isinstance(deps, tuple):
            for i in range(0, len(deps), 2):
                dep_path = os.path.normpath(deps[i])
                if dep_path.lower() != path.lower() and dep_path not in paths:
                    paths.append(dep_path)
        return paths

    # --- Document Management ---

    @ensure_sw_connection
    def open_doc(self, path: str, doc_type: int = 0, silent: bool = False) -> Tuple[Any, bool]:
        """Opens a SolidWorks document (Part, Assembly, Drawing) with auto-detection."""
        path = os.path.normpath(os.path.abspath(path))
        ext = os.path.splitext(path)[1].lower()
        
        if doc_type == 0:
            doc_type = 1 # swDocPART
            if ext == ".sldasm": doc_type = 2 # swDocASSEMBLY
            elif ext == ".slddrw": doc_type = 3 # swDocDRAWING
            
        # Check if already open
        existing = self.sw.GetOpenDocumentByName(path)
        if existing:
            self.activate_doc(path)
            return existing, False
            
        # OpenDoc6 (Options: 1 for silent if requested, 0 otherwise)
        options = 1 if silent else 0
        result = self.sw.OpenDoc6(path, doc_type, options, "", 0, 0)
        doc = result[0] if isinstance(result, tuple) else result
        if not doc:
            raise RuntimeError(f"Falha ao abrir documento: {path}")
            
        self.activate_doc(path)
        return doc, True

    @ensure_sw_connection
    def activate_doc(self, path: str):
        """Brings the specified document to the front in SolidWorks."""
        path = os.path.normpath(path)
        self.sw.ActivateDoc3(path, False, 2, 0)
        try:
            frame = self.sw.Frame()
            if frame: frame.Visible = True
        except: pass

    @ensure_sw_connection
    def close_doc(self, path: str):
        """Closes a document discarding any changes."""
        path = os.path.normpath(path)
        doc = self.sw.GetOpenDocumentByName(path)
        if doc:
            try:
                ref = doc.SetSaveFlag
                if callable(ref): ref()
            except: pass
        self.sw.CloseDoc(path)

    # --- Property Management ---

    def get_file_hash(self, file_path: str) -> str:
        """Returns the MD5 hash of a file to check for changes."""
        hasher = hashlib.md5()
        try:
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except: return ""

    def get_custom_properties_fast(self, file_path: str) -> Dict[str, str]:
        """Extracts custom properties using olefile WITHOUT opening SolidWorks."""
        if not olefile.isOleFile(file_path): return {}
        props = {}
        try:
            with olefile.OleFileIO(file_path) as ole:
                if ole.exists('\005SummaryInformation'):
                    si = ole.getproperties('\005SummaryInformation')
                    if 2 in si: props['Description'] = str(si[2])
                
                # Best effort mapping for SW common props
                mapping = {
                    "Description": ["Description", "Descrição", "Title"],
                    "Material": ["Material"],
                    "Weight": ["Weight", "Peso"],
                    "Revision": ["Revision", "Revisão"],
                    "Treatment": ["Treatment", "Tratamento"]
                }
                
                result = {}
                # (Simple mapping logic here, full OLE traversal is complex)
                for k, aliases in mapping.items():
                    if k in props: result[k] = props[k]
                return result
        except: return {}

    def get_custom_property(self, model_doc, prop_name: str) -> str:
        if not model_doc: return ""
        try:
            # Step 1: Try Get4 with useCached=True (handles expressions)
            ext = self._safe_call(model_doc, "Extension")
            if ext:
                mgr = self._safe_call(ext, "CustomPropertyManager", "")
                if mgr:
                    res = mgr.Get4(prop_name, True)
                    if isinstance(res, tuple) and len(res) > 2:
                        val = str(res[2] or res[1]).strip('"\' ')
                        if val and not _SW_EXPR_RE.match(val):
                            return val

            # Step 2: Fallback to simpler GetCustomInfoValue
            val = self._safe_call(model_doc, "GetCustomInfoValue", "", prop_name)
            if val: return str(val).strip('"\' ')
            
            return ""
        except: return ""

    def get_custom_properties(self, file_path: str) -> Dict[str, str]:
        path = os.path.normpath(os.path.abspath(file_path))
        ext = os.path.splitext(path)[1].lower()
        doc_type = {".sldprt": 1, ".sldasm": 2, ".slddrw": 3}.get(ext, 1)
        
        # 1. Check if already open
        model_doc = self.sw.GetOpenDocumentByName(path)
        was_open = model_doc is not None
        
        if not model_doc:
            result = self.sw.OpenDoc6(path, doc_type, 3, "", 0, 0)
            model_doc = result[0] if isinstance(result, tuple) else result
            
        if not model_doc: return {}
            
        try:
            props = {
                "Description": self.get_custom_property(model_doc, "Description") or self.get_custom_property(model_doc, "Descrição"),
                "Material": self.get_custom_property(model_doc, "Material"),
                "Weight": self.get_custom_property(model_doc, "Weight") or self.get_custom_property(model_doc, "Peso"),
                "Revision": self.get_custom_property(model_doc, "Revision") or self.get_custom_property(model_doc, "Revisão"),
                "Treatment": self.get_custom_property(model_doc, "Treatment") or self.get_custom_property(model_doc, "Tratamento")
            }
            # Special case for Material expressions
            if props["Material"] and _SW_EXPR_RE.match(props["Material"]):
                props["Material"] = self._get_part_material(model_doc) or props["Material"]

            return {k: v for k, v in props.items() if v}
        finally:
            if not was_open: self.sw.CloseDoc(path)

    def _get_part_material(self, model_doc) -> str:
        """Get the assigned material name directly from IPartDoc."""
        try:
            part = self._wrap(model_doc, "IPartDoc")
            mat = part.GetMaterialPropertyName2("")
            if isinstance(mat, tuple): mat = mat[0]
            return str(mat).strip() if mat else ""
        except: return ""

    # --- Engineering & Export Utilities ---

    @ensure_sw_connection
    def export_part_to_dxf(self, sldprt_path: str, output_dxf_path: str):
        """Export sheet metal flat pattern to DXF."""
        doc, was_opened = self.open_doc(sldprt_path, 1, silent=True)
        try:
            part = self._wrap(doc, "IPartDoc")
            # 1 = swExportFlatPatternViewOptions_Geometry
            if not part.ExportFlatPatternView(output_dxf_path, 1):
                raise RuntimeError("ExportFlatPatternView falhou.")
        finally:
            if was_opened: self.close_doc(sldprt_path)

    @ensure_sw_connection
    def export_drawing_to_dxf(self, slddrw_path: str, output_dxf_path: str):
        """Export drawing to DXF via SaveAs4."""
        doc, was_opened = self.open_doc(slddrw_path, 3, silent=True)
        try:
            import pythoncom
            late = win32com.client.Dispatch(self._get_raw_obj(doc))
            byref_i4 = lambda: win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            res = late.SaveAs4(output_dxf_path, 0, 1, byref_i4(), byref_i4())
            if not (res[0] if isinstance(res, tuple) else res):
                raise RuntimeError("SaveAs4 falhou para DXF.")
        finally:
            if was_opened: self.close_doc(slddrw_path)

    @ensure_sw_connection
    def export_to_step(self, file_path: str, output_step_path: str):
        """Export part or assembly to STEP AP214."""
        doc, was_opened = self.open_doc(file_path, silent=True)
        try:
            import pythoncom
            late = win32com.client.Dispatch(self._get_raw_obj(doc))
            byref_i4 = lambda: win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            # 0 = swSaveAsCurrentVersion, 1 = swSaveAsOptions_Silent
            res = late.SaveAs4(output_step_path, 0, 1, byref_i4(), byref_i4())
            if not (res[0] if isinstance(res, tuple) else res):
                raise RuntimeError("SaveAs4 falhou para STEP.")
        finally:
            if was_opened: self.close_doc(file_path)

    def save_silent(self, doc):
        """Saves a document silently to avoid UI prompts on close."""
        try:
            import pythoncom
            late = win32com.client.Dispatch(self._get_raw_obj(doc))
            byref_i4 = lambda: win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            late.Save3(1, byref_i4(), byref_i4()) # 1 = swSaveAsOptions_Silent
        except: pass

    # --- BOM & Components ---

    @ensure_sw_connection
    def get_all_parts(self, assembly_doc) -> List[Any]:
        """Recursive retrieval of all non-suppressed parts."""
        asm = self._wrap(assembly_doc, "IAssemblyDoc")
        # Late binding for ResolveAllLightweightComponents
        try:
            win32com.client.Dispatch(self._get_raw_obj(asm)).ResolveAllLightweightComponents(False)
        except: pass

        components = asm.GetComponents(False)
        if not components: return []
        
        parts = []
        for comp in components:
            comp = self._wrap(comp, "IComponent2")
            model = comp.GetModelDoc2()
            if model and self._safe_call(model, "GetType") == 1:
                parts.append(comp)
        return parts

    @ensure_sw_connection
    def get_bom_components(self, assembly_doc) -> Tuple[List[BomComponent], List[str]]:
        """Traverse assembly and classify components (produção vs comercial)."""
        bom_flat = []
        warnings = []
        
        try:
            config = assembly_doc.ConfigurationManager.ActiveConfiguration
            root = self._wrap(config.GetRootComponent3(True), "IComponent2")
            children = root.GetChildren()
            if children:
                for child in children:
                    self._bom_traverse(child, bom_flat, warnings)
        except Exception as e:
            warnings.append(f"Erro na travessia BOM: {e}")
            
        return bom_flat, warnings

    def _bom_traverse(self, comp, bom_flat, warnings):
        """Recursive BOM worker."""
        try:
            comp = self._wrap(comp, "IComponent2")
            state = self._safe_call(comp, "GetSuppression")
            if state == 0: return # Suppressed
            
            path = os.path.normpath(comp.GetPathName())
            basename = os.path.splitext(os.path.basename(path))[0]
            basename = re.sub(r'-\d+$', '', basename)
            
            model = comp.GetModelDoc2()
            doc_type = self._safe_call(model, "GetType") if model else (1 if ".sldprt" in path.lower() else 2)

            # Classification Logic
            is_comercial = bool(re.match(r'^\d+\.800\.\d+$', basename) or re.match(r'^[A-Za-z]{3}\.', basename))
            
            if is_comercial:
                bom_flat.append(BomComponent(comp, path, "comercial"))
                return
            
            if doc_type == 1: # Part
                bom_flat.append(BomComponent(comp, path, "producao"))
            elif doc_type == 2: # Assembly
                children = comp.GetChildren()
                if children:
                    for child in children:
                        self._bom_traverse(child, bom_flat, warnings)
        except Exception as e:
            warnings.append(f"Erro no componente {comp.GetPathName()}: {e}")

    # --- Weldments & Capping Detection ---

    @ensure_sw_connection
    def get_weldment_cut_list(self, part_path: str) -> Tuple[List[CutListItem], List[str]]:
        """Read weldment cut list with capping detection."""
        part_path = os.path.normpath(os.path.abspath(part_path))
        doc, was_opened = self.open_doc(part_path, 1, silent=True)
        warnings = []
        items = []
        
        try:
            part = self._wrap(doc, "IPartDoc")
            feat = self._wrap(part.FirstFeature(), "IFeature")
            
            while feat:
                if self._safe_call(feat, "GetTypeName2") == "CutListFolder":
                    if not self._safe_call(feat, "IsSuppressed"):
                        desc = self._get_cut_list_prop(feat, "DESCRIPTION")
                        length_str = self._get_cut_list_prop(feat, "LENGTH")
                        qty_str = self._get_cut_list_prop(feat, "QUANTITY") or self._get_cut_list_prop(feat, "QTY")
                        
                        try:
                            length_mm = float(length_str)
                            qty = int(float(qty_str)) if qty_str else 1
                            if desc: items.append(CutListItem(desc, length_mm, qty))
                        except: pass
                feat = self._wrap(feat.GetNextFeature(), "IFeature")

            # Capping Detection logic
            bodies = self._wrap(part.GetBodies2(0, False), "IBody2")
            if bodies and items:
                item_caps, item_cross_dims, cap_warns = self._detect_capped_ends(bodies, items, part_path)
                warnings.extend(cap_warns)
                
                if item_caps:
                    expanded = []
                    for i, item in enumerate(items):
                        caps = item_caps.get(i)
                        if not caps:
                            expanded.append(item)
                            continue
                        
                        holes_per_end = self._holes_per_end_from_desc(item.description)
                        state_counter = Counter(caps)
                        for capped_count, qty in state_counter.items():
                            suffix = self._d17_suffix(capped_count, holes_per_end)
                            expanded.append(CutListItem(item.description + suffix, item.length_mm, qty))
                    items = expanded

            return items, warnings
        finally:
            if was_opened: self.close_doc(part_path)

    def _get_cut_list_prop(self, feat, prop_name: str) -> str:
        try:
            mgr = feat.CustomPropertyManager
            res = mgr.Get4(prop_name, False)
            if isinstance(res, tuple) and len(res) > 2:
                return str(res[2] or res[1]).strip()
            return str(mgr.Get(prop_name)).strip()
        except: return ""

    def _detect_capped_ends(self, bodies, items, part_path):
        """Advanced bounding-box containment check for aluminum profiles."""
        item_caps = {}
        item_cross_dims = {}
        warnings = []
        epsilon = 0.0001 # 0.1mm
        
        body_data = []
        for body in (bodies if isinstance(bodies, list) else [bodies]):
            try:
                box = body.GetBodyBox()
                if not box or len(box) < 6: continue
                
                xmin, ymin, zmin, xmax, ymax, zmax = box[:6]
                center = np.array([(xmin+xmax)/2, (ymin+ymax)/2, (zmin+zmax)/2])
                extents_mm = [(xmax-xmin)*1000, (ymax-ymin)*1000, (zmax-zmin)*1000]
                
                # Select length axis
                axis_idx, length_mm, cross = self._select_length_axis(extents_mm, items)
                if axis_idx is not None:
                    axis = np.zeros(3)
                    axis[axis_idx] = 1.0
                    body_data.append({"center": center, "axis": axis, "length": length_mm, "bbox": box, "cross": cross})
            except: pass

        # Map bodies to items (round-robin)
        body_item_idx = []
        assign_counts = {}
        for b in body_data:
            matching = [i for i, item in enumerate(items) if abs(item.length_mm - b["length"]) <= LENGTH_MATCH_TOLERANCE_MM]
            if matching:
                chosen = min(matching, key=lambda i: assign_counts.get(i, 0))
                assign_counts[chosen] = assign_counts.get(chosen, 0) + 1
                body_item_idx.append(chosen)
            else:
                body_item_idx.append(None)

        # Containment check
        for i, b in enumerate(body_data):
            item_idx = body_item_idx[i]
            if item_idx is None: continue
            
            half = (b["length"]/1000)/2
            test1 = b["center"] + (half + epsilon) * b["axis"]
            test2 = b["center"] - (half + epsilon) * b["axis"]
            
            capped = 0
            for j, other in enumerate(body_data):
                if i == j: continue
                if self._bbox_contains(other["bbox"], test1): capped += 1
                if self._bbox_contains(other["bbox"], test2): capped += 1
            
            item_caps.setdefault(item_idx, []).append(min(capped, 2))
            
        return item_caps, item_cross_dims, warnings

    def _select_length_axis(self, extents_mm, items):
        candidates = []
        for i, ext in enumerate(extents_mm):
            for item in items:
                if abs(item.length_mm - ext) <= LENGTH_MATCH_TOLERANCE_MM:
                    candidates.append((ext, i))
                    break
        if not candidates: return None, None, None
        _, idx = max(candidates, key=lambda x: x[0])
        cross = sorted(e for j, e in enumerate(extents_mm) if j != idx)
        return idx, extents_mm[idx], cross

    def _bbox_contains(self, bbox, pt):
        return bbox[0] <= pt[0] <= bbox[3] and bbox[1] <= pt[1] <= bbox[4] and bbox[2] <= pt[2] <= bbox[5]

    def _holes_per_end_from_desc(self, description):
        desc = description.upper()
        if "45X90" in desc or "90X45" in desc: return 2
        if "45X45" in desc: return 1
        return 1 # Default

    def _d17_suffix(self, capped_ends, holes_per_end):
        if capped_ends == 0: return ""
        if holes_per_end == 1:
            return {1: " D17", 2: " D17/D17"}.get(capped_ends, "")
        if holes_per_end == 2:
            return {1: " D17/D17/-/-", 2: " D17/D17/D17/D17"}.get(capped_ends, "")
        return ""

    # --- Dowel Hole Modification ---

    @ensure_sw_connection
    def get_dowel_holes(self, part_doc) -> List[HoleInfo]:
        results = []
        part = self._wrap(part_doc, "IPartDoc")
        feat = self._wrap(part.FirstFeature(), "IFeature")
        while feat:
            if self._safe_call(feat, "GetTypeName2") == "HoleWzd":
                defn = self._wrap(feat.GetDefinition(), "IWizardHoleFeatureData2")
                try:
                    defn.AccessSelections(part_doc, None)
                    ft2 = self._safe_call(defn, "FastenerType2")
                    if ft2 in _DOWEL_FASTENER_TYPES:
                        size_str = defn.FastenerSize
                        m = re.search(r'[\d.]+', size_str)
                        if m:
                            results.append(HoleInfo(feature=feat, original_diameter_m=float(m.group())/1000))
                finally:
                    try: defn.ReleaseSelectionAccess()
                    except: pass
            feat = self._wrap(feat.GetNextFeature(), "IFeature")
        return results

    @ensure_sw_connection
    def modify_dowel_diameter(self, part_doc, hole: HoleInfo, new_diameter_m: float):
        feat = hole.feature
        defn = self._wrap(feat.GetDefinition(), "IWizardHoleFeatureData2")
        defn.AccessSelections(part_doc, None)
        try:
            defn.Type = 0 # swHoleType_Simple
            defn.Diameter = new_diameter_m
            if not feat.ModifyDefinition(defn, part_doc, None):
                raise RuntimeError("ModifyDefinition falhou.")
        finally:
            try: defn.ReleaseSelectionAccess()
            except: pass
        part_doc.EditRebuild3()

    # --- Extra Utilities ---

    def _get_raw_obj(self, obj):
        return getattr(obj, "_oleobj_", None) or getattr(obj, "_dispobj_", None) or obj

    def get_thickness(self, model_doc) -> Optional[float]:
        if not model_doc: return None
        try:
            part = self._wrap(model_doc, "IPartDoc")
            box = part.GetPartBox(True)
            dx = abs(box[3] - box[0])
            dy = abs(box[4] - box[1])
            dz = abs(box[5] - box[2])
            return round(min(dx, dy, dz) * 1000, 2)
        except: return None
