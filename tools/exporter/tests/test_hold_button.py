import pytest
import tkinter as tk
from unittest.mock import MagicMock, patch
from tools.exporter.widgets.hold_button import HoldButton

class TestHoldButton:
    @pytest.fixture
    def root(self):
        try:
            root = tk.Tk()
            yield root
            root.destroy()
        except tk.TclError:
            # For environments without display
            root = MagicMock()
            root.cget.return_value = "white"
            yield root

    def test_initialization(self, root):
        on_cancel = MagicMock()
        button = HoldButton(root, on_cancel_fn=on_cancel, size=100)
        
        assert button.size == 100
        assert button.hold_time_ms == 2000
        assert not button.holding

    def test_press_starts_timer(self, root):
        on_cancel = MagicMock()
        button = HoldButton(root, on_cancel_fn=on_cancel)
        
        # Mocking update_arc because it's recursive
        with patch.object(button, 'update_arc') as mock_update:
            button.on_press(None)
            assert button.holding is True
            assert button.start_time > 0
            mock_update.assert_called_once()

    def test_release_stops_timer(self, root):
        on_cancel = MagicMock()
        button = HoldButton(root, on_cancel_fn=on_cancel)
        button.holding = True
        button.after_id = "test_after"
        
        # Mock after_cancel to avoid Tcl errors
        with patch.object(button, 'after_cancel') as mock_cancel:
            button.on_release(None)
            assert button.holding is False
            mock_cancel.assert_called_with("test_after")
            assert button.after_id is None

    def test_trigger_on_cancel(self, root):
        on_cancel = MagicMock()
        button = HoldButton(root, on_cancel_fn=on_cancel, hold_time_ms=2000)
        button.holding = True
        
        # Mock time.time to simulate 2.5 seconds passed
        with patch('time.time', side_effect=[100, 102.5]):
            button.on_press(None) # first call sets start_time=100
            
            # Now update_arc will use 102.5
            with patch.object(button, 'after') as mock_after:
                button.update_arc()
                on_cancel.assert_called_once()
                assert not button.holding

    def test_progress_calculation(self, root):
        on_cancel = MagicMock()
        button = HoldButton(root, on_cancel_fn=on_cancel, hold_time_ms=2000)
        button.holding = True
        
        # Mock time.time to simulate 1 second passed (50% progress)
        with patch('time.time', side_effect=[100, 101]):
            button.on_press(None) # start_time = 100
            
            with patch.object(button, 'itemconfig') as mock_itemconfig:
                with patch.object(button, 'after'):
                    button.update_arc()
                    # 1s / 2s = 0.5; 360 * 0.5 = 180 degrees (negative for CW)
                    # The first itemconfig might be for start_time set, 
                    # but our mock is for the second call in update_arc
                    mock_itemconfig.assert_any_call(button.arc, extent=-180.0)
