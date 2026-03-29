"""
Bridge de compatibilidade para o novo SolidWorksClient centralizado.
Redireciona chamadas legadas para o core em src/core/solidworks.py.
"""
import sys
import os

# Adicionar raiz do projeto ao path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.core.solidworks import SolidWorksClient, HoleInfo, BomComponent, CutListItem, LENGTH_MATCH_TOLERANCE_MM

# Instância global para simular comportamento anterior (singleton-like)
_client = SolidWorksClient()

def connect_to_solidworks():
    if _client.connect():
        return _client.sw
    raise RuntimeError("Não foi possível conectar ao SolidWorks.")

def open_assembly(sw, path):
    return _client.open_doc(path, 2)

def get_all_parts(doc):
    return _client.get_all_parts(doc)

def get_bom_components(doc):
    return _client.get_bom_components(doc)

def deduplicate_bom_by_path(bom):
    seen = set()
    unique = []
    for bc in bom:
        if bc.path.lower() not in seen:
            seen.add(bc.path.lower())
            unique.append(bc)
    return unique

def count_bom_instances(bom, path):
    target = os.path.normpath(path).lower()
    return sum(1 for bc in bom if os.path.normpath(bc.path).lower() == target)

def is_laser_part(comp):
    val = _client.get_custom_property(comp.GetModelDoc2(), "Corte_Fabrico").lower()
    return "laser" in val and "soldadura" not in val

def get_part_path(comp):
    return comp.GetPathName()

def export_part_to_dxf(sw, path, out):
    return _client.export_part_to_dxf(path, out)

def export_drawing_to_dxf(sw, path, out):
    return _client.export_drawing_to_dxf(path, out)

def export_part_to_step(sw, path, out, doc=None):
    return _client.export_to_step(path, out)

def get_weldment_cut_list(sw, path):
    return _client.get_weldment_cut_list(path)

def get_dowel_holes(doc):
    return _client.get_dowel_holes(doc)

def modify_dowel_diameter(doc, hole, new_dia):
    return _client.modify_dowel_diameter(doc, hole, new_dia)

def save_silent(doc):
    return _client.save_silent(doc)

def get_part_data(comp, all_comps):
    path = comp.GetPathName()
    model = comp.GetModelDoc2()
    data = {
        "qty": sum(1 for c in all_comps if c.GetPathName().lower() == path.lower()),
        "part_number": os.path.splitext(os.path.basename(path))[0],
        "espessura": _client.get_thickness(model)
    }
    for prop in ("Description", "Corte_Fabrico", "Simetria", "Material", "TratSuperficial"):
        data[prop] = _client.get_custom_property(model, prop)
    return data

def find_drawing(path):
    base = os.path.splitext(path)[0]
    for ext in (".SLDDRW", ".slddrw"):
        if os.path.exists(base + ext): return base + ext
    return None

def is_step_part(comp):
    val = _client.get_custom_property(comp.GetModelDoc2(), "Corte_Fabrico").lower()
    return any(k in val for k in ("router", "cnc", "torno"))

def is_perfil_aluminio(comp):
    val = _client.get_custom_property(comp.GetModelDoc2(), "Corte_Fabrico").lower()
    return "perfil aluminio" in val

def count_instances(all_comps, path):
    target = os.path.normpath(path).lower()
    return sum(1 for c in all_comps if os.path.normpath(c.GetPathName()).lower() == target)
