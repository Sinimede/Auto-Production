
import os
import shutil
import numpy as np
import re
import unicodedata
import pythoncom
import win32com.client
from win32com.client import gencache
import hashlib
import olefile
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
    Unified client for interacting with SolidWorks COM API.
    Encapsulates SW 2024 quirks like early/late binding and callable-guards.
    """
    def __init__(self):
        self.sw = None
        self._mod = None

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
            # print("DEBUG: SW Client - Setting Visible", flush=True)
            # self.sw.Visible = True
            print("DEBUG: SW Client - Connected successfully", flush=True)
            return True
        except Exception as e:
            print(f"DEBUG: SW Client - Exception in connect: {e}", flush=True)
            err_msg = str(e)
            if "-2147221021" in err_msg:
                raise RuntimeError("SolidWorks está ocupado ou com um diálogo aberto. Feche todas as janelas no SolidWorks e tente novamente.")
            raise RuntimeError(f"Erro ao conectar ao SolidWorks: {e}")

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

    @ensure_sw_connection
    def get_dependencies(self, path: str) -> List[str]:
        """Returns a list of immediate dependencies for a SolidWorks document."""
        path = os.path.normpath(os.path.abspath(path))
        # GetDocumentDependencies2(path, TraverseAll, TraverseCustomProps, TraverseInternal)
        # TraverseAll=True, TraverseCustomProps=False, TraverseInternal=False
        deps = self.sw.GetDocumentDependencies2(path, True, False, False)
        if not deps:
            return []
        
        # Result is a tuple: (dependency_path1, configuration1, dependency_path2, configuration2, ...)
        # We only want unique paths
        paths = []
        if isinstance(deps, tuple):
            for i in range(0, len(deps), 2):
                dep_path = os.path.normpath(deps[i])
                if dep_path.lower() != path.lower() and dep_path not in paths:
                    paths.append(dep_path)
        return paths

    # --- Document Management ---

    @ensure_sw_connection
    def open_assembly(self, path: str) -> Tuple[Any, bool]:
        """Opens an assembly and returns (doc, was_opened_by_us)."""
        path = os.path.normpath(os.path.abspath(path))
        
        # 1. Active Doc
        active = self.sw.ActiveDoc
        if active:
            active_path = os.path.normpath(self._safe_call(active, "GetPathName"))
            if active_path.lower() == path.lower():
                return active, False
        
        # 2. Open Docs
        existing = self.sw.GetOpenDocumentByName(path)
        if existing:
            return existing, False
            
        # 3. OpenDoc6
        result = self.sw.OpenDoc6(path, 2, 0, "", 0, 0) # 2 = swDocASSEMBLY
        doc = result[0] if isinstance(result, tuple) else result
        if not doc:
            raise RuntimeError(f"Falha ao abrir assembly: {path}")
        return doc, True

    @ensure_sw_connection
    def open_doc(self, path: str) -> Tuple[Any, bool]:
        """Opens a SolidWorks document (Part or Assembly) with auto-detection."""
        path = os.path.normpath(os.path.abspath(path))
        ext = os.path.splitext(path)[1].lower()
        
        doc_type = 1 # swDocPART
        if ext == ".sldasm":
            doc_type = 2 # swDocASSEMBLY
        elif ext == ".slddrw":
            doc_type = 3 # swDocDRAWING
            
        # Check if already open
        existing = self.sw.GetOpenDocumentByName(path)
        if existing:
            return existing, False
            
        # OpenDoc6
        result = self.sw.OpenDoc6(path, doc_type, 0, "", 0, 0)
        doc = result[0] if isinstance(result, tuple) else result
        if not doc:
            raise RuntimeError(f"Falha ao abrir documento: {path}")
        return doc, True

    @ensure_sw_connection
    def open_assembly_resolved(self, path: str) -> Tuple[Any, bool]:
        """
        Opens the assembly in read-only resolved (non-lightweight) mode.
        Forcefully closes any already-open instance (discarding changes).
        """
        RESOLVED_READONLY = 2 | 64 # ReadOnly | OverrideLoadLightweight
        path = os.path.normpath(os.path.abspath(path))

        # Check if already open
        existing = self.sw.GetOpenDocumentByName(path)
        if not existing:
            active = self.sw.ActiveDoc
            if active:
                active_path = os.path.normpath(self._safe_call(active, "GetPathName"))
                if active_path.lower() == path.lower():
                    existing = active

        # Mandato: Sempre fechar e descartar para garantir modo resolvido limpo
        if existing:
            self.close_doc(path)

        # Open in resolved + read-only mode
        result = self.sw.OpenDoc6(path, 2, RESOLVED_READONLY, "", 0, 0)
        doc = result[0] if isinstance(result, tuple) else result
        if not doc:
            raise RuntimeError(f"Falha ao abrir assembly em modo resolvido: {path}")
        return doc, True

    def _is_doc_dirty(self, doc) -> bool:
        """Checks if a document has unsaved changes."""
        try:
            ref = doc.GetSaveFlag
            val = ref() if callable(ref) else ref
            return bool(val[0] if isinstance(val, tuple) else val)
        except:
            return False

    @ensure_sw_connection
    def close_doc(self, path: str):
        """Closes a document discarding any changes."""
        path = os.path.normpath(path)
        doc = self.sw.GetOpenDocumentByName(path)
        if doc:
            try:
                # Marcar como 'não modificado' para descartar alterações sem aviso
                # SetSaveFlag() sem argumentos marca como limpo em algumas versões
                # ou usamos o método ResetReadOnly (menos comum)
                # O método mais seguro em SW 2024 via COM é SetSaveFlag
                ref = doc.SetSaveFlag
                if callable(ref): ref()
            except:
                pass
        self.sw.CloseDoc(path)

    # --- Traversal & Data ---

    @ensure_sw_connection
    def get_all_parts(self, assembly_doc) -> List[Any]:
        """Returns unique part components in the assembly."""
        asm = self._wrap(assembly_doc, "IAssemblyDoc")
        
        # Resolve Lightweight (Dynamic late binding required in SW 2024)
        try:
            asm_raw = self._get_raw_obj(asm)
            win32com.client.dynamic.Dispatch(asm_raw).ResolveAllLightweightComponents(False)
        except:
            pass

        components = None
        try:
            components = asm.GetComponents(False) # All levels
        except:
            pass
            
        if not components:
            # Fallback to GetRootComponent3
            config = assembly_doc.ConfigurationManager.ActiveConfiguration
            root = self._safe_call(config, "GetRootComponent3", True)
            components = self._collect_children(root)
            
        if not components:
            return []
            
        parts = []
        for comp in components:
            comp = self._wrap(comp, "IComponent2")
            
            # Skip suppressed
            suppression = self._safe_call(comp, "GetSuppression")
            if suppression is not None and int(suppression) == 0:
                continue

            model = self._safe_call(comp, "GetModelDoc2")
            
            if not model:
                try:
                    comp_raw = self._get_raw_obj(comp)
                    win32com.client.dynamic.Dispatch(comp_raw).SetComponentState(4) # Resolve
                    model = self._safe_call(comp, "GetModelDoc2")
                except:
                    pass
            
            if model and self._safe_call(model, "GetType") == 1: # swDocPART
                parts.append(comp)
        
        return self._deduplicate_by_path(parts)

    def _collect_children(self, component) -> list:
        result = []
        if not component: return result
        children = self._safe_call(component, "GetChildren")
        if children:
            if isinstance(children, tuple): children = list(children)
            for child in children:
                child_wrapped = self._wrap(child, "IComponent2")
                result.append(child_wrapped)
                result.extend(self._collect_children(child_wrapped))
        return result

    def _deduplicate_by_path(self, components: List) -> List:
        seen = set()
        unique = []
        for comp in components:
            path = self._safe_call(comp, "GetPathName")
            if path:
                path_lower = path.lower()
                if path_lower not in seen:
                    seen.add(path_lower)
                    unique.append(comp)
        return unique

    # --- Property Management ---

    def get_file_hash(self, file_path: str) -> str:
        """Returns the MD5 hash of a file to check for changes."""
        hasher = hashlib.md5()
        try:
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except:
            return ""

    def get_custom_properties_fast(self, file_path: str) -> Dict[str, str]:
        """
        Extracts custom properties using olefile WITHOUT opening SolidWorks.
        Extremely fast, but cannot resolve dynamic SW expressions.
        """
        if not olefile.isOleFile(file_path):
            return {}

        props = {}
        try:
            with olefile.OleFileIO(file_path) as ole:
                # 1. SummaryInformation (Standard props like Title, Author)
                if ole.exists('\005SummaryInformation'):
                    si = ole.getproperties('\005SummaryInformation')
                    # si[2] is Title (often used for Description)
                    if 2 in si: props['Description'] = str(si[2])

                # 2. DocumentSummaryInformation (Custom properties)
                # This stream contains the actual custom property names and values
                if ole.exists('\005DocumentSummaryInformation'):
                    dsi = ole.getproperties('\005DocumentSummaryInformation')
                    # Standard custom properties are usually in a dictionary-like structure here.
                    # olefile maps them to indices. We iterate and look for our keys.
                    for codepage, p_dict in dsi.items():
                        for p_id, p_val in p_dict.items():
                            p_name = str(p_id)
                            # Custom property names are stored in a special section (PID_DICTIONARY = 0)
                            # But olefile often resolves them automatically if it can.
                            # Since SW properties vary, we do a best-effort mapping.
                            if isinstance(p_val, bytes):
                                try: p_val = p_val.decode('utf-16').strip('\x00')
                                except: pass
                            
                            p_val_str = str(p_val).strip()
                            if p_val_str:
                                # Map common SW property IDs or names if available
                                # (In practice, full SW property mapping in OLE is complex, 
                                # but olefile is good for quick raw extraction)
                                props[p_name] = p_val_str

                # 3. Handle specific SolidWorks custom properties stream if it exists
                # SolidWorks stores custom props in 'Custom Properties' or 'Configuration Specific' streams.
                # These are often binary-encoded.
                
            # Filter and normalize
            result = {}
            mapping = {
                "Description": ["Description", "Descrição", "Title"],
                "Material": ["Material"],
                "Weight": ["Weight", "Peso"],
                "Revision": ["Revision", "Revisão"],
                "Treatment": ["Treatment", "Tratamento"]
            }
            
            for key, aliases in mapping.items():
                for alias in aliases:
                    if alias in props:
                        result[key] = props[alias]
                        break
            
            return result
        except:
            return {}

    def get_custom_property(self, model_doc, prop_name: str) -> str:
        """
        Gets evaluated custom property, handling SW 2024 quirks.
        Checks both document-level and active configuration-level properties.
        """
        if not model_doc:
            return ""
            
        try:
            # 1. Legacy Fallback for Custom tab (very reliable)
            val = self._safe_call(model_doc, "GetCustomInfoValue", "", prop_name)
            if val: return str(val).strip('"\' ')

            # 2. Get Extension object safely
            ext = self._safe_call(model_doc, "Extension")
            if not ext: return ""
            
            # 3. Try Config-specific properties first
            config_mgr = self._safe_call(model_doc, "ConfigurationManager")
            active_cfg = self._safe_call(config_mgr, "ActiveConfiguration")
            cfg_name = self._safe_call(active_cfg, "Name") if active_cfg else ""
            
            val = self._read_from_mgr(ext, cfg_name, prop_name)
            
            # 4. Fallback to Document-level properties ("")
            if not val:
                val = self._read_from_mgr(ext, "", prop_name)
            
            # 5. Clean up results
            val = val.strip('"\' ')
            
            # 6. Handle special case: Material expression
            if prop_name == "Material" and (not val or _SW_EXPR_RE.match(val)):
                val = self._get_part_material(model_doc)
                
            return val
        except Exception:
            return ""

    def set_custom_property(self, model_doc, prop_name: str, value: str):
        """Sets a custom property at the document level."""
        if not model_doc: return
        try:
            # 1. Try via Extension.CustomPropertyManager (Modern)
            ext = self._safe_call(model_doc, "Extension")
            if ext:
                mgr = self._safe_call(ext, "CustomPropertyManager", "")
                if mgr:
                    # 30 = swCustomInfoText, 1 = Replace existing
                    try:
                        res = mgr.Add3(prop_name, 30, value, 1)
                        if res in (1, 2): # 1=Success, 2=Already exists (but Replace=1 should handle it)
                            return
                    except:
                        try:
                            mgr.Set2(prop_name, value)
                            return
                        except:
                            pass

            # 2. Fallback to Legacy Document-level property (AddCustomInfo3)
            # swCustomInfoText = 30
            try:
                model_doc.AddCustomInfo3("", prop_name, 30, value)
            except:
                pass
        except Exception as e:
            print(f"DEBUG: set_custom_property error: {e}")
            raise RuntimeError(f"Erro ao definir propriedade '{prop_name}': {e}")

    def get_custom_properties(self, file_path: str) -> Dict[str, str]:
        """Opens a file (if not open) and extracts a dictionary of common PDM properties."""
        path = os.path.normpath(os.path.abspath(file_path))
        ext = os.path.splitext(path)[1].lower()
        
        type_map = {".sldprt": 1, ".sldasm": 2, ".slddrw": 3}
        doc_type = type_map.get(ext, 1)
        
        # 1. Check if already open
        model_doc = self.sw.GetOpenDocumentByName(path)
        was_open = model_doc is not None
        
        if not model_doc:
            # 2. Open it (Silent, Read-only)
            # OpenDoc6 params: file, type, options (1=ReadOnly, 2=Silent), config, errors, warnings
            # Pass 0 for errors/warnings to avoid VARIANT vs early-binding error
            result = self.sw.OpenDoc6(path, doc_type, 3, "", 0, 0)
            model_doc = result[0] if isinstance(result, tuple) else result
            
        if not model_doc:
            return {}
            
        try:
            props = {
                "Description": self.get_custom_property(model_doc, "Description") or self.get_custom_property(model_doc, "Descrição"),
                "Material": self.get_custom_property(model_doc, "Material"),
                "Weight": self.get_custom_property(model_doc, "Weight") or self.get_custom_property(model_doc, "Peso"),
                "Revision": self.get_custom_property(model_doc, "Revision") or self.get_custom_property(model_doc, "Revisão"),
                "Treatment": self.get_custom_property(model_doc, "Treatment") or self.get_custom_property(model_doc, "Tratamento")
            }
            return {k: v for k, v in props.items() if v}
        finally:
            if not was_open:
                self.sw.CloseDoc(path)

    def _read_from_mgr(self, extension, config_name: str, prop_name: str) -> str:
        """Helper to read property from a specific CustomPropertyManager."""
        try:
            mgr = self._safe_call(extension, "CustomPropertyManager", config_name)
            if not mgr: return ""
            
            # Try to find the property name with correct casing
            names = mgr.GetNames()
            if names:
                if isinstance(names, tuple): names = list(names)
                actual_name = next((n for n in names if str(n).lower() == prop_name.lower()), prop_name)
            else:
                actual_name = prop_name
            
            # Try Get4 (Resolved value)
            res = mgr.Get4(actual_name, True)
            if isinstance(res, tuple) and len(res) > 2:
                resolved = str(res[2]).strip()
                raw = str(res[1]).strip()
                return resolved if resolved else raw
            
            return str(mgr.Get(actual_name) or "").strip()
        except:
            return ""

    def _get_part_material(self, model_doc) -> str:
        try:
            part = self._wrap(model_doc, "IPartDoc")
            mat = part.GetMaterialPropertyName2("")
            if isinstance(mat, tuple): mat = mat[0]
            return str(mat or "").strip()
        except:
            return ""

    # --- Export ---

    @ensure_sw_connection
    def export_to_step(self, doc_or_comp, output_path: str):
        """Exports document or component to STEP AP214 using late-binding SaveAs4."""
        import pythoncom as _pycom
        try:
            # 1. Ensure we have the ModelDoc2
            doc = doc_or_comp
            if hasattr(doc, "GetModelDoc2") or "IComponent2" in str(type(doc)):
                doc = self._safe_call(doc, "GetModelDoc2")
            
            if not doc:
                raise RuntimeError("Não foi possível obter o modelo do componente.")

            # 2. Use Late Binding (Dynamic) for the save operation
            raw = self._get_raw_obj(doc)
            late = win32com.client.dynamic.Dispatch(raw)
            
            # 3. Prepare by-ref parameters
            err = win32com.client.VARIANT(_pycom.VT_BYREF | _pycom.VT_I4, 0)
            warn = win32com.client.VARIANT(_pycom.VT_BYREF | _pycom.VT_I4, 0)
            
            # SaveAs4 args: Name, Version (0=Current), Options (1=Silent), Errors, Warnings
            res = late.SaveAs4(output_path, 0, 1, err, warn)
            
            # Handle possible tuple return (bool, errors, warnings)
            success = res[0] if isinstance(res, (tuple, list)) else bool(res)
            
            if not success:
                raise RuntimeError(f"Erro SW: {err.value}")
                
        except Exception as e:
            raise RuntimeError(f"Erro na exportação STEP: {e}")

    @ensure_sw_connection
    def export_to_dxf(self, component, output_path: str):
        """Exports sheet metal flat pattern to DXF."""
        model = self._safe_call(component, "GetModelDoc2")
        part = self._wrap(model, "IPartDoc")
        res = part.ExportFlatPatternView(output_path, 1) # 1 = Geometry
        if not res:
            raise RuntimeError(f"Falha ao exportar DXF: {output_path}")

    # --- BOM Traversal ---

    @ensure_sw_connection
    def get_bom_components(self, assembly_doc) -> Tuple[List[BomComponent], List[str]]:
        """Returns a flat list of BomComponent from the assembly."""
        bom_flat = []
        warnings = []
        
        # Resolve Lightweight (Dynamic late binding)
        try:
            asm_raw = self._get_raw_obj(assembly_doc)
            win32com.client.dynamic.Dispatch(asm_raw).ResolveAllLightweightComponents(False)
        except Exception as e:
            warnings.append(f"Aviso: Falha ao resolver componentes: {e}")

        config = self._safe_call(assembly_doc, "ConfigurationManager").ActiveConfiguration
        root = self._safe_call(config, "GetRootComponent3", True)
        
        children = self._safe_call(root, "GetChildren")
        if children:
            if isinstance(children, tuple): children = list(children)
            for child in children:
                self._bom_traverse(child, bom_flat, warnings)
        
        return bom_flat, warnings

    def _bom_traverse(self, comp, bom_flat, warnings):
        comp = self._wrap(comp, "IComponent2")
        
        # Check suppression
        state = self._safe_call(comp, "GetSuppression")
        if state is not None and int(state) == 0: return # Suppressed

        path = self._safe_call(comp, "GetPathName")
        if not path: return
        path = os.path.normpath(path)
        
        basename = os.path.splitext(os.path.basename(path))[0]
        basename = re.sub(r'-\d+$', '', basename) # Strip instance suffix

        model = self._safe_call(comp, "GetModelDoc2")
        
        if not model:
            # Lightweight fallback
            ext = os.path.splitext(path)[1].lower()
            if ext == '.sldasm':
                children = self._safe_call(comp, "GetChildren")
                if children:
                    for child in children: self._bom_traverse(child, bom_flat, warnings)
            elif ext == '.sldprt':
                comp_type = self._classify_by_name(basename)
                if comp_type:
                    bom_flat.append(BomComponent(comp, path, comp_type))
                else:
                    warnings.append(f"Componente ignorado (nome não reconhecido): {basename}")
            return

        doc_type = self._safe_call(model, "GetType")
        comp_type = self._classify_by_name(basename)

        if comp_type == "comercial":
            bom_flat.append(BomComponent(comp, path, "comercial"))
            return

        if doc_type == 1: # swDocPART
            if comp_type:
                bom_flat.append(BomComponent(comp, path, comp_type))
            else:
                warnings.append(f"Componente ignorado (nome não reconhecido): {basename}")
        elif doc_type == 2: # swDocASSEMBLY
            children = self._safe_call(comp, "GetChildren")
            if children:
                for child in children: self._bom_traverse(child, bom_flat, warnings)

    def _classify_by_name(self, basename: str) -> Optional[str]:
        """Classifies component based on standard naming convention."""
        # 3-letter prefix (e.g., BOS.040.001) -> comercial
        if re.match(r'^[A-Za-z]{3}\.', basename):
            return "comercial"
        
        # Numeric group pattern (e.g., 18026.800.001)
        m = re.match(r'^\d+\.(\d+)\.\d+$', basename)
        if m:
            group = int(m.group(1))
            return "comercial" if group == 800 else "producao"
        
        return None

    # --- Dowel Holes (Router Flow) ---

    @ensure_sw_connection
    def get_dowel_holes(self, part_doc) -> List[HoleInfo]:
        """Returns a list of Hole Wizard Dowel holes."""
        results = []
        part = self._wrap(part_doc, "IPartDoc")
        feat = self._safe_call(part, "FirstFeature")
        
        while feat:
            feat_wrapped = self._wrap(feat, "IFeature")
            if self._safe_call(feat_wrapped, "GetTypeName2") == "HoleWzd":
                defn = feat_wrapped.GetDefinition()
                feat_data = self._wrap(defn, "IWizardHoleFeatureData2")
                try:
                    feat_data.AccessSelections(part_doc, None)
                    ft2 = self._safe_call(feat_data, "FastenerType2")
                    if ft2 is not None and int(ft2) in _DOWEL_FASTENER_TYPES:
                        size_str = self._safe_call(feat_data, "FastenerSize")
                        m = re.search(r'[\d.]+', size_str)
                        if m:
                            diameter_m = float(m.group()) / 1000.0
                            results.append(HoleInfo(feature=feat_wrapped, original_diameter_m=diameter_m))
                finally:
                    try: feat_data.ReleaseSelectionAccess()
                    except: pass
            feat = self._safe_call(feat_wrapped, "GetNextFeature")
        return results

    @ensure_sw_connection
    def modify_dowel_diameter(self, part_doc, hole: HoleInfo, new_diameter_m: float):
        """Changes a dowel hole's diameter."""
        feat = hole.feature
        defn = feat.GetDefinition()
        feat_data = self._wrap(defn, "IWizardHoleFeatureData2")
        feat_data.AccessSelections(part_doc, None)
        try:
            feat_data.Type = 0 # Simple hole
            feat_data.Diameter = new_diameter_m
            res = feat.ModifyDefinition(defn, part_doc, None)
            if not res: raise RuntimeError("ModifyDefinition falhou")
        finally:
            try: feat_data.ReleaseSelectionAccess()
            except: pass
        part_doc.EditRebuild3()

    @ensure_sw_connection
    def save_silent(self, doc):
        """Saves document silently using late binding."""
        raw = self._get_raw_obj(doc)
        late = win32com.client.dynamic.Dispatch(raw)
        byref_i4 = lambda: win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        late.Save3(1, byref_i4(), byref_i4()) # 1 = Silent

    def copy_part_to_tmp(self, sldprt_path: str, tmp_dir: str) -> str:
        os.makedirs(tmp_dir, exist_ok=True)
        name, ext = os.path.splitext(os.path.basename(sldprt_path))
        tmp_path = os.path.join(tmp_dir, f"{name}_step_tmp{ext}")
        shutil.copy2(sldprt_path, tmp_path)
        return tmp_path

    # --- Aluminum Profiles (Weldments) ---

    def is_perfil_aluminio(self, component) -> bool:
        val = self.get_corte_fabrico(component)
        return bool(val) and "perfil aluminio" in val

    @ensure_sw_connection
    def get_perfis_parts(self, asm_doc) -> List[Tuple[str, int]]:
        """Returns list of (path, count) for all aluminum profiles."""
        all_parts = self.get_all_parts(asm_doc)
        perfil_parts = [p for p in all_parts if self.is_perfil_aluminio(p)]
        unique = self._deduplicate_by_path(perfil_parts)
        
        result = []
        for comp in unique:
            path = self._safe_call(comp, "GetPathName")
            if path:
                path = os.path.normpath(path)
                count = self.count_instances(all_parts, path)
                result.append((path, count))
        return result

    @ensure_sw_connection
    def get_weldment_cut_list(self, part_path: str) -> Tuple[List[CutListItem], List[str]]:
        """Extracts cut list items from a weldment part, including D17 capping logic."""
        part_path = os.path.normpath(os.path.abspath(part_path))
        doc = None
        warnings = []
        try:
            # Open silently
            result = self.sw.OpenDoc6(part_path, 1, 1, "", 0, 0)
            doc = result[0] if isinstance(result, tuple) else result
            part = self._wrap(doc, "IPartDoc")
            
            items = []
            feat = self._safe_call(part, "FirstFeature")
            while feat:
                fw = self._wrap(feat, "IFeature")
                if self._safe_call(fw, "GetTypeName2") == "CutListFolder":
                    if not self._safe_call(fw, "IsSuppressed"):
                        mgr = fw.CustomPropertyManager
                        desc = self._get_mgr_prop(mgr, "DESCRIPTION")
                        length_str = self._get_mgr_prop(mgr, "LENGTH")
                        qty_str = self._get_mgr_prop(mgr, "QUANTITY") or self._get_mgr_prop(mgr, "QTY")
                        
                        try:
                            length_mm = float(length_str)
                            qty = int(float(qty_str)) if qty_str else 1
                            if desc: items.append(CutListItem(desc, length_mm, qty))
                        except: pass
                feat = self._safe_call(fw, "GetNextFeature")

            # --- Capping Detection ---
            try:
                bodies_raw = part.GetBodies2(0, False)
                if bodies_raw:
                    if isinstance(bodies_raw, tuple): bodies_raw = list(bodies_raw)
                    all_bodies = [self._wrap(b, "IBody2") for b in bodies_raw if b]
                    
                    if all_bodies and items:
                        item_caps, item_cross, cap_warns = self._detect_capped_ends(all_bodies, items, part_path)
                        warnings.extend(cap_warns)
                        
                        expanded = []
                        for i, item in enumerate(items):
                            caps = item_caps.get(i)
                            if not caps:
                                expanded.append(item)
                                continue
                            
                            # Determine holes per end
                            holes_per_end = self._holes_from_desc(item.description)
                            if holes_per_end is None:
                                cross = item_cross.get(i)[0] if item_cross.get(i) else []
                                holes_per_end = self.classify_profile_holes(cross) if cross else "VERIFICAR"
                            
                            counts = Counter(caps)
                            for capped_ends in sorted(counts, reverse=True):
                                suffix = self._d17_suffix(capped_ends, holes_per_end)
                                expanded.append(CutListItem(item.description + suffix, item.length_mm, counts[capped_ends]))
                        items = expanded
            except Exception as e:
                warnings.append(f"Capping detection falhou: {e}")

            return items, warnings
        finally:
            if doc: self.sw.CloseDoc(part_path)

    def _get_mgr_prop(self, mgr, name):
        try:
            res = mgr.Get4(name, False)
            if isinstance(res, tuple) and len(res) > 1:
                return str(res[2] if (len(res) > 2 and res[2]) else res[1]).strip()
            return str(mgr.Get(name) or "").strip()
        except: return ""

    def _detect_capped_ends(self, bodies, raw_items, part_path):
        item_caps = {}
        item_cross = {}
        warnings = []
        epsilon = 0.0001 # 0.1mm
        
        body_data = []
        for body in bodies:
            try:
                box = body.GetBodyBox()
                if not (isinstance(box, tuple) and len(box) >= 6): continue
                xmin, ymin, zmin, xmax, ymax, zmax = box[:6]
                center = np.array([(xmin+xmax)/2, (ymin+ymax)/2, (zmin+zmax)/2])
                extents = [(xmax-xmin)*1000, (ymax-ymin)*1000, (zmax-zmin)*1000]
                
                axis_idx, length, cross = self.select_length_axis(extents, raw_items)
                axis = np.zeros(3)
                if axis_idx is not None:
                    axis[axis_idx] = 1.0
                    body_data.append({'center': center, 'axis': axis, 'len': length, 'bbox': box, 'cross': cross})
                else:
                    # Capper body
                    body_data.append({'center': center, 'axis': None, 'len': None, 'bbox': box, 'cross': None})
            except: pass

        # Associate and Check
        for i, b1 in enumerate(body_data):
            if b1['len'] is None: continue
            
            # Find item index
            item_idx = None
            for idx, item in enumerate(raw_items):
                if abs(item.length_mm - b1['len']) <= LENGTH_MATCH_TOLERANCE_MM:
                    item_idx = idx; break
            
            if item_idx is None: continue
            item_cross.setdefault(item_idx, []).append(b1['cross'])

            # Points
            p1 = b1['center'] + ((b1['len']/2000.0) + epsilon) * b1['axis']
            p2 = b1['center'] - ((b1['len']/2000.0) + epsilon) * b1['axis']
            
            cap1 = cap2 = False
            for j, b2 in enumerate(body_data):
                if i == j: continue
                if not cap1: cap1 = self._bbox_contains(b2['bbox'], p1)
                if not cap2: cap2 = self._bbox_contains(b2['bbox'], p2)
            
            item_caps.setdefault(item_idx, []).append(int(cap1) + int(cap2))
            
        return item_caps, item_cross, warnings

    def _bbox_contains(self, bbox, p):
        return bbox[0] <= p[0] <= bbox[3] and bbox[1] <= p[1] <= bbox[4] and bbox[2] <= p[2] <= bbox[5]

    def _holes_from_desc(self, desc):
        d = desc.upper()
        if "45X90" in d or "90X45" in d: return 2
        if "45X45" in d: return 1
        return None

    def _d17_suffix(self, capped, holes):
        if capped == 0: return ""
        if holes == "VERIFICAR": return " VERIFICAR FURAÇÕES"
        if holes == 1: return {1: " D17", 2: " D17/D17"}.get(capped, "")
        if holes == 2: return {1: " D17/D17/-/-", 2: " D17/D17/D17/D17"}.get(capped, "")
        return ""

    # --- Classification ---

    def _normalize_corte(self, val: str) -> str:
        nfkd = unicodedata.normalize("NFD", val.lower())
        return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")

    def get_corte_fabrico(self, component) -> str:
        model = self._safe_call(component, "GetModelDoc2")
        if not model: return ""
        val = self.get_custom_property(model, "Corte_Fabrico")
        return self._normalize_corte(val)

    def is_laser_part(self, component) -> bool:
        val = self.get_corte_fabrico(component)
        return "laser" in val and "soldadura" not in val

    def is_protecoes_part(self, component) -> bool:
        val = self.get_corte_fabrico(component)
        return "protecoes" in val

    def is_step_part(self, component) -> bool:
        val = self.get_corte_fabrico(component)
        return any(k in val for k in ("router", "cnc", "torno"))

    def get_part_data(self, component, all_components: list) -> dict:
        path = self._safe_call(component, "GetPathName")
        model = self._safe_call(component, "GetModelDoc2")
        
        data = {
            "qty": self.count_instances(all_components, path),
            "part_number": os.path.splitext(os.path.basename(path))[0],
            "espessura": self.get_thickness(model)
        }
        
        for prop in ("Description", "Corte_Fabrico", "Simetria", "Material", "TratSuperficial"):
            data[prop] = self.get_custom_property(model, prop)
            
        return data

    def count_instances(self, all_components: list, part_path: str) -> int:
        target = os.path.normpath(part_path).lower()
        count = 0
        for comp in all_components:
            path = self._safe_call(comp, "GetPathName")
            if path and os.path.normpath(path).lower() == target:
                state = self._safe_call(comp, "GetSuppression")
                if state is not None and int(state) != 0: # Not suppressed
                    count += 1
        return count

    def get_thickness(self, model_doc) -> Optional[float]:
        if not model_doc: return None
        try:
            # Check SheetMetal
            part = self._wrap(model_doc, "IPartDoc")
            feat = self._safe_call(part, "FirstFeature")
            while feat:
                feat_wrapped = self._wrap(feat, "IFeature")
                if self._safe_call(feat_wrapped, "GetTypeName2") == "SheetMetal":
                    defn = feat_wrapped.GetDefinition()
                    late = win32com.client.Dispatch(self._get_raw_obj(defn))
                    thickness_m = late.Thickness
                    return round(thickness_m * 1000, 2)
                feat = self._safe_call(feat_wrapped, "GetNextFeature")
            
            # Fallback to BBox
            box = part.GetPartBox(True)
            dx = abs(box[3] - box[0])
            dy = abs(box[4] - box[1])
            dz = abs(box[5] - box[2])
            return round(min(dx, dy, dz) * 1000, 2)
        except:
            return None

    def _get_raw_obj(self, obj):
        """Returns the raw COM interface (_oleobj_) for late-binding operations."""
        return getattr(obj, "_oleobj_", None) or getattr(obj, "_dispobj_", None) or obj

    # --- Geometry Helpers ---

    def select_length_axis(self, extents_mm: list, raw_items: list) -> tuple:
        if not raw_items:
            return (None, None, None)
        candidates = []
        for i, extent in enumerate(extents_mm):
            for item in raw_items:
                if abs(item.length_mm - extent) <= LENGTH_MATCH_TOLERANCE_MM:
                    candidates.append((extent, i))
                    break
        if not candidates:
            return (None, None, None)
        _, axis_idx = max(candidates, key=lambda t: t[0])
        length_mm = extents_mm[axis_idx]
        cross = sorted(e for j, e in enumerate(extents_mm) if j != axis_idx)
        return (axis_idx, length_mm, cross)

    def classify_profile_holes(self, cross_dims_mm: list) -> Any:
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
