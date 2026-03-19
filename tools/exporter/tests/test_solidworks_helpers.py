"""
Unit tests for new solidworks.py helper functions.
COM objects are mocked — SolidWorks does not need to be running.
"""
import sys
import os
import unittest
from unittest.mock import MagicMock, patch
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ---------------------------------------------------------------------------
# count_instances
# ---------------------------------------------------------------------------

def _make_comp(path, suppressed=False):
    comp = MagicMock()
    comp.GetPathName.return_value = path
    # count_instances uses GetSuppression(): 0=suppressed, 4=fully resolved
    comp.GetSuppression.return_value = 0 if suppressed else 4
    return comp


class TestCountInstances(unittest.TestCase):

    def test_counts_matching_non_suppressed(self):
        from solidworks import count_instances
        comps = [
            _make_comp("C:\\parts\\part_a.sldprt"),
            _make_comp("C:\\parts\\part_a.sldprt"),
            _make_comp("C:\\parts\\part_b.sldprt"),
        ]
        self.assertEqual(count_instances(comps, "C:\\parts\\part_a.sldprt"), 2)

    def test_skips_suppressed(self):
        from solidworks import count_instances
        comps = [
            _make_comp("C:\\parts\\part_a.sldprt"),
            _make_comp("C:\\parts\\part_a.sldprt", suppressed=True),
        ]
        self.assertEqual(count_instances(comps, "C:\\parts\\part_a.sldprt"), 1)

    def test_case_insensitive_path_match(self):
        from solidworks import count_instances
        comps = [_make_comp("C:\\Parts\\Part_A.SLDPRT")]
        self.assertEqual(count_instances(comps, "c:\\parts\\part_a.sldprt"), 1)

    def test_normpath_handles_mixed_separators(self):
        from solidworks import count_instances
        # COM may return backslashes; caller may pass forward slashes
        comps = [_make_comp("C:\\parts\\part_a.sldprt")]
        self.assertEqual(count_instances(comps, "C:/parts/part_a.sldprt"), 1)

    def test_returns_zero_no_match(self):
        from solidworks import count_instances
        comps = [_make_comp("C:\\parts\\part_b.sldprt")]
        self.assertEqual(count_instances(comps, "C:\\parts\\part_a.sldprt"), 0)

    def test_empty_components(self):
        from solidworks import count_instances
        self.assertEqual(count_instances([], "C:\\parts\\part_a.sldprt"), 0)

    def test_getpathname_exception_skipped(self):
        from solidworks import count_instances
        bad = MagicMock()
        bad.IsSuppressed.return_value = False
        bad.GetPathName.side_effect = Exception("COM error")
        good = _make_comp("C:\\parts\\part_a.sldprt")
        self.assertEqual(count_instances([bad, good], "C:\\parts\\part_a.sldprt"), 1)


# ---------------------------------------------------------------------------
# get_custom_property_evaluated
# ---------------------------------------------------------------------------

def _make_model_doc_with_props(props: dict):
    """props: {prop_name: resolved_value_str}"""
    mgr = MagicMock()
    def _get4(name, flag):
        if name in props:
            return (0, f"raw_{name}", props[name], True)
        return (0, None, None, False)
    def _get(name):
        return props.get(name)  # None for missing props
    mgr.Get4.side_effect = _get4
    mgr.Get.side_effect = _get
    ext = MagicMock()
    ext.CustomPropertyManager.return_value = mgr
    doc = MagicMock()
    doc.Extension = ext
    return doc


class TestGetCustomPropertyEvaluated(unittest.TestCase):

    def test_returns_resolved_value(self):
        from solidworks import get_custom_property_evaluated
        doc = _make_model_doc_with_props({"Material": "Cast Alloy Steel"})
        self.assertEqual(get_custom_property_evaluated(doc, "Material"), "Cast Alloy Steel")

    def test_returns_empty_string_for_missing_property(self):
        from solidworks import get_custom_property_evaluated
        doc = _make_model_doc_with_props({})
        self.assertEqual(get_custom_property_evaluated(doc, "Material"), "")

    def test_returns_empty_string_on_exception(self):
        from solidworks import get_custom_property_evaluated
        doc = MagicMock()
        doc.Extension.CustomPropertyManager.side_effect = Exception("COM error")
        self.assertEqual(get_custom_property_evaluated(doc, "Material"), "")

    def test_resolved_val_none_falls_back_to_raw(self):
        """When resolvedVal is None, fall back to raw value (not empty string)."""
        from solidworks import get_custom_property_evaluated
        mgr = MagicMock()
        mgr.Get4.return_value = (0, "raw", None, False)
        ext = MagicMock()
        ext.CustomPropertyManager.return_value = mgr
        doc = MagicMock()
        doc.Extension = ext
        self.assertEqual(get_custom_property_evaluated(doc, "Simetria"), "raw")

    def test_both_none_returns_empty(self):
        """When both resolvedVal and raw are None, and Get() also returns None → empty."""
        from solidworks import get_custom_property_evaluated
        mgr = MagicMock()
        mgr.Get4.return_value = (0, None, None, False)
        mgr.Get.return_value = None
        ext = MagicMock()
        ext.CustomPropertyManager.return_value = mgr
        doc = MagicMock()
        doc.Extension = ext
        self.assertEqual(get_custom_property_evaluated(doc, "Simetria"), "")

    def test_strips_whitespace(self):
        from solidworks import get_custom_property_evaluated
        doc = _make_model_doc_with_props({"TratSuperficial": "  Pintar RAL 9002  "})
        self.assertEqual(get_custom_property_evaluated(doc, "TratSuperficial"),
                         "Pintar RAL 9002")

    def test_falls_back_to_raw_when_resolved_empty(self):
        """Plain-text properties return empty resolvedVal on some SW versions; use raw."""
        from solidworks import get_custom_property_evaluated
        mgr = MagicMock()
        mgr.Get4.return_value = (0, "S235JR", "", True)
        ext = MagicMock()
        ext.CustomPropertyManager.return_value = mgr
        doc = MagicMock()
        doc.Extension = ext
        self.assertEqual(get_custom_property_evaluated(doc, "Material"), "S235JR")

    def test_prefers_resolved_over_raw_when_both_present(self):
        """When resolvedVal has content, prefer it (handles SW expression-linked props)."""
        from solidworks import get_custom_property_evaluated
        mgr = MagicMock()
        mgr.Get4.return_value = (0, "SW-Material@part.SLDPRT", "Cast Alloy Steel", True)
        ext = MagicMock()
        ext.CustomPropertyManager.return_value = mgr
        doc = MagicMock()
        doc.Extension = ext
        self.assertEqual(get_custom_property_evaluated(doc, "Material"), "Cast Alloy Steel")

    def test_falls_back_to_get_when_get4_yields_nothing(self):
        """If Get4 yields nothing (e.g. fails silently in some SW versions),
        Get() is used — mirrors the proven pattern in is_laser_part."""
        from solidworks import get_custom_property_evaluated
        mgr = MagicMock()
        mgr.Get4.return_value = (0, None, None, False)
        mgr.Get.return_value = "LASER"
        ext = MagicMock()
        ext.CustomPropertyManager.return_value = mgr
        doc = MagicMock()
        doc.Extension = ext
        self.assertEqual(get_custom_property_evaluated(doc, "Corte_Fabrico"), "LASER")


# ---------------------------------------------------------------------------
# _get_part_material
# ---------------------------------------------------------------------------

class TestGetPartMaterial(unittest.TestCase):

    def _make_doc(self, mat_return):
        part_mock = MagicMock()
        part_mock.GetMaterialPropertyName2.return_value = mat_return
        with patch("solidworks._wrap", return_value=part_mock):
            from solidworks import _get_part_material
            return _get_part_material(MagicMock())

    def test_returns_string_material(self):
        """Plain string return (some SW versions/stubs)."""
        from solidworks import _get_part_material
        part_mock = MagicMock()
        part_mock.GetMaterialPropertyName2.return_value = "S235JR"
        with patch("solidworks._wrap", return_value=part_mock):
            self.assertEqual(_get_part_material(MagicMock()), "S235JR")

    def test_returns_tuple_material_extracts_first_element(self):
        """SW 2024 early binding returns (name, database) tuple — extract name."""
        from solidworks import _get_part_material
        part_mock = MagicMock()
        part_mock.GetMaterialPropertyName2.return_value = ("1.0037 (S235JR)", "Materials")
        with patch("solidworks._wrap", return_value=part_mock):
            self.assertEqual(_get_part_material(MagicMock()), "1.0037 (S235JR)")

    def test_returns_empty_when_tuple_first_element_empty(self):
        from solidworks import _get_part_material
        part_mock = MagicMock()
        part_mock.GetMaterialPropertyName2.return_value = ("", "Materials")
        with patch("solidworks._wrap", return_value=part_mock):
            self.assertEqual(_get_part_material(MagicMock()), "")

    def test_returns_empty_on_exception(self):
        from solidworks import _get_part_material
        with patch("solidworks._wrap", side_effect=Exception("COM error")):
            self.assertEqual(_get_part_material(MagicMock()), "")

    def test_strips_whitespace(self):
        from solidworks import _get_part_material
        part_mock = MagicMock()
        part_mock.GetMaterialPropertyName2.return_value = ("  Cast Alloy Steel  ", "DB")
        with patch("solidworks._wrap", return_value=part_mock):
            self.assertEqual(_get_part_material(MagicMock()), "Cast Alloy Steel")


# ---------------------------------------------------------------------------
# _get_sheet_metal_thickness
# ---------------------------------------------------------------------------

