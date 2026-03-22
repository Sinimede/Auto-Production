
import sys
import subprocess
from pywinauto import Application
import time

def debug_ui_uia():
    cmd = [sys.executable, "main.py"]
    proc = subprocess.Popen(cmd)
    
    try:
        time.sleep(5) # Wait for UI to load
        app = Application(backend="uia").connect(title_re="Auto Production v2", timeout=20)
        main_win = app.window(title_re="Auto Production v2")
        main_win.set_focus()
        
        print("--- UI IDENTIFIERS (UIA) ---")
        main_win.print_control_identifiers()
        print("--- END IDENTIFIERS ---")
        
    finally:
        proc.terminate()

if __name__ == "__main__":
    debug_ui_uia()
