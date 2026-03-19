# Design Spec — Lista de Material (BOM)

**Date:** 2026-03-15
**Status:** Approved

---

## Overview

Generate `Lista de materiais.xlsx` from a SolidWorks assembly using `Templates/Lista-de-Material_template.xlsm` as the base template. The output lists all production parts (to be manufactured) and commercial items (to be purchased).

---

## Architecture

| File | Responsibility |
|---|---|
| `tools/exporter/solidworks.py` | BOM traversal functions (SW COM logic) |
| `tools/exporter/bom_writer.py` | Brand classification, column mapping, Excel writing |
| `tools/exporter/modules/bom_module.py` | tkinter GUI panel |
| `tools/exporter/main.py` | Register BomModule |

---

## Naming Convention

File basenames: `PPPPP.GGG.NNN` (e.g. `18026.100.001`).
- Groups 100–700 → **production parts**
- Group 800 → **commercial items** (parts or assemblies to be purchased as-is)
- Group 000 → main assembly entry point (never a BOM row)

SolidWorks appends `-N` instance suffixes (e.g. `-3`) to basename when the same component appears multiple times. These are never part of the actual part number and must be stripped before parsing.

**Group 800 assemblies** (e.g. pneumatic cylinders): treated as a **single purchasable item**. Their internal sub-components are not traversed. This is intentional — the BOM records what must be purchased, not the vendor's internal BOM.

---

## solidworks.py — New additions

### `BomComponent` namedtuple (module-level, after existing `HoleInfo`)

```python
BomComponent = namedtuple('BomComponent', ['component', 'path', 'comp_type'])
# component: IComponent2
# path:      os.path.normpath(component.GetPathName())
# comp_type: "producao" | "comercial"
```

### `get_bom_components(assembly_doc: IModelDoc2) -> tuple[list[BomComponent], list[str]]`

`assembly_doc` is `IModelDoc2` — the same type returned by `open_assembly`. Accesses `ConfigurationManager` directly on `IModelDoc2` (no cast needed; same access pattern as the `GetRootComponent3` fallback in `get_all_parts`).

```python
def get_bom_components(assembly_doc):
    bom_flat = []
    warnings = []
    try:
        config = assembly_doc.ConfigurationManager.ActiveConfiguration
        root = config.GetRootComponent3(True)
        children = root.GetChildren()
    except Exception as e:
        warnings.append(f"Erro ao obter componentes: {e}")
        return bom_flat, warnings
    if children:
        for child in children:
            _bom_traverse(child, bom_flat, warnings)
    return bom_flat, warnings
```

### `_bom_traverse(comp, bom_flat, warnings)`

```python
def _bom_traverse(comp, bom_flat, warnings):
    path = "(desconhecido)"
    try:
        try:
            suppressed = comp.IsSuppressed()
        except Exception:
            suppressed = True   # on exception, treat as suppressed — skip
        if suppressed:
            return
        model = comp.GetModelDoc2()
        if model is None:
            return

        path = os.path.normpath(comp.GetPathName())
        basename = os.path.splitext(os.path.basename(path))[0]
        basename = re.sub(r'-\d+$', '', basename)   # strip SW instance suffix

        m = re.match(r'^\d+\.(\d+)\.\d+$', basename)
        if not m:
            warnings.append(f"Componente ignorado (nome não reconhecido): {basename}")
            return

        group = int(m.group(1))
        doc_type = model.GetType
        if callable(doc_type):
            doc_type = doc_type()

        if group == 800:
            # Group 800 = commercial item. Record as single BOM row regardless of
            # whether it is a part or a sub-assembly. Do NOT recurse into children.
            bom_flat.append(BomComponent(comp, path, "comercial"))
            return

        if doc_type == 1:   # swDocPART = 1
            bom_flat.append(BomComponent(comp, path, "producao"))
        elif doc_type == 2:   # swDocASSEMBLY = 2
            children = comp.GetChildren()   # comp is IComponent2 — GetChildren() on the component, not on model
            if children:
                for child in children:
                    _bom_traverse(child, bom_flat, warnings)
        # doc_type values other than 1 or 2 (e.g. 3=drawing) are silently ignored.
        # Drawings and other non-part/non-assembly documents do not appear in
        # production assemblies as structural components — safe to discard.

    except Exception as e:
        warnings.append(f"Erro ao processar componente '{path}': {e}")
```

