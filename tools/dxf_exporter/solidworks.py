"""
Bridge de compatibilidade para o novo SolidWorksClient centralizado (Versão DXF Exporter).
"""
import sys
import os

# Adicionar raiz do projeto ao path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.core.solidworks import SolidWorksClient

_client = SolidWorksClient()

def connect_to_solidworks():
    if _client.connect():
        return _client.sw
    raise RuntimeError("Não foi possível conectar ao SolidWorks.")

def open_assembly(sw, path):
    return _client.open_doc(path, 2)

def get_all_parts(doc):
    return _client.get_all_parts(doc)

def is_laser_part(comp):
    val = _client.get_custom_property(comp.GetModelDoc2(), "Corte_Fabrico").lower()
    return "laser" in val and "soldadura" not in val

def get_part_path(comp):
    return comp.GetPathName()

def find_drawing(path):
    base = os.path.splitext(path)[0]
    for ext in (".SLDDRW", ".slddrw"):
        if os.path.exists(base + ext): return base + ext
    return None

def export_part_to_dxf(sw, path, out):
    return _client.export_part_to_dxf(path, out)

def export_drawing_to_dxf(sw, path, out):
    return _client.export_drawing_to_dxf(path, out)

def _open_doc(sw, path, doc_type):
    return _client.open_doc(path, doc_type)

def deduplicate_by_path(comps):
    seen = set()
    unique = []
    for c in comps:
        if c.GetPathName().lower() not in seen:
            seen.add(c.GetPathName().lower())
            unique.append(c)
    return unique
