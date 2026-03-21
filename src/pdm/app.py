from PyQt6.QtWidgets import QApplication, QMainWindow
import sys

def main():
    app = QApplication(sys.argv)
    window = QMainWindow()
    window.setWindowTitle("SWAT-PDM")
    window.resize(800, 600)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
