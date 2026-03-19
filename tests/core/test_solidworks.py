
import unittest
from unittest.mock import MagicMock, patch
from src.core.solidworks import SolidWorksClient, ensure_sw_connection

class TestSolidWorksClient(unittest.TestCase):
    def setUp(self):
        self.client = SolidWorksClient()

    @patch('win32com.client.GetActiveObject')
    @patch('pythoncom.CoInitialize')
    def test_connect_success(self, mock_coinit, mock_get_active):
        mock_sw = MagicMock()
        mock_get_active.return_value = mock_sw
        
        # Mock _wrap to return the same object
        self.client._wrap = MagicMock(return_value=mock_sw)
        
        result = self.client.connect()
        
        self.assertTrue(result)
        self.assertEqual(self.client.sw, mock_sw)
        mock_coinit.assert_called_once()
        mock_get_active.assert_called_with("SldWorks.Application")

    def test_is_alive_true(self):
        self.client.sw = MagicMock()
        self.client.sw.RevisionNumber.return_value = "32.0"
        self.assertTrue(self.client._is_alive())

    def test_is_alive_false(self):
        self.client.sw = MagicMock()
        self.client.sw.RevisionNumber.side_effect = Exception("Disconnected")
        self.assertFalse(self.client._is_alive())

    def test_ensure_sw_connection_decorator(self):
        # Create a mock class to test the decorator
        class MockClient:
            def __init__(self):
                self.sw = None
                self.connect_called = 0
            
            def connect(self):
                self.connect_called += 1
                self.sw = MagicMock()
            
            def _is_alive(self):
                return self.sw is not None

            @ensure_sw_connection
            def some_method(self):
                return "success"

        mock_client = MockClient()
        result = mock_client.some_method()
        
        self.assertEqual(result, "success")
        self.assertEqual(mock_client.connect_called, 1)

    def test_is_doc_dirty(self):
        doc = MagicMock()
        doc.GetSaveFlag = MagicMock(return_value=True)
        self.assertTrue(self.client._is_doc_dirty(doc))
        
        doc.GetSaveFlag = MagicMock(return_value=False)
        self.assertFalse(self.client._is_doc_dirty(doc))
        
        # Test tuple return
        doc.GetSaveFlag = MagicMock(return_value=(True, 0))
        self.assertTrue(self.client._is_doc_dirty(doc))

    @patch('os.path.abspath')
    @patch('os.path.normpath')
    def test_open_assembly_resolved(self, mock_norm, mock_abs):
        mock_norm.side_effect = lambda x: x
        mock_abs.side_effect = lambda x: x
        
        self.client.sw = MagicMock()
        self.client.sw.GetOpenDocumentByName.return_value = None
        self.client.sw.ActiveDoc = None
        self.client.sw.OpenDoc6.return_value = (MagicMock(), 0, 0)
        
        result_doc, was_opened = self.client.open_assembly_resolved("test.sldasm")
        
        self.assertTrue(was_opened)
        self.client.sw.OpenDoc6.assert_called_with("test.sldasm", 2, 66, "", 0, 0)

    @patch('os.path.abspath')
    @patch('os.path.normpath')
    def test_open_assembly_resolved_already_open_clean(self, mock_norm, mock_abs):
        mock_norm.side_effect = lambda x: x
        mock_abs.side_effect = lambda x: x
        
        path = "test.sldasm"
        existing_doc = MagicMock()
        existing_doc.GetSaveFlag = MagicMock(return_value=False) # Clean
        
        self.client.sw = MagicMock()
        self.client.sw.GetOpenDocumentByName.return_value = existing_doc
        self.client.sw.OpenDoc6.return_value = (MagicMock(), 0, 0)
        
        self.client.open_assembly_resolved(path)
        
        self.client.sw.CloseDoc.assert_called_with(path)
        self.client.sw.OpenDoc6.assert_called()

if __name__ == '__main__':
    unittest.main()
