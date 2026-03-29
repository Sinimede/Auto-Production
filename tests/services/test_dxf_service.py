
import unittest
from unittest.mock import MagicMock, patch
from src.services.dxf_service import DxfService

class TestDxfService(unittest.TestCase):
    def setUp(self):
        self.sw_client = MagicMock()
        self.service = DxfService(self.sw_client)

    @patch('threading.Thread')
    def test_run_export_starts_thread(self, mock_thread):
        self.service.run_export("asm_path", "out_dir", {}, False)
        mock_thread.assert_called_once()

    def test_callbacks_called(self):
        on_log = MagicMock()
        on_status = MagicMock()
        on_finish = MagicMock()
        
        self.service.set_callbacks(on_log=on_log, on_status=on_status, on_finish=on_finish)
        
        # Manually trigger internal methods to test callback logic
        self.service._log("test log")
        self.service._set_status("test status")
        self.service._finish(1, 0)
        
        on_log.assert_called_with("test log", "INFO", None)
        on_status.assert_called_with("test status")
        on_finish.assert_called_with(1, 0)

if __name__ == '__main__':
    unittest.main()
