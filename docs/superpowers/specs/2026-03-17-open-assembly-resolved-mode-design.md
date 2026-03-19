# Design: Open Assembly in Resolved Mode

**Date:** 2026-03-17
**Status:** Approved (rev 3 — post spec review round 2)

---

## Problem

When SolidWorks is configured to open assemblies in Lightweight mode, `open_assembly` returns the assembly in whatever state it's in. `GetModelDoc2()` then returns `None` for lightweight components, which are silently discarded during BOM traversal.

Confirmed behaviour:
- Assembly opened by tool (`options=0`) → **0 parts** (lightweight, model=None everywhere)
- Assembly pre-opened by user in Lightweight → **43 parts** (partially traversable)
- Assembly pre-opened by user in Resolved → **88 parts** (correct)

`ResolveAllLightweightComponents` was tried after opening — did not fix (asynchronous SW loading, traversal starts before resolution completes).

---

## Solution

Add a new function `open_assembly_resolved()` in `solidworks.py` that always opens the assembly in read-only resolved mode. Only `listas_module.py` (BOM caller) uses this new function. Existing `open_assembly` is unchanged — DXF and STEP callers are not affected.

Key findings from SW 2024 type library:
- `swOpenDocOptions_OverrideDefaultLoadLightweight = 64` — overrides the user's "open lightweight" setting, forces resolved load
- `swOpenDocOptions_ReadOnly = 2` — `CloseDoc` will never prompt to save on a read-only doc
- `swOpenAssemblyDocMode` (integer preference) **does not exist** in SW 2024 — global preference approach not viable
- `SetSaveFlag()` **marks document dirty** (opposite of intent) — no SW 2024 API to clear modified flag

---

## Design

### Scope

| File | Change |
|------|--------|
| `tools/exporter/solidworks.py` | Add `open_assembly_resolved()` function |
| `tools/exporter/modules/listas_module.py` | Import and call `open_assembly_resolved` instead of `open_assembly` |

`open_assembly` is unchanged. DXF and STEP callers (`dxf_module.py`, `step_module.py`) are not touched.

---

### New Function: `open_assembly_resolved(sw_app, sldasm_path)`

```
1. Normalise path
2. Close any existing open instance:
   a. Check ActiveDoc — if path matches → dirty check → close if clean
   b. Check GetOpenDocumentByName — if found → dirty check → close if clean
   (Both checks are needed: assembly may be open but not the active window)
3. Open via OpenDoc6 with options = 66:
      swOpenDocOptions_ReadOnly (2) | swOpenDocOptions_OverrideDefaultLoadLightweight (64)
      Silent flag (1) NOT set — ensures full component tree is loaded
4. Return (doc, True)   # always opened_by_us=True
```

### Dirty Check

`GetSaveFlag` on `IModelDoc2` returns **`True` if the document has unsaved changes** (dirty), `False` if clean.

```python
def _is_dirty(doc) -> bool:
    ref = doc.GetSaveFlag
    result = ref() if callable(ref) else ref
    if isinstance(result, tuple):
        result = result[0]
    return bool(result)
```

If dirty → raise `RuntimeError` with user-facing Portuguese message:
```
"O assembly tem alterações não guardadas. Guarda ou descarta as alterações antes de continuar."
```

If clean → `sw_app.CloseDoc(path)`. If `CloseDoc` raises → also raise `RuntimeError` (can't proceed — `OpenDoc6` would return the still-open lightweight doc and the fix would not work).

### SW API Values (confirmed from SW 2024 `swconst.tlb`)

| Name | Value | Notes |
|------|-------|-------|
| `swOpenDocOptions_ReadOnly` | `2` | No save prompt on close |
| `swOpenDocOptions_OverrideDefaultLoadLightweight` | `64` | Overrides lightweight setting → opens resolved |
| `swOpenDocOptions_LoadLightweight` | `128` | Force lightweight — NOT used |
| `swOpenDocOptions_Silent` | `1` | Suppresses component tree — NOT used |

Combined: `options = 2 | 64 = 66`

### Return Value

Always `(doc, True)`. The `asm_opened_by_us = True` flag in `listas_module.py` already causes `sw.CloseDoc(asm_path)` to be called in the `finally` block — no change needed there.

### Error Handling

| Condition | Behaviour |
|-----------|-----------|
| Assembly open with unsaved changes | `RuntimeError` with PT message — surfaced to UI |
| `CloseDoc` fails after clean check | `RuntimeError` — can't guarantee resolved open if old doc remains |
| `OpenDoc6` returns `None` | `RuntimeError`: "Não foi possível abrir o assembly" |
| `OpenDoc6` raises | Propagate exception |

---

### Callers

`open_assembly_resolved` calls `sw_app.OpenDoc6` directly — it does NOT delegate to the `_open_doc` helper (which only accepts a `silent` bool and always computes `options = 0 or 1`).

| Caller | Uses | Change |
|--------|------|--------|
| `listas_module.py` | `open_assembly` → `open_assembly_resolved` | Yes — import + call site |
| `dxf_module.py` | `open_assembly` | No change |
| `step_module.py` | `open_assembly` | No change |
| `bom_module.py` | `open_assembly` | No change |
| `all_module.py` | `open_assembly` | No change |

---

## What Does NOT Change

- `ResolveAllLightweightComponents` in `get_bom_components` — kept as safety net
- `SetComponentState(4)` fallback in `listas_module.py` — kept as last-resort fallback
- `open_assembly` function — unchanged

---

## Success Criteria

| Scenario | Expected |
|----------|----------|
| Assembly closed before running | `Produção: 88` |
| Assembly open (active) in Lightweight | Closed → reopened → `Produção: 88` |
| Assembly open (background, not active) in Lightweight | Closed → reopened → `Produção: 88` |
| Assembly open with unsaved changes | Error surfaced to UI, assembly remains open |
| `OpenDoc6` fails | Error surfaced to UI |
| DXF export after this change | Unchanged behaviour (uses `open_assembly`) |
| STEP export after this change | Unchanged behaviour (uses `open_assembly`) |
