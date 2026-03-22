
import os
import sys
import time
import subprocess
from pywinauto import Application, Desktop
from PIL import ImageGrab

def take_screenshot(name):
    os.makedirs(".tmp/screenshots", exist_ok=True)
    path = f".tmp/screenshots/{name}.png"
    ImageGrab.grab().save(path)
    print(f"Screenshot saved to: {path}")
    return path

def run_test():
    print("Starting Human-like UI Test (V3 - Final Attempt)...")
    
    cmd = [sys.executable, "main.py"]
    proc = subprocess.Popen(cmd)
    
    try:
        time.sleep(10)
        app = Application(backend="win32").connect(title_re="Auto Production v2", timeout=30)
        main_win = app.window(title_re="Auto Production v2")
        main_win.set_focus()
        
        take_screenshot("01_launched")

        # Sidebar navigation (PDM is 2nd button)
        # Sidebar X: 0-160. Y: ~180 for PDM button
        print("Navigating to Gestão PDM...")
        main_win.click_input(coords=(80, 180)) 
        time.sleep(2)
        take_screenshot("02_pdm_tab")

        # Set ASM path
        test_asm = os.path.abspath(".worktrees/pdm-launcher/18026.100.900.SLDASM")
        print(f"Setting assembly path: {test_asm}")
        # ASM Entry X: >160. Y: ~75
        main_win.click_input(coords=(400, 75))
        main_win.type_keys("^a{BACKSPACE}", with_spaces=True)
        main_win.type_keys(test_asm, with_spaces=True)
        # main_win.type_keys("{ENTER}") # Not needed if we click Refresh
        time.sleep(1)
        
        # Refresh Tree
        print("Refreshing PDM tree...")
        # Coordinate relative to window. Sidebar(160) + Padding(14) + ButtonHalf(~70) = 244
        # Y is bottom area ~580
        main_win.click_input(coords=(244, 580)) 
        time.sleep(12) # Long wait for SW
        take_screenshot("03_tree_refreshed")

        # Select first item in tree
        # Tree is middle area. X: >160. Y: ~300
        print("Selecting item in tree...")
        main_win.click_input(coords=(400, 300))
        time.sleep(1)

        # Check-Out
        print("Attempting Check-Out...")
        # Checkout is next to Refresh. X: 244 + ~150 = 394
        main_win.click_input(coords=(394, 580))
        time.sleep(5)
        take_screenshot("04_after_checkout")

        # Check-In
        print("Attempting Check-In...")
        # Checkin is next. X: 394 + ~150 = 544
        main_win.click_input(coords=(544, 580))
        time.sleep(3)
        
        # Check for Check-In dialog
        print("Looking for Check-In dialog...")
        desktop = Desktop(backend="win32")
        try:
            dialog = desktop.window(title_re=".*Check-In.*")
            if dialog.exists(timeout=10):
                print("Dialog found!")
                dialog.set_focus()
                # Comment entry might be focused by default
                dialog.type_keys("UI Test Final V3{ENTER}", with_spaces=True)
                time.sleep(2)
        except:
            print("Check-In dialog not found.")
        
        take_screenshot("05_after_checkin_v3")

        print("Test sequence completed.")

    except Exception as e:
        print(f"Error: {e}")
        take_screenshot("error_state_v3")
    finally:
        print("Closing application...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except:
            proc.kill()

if __name__ == "__main__":
    run_test()