class TestGetSheetMetalThickness(unittest.TestCase):

    def _make_late_doc(self, features):
        """features: list of (type_name, thickness_m_or_none)"""
        feat_mocks = []
        for i, (type_name, thickness) in enumerate(features):
            f = MagicMock()
            f.GetTypeName2.return_value = type_name
            if thickness is not None:
                sm_mock = MagicMock()
                sm_mock.Thickness = thickness
                defn_mock = MagicMock()
                f.GetDefinition.return_value = defn_mock
            else:
                f.GetDefinition.return_value = None
            # chain GetNextFeature
            feat_mocks.append(f)
        for i, f in enumerate(feat_mocks):
            f.GetNextFeature.return_value = feat_mocks[i + 1] if i + 1 < len(feat_mocks) else None
        return feat_mocks[0] if feat_mocks else None

    def _make_sm_scene(self, type_name, thickness_m):
        """Build a mock part with one feature of given type and thickness."""
        defn = MagicMock()
        defn_raw = MagicMock()
        late_defn = MagicMock()
        late_defn.Thickness = thickness_m
        defn._oleobj_ = defn_raw

        feat = MagicMock()
        feat.GetTypeName2.return_value = type_name
        feat.GetDefinition.return_value = defn
        feat.GetNextFeature.return_value = None

        part = MagicMock()
        part.FirstFeature.return_value = feat
        return part, late_defn

    def test_returns_thickness_from_sheet_metal_feature(self):
        from solidworks import _get_sheet_metal_thickness
        part, late_defn = self._make_sm_scene("SheetMetal", 0.002)
        with patch("solidworks._wrap", side_effect=lambda obj, iface: part if iface == "IPartDoc" else obj), \
             patch("win32com.client.Dispatch", return_value=late_defn):
            self.assertEqual(_get_sheet_metal_thickness(MagicMock()), 2.0)

    def test_rounds_to_2dp(self):
        from solidworks import _get_sheet_metal_thickness
        part, late_defn = self._make_sm_scene("SheetMetal", 0.0015)
        with patch("solidworks._wrap", side_effect=lambda obj, iface: part if iface == "IPartDoc" else obj), \
             patch("win32com.client.Dispatch", return_value=late_defn):
            self.assertEqual(_get_sheet_metal_thickness(MagicMock()), 1.5)

    def test_skips_non_sheet_metal_features(self):
        from solidworks import _get_sheet_metal_thickness
        part, late_defn = self._make_sm_scene("Sketch", 0.002)
        with patch("solidworks._wrap", side_effect=lambda obj, iface: part if iface == "IPartDoc" else obj), \
             patch("win32com.client.Dispatch", return_value=late_defn):
            self.assertIsNone(_get_sheet_metal_thickness(MagicMock()))

    def test_skips_zero_thickness(self):
        from solidworks import _get_sheet_metal_thickness
        part, late_defn = self._make_sm_scene("SheetMetal", 0.0)
        with patch("solidworks._wrap", side_effect=lambda obj, iface: part if iface == "IPartDoc" else obj), \
             patch("win32com.client.Dispatch", return_value=late_defn):
            self.assertIsNone(_get_sheet_metal_thickness(MagicMock()))

    def test_returns_none_on_exception(self):
        from solidworks import _get_sheet_metal_thickness
        with patch("solidworks._wrap", side_effect=Exception("COM error")):
            self.assertIsNone(_get_sheet_metal_thickness(MagicMock()))


# ---------------------------------------------------------------------------
# get_bounding_box_thickness
# ---------------------------------------------------------------------------

class TestGetBoundingBoxThickness(unittest.TestCase):

    def _run(self, box_metres):
        """Run get_bounding_box_thickness with sheet metal path disabled (returns None)."""
        from solidworks import get_bounding_box_thickness
        model_doc = MagicMock()
        part_mock = MagicMock()
        part_mock.GetPartBox.return_value = box_metres
        with patch("solidworks._wrap", return_value=part_mock), \
             patch("solidworks._get_sheet_metal_thickness", return_value=None):
            return get_bounding_box_thickness(model_doc)

    def test_returns_smallest_dimension_mm(self):
        # 200 x 100 x 5 mm box
        result = self._run((0.0, 0.0, 0.0, 0.200, 0.100, 0.005))
        self.assertEqual(result, 5.0)

    def test_rounds_to_2_decimal_places(self):
        # 3.33333... mm thin
        result = self._run((0.0, 0.0, 0.0, 0.200, 0.100, 0.00333333))
        self.assertEqual(result, 3.33)

    def test_square_box_returns_side(self):
        # 50 x 50 x 50 mm cube → min = 50
        result = self._run((0.0, 0.0, 0.0, 0.05, 0.05, 0.05))
        self.assertEqual(result, 50.0)

    def test_returns_none_on_exception(self):
        from solidworks import get_bounding_box_thickness
        model_doc = MagicMock()
        with patch("solidworks._get_sheet_metal_thickness", return_value=None), \
             patch("solidworks._wrap", side_effect=Exception("COM error")):
            result = get_bounding_box_thickness(model_doc)
        self.assertIsNone(result)

    def test_wrap_called_with_ipartdoc(self):
        from solidworks import get_bounding_box_thickness
        model_doc = MagicMock()
        part_mock = MagicMock()
        part_mock.GetPartBox.return_value = (0.0, 0.0, 0.0, 0.1, 0.1, 0.005)
        with patch("solidworks._get_sheet_metal_thickness", return_value=None), \
             patch("solidworks._wrap", return_value=part_mock) as mock_wrap:
            get_bounding_box_thickness(model_doc)
        mock_wrap.assert_called_once_with(model_doc, "IPartDoc")

    def test_sheet_metal_thickness_preferred_over_bbox(self):
        """Sheet metal feature thickness takes priority over bounding box minimum."""
        from solidworks import get_bounding_box_thickness
        model_doc = MagicMock()
        with patch("solidworks._get_sheet_metal_thickness", return_value=3.0):
            result = get_bounding_box_thickness(model_doc)
        self.assertEqual(result, 3.0)

    def test_bbox_used_when_sheet_metal_returns_none(self):
        """Falls back to bounding box when part is not sheet metal."""
        from solidworks import get_bounding_box_thickness
        model_doc = MagicMock()
        part_mock = MagicMock()
        part_mock.GetPartBox.return_value = (0.0, 0.0, 0.0, 0.200, 0.100, 0.005)
        with patch("solidworks._get_sheet_metal_thickness", return_value=None), \
             patch("solidworks._wrap", return_value=part_mock):
            result = get_bounding_box_thickness(model_doc)
        self.assertEqual(result, 5.0)


# ---------------------------------------------------------------------------
# get_part_data
# ---------------------------------------------------------------------------

class TestGetPartData(unittest.TestCase):

    def _make_component(self, path, props):
        mgr = MagicMock()
        def _get4(name, flag):
            return (0, f"raw_{name}", props.get(name, ""), True)
        mgr.Get4.side_effect = _get4
        ext = MagicMock()
        ext.CustomPropertyManager.return_value = mgr
        doc = MagicMock()
        doc.Extension = ext
        comp = MagicMock()
        comp.GetPathName.return_value = path
        comp.IsSuppressed.return_value = False
        comp.GetModelDoc2.return_value = doc
        return comp

    def test_returns_all_expected_keys(self):
        from solidworks import get_part_data
        comp = self._make_component("C:\\parts\\12624.100.001.SLDPRT", {
            "Description": "Chapa Base", "Corte_Fabrico": "LASER",
            "Simetria": "", "Material": "S235JR", "TratSuperficial": "Pintar"
        })
        with patch("solidworks.get_bounding_box_thickness", return_value=3.0):
            result = get_part_data(comp, [comp])
        expected_keys = {"qty", "part_number", "Description", "Corte_Fabrico",
                         "Simetria", "Material", "TratSuperficial", "espessura"}
        self.assertEqual(set(result.keys()), expected_keys)

    def test_qty_counts_instances(self):
        from solidworks import get_part_data
        path = "C:\\parts\\12624.100.001.SLDPRT"
        comp = self._make_component(path, {})
        comp2 = self._make_component(path, {})
        comp2.GetModelDoc2.return_value = comp.GetModelDoc2()
        with patch("solidworks.get_bounding_box_thickness", return_value=None):
            result = get_part_data(comp, [comp, comp2])
        self.assertEqual(result["qty"], 2)

    def test_part_number_strips_extension(self):
        from solidworks import get_part_data
        comp = self._make_component("C:\\parts\\12624.100.001.SLDPRT", {})
        with patch("solidworks.get_bounding_box_thickness", return_value=None):
            result = get_part_data(comp, [comp])
        self.assertEqual(result["part_number"], "12624.100.001")

    def test_espessura_none_when_bbox_unavailable(self):
        from solidworks import get_part_data
        comp = self._make_component("C:\\parts\\part.SLDPRT", {})
        with patch("solidworks.get_bounding_box_thickness", return_value=None):
            result = get_part_data(comp, [comp])
        self.assertIsNone(result["espessura"])

    def test_properties_populated_from_evaluated_values(self):
        from solidworks import get_part_data
        comp = self._make_component("C:\\parts\\part.SLDPRT", {
            "Material": "Cast Alloy Steel",
            "TratSuperficial": "Anodizar",
        })
        with patch("solidworks.get_bounding_box_thickness", return_value=5.0):
            result = get_part_data(comp, [comp])
        self.assertEqual(result["Material"], "Cast Alloy Steel")
        self.assertEqual(result["TratSuperficial"], "Anodizar")

    def test_sw_material_expression_resolved_via_get_part_material(self):
        """When Get4 returns SW-Material expression, _get_part_material is called."""
        from solidworks import get_part_data
        # Material prop returns the SW expression (Get4 did not resolve it)
        comp = self._make_component("C:\\parts\\part.SLDPRT", {
            "Material": "SW-Material@part.SLDPRT",
        })
        with patch("solidworks.get_bounding_box_thickness", return_value=3.0), \
             patch("solidworks._get_part_material", return_value="S235JR"):
            result = get_part_data(comp, [comp])
        self.assertEqual(result["Material"], "S235JR")

    def test_sw_material_expression_with_literal_quotes_resolved(self):
        """SW wraps raw expressions in literal quotes: '"SW-Material@part.SLDPRT"'.
        get_part_data must strip the quotes before the regex match so that
        _get_part_material is still called."""
        from solidworks import get_part_data
        # Simulate what SW actually returns: Get4 raw has literal quote chars
        comp = self._make_component("C:\\parts\\part.SLDPRT", {})
        with patch("solidworks.get_bounding_box_thickness", return_value=3.0), \
             patch("solidworks.get_custom_property_evaluated",
                   side_effect=lambda doc, prop: (
                       '"SW-Material@part.SLDPRT"' if prop == "Material" else ""
                   )), \
             patch("solidworks._get_part_material", return_value="S235JR"):
            result = get_part_data(comp, [comp])
        self.assertEqual(result["Material"], "S235JR")

    def test_sw_expr_in_non_material_prop_returns_empty(self):
        """SW expression in non-Material property → empty string (shouldn't occur)."""
        from solidworks import get_part_data
        comp = self._make_component("C:\\parts\\part.SLDPRT", {
            "Simetria": "SW-Something@part.SLDPRT",
        })
        with patch("solidworks.get_bounding_box_thickness", return_value=None):
            result = get_part_data(comp, [comp])
        self.assertEqual(result["Simetria"], "")


# ---------------------------------------------------------------------------
# BomComponent helper: _make_bom_comp
# ---------------------------------------------------------------------------

def _make_bom_comp(path, comp_type="producao"):
    """Build a minimal BomComponent for testing."""
    from solidworks import BomComponent
    comp = MagicMock()
    return BomComponent(comp, path, comp_type)


# ---------------------------------------------------------------------------
# count_bom_instances
# ---------------------------------------------------------------------------

class TestCountBomInstances(unittest.TestCase):

    def test_counts_three_matching(self):
        from solidworks import count_bom_instances
        path = "C:\\parts\\18026.100.001.SLDPRT"
        bom_flat = [_make_bom_comp(path)] * 3 + [_make_bom_comp("C:\\parts\\18026.200.001.SLDPRT")]
        self.assertEqual(count_bom_instances(bom_flat, path), 3)

    def test_case_insensitive(self):
        from solidworks import count_bom_instances
        bom_flat = [_make_bom_comp("C:\\Parts\\Part_A.SLDPRT")]
        self.assertEqual(count_bom_instances(bom_flat, "c:\\parts\\part_a.sldprt"), 1)

    def test_no_match_returns_zero(self):
        from solidworks import count_bom_instances
        bom_flat = [_make_bom_comp("C:\\parts\\18026.200.001.SLDPRT")]
        self.assertEqual(count_bom_instances(bom_flat, "C:\\parts\\18026.100.001.SLDPRT"), 0)

    def test_empty_list(self):
        from solidworks import count_bom_instances
        self.assertEqual(count_bom_instances([], "C:\\parts\\x.SLDPRT"), 0)


