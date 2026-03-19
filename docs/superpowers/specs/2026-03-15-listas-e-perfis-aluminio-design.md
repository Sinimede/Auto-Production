# Design: Listas Panel + Perfis de Alumínio List
**Date:** 2026-03-15
**Status:** Approved

---

## Overview

Two related changes:

1. **Rename "Lista de Material" tab → "Listas"** with checkboxes to select which Excel reports to generate (Laser, Router, CNC, Torno, BOM, Perfis de Alumínio).
2. **New list: Perfis de Alumínio** — aggregates weldment cut list data from all aluminium profile parts in the assembly, writes to `Perfis-de-Alumínio_template.xlsx`.

---

## 1. UI Changes

### main.py
- Change MODULES registry entry: `("Lista de Material", "bom", BomModule)` → `("Listas", "listas", ListasModule)`
- Import `ListasModule` from `modules.listas_module` instead of `BomModule`

### modules/listas_module.py (new file, replaces bom_module.py as the nav entry)
- `bom_module.py` is kept unchanged — `AllModule` continues to call it directly
- `ListasModule(tk.Frame)` UI:
  - Output folder picker (Browse… button)
  - 6 checkboxes (all checked by default): Laser, Router, CNC, Torno, BOM, Perfis de Alumínio
  - "Gerar Selecionadas" button
  - Indeterminate progress bar + status label
- Background worker opens assembly once, runs selected phases in sequence
- Each phase in its own try/except — partial failure does not stop remaining phases

---

## 2. Data Extraction — solidworks.py

### New: `get_perfis_parts(asm_doc) → list[tuple[str, int]]`
- Calls existing `get_all_parts(asm_doc)` to get all part components (flat list)
- Filters by `Corte_Fabrico` custom property matching "PERFIL ALUMINIO" or "PERFIL ALUMÍNIO" (case-insensitive; use `.lower()` + compare both accented and unaccented variants via `unicodedata.normalize`)
- Deduplicates by path with existing `deduplicate_by_path`
- Counts instances with existing `count_instances(all_parts, part_path)`
- Returns list of `(part_path: str, instance_count: int)` — one entry per unique part file

### New: `get_weldment_cut_list(sw, part_path) → list[CutListItem]`
- Opens the part with `_open_doc(sw, path, doc_type=1, silent=True)`
- Iterates features via `IPartDoc.FirstFeature()` with callable-guard pattern
- Finds features where `GetTypeName2() == "CutListFolder"`
- For each `CutListFolder` `IFeature` object (`feat`), apply callable-guard for `IsSuppressed` and skip suppressed folders:
  ```python
  is_sup_ref = feat.IsSuppressed
  if is_sup_ref() if callable(is_sup_ref) else bool(is_sup_ref):
      continue
  ```
- Read custom properties by calling `GetCustomInfoValue` **on the `IFeature` object itself** (not on `IPartDoc` or `IModelDoc2`):
  ```python
  feat.GetCustomInfoValue("", "DESCRIPTION")   # first arg = config name, empty = default
  feat.GetCustomInfoValue("", "LENGTH")
  feat.GetCustomInfoValue("", "QUANTITY")
  ```
  - `DESCRIPTION` — profile description string
  - `LENGTH` — plain numeric string in mm (no conversion needed); parse as float
  - `QUANTITY` — primary name `"QUANTITY"`, fallback `"QTY"` if empty/missing, then default to `1`. If neither found, log warning: `"AVISO: QUANTITY/QTY não encontrado em <feat_name> — assumido qty=1"`. **Exact property name must be verified against a real weldment part before implementation** — may differ in Portuguese SW installs.
- Returns list of `CutListItem(description: str, length_mm: float, qty: int)`
- Closes part in `finally` using `sw.CloseDoc(os.path.normpath(os.path.abspath(part_path)))` — normalised path required

### Aggregation (in worker)
- For each `(part_path, instance_count)` from `get_perfis_parts`:
  - Call `get_weldment_cut_list` → multiply each item's `qty` by `instance_count`
