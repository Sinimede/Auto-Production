# Design: Fornecedores Lookup — Excel-Based Brand Classification

**Date:** 2026-03-17
**Status:** Approved

---

## Objective

Replace the small hardcoded brand lists in `bom_writer.py` with a runtime lookup against `Templates/Fornecedores.xlsx`. The Excel becomes the single source of truth for supplier categorization. Classification uses case-insensitive, space-insensitive normalization so minor spelling variations (e.g. `Bruyrubio` ↔ `Bru y Rubio`, `EQUINOTEC` ↔ `Equinotec`) match correctly.

---

## Context

- `bom_writer.py` currently has three hardcoded `frozenset`s (`PNEUMATICO_BRANDS`, `ELETRICO_BRANDS`, `MECANICO_BRANDS`) with ~25 entries total.
- Three callers use `ALL_KNOWN_BRANDS` and `classify_commercial`: `bom_module.py`, `listas_module.py`, `all_module.py`. All three follow the same pattern.
- `Templates/Fornecedores.xlsx` (311 suppliers) was created earlier this session and is already bundled in the `.exe` via `paths.get_templates_dir()`.
- "Murr" in `categorias.py` must be renamed to "Murreletronik" before regenerating the Excel.

---

## Changes

| File | Action |
|------|--------|
| `tools/fornecedores/categorias.py` | Rename key `"Murr"` → `"Murreletronik"` (category stays `"Elétrico"`) |
| `Templates/Fornecedores.xlsx` | Regenerated via `generate_fornecedores.py` |
| `tools/exporter/bom_writer.py` | Remove hardcoded sets; add `normalize`, `load_fornecedores_lookup`, `is_known_brand`; update `classify_commercial`; expose `ALL_KNOWN_BRANDS` |
| `tools/exporter/modules/bom_module.py` | Import and use `is_known_brand` |
| `tools/exporter/modules/listas_module.py` | Import and use `is_known_brand` |
| `tools/exporter/modules/all_module.py` | Import and use `is_known_brand` |

---

## bom_writer.py — New API

### normalize(s: str) → str
```python
def normalize(s: str) -> str:
    return s.lower().replace(" ", "")
```
Applied to both the Excel supplier names (at load time) and the `Corte_Fabrico` values (at classify time).

`get_custom_property_evaluated()` can return a tuple in SW 2024. Both `classify_commercial` and `is_known_brand` must handle this defensively:
```python
if isinstance(corte_fabrico, tuple):
    corte_fabrico = corte_fabrico[0] if corte_fabrico else ""
corte_fabrico = corte_fabrico or ""
```

### load_fornecedores_lookup() → dict
Reads `Templates/Fornecedores.xlsx` (via `paths.get_templates_dir()`).
Returns `{normalize(nome): internal_category}` where `internal_category` is one of `"mecanico"`, `"eletrico"`, `"pneumatico"`.

Category mapping from Excel column C:
- `"Mecânico"` → `"mecanico"`
- `"Elétrico"` → `"eletrico"`
- `"Pneumático"` → `"pneumatico"`

If the Excel file is missing, logs a warning and returns an empty dict (falls back to default "mecanico" for all).

### Module-level constants (built once at import time)
```python
FORNECEDORES_LOOKUP: dict  # {normalize(name): "mecanico"/"eletrico"/"pneumatico"}
ALL_KNOWN_BRANDS: frozenset  # set of all normalized names — kept for backward compat
```

### classify_commercial(corte_fabrico: str) → str
1. Defensive unpack: if tuple, extract `[0]`; coerce to `""`  if falsy
2. `val = normalize(corte_fabrico)`
3. Exact match: `if val in FORNECEDORES_LOOKUP → return category`
4. Substring match: iterate `FORNECEDORES_LOOKUP` (alphabetical order, first match wins); `if norm_name and norm_name in val → return category`
5. Default: `return "mecanico"`

Empty/None input: `val` becomes `""` → no match → returns `"mecanico"`.

### is_known_brand(corte_fabrico: str) → bool
```python
def is_known_brand(corte_fabrico: str) -> bool:
    if isinstance(corte_fabrico, tuple):
        corte_fabrico = corte_fabrico[0] if corte_fabrico else ""
    corte_fabrico = corte_fabrico or ""
    val = normalize(corte_fabrico)
    if val in FORNECEDORES_LOOKUP:
        return True
    return any(n and n in val for n in FORNECEDORES_LOOKUP)
```

Empty/None `Corte_Fabrico` → returns `False` → caller logs warning → defaults to "mecanico".

---

## Caller Changes (bom_module.py, listas_module.py, all_module.py)

Each caller changes two things:

**Import line** — add `is_known_brand`:
```python
from bom_writer import classify_commercial, generate_bom, ALL_KNOWN_BRANDS, is_known_brand
```

**Warning check** — replace:
```python
val = (row.get("Corte_Fabrico") or "").strip().lower()
if not any(b in val for b in ALL_KNOWN_BRANDS):
    ...warn...
cat = classify_commercial(val)
```
with:
```python
val = row.get("Corte_Fabrico") or ""
if not is_known_brand(val):
    ...warn...
cat = classify_commercial(val)
```

---

## categorias.py Update

Change:
```python
"Murr": "Elétrico",
```
to:
```python
"Murreletronik": "Elétrico",
```

Then regenerate `Templates/Fornecedores.xlsx` by running `tools/fornecedores/generate_fornecedores.py`.

---

## Error Handling

- Excel missing at runtime → `load_fornecedores_lookup` logs `"AVISO: Fornecedores.xlsx não encontrado — classificação por defeito: Mecânico"` and returns `{}`. All brands fall through to default "mecanico".
- Excel present but row has no category value → skip that row.

---

## Testing

- Unit tests in `tools/exporter/tests/test_bom_writer_lookup.py`
- Test `normalize()` with spaces, mixed case, empty string
- Test `classify_commercial()` with exact match, case variation, space variation, substring match, unknown brand
- Test `is_known_brand()` with known, unknown, empty
- Test `load_fornecedores_lookup()` with a temporary Excel fixture
- Existing tests must continue to pass
