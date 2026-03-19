"""
run_dxf.py — headless DXF export (no GUI).
Usage: python run_dxf.py [assembly.sldasm] [output_dir]
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from solidworks import (
    connect_to_solidworks, open_assembly, get_all_parts,
    deduplicate_by_path, is_laser_part, get_part_path,
    export_part_to_dxf,
)
from dxf_cleaner import clean_dxf


def run(asm_path: str, out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    asm_path = os.path.abspath(asm_path)

    print("Conectando ao SolidWorks\u2026")
    sw = connect_to_solidworks()

    print(f"A abrir: {os.path.basename(asm_path)}")
    asm_doc, asm_opened = open_assembly(sw, asm_path)

    ok = err = 0
    try:
        all_parts    = get_all_parts(asm_doc)
        unique       = deduplicate_by_path(all_parts)
        laser        = [p for p in unique if is_laser_part(p)]

        print(f"Total: {len(all_parts)} | \u00danicas: {len(unique)} | Laser: {len(laser)}")
        print("\u2500" * 60)

        for part in laser:
            path      = get_part_path(part)
            name      = os.path.splitext(os.path.basename(path))[0]
            raw       = os.path.join(out_dir, name + "_raw.dxf")
            final     = os.path.join(out_dir, name + ".dxf")
            try:
                export_part_to_dxf(sw, path, raw)
                removed = clean_dxf(raw, final)
                try:
                    os.remove(raw)
                except OSError:
                    pass
                ok += 1
                print(f"  OK    {name}.dxf [{removed} c\u00edrculo(s) removido(s)]")
            except Exception as exc:
                err += 1
                print(f"  ERROR {name} \u2014 {exc}")
                if os.path.isfile(raw):
                    try:
                        os.remove(raw)
                    except OSError:
                        pass
    finally:
        if asm_opened:
            try:
                sw.CloseDoc(asm_path)
            except Exception:
                pass

    print("\u2500" * 60)
    print(f"Resultado: {ok} exportado(s)  |  {err} erro(s)")


if __name__ == "__main__":
    asm = (sys.argv[1] if len(sys.argv) > 1
           else r"c:\Users\Micael\Desktop\Auto Production\18026.100.900.SLDASM")
    out = (sys.argv[2] if len(sys.argv) > 2
           else r"c:\Users\Micael\Desktop\Auto Production\resultados")
    run(asm, out)