# ---------------------------------------------------------------------------
# deduplicate_bom_by_path
# ---------------------------------------------------------------------------

class TestDeduplicateBomByPath(unittest.TestCase):

    def test_five_with_two_dupes_yields_three(self):
        from solidworks import deduplicate_bom_by_path
        path_a = "C:\\parts\\18026.100.001.SLDPRT"
        path_b = "C:\\parts\\18026.100.002.SLDPRT"
        path_c = "C:\\parts\\18026.200.001.SLDPRT"
        bom_flat = [
            _make_bom_comp(path_a),
            _make_bom_comp(path_b),
            _make_bom_comp(path_a),  # dupe
            _make_bom_comp(path_c),
            _make_bom_comp(path_b),  # dupe
        ]
        result = deduplicate_bom_by_path(bom_flat)
        self.assertEqual(len(result), 3)

    def test_preserves_first_occurrence(self):
        from solidworks import deduplicate_bom_by_path
        path = "C:\\parts\\18026.100.001.SLDPRT"
        first  = _make_bom_comp(path, comp_type="producao")
        second = _make_bom_comp(path, comp_type="comercial")
        result = deduplicate_bom_by_path([first, second])
        self.assertEqual(result[0].comp_type, "producao")

    def test_case_insensitive_dedup(self):
        from solidworks import deduplicate_bom_by_path
        result = deduplicate_bom_by_path([
            _make_bom_comp("C:\\Parts\\A.SLDPRT"),
            _make_bom_comp("c:\\parts\\a.sldprt"),
        ])
        self.assertEqual(len(result), 1)

    def test_empty_list(self):
        from solidworks import deduplicate_bom_by_path
        self.assertEqual(deduplicate_bom_by_path([]), [])


# ---------------------------------------------------------------------------
# SW instance suffix strip (pure Python, no mocking)
# ---------------------------------------------------------------------------

class TestSuffixStrip(unittest.TestCase):

    def test_strips_dash_n(self):
        import re
        self.assertEqual(re.sub(r'-\d+$', '', '18026.100.001-3'), '18026.100.001')

    def test_strips_dash_1(self):
        import re
        self.assertEqual(re.sub(r'-\d+$', '', '18026.800.001-1'), '18026.800.001')

    def test_no_suffix_unchanged(self):
        import re
        self.assertEqual(re.sub(r'-\d+$', '', '18026.100.001'), '18026.100.001')

    def test_ignores_non_trailing_number(self):
        import re
        self.assertEqual(re.sub(r'-\d+$', '', 'PART-A'), 'PART-A')


# ---------------------------------------------------------------------------
# _bom_traverse (mocked COM)
# ---------------------------------------------------------------------------

def _make_traversal_comp(path, doc_type, suppressed=False, children=None,
                         model_none=False):
    """
    Build a mock IComponent2 for _bom_traverse tests.
    doc_type: 1=swDocPART, 2=swDocASSEMBLY
    suppressed=True  -> GetSuppression returns 0 (swComponentSuppressed)
    suppressed=False -> GetSuppression returns 4 (swComponentFullyResolved)
    model_none=True  -> GetModelDoc2 returns None (lightweight/unloaded component)
    """
    model = MagicMock()
    model.GetType = doc_type   # attribute, not callable
    comp = MagicMock()
    comp.GetSuppression.return_value = 0 if suppressed else 4
    comp.GetModelDoc2.return_value = None if model_none else model
    comp.GetPathName.return_value = path
    comp.GetChildren.return_value = children or []
    return comp


@patch("solidworks._wrap", side_effect=lambda obj, _iface: obj)
class TestBomTraverse(unittest.TestCase):

    def test_group_100_part_appended_as_producao(self, _wrap):
        from solidworks import _bom_traverse
        comp = _make_traversal_comp("C:\\parts\\18026.100.001.SLDPRT", doc_type=1)
        bom_flat, warnings = [], []
        _bom_traverse(comp, bom_flat, warnings)
        self.assertEqual(len(bom_flat), 1)
        self.assertEqual(bom_flat[0].comp_type, "producao")
        self.assertEqual(warnings, [])

    def test_group_800_appended_as_comercial_children_not_traversed(self, _wrap):
        from solidworks import _bom_traverse
        child = _make_traversal_comp("C:\\parts\\18026.800.099.SLDPRT", doc_type=1)
        comp = _make_traversal_comp(
            "C:\\parts\\18026.800.001.SLDASM", doc_type=2, children=[child])
        bom_flat, warnings = [], []
        _bom_traverse(comp, bom_flat, warnings)
        self.assertEqual(len(bom_flat), 1)
        self.assertEqual(bom_flat[0].comp_type, "comercial")

    def test_suppressed_component_skipped(self, _wrap):
        from solidworks import _bom_traverse
        comp = _make_traversal_comp(
            "C:\\parts\\18026.100.002.SLDPRT", doc_type=1, suppressed=True)
        bom_flat, warnings = [], []
        _bom_traverse(comp, bom_flat, warnings)
        self.assertEqual(bom_flat, [])
        self.assertEqual(warnings, [])

    def test_unrecognized_basename_adds_warning(self, _wrap):
        from solidworks import _bom_traverse
        comp = _make_traversal_comp("C:\\parts\\VENDOR_PART.SLDPRT", doc_type=1)
        bom_flat, warnings = [], []
        _bom_traverse(comp, bom_flat, warnings)
        self.assertEqual(bom_flat, [])
        self.assertEqual(len(warnings), 1)
        self.assertIn("VENDOR_PART", warnings[0])

    def test_assembly_group_100_recurses_into_children(self, _wrap):
        from solidworks import _bom_traverse
        child = _make_traversal_comp("C:\\parts\\18026.100.002.SLDPRT", doc_type=1)
        parent = _make_traversal_comp(
            "C:\\parts\\18026.100.001.SLDASM", doc_type=2, children=[child])
        bom_flat, warnings = [], []
        _bom_traverse(parent, bom_flat, warnings)
        self.assertEqual(len(bom_flat), 1)
        self.assertEqual(bom_flat[0].comp_type, "producao")

    def test_suffix_stripped_before_group_parse(self, _wrap):
        from solidworks import _bom_traverse
        comp = _make_traversal_comp("C:\\parts\\18026.100.001-3.SLDPRT", doc_type=1)
        bom_flat, warnings = [], []
        _bom_traverse(comp, bom_flat, warnings)
        self.assertEqual(len(bom_flat), 1)
        self.assertEqual(bom_flat[0].comp_type, "producao")
        self.assertEqual(warnings, [])

    def test_lightweight_not_skipped(self, _wrap):
        """Lightweight components (GetSuppression=1) must not be skipped — SW 2024 bug:
        IsSuppressed returns True for lightweight, but they appear active in Feature Tree."""
        from solidworks import _bom_traverse
        comp = _make_traversal_comp("C:\\parts\\18026.100.001.SLDPRT", doc_type=1)
        comp.GetSuppression.return_value = 1  # lightweight, not suppressed
        bom_flat, warnings = [], []
        _bom_traverse(comp, bom_flat, warnings)
        self.assertEqual(len(bom_flat), 1)

    def test_organizer_assembly_nonstandard_name_recurses_into_children(self, _wrap):
        """Organizer sub-assemblies with non-standard names (e.g. '15024 conj 200')
        must still be recursed into — their children (groups 200/210/500) must appear."""
        from solidworks import _bom_traverse
        child = _make_traversal_comp("C:\\parts\\15.200.001.SLDPRT", doc_type=1)
        parent = _make_traversal_comp(
            "C:\\parts\\15024 conj 200.SLDASM", doc_type=2, children=[child])
        bom_flat, warnings = [], []
        _bom_traverse(parent, bom_flat, warnings)
        self.assertEqual(len(bom_flat), 1)
        self.assertEqual(bom_flat[0].comp_type, "producao")
        self.assertEqual(warnings, [])

    def test_three_letter_prefix_appended_as_comercial(self, _wrap):
        """Parts named BOS.040.001, IFM.010.007, SIC.050.001 (3-letter prefix)
        must be classified as comercial — goes to Material Mecânico."""
        from solidworks import _bom_traverse
        for name in ("BOS.040.001", "IFM.010.007", "SIC.050.001"):
            with self.subTest(name=name):
                comp = _make_traversal_comp(
                    f"C:\\parts\\{name}.SLDPRT", doc_type=1)
                bom_flat, warnings = [], []
                _bom_traverse(comp, bom_flat, warnings)
                self.assertEqual(len(bom_flat), 1, f"{name} should be appended")
                self.assertEqual(bom_flat[0].comp_type, "comercial")
                self.assertEqual(warnings, [])

    def test_unrecognized_part_name_still_warns(self, _wrap):
        """Non-standard part names (not 3-letter prefix) must still warn and skip."""
        from solidworks import _bom_traverse
        comp = _make_traversal_comp("C:\\parts\\VENDOR_PART_EXTRA.SLDPRT", doc_type=1)
        bom_flat, warnings = [], []
        _bom_traverse(comp, bom_flat, warnings)
        self.assertEqual(bom_flat, [])
        self.assertEqual(len(warnings), 1)

    def test_lightweight_assembly_model_none_recurses_into_children(self, _wrap):
        """Sub-assemblies with model=None (lightweight/unloaded in SW) must still
        be recursed into via GetChildren — this is the root cause of groups 200/210/500
        being missing when the assembly was opened with lightweight sub-assemblies."""
        from solidworks import _bom_traverse
        child = _make_traversal_comp("C:\\parts\\15024.200.038.SLDPRT", doc_type=1)
        parent = _make_traversal_comp(
            "C:\\parts\\15024.200.900.SLDASM", doc_type=2,
            children=[child], model_none=True)
        bom_flat, warnings = [], []
        _bom_traverse(parent, bom_flat, warnings)
        self.assertEqual(len(bom_flat), 1)
        self.assertEqual(bom_flat[0].comp_type, "producao")

    def test_lightweight_part_model_none_classified_by_name(self, _wrap):
        """Parts with model=None (lightweight) are classified by filename and added to
        bom_flat — so custom properties can be attempted later via SetComponentState."""
        from solidworks import _bom_traverse
        comp = _make_traversal_comp(
            "C:\\parts\\15024.200.001.SLDPRT", doc_type=1, model_none=True)
        bom_flat, warnings = [], []
        _bom_traverse(comp, bom_flat, warnings)
        self.assertEqual(len(bom_flat), 1)
        self.assertEqual(bom_flat[0].comp_type, "producao")


