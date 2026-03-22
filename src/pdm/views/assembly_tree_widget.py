from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTreeView, QLabel, QPushButton, QHBoxLayout, QMessageBox
from PyQt6.QtGui import QStandardItemModel, QStandardItem
from PyQt6.QtCore import Qt, pyqtSignal
import os

class AssemblyTreeWidget(QWidget):
    sync_all_requested = pyqtSignal(str) # Emits the assembly path

    def __init__(self, lock_controller):
        super().__init__()
        self.lock_controller = lock_controller
        self.current_path = None
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Header/Toolbar
        toolbar_layout = QHBoxLayout()
        self.header = QLabel("Assembly Structure")
        self.header.setStyleSheet("font-weight: bold; font-size: 14px; padding: 5px;")
        toolbar_layout.addWidget(self.header)
        
        self.sync_btn = QPushButton("🔄 Sync Structure")
        self.sync_btn.setToolTip("Update the assembly tree from SolidWorks (Structure only)")
        self.sync_btn.clicked.connect(self.on_sync_structure)
        self.sync_btn.setVisible(False)
        toolbar_layout.addWidget(self.sync_btn)

        self.sync_all_btn = QPushButton("🚀 Sync All")
        self.sync_all_btn.setToolTip("Sync metadata for ALL components in this assembly")
        self.sync_all_btn.clicked.connect(self.on_sync_all)
        self.sync_all_btn.setVisible(False)
        toolbar_layout.addWidget(self.sync_all_btn)
        
        layout.addLayout(toolbar_layout)
        
        # Tree
        self.tree_view = QTreeView()
        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels(["Name", "Status", "Version"])
        self.tree_view.setModel(self.model)
        self.tree_view.setHeaderHidden(False)
        
        layout.addWidget(self.tree_view)
        
    def load_assembly(self, file_path):
        """Build the tree recursively from the database."""
        self.current_path = file_path
        self.model.clear()
        self.model.setHorizontalHeaderLabels(["Name", "Status", "Version"])
        
        if not file_path or not file_path.lower().endswith('.sldasm'):
            self.header.setText("Not an Assembly")
            self.sync_btn.setVisible(False)
            self.sync_all_btn.setVisible(False)
            return
            
        self.header.setText(f"Structure: {os.path.basename(file_path)}")
        self.sync_btn.setVisible(True)
        self.sync_all_btn.setVisible(True)
        
        # Start Recursive Build
        root_item = self._create_item(file_path)
        self.model.appendRow(root_item)
        self._build_tree_recursive(file_path, root_item, set())
        
        self.tree_view.expandAll()
        # Resize columns
        for i in range(3):
            self.tree_view.resizeColumnToContents(i)

    def _create_item(self, path):
        name = os.path.basename(path)
        # Get metadata
        status = self.lock_controller.get_status(path)
        meta = self.lock_controller.get_file_metadata(path)
        version = f"v{meta.get('version', 1)}"
        
        # Locked info
        lock = self.lock_controller.is_locked(path)
        if lock:
            name = f"🔒 {name}"
            
        item_name = QStandardItem(name)
        item_status = QStandardItem(status)
        item_version = QStandardItem(version)
        
        return [item_name, item_status, item_version]

    def _build_tree_recursive(self, parent_path, parent_item, visited):
        if parent_path in visited:
            return # Avoid circular references
        visited.add(parent_path)
        
        conn = self.lock_controller.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT child_path FROM file_references WHERE parent_path = ?", (parent_path,))
            children = cursor.fetchall()
            
            for child_row in children:
                child_path = child_row[0]
                child_items = self._create_item(child_path)
                parent_item[0].appendRow(child_items)
                
                # Recursive call if it's an assembly
                if child_path.lower().endswith('.sldasm'):
                    self._build_tree_recursive(child_path, child_items, visited)
        finally:
            conn.close()

    def on_sync_structure(self):
        """Force a SolidWorks sync to update the structure."""
        if not self.current_path: return
        self.on_sync_all(False) # Only sync structure (MainWindow will handle this)

    def on_sync_all(self, full=True):
        """Force a SolidWorks sync for everything."""
        if not self.current_path: return
        if full:
            self.sync_all_requested.emit(self.current_path)
        else:
            # Just structure (trigger regular sync)
            self.parent().parent().on_sync_data_card(self.current_path)
            self.load_assembly(self.current_path)
