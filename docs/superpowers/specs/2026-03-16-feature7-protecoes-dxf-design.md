# Feature 7 — DXF Proteções + Process Selection

**Date:** 2026-03-16
**Status:** Approved by user

---

## Objective

1. Add DXF export + Excel list for parts with `Corte_Fabrico = "Proteções"`.
2. Make DXF panel and STEP panel individually selectable per process (avoid exporting everything when only one process is needed).
3. Add "Proteções" checkbox to the Listas panel.
4. "Gerar Tudo" always runs everything (no change to behaviour, just adds Proteções DXF).

---

## Scope

### Files modified

| File | Change |
|------|--------|
| `tools/exporter/solidworks.py` | Add `is_protecoes_part()` |
| `tools/exporter/excel_writer.py` | Add `PROTECOES_COLUMNS` + `"protecoes"` entry in `PROCESS_CONFIG` |
| `tools/exporter/modules/dxf_module.py` | Refactor: add process checkboxes (Laser, Proteções) |
| `tools/exporter/modules/step_module.py` | Refactor: add process checkboxes (Router, CNC, Torno) |
| `tools/exporter/modules/listas_module.py` | Add `("Proteções", "protecoes")` to `_LISTS` |
| `tools/exporter/modules/all_module.py` | Phase 1 (DXF) also runs Proteções; title updated |

---

## Detailed Design

### 1. `solidworks.py` — `is_protecoes_part`

```python
def is_protecoes_part(component) -> bool:
    """Return True if Corte_Fabrico contains 'protecoes' (accent-insensitive)."""
    val = get_corte_fabrico(component)
    return bool(val) and "protecoes" in val
```

Follows the exact same pattern as `is_laser_part`, `is_step_part`, and `is_perfil_aluminio`.

---

### 2. `excel_writer.py` — Proteções config

Template inspection result:
- File: `Templates/Protecoes_template.xlsx`
- Sheet: `Folha1`
- Header row: 3 (B3:E3 → QTY. / PART NUMBER / DESCRIPTION / Material)
- Data starts: row 4
- Table ref: `B3:E17`

```python
PROTECOES_COLUMNS = ["qty", "part_number", "Description", "Material"]

PROCESS_CONFIG = {
    ...
    "protecoes": ("Protecoes_template.xlsx", "Protecoes.xlsx", PROTECOES_COLUMNS, 4),
}
```

---

### 3. `dxf_module.py` — process selection checkboxes

**UI changes:**
- Title: `"DXF Export"`
- Add checkbox row: `[✓] Laser`  `[✓] Proteções` (both checked by default)
- Existing buttons: "Export DXF" and "Gerar Excel apenas" — behaviour unchanged except they now iterate over selected processes

**Worker logic:**
- Collect selected processes from checkboxes
- For each selected process, filter parts and run DXF export + optional Excel
- Single SW session for all selected processes
- Log phases: `[1/2] Laser…`, `[2/2] Proteções…`
- DXF export for Proteções uses the same `export_part_to_dxf` + `clean_dxf` pipeline as Laser (flat-pattern parts)

**Excel generation:**
- Laser: `LASER_COLUMNS`, `Laser_template.xlsx` → `Laser.xlsx`
- Proteções: `PROTECOES_COLUMNS`, `Protecoes_template.xlsx` → `Protecoes.xlsx`

---

### 4. `step_module.py` — process selection checkboxes

**UI changes:**
- Title: `"STEP Export"`
- Add checkbox row: `[✓] Router`  `[✓] CNC`  `[✓] Torno` (all checked by default)
- Existing buttons and flow unchanged except parts are pre-filtered by selected processes

**Worker logic:**
- Filter `step_parts` to only processes whose checkbox is checked
- Same single SW session, same Router dowel-hole reduction logic
- Log phases per process

---

### 5. `listas_module.py` — add Proteções

```python
_LISTS = [
    ("Laser",              "laser"),
    ("Proteções",          "protecoes"),   # NEW
    ("Router",             "router"),
    ("CNC",                "cnc"),
    ("Torno",              "torno"),
    ("BOM",                "bom"),
    ("Perfis de Alumínio", "perfis"),
]
```

`_run_excel_list` already routes via `PROCESS_CONFIG[process_key]` — no other changes needed.

---

### 6. `all_module.py` — add Proteções to Phase 1

- Phase 1 label: `"[1/4] DXF Export — Laser + Proteções"`
- After exporting all Laser DXFs + Laser.xlsx, also export all Proteções DXFs + Protecoes.xlsx
- Same single SW session as before
- Phases 2–4 (STEP, BOM, Perfis) unchanged

---

## Data flow

```
Assembly (.sldasm)
  └─ get_all_parts()
       └─ deduplicate_by_path()
            ├─ is_laser_part()      → DXF + Laser.xlsx
            ├─ is_protecoes_part()  → DXF + Protecoes.xlsx   [NEW]
            └─ is_step_part()       → STEP + Router/CNC/Torno.xlsx
```

---

## Excel column mapping — Proteções

| openpyxl col | Key | Template header |
|---|---|---|
| B | qty | QTY. |
| C | part_number | PART NUMBER |
| D | Description | DESCRIPTION |
| E | Material | Material |

`get_part_data()` already returns all four keys — no changes needed to that function.

---

## Edge cases & guard behaviour

### All checkboxes unchecked (DXF and STEP panels)
If the user clicks "Export DXF" or "Export STEP" with all process checkboxes unchecked, show `messagebox.showwarning("Aviso", "Seleciona pelo menos um processo.")` and abort — consistent with `listas_module.py` line 159.

### Progress bar — DXF panel with two processes
`total = len(laser_parts) + len(protecoes_parts)` before the loop starts. A single counter accumulates across both phases so the progress bar moves continuously. Phase labels in the log (`[1/2] Laser…`, `[2/2] Proteções…`) are logged at phase start.

---

## Implementation notes

### `listas_module.py` — two places to update
Adding `("Proteções", "protecoes")` to `_LISTS` controls the UI checkbox. The `_worker` hardcoded phase chain (`if selected.get("laser"):` … `if selected.get("router"):` …) also needs a new block:
```python
if selected.get("protecoes"):
    # same pattern as other phases — calls _run_excel_list(..., "protecoes", ui)
```
Insert between the Laser and Router blocks.

### `listas_module.py` — `_run_excel_list` already handles "protecoes"
The `else` branch `process_key in get_corte_fabrico(p)` already works correctly for `"protecoes"` because `get_corte_fabrico` returns a normalised (accent-stripped, lowercase) value. No special-case branch is needed.

### `all_module.py` — title unchanged
Title stays `"Gerar Tudo — DXF + STEP + BOM + Perfis de Alumínio"`. Phase 1 label becomes `"[1/4] DXF Export — Laser + Proteções"`. Phase count stays at 4.

---

## Non-goals

- No new sidebar item for Proteções
- No changes to BOM or Perfis flows
- "Gerar Tudo" has no checkboxes — always runs all processes