# ---------------------------------------------------------------------------
# get_weldment_cut_list
# ---------------------------------------------------------------------------

class TestGetWeldmentCutList(unittest.TestCase):
    """Mocked COM tests for get_weldment_cut_list. No SW running required."""

    def _make_cut_feat(self, desc="Profile A", length="350.0", qty="2", suppressed=False):
        feat = MagicMock()
        feat.GetTypeName2.return_value = "CutListFolder"
        feat.IsSuppressed = suppressed  # non-callable (property-style, SW 2024 early binding)
        feat.Name = f"CutList<{desc}>"
        props = {"DESCRIPTION": desc, "LENGTH": length, "QUANTITY": qty}
        mgr = MagicMock()
        mgr.Get4.side_effect = lambda prop, cached: (0, props.get(prop, ""), props.get(prop, ""), True)
        feat.CustomPropertyManager = mgr
        feat.GetNextFeature.return_value = None
        return feat

    def _wrap_side(self, mock_part):
        def side(obj, iface):
            return mock_part if iface == "IPartDoc" else obj
        return side

    @patch("solidworks._open_doc")
    @patch("solidworks._wrap")
    def test_reads_cut_list_item(self, mock_wrap, mock_open_doc):
        from solidworks import get_weldment_cut_list
        feat = self._make_cut_feat("Aluminium profile 40x40", "350.0", "2")
        mock_doc = MagicMock()
        mock_open_doc.return_value = mock_doc
        mock_part = MagicMock()
        mock_part.FirstFeature.return_value = feat
        mock_wrap.side_effect = self._wrap_side(mock_part)
        items, warnings = get_weldment_cut_list(MagicMock(), "C:\\parts\\part.sldprt")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].description, "Aluminium profile 40x40")
        self.assertAlmostEqual(items[0].length_mm, 350.0)
        self.assertEqual(items[0].qty, 2)
        self.assertEqual(warnings, [])

    @patch("solidworks._open_doc")
    @patch("solidworks._wrap")
    def test_skips_suppressed_folder(self, mock_wrap, mock_open_doc):
        from solidworks import get_weldment_cut_list
        feat = self._make_cut_feat(suppressed=True)
        mock_doc = MagicMock()
        mock_open_doc.return_value = mock_doc
        mock_part = MagicMock()
        mock_part.FirstFeature.return_value = feat
        mock_wrap.side_effect = self._wrap_side(mock_part)
        items, _ = get_weldment_cut_list(MagicMock(), "C:\\parts\\part.sldprt")
        self.assertEqual(items, [])

    @patch("solidworks._open_doc")
    @patch("solidworks._wrap")
    def test_quantity_fallback_to_qty_key(self, mock_wrap, mock_open_doc):
        from solidworks import get_weldment_cut_list
        feat = MagicMock()
        feat.GetTypeName2.return_value = "CutListFolder"
        feat.IsSuppressed = False
        feat.Name = "CutList"
        props = {"DESCRIPTION": "Profile A", "LENGTH": "100.0", "QUANTITY": "", "QTY": "3"}
        mgr = MagicMock()
        mgr.Get4.side_effect = lambda prop, cached: (0, props.get(prop, ""), props.get(prop, ""), True)
        feat.CustomPropertyManager = mgr
        feat.GetNextFeature.return_value = None
        mock_doc = MagicMock()
        mock_open_doc.return_value = mock_doc
        mock_part = MagicMock()
        mock_part.FirstFeature.return_value = feat
        mock_wrap.side_effect = self._wrap_side(mock_part)
        items, warnings = get_weldment_cut_list(MagicMock(), "C:\\parts\\part.sldprt")
        self.assertEqual(items[0].qty, 3)
        self.assertEqual(warnings, [])

    @patch("solidworks._open_doc")
    @patch("solidworks._wrap")
    def test_quantity_defaults_to_1_and_warns(self, mock_wrap, mock_open_doc):
        from solidworks import get_weldment_cut_list
        feat = MagicMock()
        feat.GetTypeName2.return_value = "CutListFolder"
        feat.IsSuppressed = False
        feat.Name = "CutListItem1"
        props = {"DESCRIPTION": "Profile A", "LENGTH": "100.0"}
        mgr = MagicMock()
        mgr.Get4.side_effect = lambda prop, cached: (0, props.get(prop, ""), props.get(prop, ""), True)
        feat.CustomPropertyManager = mgr
        feat.GetNextFeature.return_value = None
        mock_doc = MagicMock()
        mock_open_doc.return_value = mock_doc
        mock_part = MagicMock()
        mock_part.FirstFeature.return_value = feat
        mock_wrap.side_effect = self._wrap_side(mock_part)
        items, warnings = get_weldment_cut_list(MagicMock(), "C:\\parts\\part.sldprt")
        self.assertEqual(items[0].qty, 1)
        self.assertTrue(any("QUANTITY/QTY" in w for w in warnings))

    @patch("solidworks._open_doc")
    @patch("solidworks._wrap")
    def test_close_doc_called_in_finally(self, mock_wrap, mock_open_doc):
        from solidworks import get_weldment_cut_list
        mock_sw = MagicMock()
        mock_doc = MagicMock()
        mock_open_doc.return_value = mock_doc
        mock_part = MagicMock()
        mock_part.FirstFeature.return_value = None
        mock_wrap.side_effect = self._wrap_side(mock_part)
        get_weldment_cut_list(mock_sw, "C:\\parts\\part.sldprt")
        mock_sw.CloseDoc.assert_called_once()

    @patch("solidworks._open_doc")
    @patch("solidworks._wrap")
    def test_capping_expands_rows_different_states(self, mock_wrap, mock_open_doc):
        """3 bodies with capping states [2,1,0] -> 3 separate rows.

        Geometry (all 1000 mm along X, different Y bands):
          b0 @ y=0:   bbox (0, -0.02, -0.02, 1.0, 0.02, 0.02)  test1=(1.0001,0,0)  test2=(-0.0001,0,0)
          b1 @ y=0.1: bbox (0, 0.08, -0.02, 1.0, 0.12, 0.02)   test1=(1.0001,0.1,0) test2=(-0.0001,0.1,0)
          b2 @ y=0.2: bbox (0, 0.18, -0.02, 1.0, 0.22, 0.02)   test1=(1.0001,0.2,0) test2=(-0.0001,0.2,0)

          cap_both: (-0.05, -0.04, -0.04, 1.05, 0.04, 0.04)  — covers both ends of b0 only
          cap_one:  ( 0.95,  0.06, -0.04, 1.05, 0.14, 0.04)  — covers test1 of b1 only
        """
        from solidworks import get_weldment_cut_list
        feat = self._make_cut_feat("Profile A", "1000.0", "3")
        mock_doc = MagicMock()
        mock_open_doc.return_value = mock_doc
        mock_part = MagicMock()
        mock_part.FirstFeature.return_value = feat

        b0 = MagicMock()
        b0.GetBodyBox.return_value = (0.0, -0.02, -0.02, 1.0, 0.02, 0.02)
        b1 = MagicMock()
        b1.GetBodyBox.return_value = (0.0, 0.08, -0.02, 1.0, 0.12, 0.02)
        b2 = MagicMock()
        b2.GetBodyBox.return_value = (0.0, 0.18, -0.02, 1.0, 0.22, 0.02)

        # cap_both: covers both test points of b0 (y~0); ymax=0.04 < 0.1 keeps b1/b2 free
        cap_both = MagicMock()
        cap_both.GetBodyBox.return_value = (-0.05, -0.04, -0.04, 1.05, 0.04, 0.04)

        # cap_one: covers test1 of b1 (x~1.0, y~0.1); xmin=0.95 keeps left end of b1 free
        cap_one = MagicMock()
        cap_one.GetBodyBox.return_value = (0.95, 0.06, -0.04, 1.05, 0.14, 0.04)

        mock_part.GetBodies2.return_value = [b0, b1, b2, cap_both, cap_one]
        mock_wrap.side_effect = self._wrap_side(mock_part)

        items, _warnings = get_weldment_cut_list(MagicMock(), "C:\\parts\\p.sldprt")

        descs = {it.description for it in items}
        self.assertIn("Profile A D17/D17", descs)
        self.assertIn("Profile A D17", descs)
        self.assertIn("Profile A", descs)
        total_qty = sum(it.qty for it in items)
        self.assertEqual(total_qty, 3)
        for it in items:
            self.assertEqual(it.qty, 1)

    @patch("solidworks._open_doc")
    @patch("solidworks._wrap")
    def test_capping_same_state_aggregates_qty(self, mock_wrap, mock_open_doc):
        """2 bodies, both capped on both ends -> 1 row with qty=2.

        Geometry (all 500 mm along X):
          b0 @ y=0:    bbox (0, -0.02, -0.02, 0.5, 0.02, 0.02)
          b1 @ y=0.08: bbox (0, 0.06, -0.02, 0.5, 0.10, 0.02)
          capper:           (-0.05, -0.05, -0.05, 0.55, 0.12, 0.05) covers both ends of both bodies
        """
        from solidworks import get_weldment_cut_list
        feat = self._make_cut_feat("Profile B", "500.0", "2")
        mock_doc = MagicMock()
        mock_open_doc.return_value = mock_doc
        mock_part = MagicMock()
        mock_part.FirstFeature.return_value = feat

        b0 = MagicMock()
        b0.GetBodyBox.return_value = (0.0, -0.02, -0.02, 0.5, 0.02, 0.02)
        b1 = MagicMock()
        b1.GetBodyBox.return_value = (0.0, 0.06, -0.02, 0.5, 0.10, 0.02)
        capper = MagicMock()
        capper.GetBodyBox.return_value = (-0.05, -0.05, -0.05, 0.55, 0.12, 0.05)

        mock_part.GetBodies2.return_value = [b0, b1, capper]
        mock_wrap.side_effect = self._wrap_side(mock_part)

        items, _ = get_weldment_cut_list(MagicMock(), "C:\\parts\\p.sldprt")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].description, "Profile B D17/D17")
        self.assertEqual(items[0].qty, 2)

    @patch("solidworks._open_doc")
    @patch("solidworks._wrap")
    def test_capping_detection_failure_returns_raw_items(self, mock_wrap, mock_open_doc):
        """If GetBodies2 raises, raw items are returned unchanged."""
        from solidworks import get_weldment_cut_list
        feat = self._make_cut_feat("Profile C", "300.0", "1")
        mock_doc = MagicMock()
        mock_open_doc.return_value = mock_doc
        mock_part = MagicMock()
        mock_part.FirstFeature.return_value = feat
        mock_part.GetBodies2.side_effect = Exception("COM error")
        mock_wrap.side_effect = self._wrap_side(mock_part)

        items, warnings = get_weldment_cut_list(MagicMock(), "C:\\parts\\p.sldprt")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].description, "Profile C")
        self.assertTrue(any("Capping detection" in w for w in warnings))

    @patch("solidworks._open_doc")
    @patch("solidworks._wrap")
    def test_getbodies2_returns_tuple_unwrapped(self, mock_wrap, mock_open_doc):
        """GetBodies2 returning a tuple is correctly unwrapped."""
        from solidworks import get_weldment_cut_list
        feat = self._make_cut_feat("Profile D", "200.0", "1")
        mock_doc = MagicMock()
        mock_open_doc.return_value = mock_doc
        mock_part = MagicMock()
        mock_part.FirstFeature.return_value = feat
        body = MagicMock()
        body.GetBodyBox.return_value = (0.0, -0.01, -0.01, 0.2, 0.01, 0.01)
        body._oleobj_ = None
        body.ContainsPoint.return_value = 0
        mock_part.GetBodies2.return_value = (body,)  # tuple, not list
        mock_wrap.side_effect = self._wrap_side(mock_part)

        items, _ = get_weldment_cut_list(MagicMock(), "C:\\parts\\p.sldprt")
        self.assertEqual(len(items), 1)
        # No capping -> description unchanged
        self.assertEqual(items[0].description, "Profile D")


