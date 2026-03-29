# Project Guide — Auto Production

Stable technical reference for this project. Covers stack, structure, commands, and conventions.

---

## Tech Stack

- **Python 3.x** — all tooling
- **win32com** — SolidWorks COM API automation
  - Early binding (generated stubs from `sldworks.tlb`) for most calls: `ISldWorks`, `IAssemblyDoc`, `IModelDoc2`, `IComponent2`, `IFeature`, etc.
  - Late binding (`win32com.client.Dispatch`) used selectively — see COM conventions below
- **tkinter** — GUI for the exporter (`main.py`)
- **SolidWorks** — must be running for any COM interaction

---

## Project Structure

```
tools/
  exporter/
    solidworks.py        # COM API wrapper — all SW interactions live here
    main.py              # tkinter GUI entry point (DXF + STEP panels)
    test_step.py         # Headless STEP export test (no GUI, requires SW running)
    modules/
      dxf_module.py      # DXF export panel
      step_module.py     # STEP export panel + background worker thread
  dxf_exporter/          # Feature 1 (complete — standalone DXF tool)
workflows/               # Markdown SOPs
docs/
  project-guide.md       # This file
.tmp/                    # Temp files (gitignored, regenerated freely)
Resultados/              # Default STEP/DXF output destination
```

---

## Key Commands

```bash
# Launch GUI (DXF + STEP export)
python tools/exporter/main.py

# Headless STEP export test — requires SolidWorks running
python tools/exporter/test_step.py
```

---

## SolidWorks COM Conventions

### Early vs Late Binding

**IMPORTANT:** SolidWorks 2024 is extremely sensitive to COM marshaling. For operations involving `BYREF` parameters (like `SaveAs4`, `Save3`, or `ResolveAllLightweightComponents`), standard early binding OR standard `win32com.client.Dispatch` often fails with `int() argument must be a string... not 'VARIANT'` or `DISP_E_TYPEMISMATCH`.

**The Stable Pattern for SW 2024 Late Binding:**
1. Prioritize `_oleobj_` (the raw COM interface) over `_dispobj_`.
2. Use `win32com.client.dynamic.Dispatch` to force a dynamic dispatcher that handles `VARIANT` pointers correctly even if stubs exist.

```python
import pythoncom
import win32com.client

def _get_raw_obj(obj):
    return getattr(obj, "_oleobj_", None) or getattr(obj, "_dispobj_", None) or obj

# Example: SaveAs4 (Step Export)
raw = _get_raw_obj(doc)
late = win32com.client.dynamic.Dispatch(raw)
byref_i4 = lambda: win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
err = byref_i4()
warn = byref_i4()

res = late.SaveAs4(output_path, 0, 1, err, warn)
success = res[0] if isinstance(res, (tuple, list)) else bool(res)
```

### OpenDoc6 Quirk

Early binding returns a tuple `(IModelDoc2, errors_int, warnings_int)` because of BYREF out-params.
Always unpack:
```python
result = sw_app.OpenDoc6(path, doc_type, options, "", 0, 0)
doc = result[0] if isinstance(result, tuple) else result
```
Pass `0` for errors/warnings — never `VT_BYREF` VARIANT (causes `int() not 'VARIANT'` error).

### Path Normalization

Always normalize before any SW COM call:
```python
path = os.path.normpath(os.path.abspath(path))
```
`CloseDoc` silently fails if the path format doesn't match what SW registered internally.

### `_wrap` Helper

Use `_wrap(obj, "IAssemblyDoc")` to cast `IModelDoc2` → `IAssemblyDoc`.
Do **not** check COM object types via `type(x).__name__` — COM wrappers vary.
Use `try/except` around `cls(inner)` instead.

**Always wrap `IComponent2` objects returned by `GetChildren`:**
Raw children from `GetChildren` are untyped `CDispatch` objects — calling `GetModelDoc2`, `GetPathName`, etc. raises `DISP_E_MEMBERNOTFOUND (-2147352573)` without wrapping:
```python
comp = _wrap(comp, "IComponent2")
model = comp.GetModelDoc2()
```

### ResolveAllLightweightComponents — Use Late Binding

`IAssemblyDoc.ResolveAllLightweightComponents(False)` via **early binding silently no-ops** in SW 2024. Components remain lightweight and `GetModelDoc2()` returns `None` for all of them.

**Always use late binding:**
```python
asm = _wrap(assembly_doc, "IAssemblyDoc")
asm_raw = getattr(asm, "_dispobj_", None) or getattr(asm, "_oleobj_", None) or asm
win32com.client.Dispatch(asm_raw).ResolveAllLightweightComponents(False)
```

