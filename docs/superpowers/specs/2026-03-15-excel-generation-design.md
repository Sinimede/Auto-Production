# Excel Generation — Design Spec
**Date:** 2026-03-15
**Status:** Under Review

---

## Overview

Add Excel file generation to both export features (DXF/Laser and STEP/Router+CNC+Torno).
Each process uses its own template from `Templates/` and generates a named `.xlsx` in the output folder.

---

## Architecture

### New files
- `tools/exporter/excel_writer.py` — copies template, fills data rows, saves output

### Modified files
- `tools/exporter/solidworks.py` — new helper functions for data gathering
- `tools/exporter/modules/dxf_module.py` — checkbox + "Gerar Excel apenas" button
- `tools/exporter/modules/step_module.py` — idem

### Templates (read-only, sheet name `Folha1` confirmed in all four files)
```
Templates/
  Laser_template.xlsx
  Router_template.xlsx
  CNC_template.xlsx
  Torno_template.xlsx
```

---

## Data Gathering (`solidworks.py` additions)

### `count_instances(all_components, part_path) -> int`
Count non-suppressed instances of a part (identified by normalised lowercase path) across `all_components` (before deduplication).
Skip components where `comp.IsSuppressed()` returns True.

### `get_custom_property_evaluated(model_doc, prop_name) -> str`
Read the **Evaluated Value** of a custom property:
```python
result = mgr.Get4(prop_name, False)
val = result[2] if isinstance(result, tuple) and len(result) > 2 else result
```
Use index **2** (`resolvedVal`) — the configuration-evaluated expression result (e.g. "Cast Alloy Steel" instead of "SW-Material@part.SLDPRT").

Note: existing helpers (`get_corte_fabrico`, `is_laser_part`) use index 1 for filtering only — that is intentional for those functions. The new helper uses index 2 for display-quality output. Both are correct in their respective contexts.

Returns empty string on any error or missing property.

### `get_bounding_box_thickness(model_doc) -> float | None`
```python
part = _wrap(model_doc, "IPartDoc")   # required — IModelDoc2 does not expose GetPartBox
box = part.GetPartBox(True)           # returns (xmin, ymin, zmin, xmax, ymax, zmax) in metres
dx, dy, dz = box[3]-box[0], box[4]-box[1], box[5]-box[2]
return round(min(dx, dy, dz) * 1000, 2)  # mm, 2 decimal places
```
Returns `None` on any error.

### `get_part_data(component, all_components) -> dict`
Internal call chain:
```python
part_path  = component.GetPathName()          # for count_instances
model_doc  = component.GetModelDoc2()         # for property reads and bounding box
```
Returns:
```python
{
    "qty":             int,   # count_instances(all_components, part_path)
    "part_number":     str,   # os.path.splitext(os.path.basename(part_path))[0]
    "Description":     str,   # get_custom_property_evaluated(model_doc, "Description")
    "Corte_Fabrico":   str,   # get_custom_property_evaluated(model_doc, "Corte_Fabrico")
    "Simetria":        str,   # get_custom_property_evaluated(model_doc, "Simetria")
    "Material":        str,   # get_custom_property_evaluated(model_doc, "Material")
    "TratSuperficial": str,   # get_custom_property_evaluated(model_doc, "TratSuperficial")
    "espessura":       float | None,  # get_bounding_box_thickness(model_doc)
}
```

---

## Column Mappings

openpyxl indexing: column A = 1, column B = 2, column C = 3, etc.
Column A is always empty (from template). Data starts at column B (openpyxl index 2).
Header is row 1 — preserved from template. Data written from row 2 onwards.
The writer maps index 0 of `column_order` → openpyxl column index 2, index 1 → col 3, etc.
Row order matches `deduplicate_by_path` traversal order (same as log output).
If output file already exists it is silently overwritten.

### Laser → `Laser.xlsx`
`column_order = ["qty", "part_number", "Description", "Corte_Fabrico", "Simetria", "Material", "TratSuperficial", "espessura"]`

| openpyxl col | Header | Data key |
|---|---|---|
| 2 (B) | QTY. | qty |
| 3 (C) | PART NUMBER | part_number |
| 4 (D) | DESCRIPTION | Description |
| 5 (E) | Corte_Fabrico | Corte_Fabrico |
| 6 (F) | Simétrica com | Simetria |
| 7 (G) | Material | Material |
| 8 (H) | TratSuperficial | TratSuperficial |
| 9 (I) | Espessura | espessura |

