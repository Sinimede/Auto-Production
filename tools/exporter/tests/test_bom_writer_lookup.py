"""
Tests for the Excel-backed brand lookup API in bom_writer.py.
Uses a controlled in-memory fixture Excel — does not depend on the real Fornecedores.xlsx.
"""
import sys
import os
import tempfile
import shutil
import unittest
import unittest.mock
import openpyxl

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def _make_fixture_excel(path: str, rows: list) -> None:
    """
    Write a minimal Fornecedores.xlsx fixture.
    rows: list of (nome, categoria) — e.g. [("Festo", "Pneumático")]
    Column layout: A=Nome, B=Código (ignored by loader), C=Categoria
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Nome", "Código", "Categoria"])  # header row 1
    for nome, categoria in rows:
        ws.append([nome, nome[:3].upper(), categoria])
    wb.save(path)


class TestNormalize(unittest.TestCase):

    def test_lowercase_and_strips_spaces(self):
        from bom_writer import normalize
        self.assertEqual(normalize("Bru y Rubio"), "bruyrubio")

    def test_already_lowercase_no_spaces(self):
        from bom_writer import normalize
        self.assertEqual(normalize("equinotec"), "equinotec")

    def test_all_uppercase(self):
        from bom_writer import normalize
        self.assertEqual(normalize("EQUINOTEC"), "equinotec")

    def test_empty_string(self):
        from bom_writer import normalize
        self.assertEqual(normalize(""), "")

    def test_spaces_only(self):
        from bom_writer import normalize
        self.assertEqual(normalize("   "), "")


class TestLoadFornecedoresLookup(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_loads_all_three_categories(self):
        from bom_writer import load_fornecedores_lookup
        _make_fixture_excel(
            os.path.join(self.tmp, "Fornecedores.xlsx"),
            [("Festo", "Pneumático"), ("Balluf", "Elétrico"), ("SKF", "Mecânico")],
        )
        with unittest.mock.patch("bom_writer.get_templates_dir", return_value=self.tmp):
            lookup = load_fornecedores_lookup()
        self.assertEqual(lookup["festo"], "pneumatico")
        self.assertEqual(lookup["balluf"], "eletrico")
        self.assertEqual(lookup["skf"], "mecanico")

    def test_normalizes_names_with_spaces(self):
        from bom_writer import load_fornecedores_lookup
        _make_fixture_excel(
            os.path.join(self.tmp, "Fornecedores.xlsx"),
            [("Bru y Rubio", "Mecânico")],
        )
        with unittest.mock.patch("bom_writer.get_templates_dir", return_value=self.tmp):
            lookup = load_fornecedores_lookup()
        self.assertIn("bruyrubio", lookup)

    def test_skips_rows_with_no_category(self):
        from bom_writer import load_fornecedores_lookup
        _make_fixture_excel(
            os.path.join(self.tmp, "Fornecedores.xlsx"),
            [("Festo", "Pneumático"), ("NoCategory", "")],
        )
        # Patch the Excel to have an empty category row
        # (fixture helper always fills col C — manually write a None cell)
        wb = openpyxl.load_workbook(os.path.join(self.tmp, "Fornecedores.xlsx"))
        ws = wb.active
        ws.cell(row=3, column=3, value=None)
        wb.save(os.path.join(self.tmp, "Fornecedores.xlsx"))

        with unittest.mock.patch("bom_writer.get_templates_dir", return_value=self.tmp):
            lookup = load_fornecedores_lookup()
        self.assertIn("festo", lookup)
        self.assertNotIn("nocategory", lookup)

    def test_missing_excel_returns_empty_dict(self):
        from bom_writer import load_fornecedores_lookup
        empty_dir = os.path.join(self.tmp, "no_excel_here")
        os.makedirs(empty_dir)
        with unittest.mock.patch("bom_writer.get_templates_dir", return_value=empty_dir):
            lookup = load_fornecedores_lookup()
        self.assertEqual(lookup, {})


_FIXTURE_LOOKUP = {
    "festo":   "pneumatico",
    "smc":     "pneumatico",
    "balluf":  "eletrico",
    "siemens": "eletrico",
    "skf":     "mecanico",
    "bruyrubio": "mecanico",  # "Bru y Rubio" normalized
}


class TestIsKnownBrand(unittest.TestCase):
    """
    Patches bom_writer.FORNECEDORES_LOOKUP directly — no reload needed.
    is_known_brand reads the module-level dict at call time, so patch.dict suffices.
    """

    def test_known_brand_exact_match(self):
        import bom_writer
        with unittest.mock.patch.dict(bom_writer.FORNECEDORES_LOOKUP, _FIXTURE_LOOKUP, clear=True):
            self.assertTrue(bom_writer.is_known_brand("Festo"))

    def test_known_brand_case_insensitive(self):
        import bom_writer
        with unittest.mock.patch.dict(bom_writer.FORNECEDORES_LOOKUP, _FIXTURE_LOOKUP, clear=True):
            self.assertTrue(bom_writer.is_known_brand("FESTO"))

    def test_known_brand_substring_match(self):
        import bom_writer
        with unittest.mock.patch.dict(bom_writer.FORNECEDORES_LOOKUP, _FIXTURE_LOOKUP, clear=True):
            self.assertTrue(bom_writer.is_known_brand("Ref 123 Festo ABC"))

    def test_unknown_brand_returns_false(self):
        import bom_writer
        with unittest.mock.patch.dict(bom_writer.FORNECEDORES_LOOKUP, _FIXTURE_LOOKUP, clear=True):
            self.assertFalse(bom_writer.is_known_brand("XYZ Unknown Corp"))

    def test_empty_string_returns_false(self):
        import bom_writer
        with unittest.mock.patch.dict(bom_writer.FORNECEDORES_LOOKUP, _FIXTURE_LOOKUP, clear=True):
            self.assertFalse(bom_writer.is_known_brand(""))

    def test_tuple_input_unpacked(self):
        import bom_writer
        # SW 2024 can return tuple from get_custom_property_evaluated
        with unittest.mock.patch.dict(bom_writer.FORNECEDORES_LOOKUP, _FIXTURE_LOOKUP, clear=True):
            self.assertTrue(bom_writer.is_known_brand(("Festo", "extra")))

    def test_tuple_empty_returns_false(self):
        import bom_writer
        with unittest.mock.patch.dict(bom_writer.FORNECEDORES_LOOKUP, _FIXTURE_LOOKUP, clear=True):
            self.assertFalse(bom_writer.is_known_brand(()))


class TestClassifyCommercialWithFixture(unittest.TestCase):
    """
    Patches bom_writer.FORNECEDORES_LOOKUP directly — no reload needed.
    classify_commercial reads the module-level dict at call time.
    """

    def test_exact_match_pneumatico(self):
        import bom_writer
        with unittest.mock.patch.dict(bom_writer.FORNECEDORES_LOOKUP, _FIXTURE_LOOKUP, clear=True):
            self.assertEqual(bom_writer.classify_commercial("Festo"), "pneumatico")

    def test_case_insensitive_pneumatico(self):
        import bom_writer
        with unittest.mock.patch.dict(bom_writer.FORNECEDORES_LOOKUP, _FIXTURE_LOOKUP, clear=True):
            self.assertEqual(bom_writer.classify_commercial("FESTO"), "pneumatico")

    def test_space_variation_mecanico(self):
        import bom_writer
        # "Bruyrubio" normalizes to "bruyrubio", same as "Bru y Rubio"
        with unittest.mock.patch.dict(bom_writer.FORNECEDORES_LOOKUP, _FIXTURE_LOOKUP, clear=True):
            self.assertEqual(bom_writer.classify_commercial("Bruyrubio"), "mecanico")

    def test_substring_match_eletrico(self):
        import bom_writer
        with unittest.mock.patch.dict(bom_writer.FORNECEDORES_LOOKUP, _FIXTURE_LOOKUP, clear=True):
            self.assertEqual(bom_writer.classify_commercial("Produto Balluf 123"), "eletrico")

    def test_unknown_brand_defaults_to_mecanico(self):
        import bom_writer
        with unittest.mock.patch.dict(bom_writer.FORNECEDORES_LOOKUP, _FIXTURE_LOOKUP, clear=True):
            self.assertEqual(bom_writer.classify_commercial("Unknown Corp XYZ"), "mecanico")

    def test_empty_string_defaults_to_mecanico(self):
        import bom_writer
        with unittest.mock.patch.dict(bom_writer.FORNECEDORES_LOOKUP, _FIXTURE_LOOKUP, clear=True):
            self.assertEqual(bom_writer.classify_commercial(""), "mecanico")

    def test_tuple_input_unpacked(self):
        import bom_writer
        with unittest.mock.patch.dict(bom_writer.FORNECEDORES_LOOKUP, _FIXTURE_LOOKUP, clear=True):
            self.assertEqual(bom_writer.classify_commercial(("Festo", "extra")), "pneumatico")

    def test_exact_match_wins_over_substring(self):
        """Exact match should return before iterating substrings."""
        import bom_writer
        with unittest.mock.patch.dict(bom_writer.FORNECEDORES_LOOKUP, _FIXTURE_LOOKUP, clear=True):
            self.assertEqual(bom_writer.classify_commercial("SMC"), "pneumatico")


if __name__ == "__main__":
    unittest.main()