Without this, `GetComponents(False)` may return all components but only 1-2 will have resolvable model docs. The BOM tree-traversal approach (`GetRootComponent3` + `GetChildren`) is not affected since it classifies by filename, not by loaded model.

---

### IComponent2 Suppression — Use GetSuppression(), not IsSuppressed

`IsSuppressed` returns `True` for **lightweight** components (not fully loaded) in SW 2024. Lightweight components appear **active** in the Feature Tree. Using `IsSuppressed` to skip suppressed components will incorrectly skip lightweight ones too.

**Always use `GetSuppression()`:**
```python
state_ref = comp.GetSuppression
state = state_ref() if callable(state_ref) else state_ref
if isinstance(state, tuple):
    state = state[0]
suppressed = (int(state) == 0)  # swComponentSuppressed=0 only; lightweight=1, resolved=4
```

`swComponentSuppressionState_e`: `0`=suppressed, `1`=lightweight, `4`=fully resolved.

### Property-vs-Method in SW 2024 Early Binding

Several `IComponent2` / `IConfiguration` methods are defined as **zero-arg properties** in the SW 2024 type library stubs. Calling them with `()` raises `TypeError: 'tuple' object is not callable` because the property getter already evaluated and returned a tuple. Use the callable-guard pattern:

```python
# Instead of: root = config.GetRootComponent3(True)
root_ref = config.GetRootComponent3
root_raw = root_ref(True) if callable(root_ref) else root_ref
if isinstance(root_raw, tuple):
    root_raw = root_raw[0]

# Instead of: children = comp.GetChildren()
children_ref = comp.GetChildren
children = children_ref() if callable(children_ref) else children_ref

# Instead of: suppressed = comp.IsSuppressed()
is_sup_ref = comp.IsSuppressed
suppressed = is_sup_ref() if callable(is_sup_ref) else bool(is_sup_ref)
```

Confirmed affected in SW 2024: `GetRootComponent3`, `GetChildren`, `IsSuppressed`.
`GetType` on `IModelDoc2` was already documented above.

### HoleWzd (Hole Wizard) — SW 2024

`GetSpecificFeature2()` returns `None` for HoleWzd features in SW 2024. Use `GetDefinition()` instead:

```python
if feat.GetTypeName2() == "HoleWzd":
    feat_data = _wrap(feat.GetDefinition(), "IWizardHoleFeatureData2")
    feat_data.AccessSelections(part_doc, None)
    size_str = feat_data.FastenerSize   # e.g. 'Ø20.0' (mm, string with Ø prefix)
    # Diameter getter returns 0.0 — parse FastenerSize with regex instead
    feat_data.Diameter = new_diameter_m  # setter works correctly
    result = feat.ModifyDefinition(feat_data, part_doc, None)  # 3 args, not 1
    feat_data.ReleaseSelectionAccess()
part_doc.EditRebuild3()
```

Key facts:
- `GetTypeName2() == "HoleWzd"` matches **all** Hole Wizard features (Clearance, Tapped, CHole, Dowel). Use `FastenerType2` to distinguish Dowel holes.
- **Dowel hole discriminator — `FastenerType2` (`swWzdHoleStandardFastenerTypes_e`):**

  | Value | Constant | Standard |
  |-------|----------|----------|
  | 703 | `swStandardAnsiInchDowelHole` | ANSI Inch |
  | 706 | `swStandardBSIDowelHole` | BSI |
  | 707 | `swStandardDINDowelHole` | DIN |
  | 710 | `swStandardISODowelHole` | ISO ← most common |
  | 711 | `swStandardJISDowelHole` | JIS |

  SW 2024 early binding may return a tuple — always unpack: `ft2 = ft2[0] if isinstance(ft2, tuple) else ft2`
- `FastenerSize` is a string like `'Ø20.0'` — extract number with `re.search(r'[\d.]+', s)`; property is **read-only**
- `Diameter` **getter** returns `0.0` for Dowel type — always parse `FastenerSize`
- `Diameter` **setter** only works after setting `Type = 0` (see below)
- `ModifyDefinition` signature: `(FeatureData, TopDoc, Component)` — pass the raw `defn_raw` object, `None` for Component
- `ChangeStandard` expects integer enum args; returns `False` for non-standard sizes (e.g., Ø19mm not in ISO table)