# ---------------------------------------------------------------------------
# _normalize_corte
# ---------------------------------------------------------------------------

class TestNormalizeCorte(unittest.TestCase):

    def test_strips_accent_from_i(self):
        from solidworks import _normalize_corte
        self.assertEqual(_normalize_corte("PERFIL ALUMÍNIO"), "perfil aluminio")

    def test_already_unaccented_unchanged(self):
        from solidworks import _normalize_corte
        self.assertEqual(_normalize_corte("PERFIL ALUMINIO"), "perfil aluminio")

    def test_lowercases(self):
        from solidworks import _normalize_corte
        self.assertEqual(_normalize_corte("ABC"), "abc")


# ---------------------------------------------------------------------------
# is_perfil_aluminio
# ---------------------------------------------------------------------------

def _make_perfil_comp(corte_fabrico_value):
    """Create a mock component whose GetModelDoc2 returns a mock model
    with GetCustomPropertyManager("").Get returning corte_fabrico_value."""
    mgr = MagicMock()
    mgr.Get.return_value = corte_fabrico_value
    mgr.Get4.side_effect = Exception("not used")
    model = MagicMock()
    model.Extension.CustomPropertyManager.return_value = mgr
    comp = MagicMock()
    comp.GetModelDoc2.return_value = model
    return comp


class TestIsPerfisAluminio(unittest.TestCase):

    def test_uppercase_no_accent_matches(self):
        from solidworks import is_perfil_aluminio
        comp = _make_perfil_comp("PERFIL ALUMINIO")
        self.assertTrue(is_perfil_aluminio(comp))

    def test_uppercase_with_accent_matches(self):
        from solidworks import is_perfil_aluminio
        comp = _make_perfil_comp("PERFIL ALUMÍNIO")
        self.assertTrue(is_perfil_aluminio(comp))

    def test_mixed_case_matches(self):
        from solidworks import is_perfil_aluminio
        comp = _make_perfil_comp("Perfil Alumínio")
        self.assertTrue(is_perfil_aluminio(comp))

    def test_laser_does_not_match(self):
        from solidworks import is_perfil_aluminio
        comp = _make_perfil_comp("LASER")
        self.assertFalse(is_perfil_aluminio(comp))

    def test_empty_does_not_match(self):
        from solidworks import is_perfil_aluminio
        comp = _make_perfil_comp("")
        self.assertFalse(is_perfil_aluminio(comp))

    def test_none_model_does_not_match(self):
        from solidworks import is_perfil_aluminio
        comp = MagicMock()
        comp.GetModelDoc2.return_value = None
        self.assertFalse(is_perfil_aluminio(comp))


# ---------------------------------------------------------------------------
# _contains_point
# ---------------------------------------------------------------------------

class TestContainsPoint(unittest.TestCase):

    def test_early_binding_returns_true(self):
        from solidworks import _contains_point
        body = MagicMock()
        body.ContainsPoint.return_value = 1  # SW returns non-zero int for True
        self.assertTrue(_contains_point(body, 0.0, 0.0, 0.0))

    def test_early_binding_returns_false(self):
        from solidworks import _contains_point
        body = MagicMock()
        body.ContainsPoint.return_value = 0
        self.assertFalse(_contains_point(body, 0.0, 0.0, 0.0))

    @patch("win32com.client.Dispatch")
    def test_late_binding_fallback_when_early_raises(self, mock_dispatch):
        from solidworks import _contains_point
        body = MagicMock()
        body.ContainsPoint.side_effect = AttributeError("no attribute")
        body._oleobj_ = MagicMock()
        late = MagicMock()
        late.ContainsPoint.return_value = 1
        mock_dispatch.return_value = late
        self.assertTrue(_contains_point(body, 1.0, 2.0, 3.0))
        late.ContainsPoint.assert_called_once_with(1.0, 2.0, 3.0)

    def test_returns_false_when_both_paths_fail(self):
        from solidworks import _contains_point
        body = MagicMock()
        body.ContainsPoint.side_effect = Exception("fail")
        body._oleobj_ = None
        body._dispobj_ = None
        self.assertFalse(_contains_point(body, 0.0, 0.0, 0.0))


# ---------------------------------------------------------------------------
# _get_sketch_directions
# ---------------------------------------------------------------------------

class TestGetSketchDirections(unittest.TestCase):

    def _make_sketch_feat(self, segments):
        """Build a mock 3DSketch IFeature with given (start, end) mm tuples."""
        feat = MagicMock()
        feat.GetTypeName2.return_value = "3DSketch"
        sketch = MagicMock()
        mock_segs = []
        for (sx, sy, sz), (ex, ey, ez) in segments:
            seg = MagicMock()
            p1, p2 = MagicMock(), MagicMock()
            p1.X, p1.Y, p1.Z = sx, sy, sz
            p2.X, p2.Y, p2.Z = ex, ey, ez
            seg.GetStartPoint2.return_value = p1
            seg.GetEndPoint2.return_value = p2
            mock_segs.append(seg)
        sketch.GetSketchSegments.return_value = mock_segs
        feat.GetSpecificFeature2.return_value = sketch
        feat.GetNextFeature.return_value = None
        return feat

    @patch("solidworks._wrap")
    def test_returns_line_endpoints_from_sketch(self, mock_wrap):
        from solidworks import _get_sketch_directions
        sketch_feat = self._make_sketch_feat([
            ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
        ])
        mock_part = MagicMock()
        mock_part.FirstFeature.return_value = sketch_feat
        mock_wrap.side_effect = lambda obj, iface: obj  # passthrough
        lines = _get_sketch_directions(mock_part)
        self.assertEqual(len(lines), 1)
        np.testing.assert_allclose(lines[0][0], [0.0, 0.0, 0.0])
        np.testing.assert_allclose(lines[0][1], [1.0, 0.0, 0.0])

    @patch("solidworks._wrap")
    def test_skips_zero_length_segments(self, mock_wrap):
        from solidworks import _get_sketch_directions
        sketch_feat = self._make_sketch_feat([
            ((0.5, 0.5, 0.5), (0.5, 0.5, 0.5)),  # zero-length
        ])
        mock_part = MagicMock()
        mock_part.FirstFeature.return_value = sketch_feat
        mock_wrap.side_effect = lambda obj, iface: obj
        lines = _get_sketch_directions(mock_part)
        self.assertEqual(lines, [])

    @patch("solidworks._wrap")
    def test_returns_empty_when_no_3dsketch(self, mock_wrap):
        from solidworks import _get_sketch_directions
        feat = MagicMock()
        feat.GetTypeName2.return_value = "BaseFlangeFeature"
        feat.GetNextFeature.return_value = None
        mock_part = MagicMock()
        mock_part.FirstFeature.return_value = feat
        mock_wrap.side_effect = lambda obj, iface: obj
        lines = _get_sketch_directions(mock_part)
        self.assertEqual(lines, [])


# ---------------------------------------------------------------------------
# _match_body_to_direction
# ---------------------------------------------------------------------------

class TestMatchBodyToDirection(unittest.TestCase):

    def _make_body(self, xmin, ymin, zmin, xmax, ymax, zmax):
        body = MagicMock()
        body.GetBodyBox.return_value = (xmin, ymin, zmin, xmax, ymax, zmax)
        return body

    def test_axis_aligned_horizontal(self):
        from solidworks import _match_body_to_direction
        # 1000 mm profile along X axis
        body = self._make_body(-0.5, -0.02, -0.02, 0.5, 0.02, 0.02)
        sketch_lines = [(np.array([-0.5, 0.0, 0.0]), np.array([0.5, 0.0, 0.0]))]
        center, axis = _match_body_to_direction(body, sketch_lines)
        np.testing.assert_allclose(center, [0.0, 0.0, 0.0], atol=1e-9)
        np.testing.assert_allclose(np.abs(axis), [1.0, 0.0, 0.0], atol=1e-6)

    def test_angled_45_degrees(self):
        from solidworks import _match_body_to_direction
        # 1000 mm profile at 45° in XY plane (0,0,0) → (0.707, 0.707, 0)
        d = 0.707
        body = self._make_body(0.0, 0.0, -0.02, d, d, 0.02)
        sketch_lines = [(np.array([0.0, 0.0, 0.0]), np.array([d, d, 0.0]))]
        center, axis = _match_body_to_direction(body, sketch_lines)
        expected_axis = np.array([1.0, 1.0, 0.0]) / np.sqrt(2)
        np.testing.assert_allclose(np.abs(axis), np.abs(expected_axis), atol=1e-3)

    def test_fallback_to_bbox_when_no_sketch(self):
        from solidworks import _match_body_to_direction
        # Profile 1000 mm along Z, no sketch
        body = self._make_body(-0.02, -0.02, 0.0, 0.02, 0.02, 1.0)
        center, axis = _match_body_to_direction(body, [])
        np.testing.assert_allclose(axis, [0.0, 0.0, 1.0], atol=1e-9)

    def test_getbodybox_failure_returns_safe_defaults(self):
        from solidworks import _match_body_to_direction
        body = MagicMock()
        body.GetBodyBox.side_effect = Exception("COM error")
        center, axis = _match_body_to_direction(body, [])
        np.testing.assert_allclose(center, [0.0, 0.0, 0.0])
        self.assertEqual(np.linalg.norm(axis), 1.0)


# ---------------------------------------------------------------------------
# _select_length_axis
# ---------------------------------------------------------------------------