### Router → `Router.xlsx`
`column_order = ["qty", "part_number", "Description", "Corte_Fabrico", "espessura", "Material", "Simetria"]`

| openpyxl col | Header | Data key |
|---|---|---|
| 2 (B) | QTY. | qty |
| 3 (C) | PART NUMBER | part_number |
| 4 (D) | DESCRIPTION | Description |
| 5 (E) | Corte_Fabrico | Corte_Fabrico |
| 6 (F) | Espessura | espessura |
| 7 (G) | Material | Material |
| 8 (H) | Simétrica com | Simetria |

### CNC → `CNC.xlsx`
`column_order = ["qty", "part_number", "Description", "Corte_Fabrico", "Material", "TratSuperficial", "Simetria"]`

| openpyxl col | Header | Data key |
|---|---|---|
| 2 (B) | QTY. | qty |
| 3 (C) | PART NUMBER | part_number |
| 4 (D) | DESCRIPTION | Description |
| 5 (E) | Corte_Fabrico | Corte_Fabrico |
| 6 (F) | Material | Material |
| 7 (G) | TratSuperficial | TratSuperficial |
| 8 (H) | Simétrica com | Simetria |

### Torno → `Torno.xlsx`
`column_order = ["qty", "part_number", "Description", "Corte_Fabrico", "Material", "TratSuperficial", "Simetria"]`
(identical column order to CNC)

| openpyxl col | Header | Data key |
|---|---|---|
| 2 (B) | QTY. | qty |
| 3 (C) | PART NUMBER | part_number |
| 4 (D) | DESCRIPTION | Description |
| 5 (E) | Corte_Fabrico | Corte_Fabrico |
| 6 (F) | Material | Material |
| 7 (G) | TratSuperficial | TratSuperficial |
| 8 (H) | Simétrica com | Simetria |

---

## `excel_writer.py`

```python
def generate_excel(template_path: str, rows: list[dict],
                   output_path: str, column_order: list[str]) -> None
```

1. `shutil.copy2(template_path, output_path)` — copy template, never modify original
2. `wb = openpyxl.load_workbook(output_path)`
3. `ws = wb["Folha1"]`
4. Row 1 = header (preserved). Write data from row 2.
5. For each `row_dict` in `rows` (enumerate from row index 2):
   ```python
   for col_offset, key in enumerate(column_order):
       ws.cell(row=row_idx, column=2 + col_offset).value = row_dict.get(key, "")
   ```
   `espessura` is written as-is (float or empty string if None).
6. `wb.save(output_path)`

Template path resolved relative to `excel_writer.py` location (`tools/exporter/`):
```python
TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "Templates"
)
```
This formula is correct for `excel_writer.py` at `tools/exporter/` (3 `dirname` calls reach repo root).

---

## UI Changes

### Row layout after changes (both modules)

| Row | Widget |
|---|---|
| 0 | Section title |
| 1 | Separator |
| 2 | Output folder (label + entry + browse button) |
| 3 | Checkbox "Gerar Excel" |
| 4 | Export button (DXF / STEP) |
| 5 | "Gerar Excel apenas" button |
| 6 | Progress bar |
| 7 | Status label |

Existing rows 3–5 shift to rows 4–7 to accommodate the two new UI elements.

### Button state management
At the start of **either** background operation (export or Excel-only):
- Disable both `btn_export` and `btn_excel_only`

On finish (success or error):
- Re-enable both buttons

This prevents concurrent operations.

### "Gerar Excel apenas" button style
Same styling as Export button but with a distinct background (e.g. `"#3a3a5a"` instead of ACCENT blue) to signal secondary action. Same `relief="flat"`, `cursor="hand2"`, `FONT_BTN`.

---

## STEP — Multiple Excel files per run

Parts are grouped by `Corte_Fabrico` value (lowercased). A part may appear in **multiple groups** if its value contains multiple keywords (e.g. `"router+cnc"` → appears in both `Router.xlsx` and `CNC.xlsx`).

Grouping rules:
- `"router" in corte_fabrico` → include in Router group
- `"cnc" in corte_fabrico` → include in CNC group
- `"torno" in corte_fabrico` → include in Torno group

Each non-empty group generates its own Excel. Up to 3 files per run.

---

## Dependencies

Add `openpyxl` to `tools/exporter/requirements.txt`.

---

## Error Handling

- Missing template file → log error, skip Excel generation (do not abort export)
- SW property not found → write empty string in cell
- Bounding box unavailable → write empty string in espessura cell
- Excel write failure → log error, do not abort export
