from PyQt6.QtWidgets import QApplication
import sys
from views.main_window import SWATMainWindow

def main():
    app = QApplication(sys.argv)
    window = SWATMainWindow()
    window.showMaximized()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