class TestSelectLengthAxis(unittest.TestCase):

    def _items(self, *lengths):
        from solidworks import CutListItem
        return [CutListItem(f"P{i}", float(l), 1) for i, l in enumerate(lengths)]

    def test_square_profile_200mm_along_x(self):
        """45×45 profile, 200 mm along X: axis=0, cross=[45,45]."""
        from solidworks import _select_length_axis
        extents = [200.0, 45.0, 45.0]
        axis_idx, length_mm, cross = _select_length_axis(extents, self._items(200))
        self.assertEqual(axis_idx, 0)
        self.assertAlmostEqual(length_mm, 200.0)
        self.assertEqual(cross, [45.0, 45.0])

    def test_45x90_profile_150mm(self):
        """45×90 profile, 150 mm along Z: axis=2, cross=[45,90]."""
        from solidworks import _select_length_axis
        extents = [45.0, 90.0, 150.0]
        axis_idx, length_mm, cross = _select_length_axis(extents, self._items(150))
        self.assertEqual(axis_idx, 2)
        self.assertAlmostEqual(length_mm, 150.0)
        self.assertEqual(cross, [45.0, 90.0])

    def test_45x90_short_body_80mm(self):
        """Critical: 45×90 profile 80 mm long — length < cross-section height.
        extents = [45, 80, 90] mm. Must pick axis 1 (80 mm), not axis 2 (90 mm)."""
        from solidworks import _select_length_axis
        extents = [45.0, 80.0, 90.0]
        axis_idx, length_mm, cross = _select_length_axis(extents, self._items(80))
        self.assertEqual(axis_idx, 1)
        self.assertAlmostEqual(length_mm, 80.0)
        self.assertEqual(cross, [45.0, 90.0])

    def test_no_matching_axis_returns_none_triple(self):
        """No axis extent matches any item length → (None, None, None)."""
        from solidworks import _select_length_axis
        extents = [45.0, 45.0, 200.0]
        result = _select_length_axis(extents, self._items(999))
        self.assertEqual(result, (None, None, None))

    def test_tiebreak_picks_largest_extent(self):
        """Two axes both match the same item: pick the axis with larger extent."""
        from solidworks import _select_length_axis
        # extents [100, 100, 45] — axes 0 and 1 both match item(100)
        extents = [100.0, 100.0, 45.0]
        axis_idx, length_mm, cross = _select_length_axis(extents, self._items(100))
        # Both axis 0 and 1 are 100 mm — tiebreak → pick the one with largest value (either 0).
        # The important check: axis_idx is 0 or 1, NOT 2, and length=100.
        self.assertIn(axis_idx, (0, 1))
        self.assertAlmostEqual(length_mm, 100.0)

    def test_within_tolerance(self):
        """Item length 200 mm, extent 200.5 mm (within 1 mm tolerance) → matches."""
        from solidworks import _select_length_axis
        extents = [200.5, 45.0, 45.0]
        axis_idx, _, _ = _select_length_axis(extents, self._items(200))
        self.assertEqual(axis_idx, 0)

    def test_empty_items_returns_none_triple(self):
        from solidworks import _select_length_axis
        result = _select_length_axis([200.0, 45.0, 45.0], [])
        self.assertEqual(result, (None, None, None))


# ---------------------------------------------------------------------------
# _classify_profile_holes
# ---------------------------------------------------------------------------

class TestClassifyProfileHoles(unittest.TestCase):

    def test_45x45_returns_1(self):
        from solidworks import _classify_profile_holes
        self.assertEqual(_classify_profile_holes([45.0, 45.0]), 1)

    def test_45x90_returns_2(self):
        from solidworks import _classify_profile_holes
        self.assertEqual(_classify_profile_holes([45.0, 90.0]), 2)

    def test_within_tolerance_45x45(self):
        from solidworks import _classify_profile_holes
        self.assertEqual(_classify_profile_holes([44.0, 50.0]), 1)

    def test_within_tolerance_45x90(self):
        from solidworks import _classify_profile_holes
        self.assertEqual(_classify_profile_holes([44.0, 91.0]), 2)

    def test_unknown_cross_section_returns_verificar(self):
        from solidworks import _classify_profile_holes
        self.assertEqual(_classify_profile_holes([30.0, 60.0]), "VERIFICAR")

    def test_empty_list_returns_verificar(self):
        from solidworks import _classify_profile_holes
        self.assertEqual(_classify_profile_holes([]), "VERIFICAR")


# ---------------------------------------------------------------------------
# _d17_suffix
# ---------------------------------------------------------------------------

class TestD17Suffix(unittest.TestCase):

    def test_zero_capped_any_holes_returns_empty(self):
        from solidworks import _d17_suffix
        self.assertEqual(_d17_suffix(0, 1), "")
        self.assertEqual(_d17_suffix(0, 2), "")
        self.assertEqual(_d17_suffix(0, "VERIFICAR"), "")

    def test_one_end_one_hole(self):
        from solidworks import _d17_suffix
        self.assertEqual(_d17_suffix(1, 1), " D17")

    def test_two_ends_one_hole(self):
        from solidworks import _d17_suffix
        self.assertEqual(_d17_suffix(2, 1), " D17/D17")

    def test_one_end_two_holes(self):
        from solidworks import _d17_suffix
        self.assertEqual(_d17_suffix(1, 2), " D17/D17/-/-")

    def test_two_ends_two_holes(self):
        from solidworks import _d17_suffix
        self.assertEqual(_d17_suffix(2, 2), " D17/D17/D17/D17")

    def test_capped_verificar_returns_warning(self):
        from solidworks import _d17_suffix
        self.assertEqual(_d17_suffix(1, "VERIFICAR"), " VERIFICAR FURAÇÕES")
        self.assertEqual(_d17_suffix(2, "VERIFICAR"), " VERIFICAR FURAÇÕES")


# ---------------------------------------------------------------------------
# _holes_per_end_from_description
# ---------------------------------------------------------------------------

class TestHolesPerEndFromDescription(unittest.TestCase):

    def test_45x45_ascii_returns_1(self):
        from solidworks import _holes_per_end_from_description
        self.assertEqual(_holes_per_end_from_description("Perfil 45x45 L=200"), 1)

    def test_45x90_ascii_returns_2(self):
        from solidworks import _holes_per_end_from_description
        self.assertEqual(_holes_per_end_from_description("Perfil 45x90 L=200"), 2)

    def test_45x45_unicode_returns_1(self):
        from solidworks import _holes_per_end_from_description
        self.assertEqual(_holes_per_end_from_description("Perfil 45×45"), 1)

    def test_45x90_unicode_returns_2(self):
        from solidworks import _holes_per_end_from_description
        self.assertEqual(_holes_per_end_from_description("Perfil 45×90"), 2)

    def test_90x45_order_returns_2(self):
        """Order-independent: 90x45 also matches 45×90 profile."""
        from solidworks import _holes_per_end_from_description
        self.assertEqual(_holes_per_end_from_description("Perfil 90x45"), 2)

    def test_case_insensitive(self):
        from solidworks import _holes_per_end_from_description
        self.assertEqual(_holes_per_end_from_description("PERFIL STRUCT 45X45"), 1)
        self.assertEqual(_holes_per_end_from_description("PERFIL STRUCT 45X90"), 2)

    def test_unknown_profile_returns_none(self):
        from solidworks import _holes_per_end_from_description
        self.assertIsNone(_holes_per_end_from_description("Perfil 30x60"))

    def test_empty_description_returns_none(self):
        from solidworks import _holes_per_end_from_description
        self.assertIsNone(_holes_per_end_from_description(""))

    def test_no_profile_info_returns_none(self):
        from solidworks import _holes_per_end_from_description
        self.assertIsNone(_holes_per_end_from_description("Chapa 3mm"))


# ---------------------------------------------------------------------------
# _detect_capped_ends
# ---------------------------------------------------------------------------

class TestBboxContainsPoint(unittest.TestCase):

    def test_point_inside_returns_true(self):
        from solidworks import _bbox_contains_point
        bbox = (0.0, 0.0, 0.0, 1.0, 0.1, 0.1)
        self.assertTrue(_bbox_contains_point(bbox, 0.5, 0.05, 0.05))

    def test_point_outside_x_returns_false(self):
        from solidworks import _bbox_contains_point
        bbox = (0.0, 0.0, 0.0, 1.0, 0.1, 0.1)
        self.assertFalse(_bbox_contains_point(bbox, 1.001, 0.05, 0.05))

    def test_point_on_boundary_returns_true(self):
        from solidworks import _bbox_contains_point
        bbox = (0.0, 0.0, 0.0, 1.0, 0.1, 0.1)
        self.assertTrue(_bbox_contains_point(bbox, 0.0, 0.0, 0.0))
        self.assertTrue(_bbox_contains_point(bbox, 1.0, 0.1, 0.1))

    def test_none_bbox_returns_false(self):
        from solidworks import _bbox_contains_point
        self.assertFalse(_bbox_contains_point(None, 0.5, 0.05, 0.05))


