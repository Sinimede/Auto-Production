
import sys
import os

# Add src to python path to allow imports like 'from src.core...'
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.ui.main_window import MainWindow

if __name__ == "__main__":
    app = MainWindow()
    app.mainloop()