**To change a Dowel hole diameter:**
```python
feat_data.Type = 0          # swHoleType_Simple — REQUIRED before setting Diameter
feat_data.Diameter = new_m  # now works (Dowel type ignores Diameter; Simple type uses it)
feat.ModifyDefinition(defn_raw, part_doc, None)
feat_data.ReleaseSelectionAccess()
part_doc.EditRebuild3()
```
Without `Type = 0`, `Diameter` setter is silently ignored — geometry remains table-driven.

### Custom Property Values — SW 2024 Quirks

**`Get4` returns raw expression with literal quotes:**
SW 2024 sometimes returns the raw custom property value wrapped in literal quote characters (e.g., `'"SW-Material@part.SLDPRT"'`). Always strip before matching:
```python
val = get_custom_property_evaluated(model_doc, prop)
val = val.strip('"\'')
```

**`GetMaterialPropertyName2("")` returns a tuple:**
Early-bound `IPartDoc.GetMaterialPropertyName2("")` returns `(material_name, database_name)` in SW 2024 — not a plain string. Extract index `[0]`:
```python
mat = part.GetMaterialPropertyName2("")
if isinstance(mat, tuple):
    mat = mat[0]
```
`IPartDoc2` variant fails with BADPARAMCOUNT — use `IPartDoc` only.

### Feature Iteration — SW 2024

`IModelDoc2.FirstFeature()` is **not** accessible via IDispatch (MEMBERNOTFOUND) in SW 2024.
`IPartDoc.FirstFeature()` **is** in the type library stubs and works via early binding.

Correct pattern:
```python
part = _wrap(model_doc, "IPartDoc")
feat = _wrap(part.FirstFeature(), "IFeature")
while feat is not None:
    if feat.GetTypeName2() == "SheetMetal":
        defn = feat.GetDefinition()
        if defn is not None:
            defn_raw = getattr(defn, "_dispobj_", None) or getattr(defn, "_oleobj_", None) or defn
            thickness_m = win32com.client.Dispatch(defn_raw).Thickness  # late binding — not in ISheetMetalFeatureData stubs
    next_raw = feat.GetNextFeature()
    feat = _wrap(next_raw, "IFeature") if next_raw is not None else None
```

Key facts:
- `ISheetMetalFeatureData` exists in stubs but has **no `Thickness` property** — use late binding on `defn`
- `ISheetMetalFeatureData2` does **not** exist in SW 2024 stubs
- `AccessSelections` is NOT required for reading `Thickness`
- Early-bound objects from `GetModelDoc2()` are `CDispatch` with `_oleobj_` (not `_dispobj_`)
- Always try both: `getattr(obj, "_dispobj_", None) or getattr(obj, "_oleobj_", None)`

### Cut List Item Properties — SW 2024

`IFeature.GetCustomInfoValue` does **not** exist in SW 2024 early-bound stubs. Use `feat.CustomPropertyManager` → `ICustomPropertyManager` instead:

```python
mgr = feat.CustomPropertyManager
try:
    result = mgr.Get4(prop_name, False)  # returns (retval, val, resolvedVal, wasResolved)
    if isinstance(result, tuple) and len(result) > 1:
        val = result[2] if (len(result) > 2 and result[2]) else result[1]
except Exception:
    val = mgr.Get(prop_name)
```

This applies to any `CutListFolder` feature when reading DESCRIPTION, LENGTH, QUANTITY, etc.

### Verified Enum Values

| Name | Value |
|------|-------|
| `swDocPART` | `1` |
| `swDocASSEMBLY` | `2` |
| `swComponentFullyResolved` | `4` (not 3) |
| `swStepAP214` | `1` (for `IStepExportOptions.ExportAs`) |

---

## Temp File Convention

- Router STEP flow copies parts to `.tmp/` before modification
- Always clean up in `finally` blocks: close SW doc first, then `os.remove()` the file
- The `.tmp/` directory itself is persistent — do not delete it between runs

---

## Never Do (BOM / read-only operations)

- Do NOT call `get_bounding_box_thickness` or iterate SW features (GetDefinition, GetPartBox) from read-only flows (BOM, reports). These can mark parts as modified in SW even without explicit writes. Read custom properties only via `get_custom_property_evaluated`.

## Never Do

- Do NOT pass `VT_BYREF` VARIANT objects to early-bound COM methods
- Do NOT check COM object types via `type(x).__name__` — use try/except
- Do NOT skip path normalization before `CloseDoc` or `OpenDoc6`
- Do NOT store secrets outside `.env`
- Do NOT create or overwrite workflows without asking (unless explicitly told to)
- Do NOT re-run tools that use paid API calls without checking with the user first
