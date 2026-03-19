"""
test_step.py -- Headless STEP export test (ASCII-safe output).

Runs the same logic as StepModule._worker without the GUI.
Usage:
    python test_step.py

Requires SolidWorks to be running.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from solidworks import (
    connect_to_solidworks, open_assembly, get_all_parts,
    deduplicate_by_path, is_step_part, get_corte_fabrico,
    get_part_path, copy_part_to_tmp, get_dowel_holes,
    modify_dowel_diameter, export_part_to_step, save_silent, _open_doc,
)

ROOT     = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
ASM_PATH = os.path.normpath(os.path.join(ROOT, "18026.100.900.SLDASM"))
OUT_DIR  = os.path.normpath(os.path.join(ROOT, "Resultados"))
TMP_DIR  = os.path.normpath(os.path.join(ROOT, ".tmp"))

SEP  = "-" * 68
SEP2 = "=" * 68


def export_router_part(sw, part_path, output_step, tmp_dir):
    tmp_path = None
    tmp_doc  = None
    try:
        tmp_path = copy_part_to_tmp(part_path, tmp_dir)
        tmp_doc  = _open_doc(sw, tmp_path, doc_type=1, silent=True)

        holes = get_dowel_holes(tmp_doc)
        notes = []
        for hole in holes:
            orig_mm = hole.original_diameter_m * 1000
            new_m   = hole.original_diameter_m - 0.001
            new_mm  = new_m * 1000
            modify_dowel_diameter(tmp_doc, hole, new_m)
            notes.append("d%.0f->d%.0f" % (orig_mm, new_mm))

        export_part_to_step(sw, tmp_path, output_step, doc=tmp_doc)
        return ("%d dowel(s): %s" % (len(holes), ", ".join(notes))) if notes else "sem furos de cavilha"

    finally:
        if tmp_doc is not None:
            try:
                save_silent(tmp_doc)
                sw.CloseDoc(tmp_path)
            except Exception:
                pass
        if tmp_path and os.path.isfile(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def main():
    ok_count = skip_count = err_count = 0
    asm_doc = asm_opened_by_us = None
    sw = None

    print(SEP2)
    print("STEP Export -- teste headless")
    print("Assembly : " + ASM_PATH)
    print("Output   : " + OUT_DIR)
    print(SEP2)

    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(TMP_DIR, exist_ok=True)

    try:
        print("A conectar ao SolidWorks...")
        sw = connect_to_solidworks()
        print("Conectado.")

        print("A abrir assembly: " + os.path.basename(ASM_PATH))
        asm_doc, asm_opened_by_us = open_assembly(sw, ASM_PATH)
        print("Assembly %s." % ("aberto por nos" if asm_opened_by_us else "ja estava aberto"))

        print("A percorrer componentes...")
        all_parts    = get_all_parts(asm_doc)
        unique_parts = deduplicate_by_path(all_parts)
        print("  Pecas unicas: %d" % len(unique_parts))

        step_parts   = [p for p in unique_parts if is_step_part(p)]
        router_parts = [p for p in step_parts if "router" in get_corte_fabrico(p)]
        direct_parts = [p for p in step_parts if "router" not in get_corte_fabrico(p)]

        print("STEP: %d peca(s) -- router: %d | direto: %d" % (
            len(step_parts), len(router_parts), len(direct_parts)))
        print(SEP)

        if not step_parts:
            print("AVISO: 0 pecas com Corte_Fabrico router/cnc/torno.")
            return

        for part in step_parts:
            part_path   = get_part_path(part)
            base_name   = os.path.splitext(os.path.basename(part_path))[0]
            corte       = get_corte_fabrico(part)
            is_router   = "router" in corte
            output_step = os.path.join(OUT_DIR, base_name + ".step")

            try:
                if is_router:
                    note = export_router_part(sw, part_path, output_step, TMP_DIR)
                else:
                    export_part_to_step(sw, part_path, output_step)
                    note = "%s -- exportado direto" % corte

                ok_count += 1
                size_kb = os.path.getsize(output_step) // 1024 if os.path.isfile(output_step) else 0
                print("  OK    %s.step  [%s]  (%d KB)" % (base_name, note, size_kb))

            except Exception as exc:
                err_count += 1
                print("  ERROR %s -- %s" % (base_name, exc))

    except Exception as exc:
        err_count += 1
        print("ERRO FATAL: %s" % exc)

    finally:
        if sw is not None and asm_opened_by_us and asm_doc is not None:
            try:
                sw.CloseDoc(ASM_PATH)
                print("Assembly fechado.")
            except Exception as e:
                print("AVISO: nao foi possivel fechar o assembly: %s" % e)

        print(SEP)
        print("Resultado: %d exportado(s)  |  %d ignorado(s)  |  %d erro(s)" % (
            ok_count, skip_count, err_count))
        print(SEP2)


if __name__ == "__main__":
    main()
