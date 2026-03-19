# Spec: Integrated Exporter GUI + STEP Export Feature
**Date:** 2026-03-14
**Status:** Approved

---

## 1. Overview

Redesign the existing DXF Exporter tool into a unified **Auto Production** desktop app with a sidebar navigation. The app integrates all current and future export features in a single window. This spec covers:

1. **GUI redesign** — sidebar + content panel architecture, modern dark theme
2. **Feature 2: STEP Export** — batch export of router/cnc/torno parts as STEP AP214, with automatic dowel hole diameter reduction for router parts

---

## 2. GUI Architecture

### Layout

```
┌─────────────────────────────────────────────────────┐
│  Auto Production                              [─][□][×]│
├──────────┬──────────────────────────────────────────┤
│          │  Assembly: [___________________] [Browse] │
│  DXF     ├──────────────────────────────────────────┤
│  Export  │                                          │
│  ──────  │   (active module panel)                  │
│  STEP    │                                          │
│  Export  │                                          │
│          │                                          │
│  (future ├──────────────────────────────────────────┤
│  modules)│  [log output — scrollable]               │
└──────────┴──────────────────────────────────────────┘
```

### Visual style

- **Theme:** `ttk` with `clam` base, overridden with custom dark palette
- **Background:** `#1e1e2e` (sidebar + main), `#2a2a3e` (content panels)
- **Accent:** `#0078D4` (active sidebar item, primary buttons)
- **Text:** `#e0e0e0` (normal), `#ffffff` (active/labels)
- **Log font:** `Consolas 9`
- **UI font:** `Segoe UI 10`
- **No external dependencies** — stdlib + tkinter only

### Assembly field

- Shared across all modules — sits in a fixed header above the content panel
- Persists when switching between modules

### Sidebar

- Vertical list of navigation buttons, one per module
- Active module highlighted with accent colour
- Extensible: adding a new module = adding one entry to a registry list in `main.py`

### Log area

- Shared scrollable log at the bottom of the content area
- Each module writes to the same log (with a header line per run)
- Clear log button per run

---

## 3. File Structure

```
tools/
  exporter/                        # replaces tools/dxf_exporter/
    main.py                        # entry point — MainWindow + sidebar
    solidworks.py                  # COM API wrapper (expanded)
    dxf_cleaner.py                 # unchanged
    modules/
      __init__.py
      dxf_module.py                # DXF export panel (extracted from old main.py)
      step_module.py               # STEP export panel (new)
    requirements.txt               # pywin32>=306, ezdxf>=1.1.0
    run_dxf.py                     # headless DXF runner (updated paths)
```

`tools/dxf_exporter/` is kept intact for reference until the new tool is validated.

`run_step.py` headless runner is out of scope for this iteration — STEP export is GUI-only.

---

## 4. Feature 2 — STEP Export

### 4.1 Part selection and treatment

A part is included in the STEP export if its `Corte_Fabrico` custom property (case-insensitive) contains **at least one** of: `router`, `cnc`, `torno`.

| `Corte_Fabrico` contains | Treatment |
|---|---|
| `router` (alone or in combination) | Copy to tmp → reduce dowel holes → export STEP → delete tmp |
| `cnc` or `torno` only (no `router`) | Export STEP directly — no modifications |

Examples: `ROUTER` → router treatment. `router+cnc` → router treatment. `CNC+TORNO` → direct export. `torno` → direct export.

Function: `is_step_part(component) -> bool` in `solidworks.py`.
Function: `get_corte_fabrico(component) -> str` — returns raw value lowercase, used to determine treatment.

### 4.2 Dowel hole identification (router parts only)

Dowel holes are identified via the SolidWorks Hole Wizard API:
- Iterate `IFeature` objects in the part model via `IModelDoc2.FirstFeature()` / `IFeature.GetNextFeature()`
- For each feature, call `GetSpecificFeature2()` which returns a generic IDispatch
- Wrap result with `_wrap(result, "IHoleWizardFeatureData2")` before accessing properties
- Check `IHoleWizardFeatureData2.Type == _sw_module().swHoleType_Dowel` (constant from the early-binding module, same pattern as all other SW enums in this codebase)
- Collect matching features and their diameter via `IHoleWizardFeatureData2.Diameter` (Double, **metres** — SI units, consistent with all SolidWorks dimension properties)

Function: `get_dowel_holes(part_doc) -> List[HoleInfo]` in `solidworks.py`
where `HoleInfo = namedtuple('HoleInfo', ['feature', 'original_diameter_m'])`.
`original_diameter_m` is in metres (e.g. a 10 mm dowel = `0.010`).

### 4.3 Temporary copy workflow (router parts)

