# Design: Fornecedores Excel Template

**Date:** 2026-03-17
**Status:** Approved

---

## Objective

Generate `Templates/Fornecedores.xlsx` — a lookup table mapping suppliers to their category (Mecânico / Elétrico / Pneumático). Used to categorize commercial parts whose part number starts with a 3-letter supplier code (e.g., `BOS.010.001`).

---

## Context

- Source list: `Templates/Fornecedores.txt` — ~311 non-blank supplier entries, one per line
- Commercial parts with 3-letter prefix → category derived from Fornecedores.xlsx
- Commercial parts with numeric codes (e.g., `15024.800.001`) → category derived from SolidWorks `corte_fabrico` property (existing mechanism, out of scope here)
- The Excel is the single source of truth for supplier-to-category mapping; users can correct entries at any time via the dropdown
- **Re-running the script is destructive** — it regenerates the Excel from scratch, overwriting any manual corrections. Users should treat the Excel as the editable source and the script as a one-time bootstrap tool

---

## Deliverables

| File | Description |
|------|-------------|
| `tools/fornecedores/generate_fornecedores.py` | Script that reads the .txt and generates the .xlsx |
| `tools/fornecedores/categorias.py` | Hardcoded dict: supplier name → category (311 entries, best-effort research) |
| `Templates/Fornecedores.xlsx` | Output Excel template |

---

## Script: generate_fornecedores.py

**Inputs:** `Templates/Fornecedores.txt`
**Outputs:** `Templates/Fornecedores.xlsx`

**Logic:**
1. Read supplier names from the .txt — use `line.strip()` to remove leading/trailing whitespace and tab characters; skip blank lines
2. Deduplicate: if the same name appears more than once (e.g., `Reiman` appears twice), keep only the first occurrence
3. Derive `Código`:
   - `name[:3].upper()` for names with 3+ characters
   - For names with fewer than 3 characters (e.g., `NB`, `RS`, `RW`, `HP`), use the full name uppercased as-is (2-letter code). These entries are flagged in the Notes column for manual review.
4. Look up `Categoria` from the hardcoded dict in `categorias.py`; default to `Mecânico` for any entry not found in the dict
5. Sort rows alphabetically by Nome
6. Write Excel with openpyxl

**Data quality handling:**
- `line.strip()` handles trailing tabs (e.g., `Schroff\t`) and extra spaces
- Encoding artifacts (e.g., `Goldl cke`, `Rodalg s`, `L2W `) are passed through as-is from the source file; the user can correct them directly in the Excel

---

## Excel Structure

| Column | Header | Width | Content |
|--------|--------|-------|---------|
| A | Nome | 40 | Full supplier name from .txt |
| B | Código | 10 | First 3 letters uppercase (or full name if < 3 chars) |
| C | Categoria | 15 | Mecânico / Elétrico / Pneumático |

**Formatting:**
- Header row: bold, grey background (`#D9D9D9`)
- Column C: data validation dropdown (Mecânico / Elétrico / Pneumático) — prevents typos when correcting
- Row fill color by category:
  - Mecânico → light blue (`#CCE5FF`)
  - Elétrico → light yellow (`#FFFACC`)
  - Pneumático → light green (`#CCFFCC`)
- Sorted alphabetically by Nome

---

## Categorization Dict (categorias.py)

Contains 311 supplier-to-category mappings based on each supplier's primary product line. This is a best-effort initial categorization — the dropdown in column C exists precisely so users can correct any entry that is wrong.

**Rules applied:**
- **Mecânico** — bearings, linear guides, structural profiles, fasteners, gearboxes, couplings, springs, conveyor components, clamping/gripping, tooling, seals, lubrication, shock absorbers, castors
- **Elétrico** — PLCs, drives, motors, sensors, vision systems, cables/connectors, power supplies, HMI/computers, safety systems, lighting, measurement instruments, robotics, encoders, ESD, labeling/printing, soldering
- **Pneumático** — pneumatic cylinders/valves, air treatment, vacuum, fluid fittings, pneumatic tools, compressors

When a supplier spans multiple categories (e.g., Bosch Rexroth covers both electric drives and hydraulics), the **dominant product line in industrial automation context** determines the category.

---

## Collision Handling

Multiple suppliers sharing the same 3-letter code (e.g., `Bosch Automation` and `Bosch Rexroth` → both `BOS`) appear as separate rows. The consuming lookup system is expected to pick the **first match** on `Código`. Since both Bosch entities are categorized as `Elétrico`, this produces no ambiguity in practice. Where colliding entries have different categories, both rows remain and the user resolves via the dropdown.

---

## Future Integration

This Excel will be consumed by the broader categorization system:
- Parts with 3-letter prefix → look up `Código` in Fornecedores.xlsx → get `Categoria`
- Parts with numeric codes → read `corte_fabrico` SW property (existing mechanism)

No changes to existing tools are required for this task.
