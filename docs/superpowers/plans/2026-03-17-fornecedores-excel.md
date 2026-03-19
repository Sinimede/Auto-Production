# Fornecedores Excel Template — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate `Templates/Fornecedores.xlsx` — a supplier lookup table with Name, 3-letter Code, and Category (Mecânico / Elétrico / Pneumático), with dropdown validation for easy correction.

**Architecture:** A standalone Python script reads `Templates/Fornecedores.txt`, derives each supplier's code from the first 3 characters of its name, looks up the category from a hardcoded dict, and writes a formatted Excel file with openpyxl. The categorization dict lives in its own module. Tests cover the core data-transformation logic independently of file I/O.

**Tech Stack:** Python 3.x, openpyxl 3.x

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `tools/fornecedores/categorias.py` | Hardcoded dict: supplier name → category |
| Create | `tools/fornecedores/generate_fornecedores.py` | CLI script: reads .txt, writes .xlsx |
| Create | `tools/fornecedores/tests/test_generate_fornecedores.py` | Unit tests for helper logic |
| Generate | `Templates/Fornecedores.xlsx` | Output — produced by running the script |

---

## Task 1: Create categorias.py

**Files:**
- Create: `tools/fornecedores/categorias.py`

No tests for this file — it is pure data. Correctness is validated visually in the Excel output.

- [ ] **Step 1: Create `tools/fornecedores/categorias.py`**

