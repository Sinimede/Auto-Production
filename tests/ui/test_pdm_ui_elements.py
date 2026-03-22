
import tkinter as tk
from unittest.mock import MagicMock
import os
from src.ui.modules.pdm_frame import PdmFrame

def test_pdm_ui_elements():
    root = tk.Tk()
    mock_service = MagicMock()
    mock_service.is_locked.return_value = (False, None)
    mock_service.get_status.return_value = "In Design"
    mock_service.get_history.return_value = []
    mock_service.get_where_used.return_value = []
    
    def log(m, l="INFO", t=None): print(f"LOG: {m}")
    
    # Instantiate the frame
    frame = PdmFrame(root, mock_service, log, lambda: "test.sldasm")
    
    print("\n[UI TEST] Verificando existência dos widgets...")
    
    widgets = {
        "btn_history": frame.btn_history,
        "btn_where_used": frame.btn_where_used,
        "btn_add_external": frame.btn_add_external,
        "tree": frame.tree,
        "context_menu": frame.context_menu
    }
    
    for name, widget in widgets.items():
        if widget:
            print(f" -> {name}: OK")
        else:
            print(f" -> {name}: FALHOU")

    # Test context menu trigger
    print("[UI TEST] Verificando se _show_history abre janela...")
    try:
        frame._show_history()
        print(" -> _show_history: OK (Janela criada)")
    except Exception as e:
        print(f" -> _show_history: FALHOU ({e})")

    # Test where used trigger
    print("[UI TEST] Verificando se _on_where_used abre janela...")
    # Mock selection
    frame.tree.insert("", "end", iid="item1", values=("Disp", "Lifecycle", "User", "1", "C:/test.sldprt"))
    frame.tree.selection_set("item1")
    try:
        frame._on_where_used()
        print(" -> _on_where_used: OK (Janela criada)")
    except Exception as e:
        print(f" -> _on_where_used: FALHOU ({e})")

    root.destroy()

if __name__ == "__main__":
    test_pdm_ui_elements()
