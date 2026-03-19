# Assembly DXF Exporter & Cleaner — Design Spec

**Date:** 2026-03-12
**Status:** Approved
**Domain:** Mechanical Engineering / SolidWorks / Laser Cutting

---

## Problem

Mechanical engineers at the department design industrial machines in SolidWorks. Parts intended for laser cutting are tagged with the custom property `corte fabrico = laser`. The current workflow requires:

1. Manually identifying which parts in an assembly are laser-cut
2. Opening each part's drawing (.slddrw) one by one
3. Exporting to DXF manually
4. Post-editing each DXF to remove concentric circles caused by countersunk holes

Countersunk (escareado) holes produce two concentric circles when exported to DXF:
- Small circle = the through-hole (needed by laser cutter)
- Large circle = the countersink diameter (not needed; causes double-cut if left in)

If not removed, the laser would attempt to cut both circles, wasting time and potentially damaging the part or sheet.

**Exception:** If the large circle is the outer contour of the part (e.g., a round disc), it must be kept. The through-hole and countersink circles are interior features; the outer contour defines the part boundary.

---

## Solution

A Windows Desktop application (Python + tkinter) that:

1. Accepts a SolidWorks Assembly file (.sldasm) and an output folder
2. Connects to a running SolidWorks instance via COM API
3. Traverses all components in the assembly (recursively, including sub-assemblies)
4. Filters parts where `corte fabrico = laser`
5. Deduplicates (same part used in multiple instances → export once)
6. For each laser part: finds the corresponding .slddrw (same name, same folder), exports to DXF via SolidWorks COM, cleans the DXF
7. DXF cleaning: removes concentric circle duplicates, preserving outer contours
8. Saves cleaned DXFs to the user-selected output folder
9. Shows real-time progress and a final summary log

---

## Architecture

```
tools/dxf_exporter/
├── main.py           # tkinter UI + threading worker
├── solidworks.py     # SolidWorks COM API wrapper
├── dxf_cleaner.py    # ezdxf-based DXF post-processing
└── requirements.txt  # pywin32>=306, ezdxf>=1.1.0
```

### Component Responsibilities

**`main.py`**
- Renders the tkinter window
- Handles file/folder selection via dialogs
- Validates inputs before starting work
- Dispatches the export pipeline to a background thread
- Receives progress updates via `root.after(0, callback)` and updates the UI