```python
# tools/fornecedores/categorias.py
"""
Hardcoded supplier → category mapping.
Categories: Mecânico | Elétrico | Pneumático
Best-effort initial categorization — use the Excel dropdown to correct any entry.
"""

CATEGORIAS = {
    "AIM SOLDER": "Elétrico",
    "AND": "Elétrico",
    "ABB": "Elétrico",
    "Accuride": "Mecânico",
    "Advantech": "Elétrico",
    "Afag": "Pneumático",
    "Allen-Bradley": "Elétrico",
    "Amada": "Mecânico",
    "Ammeraal beltech": "Mecânico",
    "Amplicon": "Elétrico",
    "Antistat": "Elétrico",
    "Apex": "Mecânico",
    "Aquaeden": "Mecânico",
    "Asahi Yukizai": "Pneumático",
    "ASS": "Elétrico",
    "ASUS": "Elétrico",
    "Asutec": "Mecânico",
    "Ateq": "Pneumático",
    "Atlas Copco": "Pneumático",
    "Aventics": "Pneumático",
    "Balluf": "Elétrico",
    "Banner": "Elétrico",
    "Barboflex": "Mecânico",
    "Baumer": "Elétrico",
    "Becker": "Pneumático",
    "Beckhoff": "Elétrico",
    "Beijer Electronics": "Elétrico",
    "Bene inox": "Mecânico",
    "Berger Lahr": "Elétrico",
    "Blickle": "Mecânico",
    "Bru y Rubio": "Mecânico",
    "Bosch Automation": "Elétrico",
    "Bosch Rexroth": "Mecânico",
    "Boteco": "Mecânico",
    "Burkert": "Pneumático",
    "Burster": "Elétrico",
    "CAB": "Elétrico",
    "Captron": "Elétrico",
    "Camozzi": "Pneumático",
    "Casalmáquinas": "Mecânico",
    "Cembre": "Elétrico",
    "Cherry": "Elétrico",
    "Chiaravalli": "Mecânico",
    "Cognex": "Elétrico",
    "Contrinex": "Elétrico",
    "Coolens": "Mecânico",
    "Datalogic": "Elétrico",
    "DCM Sistemes": "Elétrico",
    "Dell": "Elétrico",
    "Deprag": "Pneumático",
    "Desoutter": "Elétrico",
    "De-Sta-Co": "Mecânico",
    "Deimos": "Mecânico",
    "Denso": "Elétrico",
    "Di-Soric": "Elétrico",
    "Dini Argeo": "Elétrico",
    "Dirak": "Mecânico",
    "Doceram": "Mecânico",
    "Dopag": "Mecânico",
    "DPV": "Mecânico",
    "Dukane": "Elétrico",
    "Dunkermotoren": "Elétrico",
    "Eaton": "Elétrico",
    "Efectoled": "Elétrico",
    "Egana": "Mecânico",
    "Eldon": "Elétrico",
    "Electron": "Elétrico",
    "Elesa": "Mecânico",
    "Elesa+Ganter": "Mecânico",
    "Elcom": "Elétrico",
    "Elfin": "Elétrico",
    "Emile Maurin": "Mecânico",
    "Enidine": "Mecânico",
    "Epson": "Elétrico",
    "Ersa": "Elétrico",
    "Ettinger": "Mecânico",
    "Equinotec": "Mecânico",
    "ETL": "Elétrico",
    "Everett C.T.": "Elétrico",
    "Euchner": "Elétrico",
    "Fabory": "Mecânico",
    "Fag": "Mecânico",
    "Fanamol": "Mecânico",
    "Fandis": "Elétrico",
    "Fanuc": "Elétrico",
    "Farnell": "Elétrico",
    "Fasten": "Mecânico",
    "Fath": "Mecânico",
    "Faytech": "Elétrico",
    "Fersilva": "Mecânico",
    "Festo": "Pneumático",
    "Fett": "Mecânico",
    "Fibro": "Mecânico",
    "Fitek": "Mecânico",
    "Fixo": "Mecânico",
    "Fixsolda": "Elétrico",
    "Fli": "Mecânico",
    "Footmaster": "Mecânico",
    "Fortest": "Elétrico",
    "Frezite": "Mecânico",
    "FKK": "Mecânico",
    "Gayner": "Mecânico",
    "Gemalto": "Elétrico",
    "Greenkinetics": "Elétrico",
    "Greenlux": "Elétrico",
    "Gewiss": "Elétrico",
    "Goldl cke": "Mecânico",
    "GomsiParts": "Mecânico",
    "Good-Hand": "Mecânico",
    "Gutekunst": "Mecânico",
    "Gimatic": "Pneumático",
    "Habasit": "Mecânico",
    "Hager": "Elétrico",
    "Hansen": "Mecânico",
    "Harting": "Elétrico",
    "Hasco": "Mecânico",
    "Heidenhain": "Elétrico",
    "Heitec": "Elétrico",
    "Hiwin": "Mecânico",
    "Hoffman": "Elétrico",
    "HP": "Elétrico",
    "Huco": "Mecânico",
    "Huf": "Mecânico",
    "Hypertronics": "Elétrico",
    "IAI": "Elétrico",
    "IBC": "Mecânico",
    "IDE": "Elétrico",
    "IDS": "Elétrico",
    "IFM": "Elétrico",
    "Igus": "Mecânico",
    "IHS Handling": "Mecânico",
    "IKO": "Mecânico",
    "INA": "Mecânico",
    "Infaimon": "Elétrico",
    "Ingun": "Elétrico",
    "Itec": "Mecânico",
    "Item": "Mecânico",
    "Itt": "Elétrico",
    "Jacob": "Elétrico",
    "Jaguar": "Mecânico",
    "Juncor": "Mecânico",
    "Jura-Schrauben": "Mecânico",
    "JVL": "Elétrico",
    "Keyence": "Elétrico",
    "Kistler": "Elétrico",
    "Kipp": "Mecânico",
    "Kolver": "Elétrico",
    "Kuka": "Elétrico",
    "Lanema": "Mecânico",
    "Lapp Kabel": "Elétrico",
    "Lauda": "Elétrico",
    "Legrand": "Elétrico",
    "Legris": "Pneumático",
    "Lenovo": "Elétrico",
    "Lenze": "Elétrico",
    "Leschhorn": "Mecânico",
    "LMI Technologies": "Elétrico",
    "Logitech": "Elétrico",
    "Lumberg": "Elétrico",
    "Lupatec": "Mecânico",
    "Luxtar": "Elétrico",
    "Lypsis": "Mecânico",
    "L2W": "Mecânico",
    "Manutan": "Mecânico",
    "Marbett": "Mecânico",
    "Marchesini": "Mecânico",
    "MayTeC": "Mecânico",
    "Macsa": "Elétrico",
    "Mauser": "Mecânico",
    "Meanwell": "Elétrico",
    "Mecanarte": "Mecânico",
    "Megatron Elecktronik": "Elétrico",
    "Menekes": "Elétrico",
    "Merlin Gerin": "Elétrico",
    "Metal Work": "Pneumático",
    "Meusburger": "Mecânico",
    "Misumi": "Mecânico",
    "Mitutoyo": "Elétrico",
    "Moeller": "Elétrico",
    "Montech": "Mecânico",
    "Murr": "Elétrico",
    "Mustek": "Elétrico",
    "Neugart": "Mecânico",
    "Nex Flow": "Pneumático",
    "NB": "Mecânico",
    "NBK": "Mecânico",
    "Nicolau Rosa": "Mecânico",
    "Nord": "Mecânico",
    "Norelem": "Mecânico",
    "NSK": "Mecânico",
    "NTN": "Mecânico",
    "Obo Bettermann": "Elétrico",
    "OleoDinamica Marchesini": "Mecânico",
    "OMC": "Mecânico",
    "Omega": "Elétrico",
    "Omron": "Elétrico",
    "Omge": "Mecânico",
    "Optibelt": "Mecânico",
    "Opto Engineering": "Elétrico",
    "Oriental Motor": "Elétrico",
    "Panasonic": "Elétrico",
    "Panduit": "Elétrico",
    "Patlite": "Elétrico",
    "Paulifer": "Mecânico",
    "PCE": "Elétrico",
    "Pemsa": "Elétrico",
    "Pepperl+Fuchs": "Elétrico",
    "Pfeiffer": "Pneumático",
    "Phasa": "Elétrico",
    "Philips": "Elétrico",
    "Phoenix Contact": "Elétrico",
    "Pilz": "Elétrico",
    "Pinet": "Mecânico",
    "PMA": "Elétrico",
    "PMI": "Mecânico",
    "Potermic": "Elétrico",
    "Proface": "Elétrico",
    "Promag": "Elétrico",
    "Promess": "Elétrico",
    "Purex": "Elétrico",
    "Puzzle Advance": "Mecânico",
    "Rabourdin": "Mecânico",
    "Rad": "Elétrico",
    "Reichelt": "Elétrico",
    "Reiman": "Mecânico",
    "Richco": "Mecânico",
    "Rittal": "Elétrico",
    "Rockwell": "Elétrico",
    "Rodalg s": "Mecânico",
    "Rohde & Schwarz": "Elétrico",
    "Rolisa": "Mecânico",
    "Rollon": "Mecânico",
    "Rose": "Elétrico",
    "Rose Krieger": "Mecânico",
    "Rotex": "Mecânico",
    "RS": "Elétrico",
    "Ruwac": "Pneumático",
    "RW": "Mecânico",
    "Sato": "Elétrico",
    "Satech": "Mecânico",
    "Schaeffner": "Elétrico",
    "Schmersal": "Elétrico",
    "Schmidt": "Mecânico",
    "Schneider": "Elétrico",
    "Schunk": "Mecânico",
    "Schrader": "Pneumático",
    "Schroff": "Elétrico",
    "SEW": "Elétrico",
    "Sejin": "Elétrico",
    "Selfoil": "Mecânico",
    "Sensopart": "Elétrico",
    "Senstronic": "Elétrico",
    "Shunk": "Mecânico",
    "Sick": "Elétrico",
    "Siemens": "Elétrico",
    "SKF": "Mecânico",
    "SMAC": "Elétrico",
    "SMC": "Pneumático",
    "SNR": "Mecânico",
    "Special springs": "Mecânico",
    "Socafluid": "Pneumático",
    "Sofima": "Pneumático",
    "Solartron": "Elétrico",
    "Sonitek": "Elétrico",
    "Sonorous": "Elétrico",
    "Sove": "Mecânico",
    "Staubli": "Mecânico",
    "Stieber": "Mecânico",
    "Supermagnete": "Mecânico",
    "Sutafer": "Mecânico",
    "Switchcraft": "Elétrico",
    "Swagelok": "Pneumático",
    "Syskomp": "Elétrico",
    "Tecnitem": "Mecânico",
    "Teknokol": "Mecânico",
    "Tente": "Mecânico",
    "Thenar": "Mecânico",
    "THK": "Mecânico",
    "Tironi": "Mecânico",
    "Triplo W": "Mecânico",
    "Troax": "Mecânico",
    "Trumpf": "Elétrico",
    "Turck": "Elétrico",
    "Vanel": "Mecânico",
    "Vetter": "Mecânico",
    "Vibrant": "Mecânico",
    "Vico": "Mecânico",
    "Videojet": "Elétrico",
    "Viewsonic": "Elétrico",
    "Xecro": "Elétrico",
    "Wago": "Elétrico",
    "Waicon": "Elétrico",
    "Walter-Praezision": "Mecânico",
    "Wandres": "Mecânico",
    "Weber": "Mecânico",
    "Wemo": "Elétrico",
    "Weidmuller": "Elétrico",
    "Weintek": "Elétrico",
    "Weiss": "Mecânico",
    "Weller": "Elétrico",
    "Wenglor": "Elétrico",
    "Werma": "Elétrico",
    "Wide Range": "Elétrico",
    "Wittenstein Alpha": "Mecânico",
    "Wiva": "Elétrico",
    "Wolfgang Warmbier": "Elétrico",
    "Woerner": "Mecânico",
    "Yaskawa": "Elétrico",
    "Zebra": "Elétrico",
    "Zimmer": "Mecânico",
    "Zitec": "Mecânico",
}

VALID_CATEGORIES = ("Mecânico", "Elétrico", "Pneumático")
DEFAULT_CATEGORY = "Mecânico"
```

