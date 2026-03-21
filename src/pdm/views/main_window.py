from PyQt6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QSplitter, QFrame, QLabel, QVBoxLayout, QTreeView, QFileSystemModel, QTableView
from PyQt6.QtCore import Qt, QDir
import os
from .file_table_model import FileTableModel
from ..controllers.lock_controller import LockController

class SWATMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SWAT-PDM")
        self.resize(1200, 800)
        
        self.lock_controller = LockController()
        
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
        
        # Project Tree
        self.tree_model = QFileSystemModel()
        root_path = os.getcwd() # Project Root
        self.tree_model.setRootPath(root_path)
        self.tree_model.setFilter(QDir.Filter.Dirs | QDir.Filter.NoDotAndDotDot)
        
        self.tree_view = QTreeView()
        self.tree_view.setModel(self.tree_model)
        self.tree_view.setRootIndex(self.tree_model.index(root_path))
        self.tree_view.setHeaderHidden(True)
        # Hide columns except Name
        for i in range(1, self.tree_model.columnCount()):
            self.tree_view.hideColumn(i)
            
        left_layout.addWidget(QLabel("Project Tree"))
        left_layout.addWidget(self.tree_view)
        self.splitter.addWidget(self.left_panel)
        
        # 2. Center Panel (Table)
        self.center_panel = QFrame()
        self.center_panel.setFrameShape(QFrame.Shape.StyledPanel)
        center_layout = QVBoxLayout(self.center_panel)
        
        self.file_model = FileTableModel(lock_controller=self.lock_controller)
        self.file_view = QTableView()
        self.file_view.setModel(self.file_model)
        self.file_view.horizontalHeader().setStretchLastSection(True)
        
        center_layout.addWidget(QLabel("File Explorer"))
        center_layout.addWidget(self.file_view)
        self.splitter.addWidget(self.center_panel)
        
        # Connections
        self.tree_view.clicked.connect(self.on_tree_clicked)
        
        # 3. Right Panel (Details)
        self.right_panel = QFrame()
        self.right_panel.setFrameShape(QFrame.Shape.StyledPanel)
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.addWidget(QLabel("Details"))
        self.splitter.addWidget(self.right_panel)
        
        # Initial Sizes
        self.splitter.setSizes([250, 650, 300])

    def on_tree_clicked(self, index):
        path = self.tree_model.filePath(index)
        self.file_model.refresh(path)
        
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