Exceptions on individual components are recorded as warnings (not silently swallowed) so the user can see them in the log.

### `count_bom_instances(bom_flat: list[BomComponent], part_path: str) -> int`

Counts how many entries in the pre-dedup `bom_flat` list match `part_path` (case-insensitive). Used by the worker to compute the correct BOM-level quantity for each unique component.

**No suppression check is performed here** — this is intentional. `_bom_traverse` already skips suppressed components, so `bom_flat` contains only non-suppressed entries. A suppression check inside this function would be redundant.

```python
def count_bom_instances(bom_flat, part_path):
    target = os.path.normpath(part_path).lower()
    return sum(1 for bc in bom_flat
               if os.path.normpath(bc.path).lower() == target)
```

**Why not use `get_part_data`'s internal qty?** `get_part_data` internally calls `count_instances(all_components, path)` where `all_components` is a flat `list[IComponent2]` from `GetComponents(False)`. This list is not available in the BOM worker — the BOM worker builds its own traversal-level flat list (`bom_flat`). The BOM-level count may also differ from the `GetComponents(False)` count when commercial assemblies are present (their internal components are excluded from `bom_flat`). `count_bom_instances` is the authoritative count for BOM purposes.

### `deduplicate_bom_by_path(bom_components: list[BomComponent]) -> list[BomComponent]`

Preserves first occurrence, case-insensitive path key.

```python
def deduplicate_bom_by_path(bom_components):
    seen = set()
    unique = []
    for bc in bom_components:
        if bc.path.lower() not in seen:
            seen.add(bc.path.lower())
            unique.append(bc)
    return unique
```

---

## bom_writer.py — New file

### Brand sets and `ALL_KNOWN_BRANDS`

`Corte_Fabrico` is a controlled vocabulary field — engineers set it to the exact manufacturer name. It is not free text. Brand matching is case-insensitive substring (`brand in value`) to handle variations like `"FESTO"`, `"Festo"`, `"festo"`.

```python
PNEUMATICO_BRANDS = frozenset({"festo", "smc"})
ELETRICO_BRANDS = frozenset({
    "balluf", "ifm", "datalogic", "sick", "siemens", "pepperl+fuchs",
    "rittal", "schneider-eletric", "nord", "banner", "datasensing", "efectoled"
})
MECANICO_BRANDS = frozenset({
    "norelem", "misumi", "rolisa", "item", "igus", "bosch", "bosch rexroth",
    "lanema", "boteco", "skf", "gayner"
})
ALL_KNOWN_BRANDS = PNEUMATICO_BRANDS | ELETRICO_BRANDS | MECANICO_BRANDS
```

### `classify_commercial(corte_fabrico: str) -> str`

Returns `"pneumatico"`, `"eletrico"`, or `"mecanico"` (unknown brands fall back to `"mecanico"`).
Check priority: pneumatico → eletrico → mecanico.

```python
def classify_commercial(corte_fabrico: str) -> str:
    val = corte_fabrico.strip().lower()
    if any(b in val for b in PNEUMATICO_BRANDS):
        return "pneumatico"
    if any(b in val for b in ELETRICO_BRANDS):
        return "eletrico"
    return "mecanico"   # unconditional else-branch — MECANICO_BRANDS is NOT checked here
    # "mecanico" is returned for both: (a) brands in MECANICO_BRANDS, (b) completely unknown brands
    # Unknown brand detection is the CALLER's responsibility (check against ALL_KNOWN_BRANDS first)
```

**Design note on unknown brands:** `classify_commercial` always returns one of three values — it has no "unknown" return. Unknown brands fall back to `"mecanico"`. The CALLER (bom_module.py worker) is responsible for detecting and logging unknown brands using a separate pre-check:

```python
# In worker, before calling classify_commercial:
val = row["Corte_Fabrico"].strip().lower()
if not any(b in val for b in ALL_KNOWN_BRANDS):
    [log warning + warn_count += 1]   # detection happens HERE
cat = classify_commercial(row["Corte_Fabrico"])  # still returns "mecanico" for unknown brands
```

This pattern means unknown brands are logged AND go to Material Mecânico — intentional behavior. `classify_commercial` never needs to signal "unknown" because the pre-check already handles it.

