from PyQt6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QSplitter, QFrame, QLabel, QVBoxLayout
from PyQt6.QtCore import Qt

class SWATMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SWAT-PDM")
        self.resize(1200, 800)
        
        # Central Widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main Horizontal Layout
        layout = QHBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Splitter
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(self.splitter)
        
        # 1. Left Panel (Tree)
        self.left_panel = QFrame()
        self.left_panel.setFrameShape(QFrame.Shape.StyledPanel)
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.addWidget(QLabel("Project Tree"))
        self.splitter.addWidget(self.left_panel)
        
        # 2. Center Panel (Table)
        self.center_panel = QFrame()
        self.center_panel.setFrameShape(QFrame.Shape.StyledPanel)
        center_layout = QVBoxLayout(self.center_panel)
        center_layout.addWidget(QLabel("File Explorer"))
        self.splitter.addWidget(self.center_panel)
        
        # 3. Right Panel (Details)
        self.right_panel = QFrame()
        self.right_panel.setFrameShape(QFrame.Shape.StyledPanel)
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.addWidget(QLabel("Details"))
        self.splitter.addWidget(self.right_panel)
        
        # Initial Sizes
        self.splitter.setSizes([250, 650, 300])

if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    import sys
    app = QApplication(sys.argv)
    window = SWATMainWindow()
    window.show()
    sys.exit(app.exec())