- Merge rows with same `(description, length_mm)` across parts — sum quantities
- Sort final rows by `length_mm` ascending

---

## 3. perfis_writer.py (new file)

### `generate_perfis(rows: list[dict], output_path: str)`
- `rows` format: `[{"qty": int, "description": str, "length_mm": float}, ...]`
- Opens `Templates/Perfis-de-Alumínio_template.xlsx`
- Template Excel Table (`Tabela1`) has ref `B2:D24`: header at row 2 (B2=QTY, C2=DESCRIPTION, D2=LENGTH)
- Writes data from row 3 onwards:
  - **Column A**: ITEM NO (1, 2, 3… sequential, written as plain cell values outside the table)
  - **Column B**: qty
  - **Column C**: description
  - **Column D**: length_mm (rounded to 2 decimal places)
- Column A header (`A2 = "ITEM NO."`) is written at output time since it is not pre-defined in the template; column A has no template styling
- Template has 22 pre-styled rows (3–24); writes beyond if needed
- After writing data, update the Excel Table `Tabela1` ref to cover all data rows (e.g. `B2:D{last_row}`) — same pattern as `bom_writer.py`
- Saves to `output_path`

---

## 4. listas_module.py — Worker Phases

Opens assembly once. Runs selected phases in order:

| # | Checkbox | Excel output | Logic |
|---|----------|-------------|-------|
| 1 | Laser | `Laser.xlsx` | `get_all_parts` → filter laser → `generate_excel` with `Laser_template.xlsx` |
| 2 | Router | `Router.xlsx` | filter router → `generate_excel` with `Router_template.xlsx` |
| 3 | CNC | `CNC.xlsx` | filter cnc → `generate_excel` with `CNC_template.xlsx` |
| 4 | Torno | `Torno.xlsx` | filter torno → `generate_excel` with `Torno_template.xlsx` |
| 5 | BOM | `Lista de materiais.xlsx` | `bom_writer.generate_bom` (existing logic) |
| 6 | Perfis | `Perfis de Alumínio.xlsx` | `get_perfis_parts` → `get_weldment_cut_list` → aggregate → `generate_perfis` |

Note: Laser/Router/CNC/Torno phases generate **Excel only** (no DXF/STEP files). This is intentional — the "Listas" panel is specifically for generating Excel reports/planning documents. DXF and STEP file exports remain in their own dedicated panels.

---

## 5. all_module.py Changes

- Update title label: `"Gerar Tudo — DXF + STEP + BOM + Perfis de Alumínio"`
- Phase counter: `[1/4]` DXF, `[2/4]` STEP, `[3/4]` BOM, `[4/4]` Perfis
- Add `_run_perfis(sw, asm_doc, out_dir, ui) → list[str]` method — same structure as `_run_dxf`, `_run_step`, `_run_bom` (returns list of error strings)
- "Gerar Tudo" always runs Perfis unconditionally (no checkboxes here — that's the Listas panel's job)
- Partial failure resilient — errors collected, remaining phases always run

---

## Files Changed / Created

| File | Action |
|------|--------|
| `tools/exporter/main.py` | Edit — rename nav entry, swap import |
| `tools/exporter/modules/listas_module.py` | Create |
| `tools/exporter/modules/bom_module.py` | No change |
| `tools/exporter/solidworks.py` | Edit — add `get_perfis_parts`, `get_weldment_cut_list` |
| `tools/exporter/perfis_writer.py` | Create |
| `tools/exporter/all_module.py` | Edit — add phase 4 |

---

## Edge Cases

- **No perfis parts found**: log "Nenhuma peça Perfil Alumínio encontrada." and skip — not an error.
- **Part not open in SW**: `_open_doc` opens it; closed in `finally`.
- **Empty cut list**: part has no `CutListFolder` features → skip with warning.
- **`LENGTH` property missing or non-numeric**: skip item, log warning.
- **`QUANTITY` property missing**: default to 1.
- **Corte_Fabrico variants**: normalise with `unicodedata.normalize('NFD')` + strip accents before comparison, then compare lowercase.