class TestDetectCappedEnds(unittest.TestCase):
    """Tests use bbox geometry — _bbox_contains_point is the detection method.

    body_a: 1000 mm along X, center (0.5, 0, 0), bbox (0, -0.02, -0.02, 1.0, 0.02, 0.02)
      test1 = (1.0001, 0, 0)   [just past right end]
      test2 = (-0.0001, 0, 0)  [just past left end]

    Capper bodies straddle one end face so their bbox contains the test point.
    """

    def _make_body(self, xmin, ymin, zmin, xmax, ymax, zmax):
        """Profile body with explicit bounding box."""
        body = MagicMock()
        body.GetBodyBox.return_value = (xmin, ymin, zmin, xmax, ymax, zmax)
        return body

    def _make_profile(self, cx, cy, cz, half=0.5, cross=0.02):
        """Axis-aligned profile centred at (cx, cy, cz), length=2*half along X."""
        return self._make_body(
            cx - half, cy - cross, cz - cross,
            cx + half, cy + cross, cz + cross,
        )

    def _make_items(self, *lengths):
        from solidworks import CutListItem
        return [CutListItem(f"Profile {i}", float(l), 1)
                for i, l in enumerate(lengths)]

    def test_both_ends_capped(self):
        from solidworks import _detect_capped_ends
        # body_a: 1000 mm along X, center (0.5, 0, 0)
        #   test1=(1.0001, 0, 0)  test2=(-0.0001, 0, 0)
        body_a = self._make_profile(0.5, 0.0, 0.0, half=0.5)
        # body_b straddles left end: bbox (-0.05, -0.02, -0.02, 0.05, 0.02, 0.02)
        #   → contains test2=(-0.0001, 0, 0) ✓  max_extent=100mm ≠ 1000mm
        body_b = self._make_body(-0.05, -0.02, -0.02, 0.05, 0.02, 0.02)
        # body_c straddles right end: bbox (0.95, -0.02, -0.02, 1.05, 0.02, 0.02)
        #   → contains test1=(1.0001, 0, 0) ✓  max_extent=100mm ≠ 1000mm
        body_c = self._make_body(0.95, -0.02, -0.02, 1.05, 0.02, 0.02)
        items = self._make_items(1000)
        sketch_lines = [(np.array([0.0, 0.0, 0.0]), np.array([1.0, 0.0, 0.0]))]
        item_caps, _cross, _ = _detect_capped_ends(
            [body_a, body_b, body_c], items, sketch_lines)
        self.assertIn(0, item_caps)
        self.assertEqual(item_caps[0], [2])

    def test_one_end_capped(self):
        from solidworks import _detect_capped_ends
        body_a = self._make_profile(0.5, 0.0, 0.0, half=0.5)
        # body_b caps only the left end (test2=(-0.0001, 0, 0))
        body_b = self._make_body(-0.05, -0.02, -0.02, 0.05, 0.02, 0.02)
        items = self._make_items(1000)
        sketch_lines = [(np.array([0.0, 0.0, 0.0]), np.array([1.0, 0.0, 0.0]))]
        item_caps, _cross, _ = _detect_capped_ends([body_a, body_b], items, sketch_lines)
        self.assertEqual(item_caps[0], [1])

    def test_no_ends_capped(self):
        from solidworks import _detect_capped_ends
        body_a = self._make_profile(0.5, 0.0, 0.0, half=0.5)
        items = self._make_items(1000)
        sketch_lines = [(np.array([0.0, 0.0, 0.0]), np.array([1.0, 0.0, 0.0]))]
        item_caps, _cross, _ = _detect_capped_ends([body_a], items, sketch_lines)
        self.assertEqual(item_caps.get(0, [0]), [0])

    def test_multiple_bodies_same_item_different_capping(self):
        from solidworks import _detect_capped_ends, CutListItem
        # 3 horizontal profile bodies (1000 mm each) at y=0, y=0.1, y=0.2
        # body0: test points at y=0; body1: y=0.1; body2: y=0.2
        body0 = self._make_profile(0.5, 0.00, 0.0, half=0.5)
        body1 = self._make_profile(0.5, 0.10, 0.0, half=0.5)
        body2 = self._make_profile(0.5, 0.20, 0.0, half=0.5)
        # body_cap: bbox spans full X range, narrow Y (-0.04 to 0.04)
        # → contains body0's test points (y=0) but NOT body1's (y=0.1) or body2's (y=0.2)
        body_cap = self._make_body(-0.1, -0.04, -0.04, 1.1, 0.04, 0.04)
        items = [CutListItem("Profile", 1000.0, 3), CutListItem("Plate", 50.0, 1)]
        sketch_lines = [(np.array([0.0, 0.0, 0.0]), np.array([1.0, 0.0, 0.0]))]
        item_caps, _cross, _ = _detect_capped_ends(
            [body0, body1, body2, body_cap], items, sketch_lines)
        # body0: both test points (y=0) inside body_cap → 2
        # body1: test points y=0.1 outside body_cap (ymax=0.04) → 0
        # body2: test points y=0.2 → 0
        self.assertIn(0, item_caps)
        self.assertEqual(sorted(item_caps[0]), [0, 0, 2])

    def test_empty_bodies_returns_empty(self):
        from solidworks import _detect_capped_ends, CutListItem
        item_caps, _cross, warns = _detect_capped_ends([], [CutListItem("A", 100.0, 1)], [])
        self.assertEqual(item_caps, {})
        self.assertEqual(warns, [])

    def test_getbodies2_returns_tuple_handled(self):
        """Verify that a body with no capper produces no false positives."""
        from solidworks import _detect_capped_ends, CutListItem
        body = self._make_body(0.0, -0.02, -0.02, 1.0, 0.02, 0.02)
        items = [CutListItem("Profile 0", 1000.0, 1)]
        sketch_lines = [(np.array([0.0, 0.0, 0.0]), np.array([1.0, 0.0, 0.0]))]
        item_caps, _cross, _ = _detect_capped_ends([body], items, sketch_lines)
        self.assertIsInstance(item_caps, dict)
        self.assertEqual(item_caps.get(0, [0]), [0])

    def _make_45x90_profile(self, cx, half_length, along='x'):
        """45×90 mm profile centred at (cx, 0, 0) with length along specified axis.
        cross = 45 mm (Y) × 90 mm (Z).
        """
        c45 = 0.0225  # 45mm / 2
        c90 = 0.0450  # 90mm / 2
        if along == 'x':
            return self._make_body(
                cx - half_length, -c45, -c90,
                cx + half_length,  c45,  c90)
        raise NotImplementedError

    def test_45x90_one_end_capped(self):
        """45×90, 150 mm long, one end capped — item_cross_dims should show [45, 90]."""
        from solidworks import _detect_capped_ends, CutListItem
        body_a = self._make_45x90_profile(0.075, half_length=0.075)  # 150 mm along X
        # capper straddles the right end
        body_cap = self._make_body(0.145, -0.05, -0.05, 0.155, 0.05, 0.05)
        items = [CutListItem("Perfil 45x90", 150.0, 1)]
        item_caps, item_cross_dims, _ = _detect_capped_ends([body_a, body_cap], items, [])
        self.assertIn(0, item_caps)
        self.assertEqual(item_caps[0], [1])
        self.assertIn(0, item_cross_dims)
        self.assertEqual(item_cross_dims[0][0], [45.0, 90.0])

    def test_45x90_both_ends_capped(self):
        """45×90, 150 mm long, both ends capped."""
        from solidworks import _detect_capped_ends, CutListItem
        body_a = self._make_45x90_profile(0.075, half_length=0.075)
        body_cap_left  = self._make_body(-0.005, -0.05, -0.05, 0.005, 0.05, 0.05)
        body_cap_right = self._make_body(0.145,  -0.05, -0.05, 0.155, 0.05, 0.05)
        items = [CutListItem("Perfil 45x90", 150.0, 1)]
        item_caps, item_cross_dims, _ = _detect_capped_ends(
            [body_a, body_cap_left, body_cap_right], items, [])
        self.assertEqual(item_caps[0], [2])
        self.assertEqual(item_cross_dims[0][0], [45.0, 90.0])

    def test_45x90_short_body_80mm_is_matched(self):
        """Critical regression: 45×90 with length 80 mm < cross-section 90 mm.
        Old code: max(extents)=90 mm → no item match.
        Fixed code: _select_length_axis picks 80 mm axis → body matched."""
        from solidworks import _detect_capped_ends, CutListItem
        # bbox extents: X=0.045m(45mm), Y=0.08m(80mm), Z=0.09m(90mm)
        body_a = self._make_body(0.0, 0.0, 0.0, 0.045, 0.08, 0.09)
        items = [CutListItem("Perfil 45x90 curto", 80.0, 1)]
        item_caps, item_cross_dims, warns = _detect_capped_ends([body_a], items, [])
        # Body must be matched to item 0 (not treated as unmatched tampo)
        self.assertIn(0, item_caps)
        # cross_dims should be [45, 90]
        self.assertIn(0, item_cross_dims)
        self.assertEqual(item_cross_dims[0][0], [45.0, 90.0])
        # No "sem correspondência" warning
        self.assertFalse(any("sem correspondência" in w for w in warns))


# ---------------------------------------------------------------------------
# is_protecoes_part
# ---------------------------------------------------------------------------

class TestIsProtecoesPart(unittest.TestCase):

    def _make_part(self, corte_fabrico_value):
        """Return a mock IComponent2 whose Corte_Fabrico returns the given value."""
        comp = MagicMock()
        model = MagicMock()
        comp.GetModelDoc2.return_value = model
        mgr = MagicMock()
        model.Extension.CustomPropertyManager.return_value = mgr
        mgr.Get.return_value = corte_fabrico_value
        mgr.Get4.side_effect = Exception("not used")
        return comp

    def test_exact_match(self):
        from solidworks import is_protecoes_part
        self.assertTrue(is_protecoes_part(self._make_part("Proteções")))

    def test_exact_match_no_accent(self):
        from solidworks import is_protecoes_part
        self.assertTrue(is_protecoes_part(self._make_part("Protecoes")))

    def test_uppercase(self):
        from solidworks import is_protecoes_part
        self.assertTrue(is_protecoes_part(self._make_part("PROTEÇÕES")))

    def test_laser_part_returns_false(self):
        from solidworks import is_protecoes_part
        self.assertFalse(is_protecoes_part(self._make_part("Laser")))

    def test_empty_returns_false(self):
        from solidworks import is_protecoes_part
        self.assertFalse(is_protecoes_part(self._make_part("")))

    def test_none_model_returns_false(self):
        from solidworks import is_protecoes_part
        comp = MagicMock()
        comp.GetModelDoc2.return_value = None
        self.assertFalse(is_protecoes_part(comp))


# ---------------------------------------------------------------------------
# is_laser_part
# ---------------------------------------------------------------------------

class TestIsLaserPart(unittest.TestCase):

    def _make_part(self, corte_fabrico_value):
        """Return a mock IComponent2 whose Corte_Fabrico returns the given value."""
        comp = MagicMock()
        model = MagicMock()
        comp.GetModelDoc2.return_value = model
        mgr = MagicMock()
        model.Extension.CustomPropertyManager.return_value = mgr
        mgr.Get.return_value = corte_fabrico_value
        mgr.Get4.side_effect = Exception("not used")
        return comp

    def test_laser_only_returns_true(self):
        from solidworks import is_laser_part
        self.assertTrue(is_laser_part(self._make_part("LASER")))

    def test_laser_quinagem_returns_true(self):
        from solidworks import is_laser_part
        self.assertTrue(is_laser_part(self._make_part("LASER+QUINAGEM")))

    def test_laser_soldadura_returns_false(self):
        from solidworks import is_laser_part
        self.assertFalse(is_laser_part(self._make_part("LASER+SOLDADURA")))

    def test_laser_quinagem_soldadura_returns_false(self):
        from solidworks import is_laser_part
        self.assertFalse(is_laser_part(self._make_part("LASER+QUINAGEM+SOLDADURA")))

    def test_soldadura_only_returns_false(self):
        from solidworks import is_laser_part
        self.assertFalse(is_laser_part(self._make_part("SOLDADURA")))

    def test_empty_returns_false(self):
        from solidworks import is_laser_part
        self.assertFalse(is_laser_part(self._make_part("")))

    def test_none_model_returns_false(self):
        from solidworks import is_laser_part
        comp = MagicMock()
        comp.GetModelDoc2.return_value = None
        self.assertFalse(is_laser_part(comp))


# ---------------------------------------------------------------------------
# _is_dirty
# ---------------------------------------------------------------------------

class TestIsDirty(unittest.TestCase):

    def test_returns_true_when_dirty_method(self):
        """GetSaveFlag is a callable returning True (document has unsaved changes)."""
        from solidworks import _is_dirty
        doc = MagicMock()
        doc.GetSaveFlag = MagicMock(return_value=True)
        self.assertTrue(_is_dirty(doc))

    def test_returns_false_when_clean_method(self):
        """GetSaveFlag is a callable returning False (document is clean)."""
        from solidworks import _is_dirty
        doc = MagicMock()
        doc.GetSaveFlag = MagicMock(return_value=False)
        self.assertFalse(_is_dirty(doc))

    def test_returns_true_when_dirty_property(self):
        """GetSaveFlag is a non-callable property (True = dirty)."""
        from solidworks import _is_dirty
        doc = MagicMock()
        doc.GetSaveFlag = True  # property, not method
        self.assertTrue(_is_dirty(doc))

    def test_returns_false_when_clean_property(self):
        """GetSaveFlag is a non-callable property (False = clean)."""
        from solidworks import _is_dirty
        doc = MagicMock()
        doc.GetSaveFlag = False
        self.assertFalse(_is_dirty(doc))

    def test_handles_tuple_return(self):
        """SW 2024 sometimes returns tuple — first element is the value."""
        from solidworks import _is_dirty
        doc = MagicMock()
        doc.GetSaveFlag = MagicMock(return_value=(True, 0))
        self.assertTrue(_is_dirty(doc))

    def test_handles_tuple_clean(self):
        """SW 2024 tuple return — first element is False (document is clean)."""
        from solidworks import _is_dirty
        doc = MagicMock()
        doc.GetSaveFlag = MagicMock(return_value=(False, 0))
        self.assertFalse(_is_dirty(doc))