- [ ] **Step 2: Commit**

```bash
git add tools/fornecedores/categorias.py
git commit -m "feat: add supplier categorization dict (categorias.py)"
```

---

## Task 2: Write failing tests

**Files:**
- Create: `tools/fornecedores/tests/test_generate_fornecedores.py`

- [ ] **Step 1: Create test file**

```python
# tools/fornecedores/tests/test_generate_fornecedores.py
import sys
import os
import tempfile
import unittest
import openpyxl

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from generate_fornecedores import derive_code, load_suppliers, build_rows


class TestDeriveCode(unittest.TestCase):
    def test_normal_name(self):
        self.assertEqual(derive_code("Bosch Automation"), "BOS")

    def test_exact_3_chars(self):
        self.assertEqual(derive_code("SMC"), "SMC")

    def test_short_name_2_chars(self):
        # Names shorter than 3 chars → use full name uppercased
        self.assertEqual(derive_code("NB"), "NB")

    def test_short_name_1_char(self):
        self.assertEqual(derive_code("A"), "A")

    def test_lowercase_input(self):
        self.assertEqual(derive_code("festo"), "FES")

    def test_mixed_case(self):
        self.assertEqual(derive_code("MayTeC"), "MAY")


class TestLoadSuppliers(unittest.TestCase):
    def _write_txt(self, lines):
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                        delete=False, encoding="utf-8")
        f.write("\n".join(lines))
        f.close()
        return f.name

    def test_strips_whitespace(self):
        path = self._write_txt(["  SMC  ", "Festo"])
        result = load_suppliers(path)
        self.assertIn("SMC", result)
        self.assertIn("Festo", result)

    def test_strips_tab(self):
        path = self._write_txt(["Schroff\t", "Festo"])
        result = load_suppliers(path)
        self.assertIn("Schroff", result)

    def test_skips_blank_lines(self):
        path = self._write_txt(["SMC", "", "Festo", "   "])
        result = load_suppliers(path)
        self.assertEqual(len(result), 2)

    def test_deduplicates(self):
        path = self._write_txt(["Reiman", "SMC", "Reiman"])
        result = load_suppliers(path)
        self.assertEqual(result.count("Reiman"), 1)

    def test_preserves_order(self):
        path = self._write_txt(["Festo", "SMC", "ABB"])
        result = load_suppliers(path)
        self.assertEqual(result, ["Festo", "SMC", "ABB"])


class TestBuildRows(unittest.TestCase):
    def test_known_supplier(self):
        rows = build_rows(["SMC"])
        self.assertEqual(rows[0], ("SMC", "SMC", "Pneumático"))

    def test_unknown_supplier_defaults_to_mecanico(self):
        rows = build_rows(["XyzUnknown"])
        self.assertEqual(rows[0][2], "Mecânico")

    def test_code_derivation(self):
        rows = build_rows(["Festo"])
        self.assertEqual(rows[0][1], "FES")

    def test_sorted_alphabetically(self):
        rows = build_rows(["SMC", "ABB", "Festo"])
        names = [r[0] for r in rows]
        self.assertEqual(names, sorted(names))

    def test_short_name_code(self):
        rows = build_rows(["NB"])
        self.assertEqual(rows[0][1], "NB")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests — verify they all FAIL**

```bash
cd "c:/Users/Micael/Desktop/Auto Production"
python -m pytest tools/fornecedores/tests/test_generate_fornecedores.py -v
```

Expected: all tests fail with `ModuleNotFoundError` (generate_fornecedores doesn't exist yet).

- [ ] **Step 3: Commit tests**

```bash
git add tools/fornecedores/tests/test_generate_fornecedores.py
git commit -m "test: add failing tests for generate_fornecedores helpers"
```

---

## Task 3: Implement generate_fornecedores.py

**Files:**
- Create: `tools/fornecedores/generate_fornecedores.py`

- [ ] **Step 1: Create `tools/fornecedores/generate_fornecedores.py`**

```python
# tools/fornecedores/generate_fornecedores.py
"""
Bootstrap script — run once to generate Templates/Fornecedores.xlsx.
Re-running overwrites the file; manual corrections in the Excel are lost.
"""
import os
import sys
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.worksheet.datavalidation import DataValidation

