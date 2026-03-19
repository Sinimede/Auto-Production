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