```
1. copy_part_to_tmp(sldprt_path, tmp_dir) → tmp_path   (.tmp/<partname>_step_tmp.sldprt)
2. open tmp_path in SolidWorks with OpenDoc6(..., options=1)  # 1 = swOpenDocOptions_Silent
3. get_dowel_holes(tmp_doc)
4. for each hole: new_diameter = original_diameter_m - 0.001  (subtract 1 mm in metres)
                  modify_dowel_diameter(hole.feature, new_diameter)
                  # internally: set IHoleWizardFeatureData2.Diameter,
                  #             call IFeature.ModifyDefinition(featureData),
                  #             then IModelDoc2.EditRebuild3()
5. export_part_to_step(sw_app, tmp_path, output_step_path)
6. sw_app.CloseDoc(tmp_path) — do NOT save
7. delete tmp_path
```

The `.tmp/` directory lives at the repo root (already gitignored per project conventions).

Failure handling: if any step from 2 onwards fails, still attempt CloseDoc(tmp_path) + delete tmp file before re-raising the exception.

### 4.4 STEP export (all step parts)

Export method: `IModelDoc2.SaveAs4(output_path, version, options, exportData, errors, warnings)`
- `version = 0` (swSaveAsCurrentVersion)
- `options = 1` (swSaveAsOptions_Silent)
- `exportData`: obtained via `sw_app.GetExportFileData(2)` (2 = swExportStep), then wrapped with `_wrap(result, "IStepExportOptions")` to set `.ExportAs = _sw_module().swStepAP214` before passing to SaveAs4. This ensures AP214 schema regardless of the user's last UI selection.

Fallback: if `SaveAs4` returns False, log error with SW error code (from `errors` ByRef parameter), continue with next part.

Output filename: `{part_base_name}.step` in the user-selected output folder.

### 4.5 Module panel (step_module.py)

Controls:
- Output folder field + Browse button
- "Export STEP" button (disabled during run)
- Progress bar (determinate, advances once per part)
- Status label

Log output (shared with main window):
```
A exportar STEP: 5 peça(s) — router: 3 | cnc: 1 | torno: 1
────────────────────────────────────────────────────────────
  OK    18026.100.001.step  [2 dowel(s) reduzido(s): ⌀10→⌀9, ⌀8→⌀7]
  OK    18026.100.002.step  [sem furos de cavilha]
  OK    18026.100.003.step  [cnc — exportado direto]
  SKIP  18026.100.005 — ficheiro aberto no SolidWorks; fechar e tentar novamente
  ERROR 18026.100.004 — SaveAs4 falhou (código 2)
────────────────────────────────────────────────────────────
Resultado: 3 exportado(s)  |  1 ignorado(s)  |  1 erro(s)
```

---

## 5. solidworks.py additions

New functions to add (existing functions unchanged):

| Function | Signature | Purpose |
|---|---|---|
| `is_step_part` | `(component) -> bool` | Check Corte_Fabrico for router/cnc/torno |
| `get_corte_fabrico` | `(component) -> str` | Return raw Corte_Fabrico value (lowercase) |
| `get_dowel_holes` | `(part_doc) -> list[HoleInfo]` | Return list of HoleInfo (feature + diameter in metres) |
| `modify_dowel_diameter` | `(feature, new_diameter_m: float)` | Set IHoleWizardFeatureData2.Diameter, call IFeature.ModifyDefinition(featureData), then IModelDoc2.EditRebuild3() |
| `export_part_to_step` | `(sw_app, sldprt_path, output_step_path)` | Export STEP AP214 via SaveAs4 + IStepExportOptions |
| `copy_part_to_tmp` | `(sldprt_path, tmp_dir) -> str` | Copy .sldprt to tmp_dir, return new path |

---

## 6. Error handling

| Scenario | Behaviour |
|---|---|
| No step parts found | Log message, no error |
| Dowel hole type not recognised | Skip modification, export as-is, log warning |
| SaveAs4 returns False | Log error with SW error code, continue with next part |
| Tmp file copy fails | Log error, skip part |
| SolidWorks not running | Fatal error dialog, abort |
| Router part already open in SW | Log `SKIP — ficheiro aberto no SolidWorks; fechar e tentar novamente`, continue |
| CNC/torno part already open in SW | Use open doc directly (no copy needed) |

---

## 7. Testing

Test assembly: `c:\Users\Micael\Desktop\Auto Production\18026.100.900.SLDASM`

Verification checklist:
- [ ] router parts: STEP exported, dowel diameters reduced by exactly 1mm
- [ ] cnc/torno parts: STEP exported unchanged
- [ ] combinations (router+cnc): treated as router (dowel modification applies)
- [ ] tmp files: fully cleaned up after export (success and failure)
- [ ] original .sldprt files: unmodified after run
- [ ] GUI: sidebar switches correctly between DXF and STEP modules
- [ ] DXF export: still works as before (regression)

---

## 8. Out of scope

- Batch processing of multiple assemblies
- STEP export of assemblies (parts only)
- Other STEP schemas (AP203, AP242)
- Undo/redo integration with SolidWorks history
- Headless STEP runner (`run_step.py`)