**`solidworks.py`**
- All SolidWorks COM interactions are isolated here
- `connect_to_solidworks()` — attaches to running SolidWorks via `win32com.client.Dispatch("SldWorks.Application")`
- `open_assembly(sw, path)` — checks if already open via `sw.GetOpenDocumentByName(path)` first; only calls `OpenDoc6` if not already open; tracks whether it was opened by us (so we only close documents we opened, never closing the engineer's work)
- `get_all_parts(asm_doc)` — recursively collects all part components via `GetComponents(False)` (SW API: `topLevelOnly=False` = ALL levels, i.e. recursive), filters out suppressed/lightweight
- `deduplicate_by_path(components)` — deduplicates by .sldprt path (handles multiple instances of the same part)
- `is_laser_part(component)` — reads `corte fabrico` custom property, returns True if value == "laser"
- `get_part_path(component)` — returns full .sldprt path
- `find_drawing(part_path)` — looks for .slddrw at same path/name; returns None if not found
- `export_drawing_to_dxf(sw, drw_path, out_path)` — checks if drawing already open before `OpenDoc6`; exports via `SaveAs4(path, 0, 1, None, err, warn)` (version=0=current, options=1=silent, pExportData=None accepted for DXF in SW2018+); only calls `CloseDoc` if we opened it; all inside try/finally

**`dxf_cleaner.py`**
- No SolidWorks dependency — pure Python + ezdxf
- `clean_dxf(input_path, output_path)` — entry point; returns count of circles removed
- Internal: groups circles by center (union-find, tolerance 0.1mm), determines outer contour, removes redundant circles

---

## DXF Cleanup Algorithm

```
Input: DXF file with potential concentric circle groups

1. Collect all CIRCLE entities from model space
2. Group concentric circles (center distance ≤ 0.1mm) using union-find
3. For each group with 2+ circles:
   a. Sort by radius ascending → [smallest, ..., largest]
   b. Is largest the outer contour?
      → YES if: every other circle's (center + radius) is inside largest
                AND every sampled point from non-circle geometry is inside largest
      → KEEP: largest + smallest
      → REMOVE: all intermediates
   c. Is largest NOT the outer contour?
      → KEEP: smallest only
      → REMOVE: all others
4. Delete all marked circles (collect list first, delete after iteration)
5. Save to output path
```

**Geometry point sampling for outer contour test:**
- LINE → start + end
- ARC → sample every 5 degrees along the full arc curve (using `start_angle`, `end_angle`, `radius`; handle wrap-around at 360°)
- LWPOLYLINE → all vertices
- SPLINE → all control points
- ELLIPSE, INSERT → ignored (out of scope for laser cutting DXFs)

**Why dense arc sampling:** An arc sampled at only 3 points (start/end/mid) can appear fully inside a candidate circle even when it bulges outside. Sampling every 5° catches all such cases without being excessively expensive.

**Constants:** `CONCENTRIC_TOLERANCE = 0.1` (mm)

---

## UI Layout

```
┌─────────────────────────────────────────────────────────────┐
│  Assembly DXF Exporter & Cleaner                            │
├─────────────────────────────────────────────────────────────┤
│  Assembly (.sldasm): [________________________] [Browse...] │
│  Output folder:      [________________________] [Browse...] │
│                                                             │
│                    [  Export & Clean  ]                     │
│                                                             │
│  Progress: [████████████░░░░░░░░░░] 60%                     │
│  Status:   Processing Flange_001.SLDPRT...                  │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  OK    Flange_001.dxf (2 circles removed)             │  │
│  │  SKIP  Parafuso_M8 (corte fabrico != laser)           │  │
│  │  ERROR Chapa_002.slddrw not found                     │  │
│  └───────────────────────────────────────────────────────┘  │
│  Finished: 12 exported, 1 error.                            │
└─────────────────────────────────────────────────────────────┘
```

---

## SolidWorks COM API Reference

| Operation | Method | Notes |
|---|---|---|
| Connect | `Dispatch("SldWorks.Application")` | SW must be running |
| Open assembly | `OpenDoc6(path, 2, 1, "", err, warn)` | Type 2 = assembly |
| Open drawing | `OpenDoc6(path, 3, 1, "", err, warn)` | Type 3 = drawing |
| Close doc | `CloseDoc(path)` | Always in finally block |
| Get components | `GetComponents(False)` | False = recursive |
| Get model | `GetModelDoc2()` | None if suppressed |
| Get type | `GetType()` | 1=part, 2=asm, 3=drw |
| Get path | `GetPathName()` | Full path to .sldprt |
| Read property | `Extension.CustomPropertyManager("").Get("corte fabrico")` | "" = doc-level |
| Export DXF | `SaveAs4(dxf_path, 0, 1, None, err, warn)` | Extension drives format |

**Note on late-binding VARIANT ByRef:** If `Get()` fails, fall back to `Get6()` with explicit VARIANT ByRef parameters. To avoid this complexity, run `python -m win32com.client.makepy "SldWorks 20XX Type Library"` once to generate early-binding wrappers.

---

## Error Handling

| Condition | Handling |
|---|---|
| SolidWorks not running | RuntimeError → FATAL in log, button re-enabled |
| Invalid .sldasm path | UI validation before thread start |
| Assembly fails to open | RuntimeError → ERROR in log |
| Lightweight component | Attempt SetComponentState(3); if fails → WARN + skip |
| Property absent | Treat as non-laser, skip silently |
| .slddrw not found | WARN in log (not ERROR), counted in warnings total (separate from errors) |
| DXF export fails | ERROR in log (SaveAs4 returned False) |
| DXF unreadable | Exception caught → ERROR in log |
| Output not writable | Exception caught → ERROR in log |
| Duplicate part instances | Deduplicated by path before processing |

---

## Verification Plan

1. **Unit test `dxf_cleaner.py` with reference DXF** (`18026.100.001.DXF`, 1 circle + 4 lines) → expect 0 circles removed
2. **Synthetic DXF tests** (4 scenarios: 2-concentric, 3-concentric-disc, 3-concentric-non-outer, no pairs)
3. **COM connectivity test** — `sw.RevisionNumber` prints SolidWorks version
4. **Property read test** — open one .sldprt with `corte fabrico=laser`, confirm reader returns `"laser"`
5. **Full pipeline test** — small assembly (3 parts, 1 laser), verify only the laser part is exported and its DXF is clean