sys.path.insert(0, os.path.dirname(__file__))
from categorias import CATEGORIAS, VALID_CATEGORIES, DEFAULT_CATEGORY

# ── Colours ────────────────────────────────────────────────────────────────
HEADER_FILL  = PatternFill("solid", fgColor="D9D9D9")
CAT_FILLS = {
    "Mecânico":   PatternFill("solid", fgColor="CCE5FF"),
    "Elétrico":   PatternFill("solid", fgColor="FFFACC"),
    "Pneumático": PatternFill("solid", fgColor="CCFFCC"),
}

# ── Helpers ─────────────────────────────────────────────────────────────────

def derive_code(name: str) -> str:
    """Return uppercase 3-letter (or shorter) prefix from supplier name."""
    return name[:3].upper()


def load_suppliers(txt_path: str) -> list:
    """Read supplier names from txt file; strip whitespace, skip blanks, deduplicate (keep first)."""
    seen = set()
    result = []
    with open(txt_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            name = line.strip()
            if not name:
                continue
            if name not in seen:
                seen.add(name)
                result.append(name)
    return result


def build_rows(suppliers: list) -> list:
    """Return sorted list of (nome, código, categoria) tuples."""
    rows = []
    for name in suppliers:
        code = derive_code(name)
        cat  = CATEGORIAS.get(name, DEFAULT_CATEGORY)
        rows.append((name, code, cat))
    rows.sort(key=lambda r: r[0].lower())
    return rows


def write_excel(rows: list, out_path: str) -> None:
    """Write the formatted Excel file."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Fornecedores"

    # Header
    headers = ["Nome", "Código", "Categoria"]
    ws.append(headers)
    for col, _ in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col)
        cell.font = Font(bold=True)
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center")

    # Data validation dropdown on column C
    dv = DataValidation(
        type="list",
        formula1='"Mecânico,Elétrico,Pneumático"',
        allow_blank=False,
        showDropDown=False,
    )
    ws.add_data_validation(dv)

    # Data rows
    for i, (nome, codigo, categoria) in enumerate(rows, start=2):
        ws.cell(row=i, column=1, value=nome)
        ws.cell(row=i, column=2, value=codigo)
        cat_cell = ws.cell(row=i, column=3, value=categoria)
        fill = CAT_FILLS.get(categoria, CAT_FILLS["Mecânico"])
        for col in range(1, 4):
            ws.cell(row=i, column=col).fill = fill
        dv.add(cat_cell)

    # Column widths
    ws.column_dimensions["A"].width = 40
    ws.column_dimensions["B"].width = 10
    ws.column_dimensions["C"].width = 15

    wb.save(out_path)
    print(f"Saved {len(rows)} suppliers → {out_path}")


def main():
    base     = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    txt_path = os.path.join(base, "Templates", "Fornecedores.txt")
    out_path = os.path.join(base, "Templates", "Fornecedores.xlsx")

    if not os.path.exists(txt_path):
        print(f"ERROR: source file not found: {txt_path}")
        sys.exit(1)

    suppliers = load_suppliers(txt_path)
    rows      = build_rows(suppliers)
    write_excel(rows, out_path)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run tests — verify they all PASS**

```bash
cd "c:/Users/Micael/Desktop/Auto Production"
python -m pytest tools/fornecedores/tests/test_generate_fornecedores.py -v
```

Expected: all tests PASS.

- [ ] **Step 3: Commit implementation**

```bash
git add tools/fornecedores/generate_fornecedores.py
git commit -m "feat: implement generate_fornecedores script"
```

---

## Task 4: Generate the Excel and verify

**Files:**
- Generate: `Templates/Fornecedores.xlsx`

- [ ] **Step 1: Run the script**

```bash
cd "c:/Users/Micael/Desktop/Auto Production"
python tools/fornecedores/generate_fornecedores.py
```

Expected output:
```
Saved 310 suppliers → c:\Users\Micael\Desktop\Auto Production\Templates\Fornecedores.xlsx
```

(Exact count may vary slightly due to deduplication of `Reiman`.)

- [ ] **Step 2: Spot-check the Excel**

Open `Templates/Fornecedores.xlsx` and verify:
- Column headers: Nome / Código / Categoria
- SMC → SMC → Pneumático (green)
- Siemens → SIE → Elétrico (yellow)
- SKF → SKF → Mecânico (blue)
- NB → NB → Mecânico (2-letter code)
- Reiman appears only once
- Dropdown works on column C (click a cell → dropdown arrow appears)

- [ ] **Step 3: Final commit**

```bash
git add Templates/Fornecedores.xlsx
git commit -m "feat: generate Fornecedores.xlsx supplier lookup table"
```