# ---------------------------------------------------------------------------
# open_assembly_resolved
# ---------------------------------------------------------------------------

def _make_sw_app(active_doc=None, open_doc_by_name=None, open_doc6_return=None):
    """Helper: build a mock ISldWorks object."""
    sw = MagicMock()
    sw.ActiveDoc = active_doc
    sw.GetOpenDocumentByName = MagicMock(return_value=open_doc_by_name)
    # OpenDoc6 returns a tuple (doc, errors, warnings) in early binding
    mock_doc = open_doc6_return or MagicMock()
    sw.OpenDoc6 = MagicMock(return_value=(mock_doc, 0, 0))
    return sw, mock_doc


class TestOpenAssemblyResolved(unittest.TestCase):

    def test_opens_with_default_options(self):
        """OpenDoc6 must be called with options=0 (no ReadOnly, no ForceLightweight).
        ReadOnly blocks ResolveAllLightweightComponents and SetComponentState.
        OverrideDefaultLoadLightweight (64) forces lightweight — opposite of intent."""
        from solidworks import open_assembly_resolved
        sw, doc = _make_sw_app()
        sw.ActiveDoc = None
        result_doc, opened_by_us = open_assembly_resolved(sw, r"C:\asm\test.SLDASM")
        call_args = sw.OpenDoc6.call_args
        options_arg = call_args[0][2]  # third positional arg
        self.assertEqual(options_arg, 0)
        self.assertTrue(opened_by_us)

    def test_closes_active_doc_if_already_open_and_clean(self):
        """If assembly is the active doc and clean, it is closed with the normalised path."""
        import os
        from solidworks import open_assembly_resolved
        active = MagicMock()
        active.GetPathName = MagicMock(return_value=r"C:\asm\test.SLDASM")
        active.GetSaveFlag = MagicMock(return_value=False)  # clean
        sw, _ = _make_sw_app(active_doc=active)
        open_assembly_resolved(sw, r"C:\asm\test.SLDASM")
        sw.CloseDoc.assert_called_once_with(os.path.normpath(os.path.abspath(r"C:\asm\test.SLDASM")))

    def test_raises_if_active_doc_is_dirty(self):
        """If assembly is the active doc and dirty, raise RuntimeError."""
        from solidworks import open_assembly_resolved
        active = MagicMock()
        active.GetPathName = MagicMock(return_value=r"C:\asm\test.SLDASM")
        active.GetSaveFlag = MagicMock(return_value=True)  # dirty
        sw, _ = _make_sw_app(active_doc=active)
        with self.assertRaises(RuntimeError):
            open_assembly_resolved(sw, r"C:\asm\test.SLDASM")

    def test_closes_background_doc_if_already_open_and_clean(self):
        """If assembly is open in background (not active), it is still closed."""
        import os
        from solidworks import open_assembly_resolved
        bg_doc = MagicMock()
        bg_doc.GetSaveFlag = MagicMock(return_value=False)  # clean
        sw, _ = _make_sw_app(open_doc_by_name=bg_doc)
        sw.ActiveDoc = None  # not the active doc
        # First call returns bg_doc (detect open); after CloseDoc the second call returns None (doc gone)
        sw.GetOpenDocumentByName = MagicMock(side_effect=[bg_doc, None])
        open_assembly_resolved(sw, r"C:\asm\test.SLDASM")
        sw.CloseDoc.assert_called_once_with(os.path.normpath(os.path.abspath(r"C:\asm\test.SLDASM")))

    def test_raises_if_background_doc_is_dirty(self):
        """If assembly is open in background and dirty, raise RuntimeError."""
        from solidworks import open_assembly_resolved
        bg_doc = MagicMock()
        bg_doc.GetSaveFlag = MagicMock(return_value=True)  # dirty
        sw, _ = _make_sw_app(open_doc_by_name=bg_doc)
        sw.ActiveDoc = None
        with self.assertRaises(RuntimeError):
            open_assembly_resolved(sw, r"C:\asm\test.SLDASM")

    def test_raises_if_open_doc6_returns_none(self):
        """If OpenDoc6 returns None, raise RuntimeError."""
        from solidworks import open_assembly_resolved
        sw = MagicMock()
        sw.ActiveDoc = None
        sw.GetOpenDocumentByName = MagicMock(return_value=None)
        sw.OpenDoc6 = MagicMock(return_value=(None, 0, 0))
        with self.assertRaises(RuntimeError):
            open_assembly_resolved(sw, r"C:\asm\test.SLDASM")


# ---------------------------------------------------------------------------
# get_dowel_holes — FastenerType2 filter
# Dowel constants (swWzdHoleStandardFastenerTypes_e):
#   703=ANSI Inch, 706=BSI, 707=DIN, 710=ISO, 711=JIS
# ---------------------------------------------------------------------------

class TestGetDowelHoles(unittest.TestCase):

    def _make_scene(self, fastener_type, fastener_size='Ø20.0'):
        """One HoleWzd feature with given FastenerType2 and FastenerSize."""
        feat_data = MagicMock()
        feat_data.FastenerType2 = fastener_type
        feat_data.FastenerSize = fastener_size

        defn_raw = MagicMock()

        feat = MagicMock()
        feat.GetTypeName2.return_value = "HoleWzd"
        feat.GetDefinition.return_value = defn_raw
        feat.GetNextFeature.return_value = None

        part = MagicMock()
        part.FirstFeature.return_value = feat

        return part, feat_data, defn_raw

    def _wrap_side(self, part, feat_data, defn_raw):
        def side(obj, iface):
            if iface == "IPartDoc":
                return part
            elif iface == "IWizardHoleFeatureData2":
                return feat_data
            return obj  # IFeature: return the same mock
        return side

    def test_iso_dowel_hole_collected(self):
        from solidworks import get_dowel_holes
        part, feat_data, defn_raw = self._make_scene(fastener_type=710, fastener_size='Ø20.0')
        with patch("solidworks._wrap", side_effect=self._wrap_side(part, feat_data, defn_raw)):
            holes = get_dowel_holes(MagicMock())
        self.assertEqual(len(holes), 1)
        self.assertAlmostEqual(holes[0].original_diameter_m, 0.020)

    def test_all_dowel_standards_collected(self):
        """Each of the 5 Dowel constants (703,706,707,710,711) must be recognised."""
        from solidworks import get_dowel_holes
        for ft in (703, 706, 707, 710, 711):
            part, feat_data, defn_raw = self._make_scene(fastener_type=ft)
            with patch("solidworks._wrap", side_effect=self._wrap_side(part, feat_data, defn_raw)):
                holes = get_dowel_holes(MagicMock())
            self.assertEqual(len(holes), 1, f"FastenerType2={ft} should be collected")

    def test_clearance_hole_skipped(self):
        """CHole / Clearance Hole must NOT be modified — FastenerType2 != Dowel."""
        from solidworks import get_dowel_holes
        part, feat_data, defn_raw = self._make_scene(fastener_type=100, fastener_size='M10')
        with patch("solidworks._wrap", side_effect=self._wrap_side(part, feat_data, defn_raw)):
            holes = get_dowel_holes(MagicMock())
        self.assertEqual(holes, [])

    def test_tapped_hole_skipped(self):
        from solidworks import get_dowel_holes
        part, feat_data, defn_raw = self._make_scene(fastener_type=200, fastener_size='M10')
        with patch("solidworks._wrap", side_effect=self._wrap_side(part, feat_data, defn_raw)):
            holes = get_dowel_holes(MagicMock())
        self.assertEqual(holes, [])

    def test_counterbore_hole_skipped(self):
        from solidworks import get_dowel_holes
        part, feat_data, defn_raw = self._make_scene(fastener_type=50, fastener_size='M8')
        with patch("solidworks._wrap", side_effect=self._wrap_side(part, feat_data, defn_raw)):
            holes = get_dowel_holes(MagicMock())
        self.assertEqual(holes, [])

    def test_mixed_features_only_dowels_returned(self):
        """Clearance hole followed by ISO Dowel: only Dowel in results."""
        from solidworks import get_dowel_holes

        feat_data_clearance = MagicMock()
        feat_data_clearance.FastenerType2 = 100
        feat_data_clearance.FastenerSize = 'M10'

        feat_data_dowel = MagicMock()
        feat_data_dowel.FastenerType2 = 710
        feat_data_dowel.FastenerSize = 'Ø20.0'

        defn_clearance = MagicMock()
        defn_dowel = MagicMock()

        feat_clearance = MagicMock()
        feat_clearance.GetTypeName2.return_value = "HoleWzd"
        feat_clearance.GetDefinition.return_value = defn_clearance

        feat_dowel = MagicMock()
        feat_dowel.GetTypeName2.return_value = "HoleWzd"
        feat_dowel.GetDefinition.return_value = defn_dowel
        feat_dowel.GetNextFeature.return_value = None

        feat_clearance.GetNextFeature.return_value = feat_dowel

        part = MagicMock()
        part.FirstFeature.return_value = feat_clearance

        def wrap_side(obj, iface):
            if iface == "IPartDoc":
                return part
            elif iface == "IWizardHoleFeatureData2":
                return feat_data_clearance if obj is defn_clearance else feat_data_dowel
            return obj

        with patch("solidworks._wrap", side_effect=wrap_side):
            holes = get_dowel_holes(MagicMock())

        self.assertEqual(len(holes), 1)
        self.assertAlmostEqual(holes[0].original_diameter_m, 0.020)

    def test_non_holewzd_feature_not_opened(self):
        """Non-HoleWzd features are skipped without calling GetDefinition."""
        from solidworks import get_dowel_holes
        feat = MagicMock()
        feat.GetTypeName2.return_value = "Extrude"
        feat.GetNextFeature.return_value = None
        part = MagicMock()
        part.FirstFeature.return_value = feat
        with patch("solidworks._wrap", side_effect=lambda obj, iface: part if iface == "IPartDoc" else obj):
            holes = get_dowel_holes(MagicMock())
        self.assertEqual(holes, [])
        feat.GetDefinition.assert_not_called()

    def test_fastener_type2_tuple_unwrapped(self):
        """SW 2024 early binding may return tuple for FastenerType2 — must unpack."""
        from solidworks import get_dowel_holes
        part, feat_data, defn_raw = self._make_scene(fastener_type=(710,), fastener_size='Ø20.0')
        with patch("solidworks._wrap", side_effect=self._wrap_side(part, feat_data, defn_raw)):
            holes = get_dowel_holes(MagicMock())
        self.assertEqual(len(holes), 1)


if __name__ == "__main__":
    unittest.main()