### `TEMPLATES_DIR` constant

```python
# bom_writer.py lives at tools/exporter/bom_writer.py
# dirname(__file__)       → tools/exporter/
# dirname(dirname)        → tools/
# dirname(dirname(dirname)) → project root (e.g. c:\Users\...\Auto Production\)
TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "Templates"
)
# Resolves to: <project_root>/Templates/
```

### Column definitions

All four template sheets follow the invariant: row 1 = title, row 2 = headers, data from row 3. `header_row = 2` is fixed for all sheets.

```python
# None entries in column lists → write "" for that column
PRODUCAO_COLUMNS = [
    "qty",            # col 1 (A) — Quant.
    "part_number",    # col 2 (B) — Número Interno
    None,             # col 3 (C) — Rev. (always empty — dept. convention)
    "Description",    # col 4 (D) — Descrição
    "Corte_Fabrico",  # col 5 (E) — Corte/Fabrico
    "Simetria",       # col 6 (F) — Simetria
    "Material",       # col 7 (G) — Material
    "TratSuperficial",# col 8 (H) — Tratamento Superficial
    "A_Partir_de",    # col 9 (I) — A partir de
]

COMERCIAL_COLUMNS = [
    "qty",            # col 1 (A) — Quant.
    "part_number",    # col 2 (B) — Número Interno
    None,             # col 3 (C) — Coluna1 (Excel auto-name, no business meaning, always empty)
    "Description",    # col 4 (D) — Referência/nº Proposta
    "Corte_Fabrico",  # col 5 (E) — Marca/Fabricante
    None,             # col 6 (F) — Descrição (always empty — dept. convention)
]
```

### Row dicts

**Production:** `{qty: int, part_number: str, Description: str, Corte_Fabrico: str, Simetria: str, Material: str, TratSuperficial: str, A_Partir_de: str}`

**Commercial:** `{qty: int, part_number: str, Description: str, Corte_Fabrico: str}`

