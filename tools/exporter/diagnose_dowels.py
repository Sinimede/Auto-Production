"""
diagnose_dowels.py — Dry-run: list dowel holes found per router part.

Connects to the active SolidWorks assembly (already open), resolves
lightweight components, and for each router part calls get_dowel_holes.
Does NOT modify anything.

Usage:
    python diagnose_dowels.py [optional_asm_path]

If no path is given, uses the active SW document.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import win32com.client

from solidworks import (
    _wrap, _open_doc,
    connect_to_solidworks,
    get_all_parts, deduplicate_by_path,
    is_step_part, get_corte_fabrico, get_part_path,
    get_dowel_holes,
)

SEP  = "-" * 72
SEP2 = "=" * 72


def count_all_holewzd(part_doc):
    """
    Iterate every feature and count all HoleWzd features (no sub-type filter).
    Returns (total_holewzd, [(feat_name, fastener_type2), ...])
    """
    records = []
    try:
        import re
        part = _wrap(part_doc, "IPartDoc")
        feat_raw = part.FirstFeature()
        while feat_raw is not None:
            feat = _wrap(feat_raw, "IFeature")
            try:
                type_name_ref = feat.GetTypeName2
                type_name = type_name_ref() if callable(type_name_ref) else str(type_name_ref)
                if type_name == "HoleWzd":
                    feat_name = ""
                    try:
                        n = feat.Name
                        feat_name = n() if callable(n) else str(n)
                    except Exception:
                        pass
                    ft2_val = None
                    try:
                        defn_raw = feat.GetDefinition()
                        feat_data = _wrap(defn_raw, "IWizardHoleFeatureData2")
                        feat_data.AccessSelections(part_doc, None)
                        try:
                            ft2 = feat_data.FastenerType2
                            if isinstance(ft2, tuple):
                                ft2 = ft2[0]
                            ft2_val = int(ft2)
                        finally:
                            try:
                                feat_data.ReleaseSelectionAccess()
                            except Exception:
                                pass
                    except Exception:
                        pass
                    records.append((feat_name, ft2_val))
            except Exception:
                pass
            try:
                feat_raw = feat.GetNextFeature()
            except Exception:
                break
    except Exception:
        pass
    return records


_DOWEL_FASTENER_TYPES = frozenset({703, 706, 707, 710, 711})

_FT2_LABELS = {
    703: "Dowel-ANSI-Inch",
    706: "Dowel-BSI",
    707: "Dowel-DIN",
    710: "Dowel-ISO",
    711: "Dowel-JIS",
}


def ft2_label(ft2_val):
    if ft2_val is None:
        return "? (read error)"
    if ft2_val in _DOWEL_FASTENER_TYPES:
        return _FT2_LABELS.get(ft2_val, f"Dowel-{ft2_val}")
    return f"Non-dowel ({ft2_val})"


def main():
    ok = 0
    err = 0
    opened_parts = []

    sw = None
    asm_doc = None
    asm_opened_by_us = False

    print(SEP2)
    print("DIAGNÓSTICO — Dowel holes por peça router (dry-run, sem modificações)")
    print(SEP2)

    try:
        sw = connect_to_solidworks()
        print("Conectado ao SolidWorks.")

        # Determine assembly: arg or active doc
        if len(sys.argv) > 1:
            asm_path = os.path.normpath(os.path.abspath(sys.argv[1]))
            print(f"Assembly (argumento): {asm_path}")
            # Use the already-open doc if it matches; open otherwise
            try:
                active = sw.ActiveDoc
                if active is not None:
                    ap = os.path.normpath(active.GetPathName())
                    if ap.lower() == asm_path.lower():
                        asm_doc = active
                        asm_opened_by_us = False
            except Exception:
                pass
            if asm_doc is None:
                result = sw.OpenDoc6(asm_path, 2, 0, "", 0, 0)
                asm_doc = result[0] if isinstance(result, tuple) else result
                asm_opened_by_us = True
        else:
            asm_doc = sw.ActiveDoc
            if asm_doc is None:
                print("ERRO: Nenhum documento ativo no SolidWorks.")
                return
            _gpn = asm_doc.GetPathName
            asm_path = os.path.normpath(_gpn() if callable(_gpn) else _gpn)
            print(f"Assembly ativo: {os.path.basename(asm_path)}")

        # Resolve lightweight
        print("A resolver componentes lightweight...")
        try:
            asm = _wrap(asm_doc, "IAssemblyDoc")
            asm_raw = getattr(asm, "_dispobj_", None) or getattr(asm, "_oleobj_", None) or asm
            win32com.client.Dispatch(asm_raw).ResolveAllLightweightComponents(False)
            print("Resolve OK.")
        except Exception as e:
            print(f"AVISO: ResolveAllLightweightComponents falhou: {e}")

        all_parts = get_all_parts(asm_doc)
        unique   = deduplicate_by_path(all_parts)
        step_p   = [p for p in unique if is_step_part(p)]
        router_p = [p for p in step_p if "router" in get_corte_fabrico(p)]
        other_p  = [p for p in step_p if "router" not in get_corte_fabrico(p)]

        print(f"Peças únicas: {len(unique)}  |  STEP: {len(step_p)}  |  router: {len(router_p)}  |  direto: {len(other_p)}")
        print(SEP)

        if not router_p:
            print("Nenhuma peça router encontrada. Verifica Corte_Fabrico no assembly.")
            return

        for part_comp in router_p:
            part_path = get_part_path(part_comp)
            base = os.path.basename(part_path)
            part_doc = None
            part_opened = False

            try:
                # Try to get already-open doc
                existing = sw.GetOpenDocumentByName(part_path)
                if existing is not None:
                    part_doc = existing
                else:
                    # Open in read mode (options=1 = swOpenDocOptions_Silent)
                    result = sw.OpenDoc6(part_path, 1, 1, "", 0, 0)
                    part_doc = result[0] if isinstance(result, tuple) else result
                    part_opened = True
                    if part_doc is not None:
                        opened_parts.append(part_path)

                if part_doc is None:
                    print(f"  SKIP  {base}  (não foi possível abrir)")
                    err += 1
                    continue

                # Count ALL HoleWzd features (raw, no filter)
                all_records = count_all_holewzd(part_doc)

                # Get only Dowel holes (via the fixed function)
                dowels = get_dowel_holes(part_doc)

                dowel_count   = len(dowels)
                total_holewzd = len(all_records)
                non_dowel     = [r for r in all_records if r[1] not in _DOWEL_FASTENER_TYPES]

                print(f"  {base}")
                print(f"    HoleWzd total : {total_holewzd}  |  Dowel: {dowel_count}  |  Non-dowel filtrado: {len(non_dowel)}")

                # Show all HoleWzd with their sub-type
                for feat_name, ft2_val in all_records:
                    tag = "DOWEL" if (ft2_val in _DOWEL_FASTENER_TYPES) else "SKIP "
                    print(f"      [{tag}]  {feat_name or '?'}  ft2={ft2_val}  ({ft2_label(ft2_val)})")

                # Show diameters of confirmed Dowels
                for h in dowels:
                    print(f"      -> d={h.original_diameter_m*1000:.1f}mm  (seria reduzido para d={(h.original_diameter_m-0.001)*1000:.1f}mm)")

                ok += 1

            except Exception as exc:
                print(f"  ERROR {base}: {exc}")
                err += 1

            finally:
                if part_opened and part_doc is not None:
                    try:
                        sw.CloseDoc(part_path)
                    except Exception:
                        pass

        print(SEP)
        print(f"Resultado: {ok} OK  |  {err} erros")

    except Exception as exc:
        print(f"ERRO FATAL: {exc}")

    finally:
        if asm_opened_by_us and asm_doc is not None and sw is not None:
            try:
                sw.CloseDoc(asm_path)
            except Exception:
                pass
        print(SEP2)


if __name__ == "__main__":
    main()
