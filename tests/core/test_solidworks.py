import unittest
from unittest.mock import MagicMock, patch
import os
from src.core.solidworks import SolidWorksClient, ensure_sw_connection

class TestSolidWorksClient(unittest.TestCase):
    def setUp(self):
        self.client = SolidWorksClient()
        self.client.sw = MagicMock()

    def test_ensure_sw_connection_decorator(self):
        mock_func = MagicMock()
        decorated = ensure_sw_connection(mock_func)
        
        # Test: not connected -> should call connect
        self.client.sw = None
        with patch.object(self.client, 'connect', return_value=True) as mock_connect:
            decorated(self.client, "test_arg")
            mock_connect.assert_called_once()
            mock_func.assert_called_once_with(self.client, "test_arg")

    def test_safe_call_handles_callable(self):
        obj = MagicMock()
        obj.SomeMethod = MagicMock(return_value="result")
        val = self.client._safe_call(obj, "SomeMethod")
        self.assertEqual(val, "result")
        obj.SomeMethod.assert_called_once()

    def test_safe_call_handles_property(self):
        obj = MagicMock()
        obj.SomeProp = "value"
        # Since it's not callable, it should just return the value
        val = self.client._safe_call(obj, "SomeProp")
        self.assertEqual(val, "value")

    def test_safe_call_unwraps_variant(self):
        obj = MagicMock()
        variant_mock = MagicMock()
        variant_mock.value = "real_value"
        obj.SomeMethod = MagicMock(return_value=variant_mock)
        val = self.client._safe_call(obj, "SomeMethod")
        self.assertEqual(val, "real_value")

    def test_open_doc_already_open(self):
        path = "test.sldprt"
        existing_doc = MagicMock()
        self.client.sw.GetOpenDocumentByName.return_value = existing_doc
        
        doc, was_opened = self.client.open_doc(path)
        
        abs_path = os.path.normpath(os.path.abspath(path))
        self.assertEqual(doc, existing_doc)
        self.assertFalse(was_opened)
        self.client.sw.ActivateDoc3.assert_called_with(abs_path, False, 2, 0)

    def test_open_doc_new(self):
        path = "test.sldasm"
        new_doc = MagicMock()
        self.client.sw.GetOpenDocumentByName.return_value = None
        self.client.sw.OpenDoc6.return_value = (new_doc, 0, 0)
        
        doc, was_opened = self.client.open_doc(path)
        
        self.assertEqual(doc, new_doc)
        self.assertTrue(was_opened)
        self.client.sw.OpenDoc6.assert_called()

    def test_get_thickness(self):
        model = MagicMock()
        part = MagicMock()
        # Box: xmin, ymin, zmin, xmax, ymax, zmax (metres)
        # 100x200x5 mm
        part.GetPartBox.return_value = (0, 0, 0, 0.1, 0.2, 0.005)
        
        with patch.object(self.client, '_wrap', return_value=part):
            thickness = self.client.get_thickness(model)
            self.assertEqual(thickness, 5.0)

if __name__ == '__main__':
    unittest.main()