`A_Partir_de` is added by the worker via a separate `get_custom_property_evaluated` call (not part of `get_part_data`'s output). Extra keys (e.g. `espessura`) are silently ignored. Missing keys → `""`. `None` values → `""`.

### `generate_bom(rows_producao, rows_mecanico, rows_eletrico, rows_pneumatico, output_path) -> None`

All four args are `list[dict]` (empty lists allowed). Raises `FileNotFoundError` if template is missing; raises `openpyxl` errors on workbook failure.

**VBA handling:** The template is `.xlsm` (has VBA macros). The output is `.xlsx`. `keep_vba=False` intentionally strips all VBA — the output is a plain workbook. This is acceptable; no macros are needed in the output.

```python
import shutil, os, re
import openpyxl

template_path = os.path.join(TEMPLATES_DIR, "Lista-de-Material_template.xlsm")
shutil.copy2(template_path, output_path)   # byte copy; silent overwrite if output_path exists
wb = openpyxl.load_workbook(output_path, keep_vba=False)

# Sheet names verified against template (openpyxl wb.sheetnames):
# b'Produ\xc3\xa7\xc3\xa3o' → "Produção"
# b'Material Mec\xc3\xa2nico' → "Material Mecânico"
# b'Material El\xc3\xa9trico' → "Material Elétrico"
# b'Material Pneum\xc3\xa1tico' → "Material Pneumático"
sheet_config = [
    ("Produção",             rows_producao,   PRODUCAO_COLUMNS),
    ("Material Mecânico",    rows_mecanico,   COMERCIAL_COLUMNS),
    ("Material Elétrico",    rows_eletrico,   COMERCIAL_COLUMNS),
    ("Material Pneumático",  rows_pneumatico, COMERCIAL_COLUMNS),
]

for sheet_name, rows, col_keys in sheet_config:
    ws = wb[sheet_name]
    data_start_row = 3
    header_row = 2   # invariant for all 4 sheets

    for row_offset, row_dict in enumerate(rows):
        row_idx = data_start_row + row_offset
        for col_offset, key in enumerate(col_keys):
            value = row_dict.get(key, "") if key else ""
            ws.cell(row=row_idx, column=1 + col_offset).value = value or ""

    # Remove trailing blank template rows
    first_blank = data_start_row + len(rows)
    if first_blank <= ws.max_row:
        ws.delete_rows(first_blank, ws.max_row - first_blank + 1)

    # Update Excel Table refs to match actual data range.
    # The regex extracts and preserves the column letters (e.g. "A", "I") from
    # the template's existing ref — the column bounds are NOT hardcoded here.
    # For Produção the template ref is e.g. "A2:I1098"; for commercial sheets "A2:F15".
    # After update: Produção with 5 rows → "A2:I7"; empty → "A2:I2".
    last_row = header_row if not rows else data_start_row + len(rows) - 1
    for tbl in ws.tables.values():
        m = re.match(r'([A-Z]+)\d+:([A-Z]+)\d+', tbl.ref)
        if m:
            tbl.ref = f"{m.group(1)}{header_row}:{m.group(2)}{last_row}"
    # If a sheet has no Excel Table (template inconsistency), the loop is a no-op.

wb.save(output_path)
```

**Row order:** Written in assembly tree traversal order. No sorting applied.

---

## modules/bom_module.py — New file

Follows `StepModule` structure. All worker-thread UI updates via `self.after(0, fn)`.

**UI elements:**
- Title: `"Lista de Material — BOM"`
- Separator
- Output folder `tk.Entry` + Browse button (`filedialog.askdirectory`)
- `"Gerar Lista de Material"` button (`self.btn_generate`)
- `ttk.Progressbar` with `mode="indeterminate"`
- Status label

### Worker: imports (resolved via `sys.path.insert` same as `step_module.py`)

```python
from solidworks import (
    connect_to_solidworks, open_assembly,
    get_bom_components, deduplicate_bom_by_path, count_bom_instances,
    get_part_data, get_custom_property_evaluated,
)
from bom_writer import (
    classify_commercial, generate_bom, ALL_KNOWN_BRANDS,
)
```

### Worker: body

```python
asm_path = os.path.normpath(os.path.abspath(asm_path))
sw = None; asm_doc = None; asm_opened_by_us = False; error = False

try:
    ui(log separator + "Gerar Lista de Material")
    sw = connect_to_solidworks()
    asm_doc, asm_opened_by_us = open_assembly(sw, asm_path)
    # open_assembly opens non-silently (options=0) by default — correct for assemblies
    # Returns (IModelDoc2, True) if opened here; (IModelDoc2, False) if already open

    bom_flat, warnings = get_bom_components(asm_doc)
    for w in warnings:
        ui(log f"  AVISO {w}")

    unique = deduplicate_bom_by_path(bom_flat)
    all_raw = [bc.component for bc in bom_flat]
    # all_raw: list[IComponent2] passed to get_part_data as its second arg.
    # get_part_data uses all_raw only for count_instances (qty) — no documents
    # are opened or closed by get_part_data. It reads custom properties via
    # comp.GetModelDoc2().Extension.CustomPropertyManager("") on the component
    # that SolidWorks already has in memory from the loaded assembly.
    # get_part_data does NOT open or close any SolidWorks document.
    # The qty computed by get_part_data is immediately overridden below.

    pairs = []
    for bc in unique:
        model_doc = bc.component.GetModelDoc2()
        if model_doc is None:
            ui(log f"  AVISO GetModelDoc2() None: {bc.path}")
            continue
        row = get_part_data(bc.component, all_raw)
        row["qty"] = count_bom_instances(bom_flat, bc.path)   # override with BOM-level count
        if bc.comp_type == "producao":
            row["A_Partir_de"] = get_custom_property_evaluated(model_doc, "A_Partir_de")
        pairs.append((bc, row))

    rows_producao = [row for bc, row in pairs if bc.comp_type == "producao"]
    rows_mecanico, rows_eletrico, rows_pneumatico = [], [], []
    warn_count = len(warnings)

    for bc, row in pairs:
        if bc.comp_type != "comercial":
            continue
        val = row["Corte_Fabrico"].strip().lower()
        if not any(b in val for b in ALL_KNOWN_BRANDS):
            msg = f"Fabricante desconhecido: '{row['Corte_Fabrico']}' → Material Mecânico"
            ui(log f"  AVISO {msg}")
            warn_count += 1
        cat = classify_commercial(row["Corte_Fabrico"])
        {"mecanico": rows_mecanico, "eletrico": rows_eletrico,
         "pneumatico": rows_pneumatico}[cat].append(row)

    output_path = os.path.join(out_dir, "Lista de materiais.xlsx")
    generate_bom(rows_producao, rows_mecanico, rows_eletrico, rows_pneumatico, output_path)
    ui(log "  OK    Lista de materiais.xlsx")
    # warn_count = len(warnings from get_bom_components) + unknown-brand warnings
    # It is displayed in the summary line to alert the user to skipped components.
    ui(log f"Produção: {len(rows_producao)} | Mecânico: {len(rows_mecanico)} | "
           f"Elétrico: {len(rows_eletrico)} | Pneumático: {len(rows_pneumatico)} | "
           f"Avisos: {warn_count}")

except Exception as exc:
    error = True
    ui(log f"ERRO FATAL: {exc}")

finally:
    if asm_opened_by_us and asm_doc is not None:
        try: sw.CloseDoc(asm_path)   # asm_path is already normpath'd
        except: pass
    ui(lambda: (
        self.btn_generate.config(state="normal"),
        self.progress.stop(),
        self._set_status("Concluído." if not error else "Erro — ver log."),
        self._log("─" * 68),
    ))
```

`self.progress.start()` + `self.btn_generate.config(state="disabled")` before thread start.

---

## main.py

```python
from modules.bom_module import BomModule

MODULES = [
    ("DXF Export",        "dxf",  DxfModule),
    ("STEP Export",       "step", StepModule),
    ("Lista de Material", "bom",  BomModule),
]
```

---

## Output

- **File:** `Lista de materiais.xlsx` in user-specified folder
- **Overwrite:** Silent (consistent with STEP exporter)
- **VBA:** Intentionally stripped via `keep_vba=False`

---

## Edge Cases

| Case | Handling |
|---|---|
| Basename no match after `-N` strip | Skip + `warnings.append(...)` |
| SW instance suffix on basename | `re.sub(r'-\d+$', '')` before regex |
| Group 800 sub-assembly | Single BOM row, children not traversed (intentional — purchasable unit) |
| Unknown commercial brand | `"mecanico"` sheet + logged AVISO |
| Empty sheet | Template rows deleted; table ref = header-only (`A2:X2`) |
| No Excel Table in sheet | `ws.tables.values()` no-op |
| Assembly not open in SW | `open_assembly` opens with `options=0` (non-silent); `asm_opened_by_us=True`; `CloseDoc` in finally |
| `A_Partir_de` property missing | `get_custom_property_evaluated` returns `""` |
| `GetModelDoc2()` None in worker | Log AVISO + skip component |
| Suppressed component | Skipped in `_bom_traverse` guard |
| `GetChildren()` returns None | Guarded with `if children:` |
| COM exception on component | Caught; appended to `warnings`; component skipped |
| Template file missing | `FileNotFoundError` from `shutil.copy2` → caught by worker except |
| Output file already exists | Silently overwritten |

---

## Files Changed / Created

| File | Change |
|---|---|
| `tools/exporter/solidworks.py` | Add `BomComponent`, `get_bom_components`, `_bom_traverse`, `count_bom_instances`, `deduplicate_bom_by_path` |
| `tools/exporter/bom_writer.py` | New file |
| `tools/exporter/modules/bom_module.py` | New file |
| `tools/exporter/main.py` | Import + register `BomModule` |

---

## Tests

**`test_bom_writer.py`:**
- `classify_commercial`: "FESTO"/"festo"/"Festo" → pneumatico; "Siemens" → eletrico; "SKF"/"Bosch Rexroth" → mecanico; `""` / "XYZ" → mecanico
- Unknown detection: `"xyz"` not in ALL_KNOWN_BRANDS
- `generate_bom`: column indices per sheet, None→"", empty rows, table ref (header-only and with data), blank row deletion, saves as .xlsx

**`test_solidworks_helpers.py` (extend):**
- `count_bom_instances`: count=3 for path appearing 3×, case-insensitive path
- `deduplicate_bom_by_path`: 5 with 2 dupes → 3 unique, preserves first
- Suffix strip: `re.sub(r'-\d+$', '', "18026.100.001-3")` == `"18026.100.001"`
- `_bom_traverse` logic: mock `BomComponent` construction for group/doc_type combinations
