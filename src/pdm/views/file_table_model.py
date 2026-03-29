from PyQt6.QtCore import QAbstractTableModel, Qt, QModelIndex
from PyQt6.QtGui import QColor
import os
import getpass

class FileTableModel(QAbstractTableModel):
    def __init__(self, folder_path="", lock_controller=None):
        super().__init__()
        self.folder_path = folder_path
        self.lock_controller = lock_controller
        self.files = []
        self.filter_text = ""
        self.filters = {} # Advanced filters: {property: value}
        self.headers = ["Name", "Status", "Lifecycle", "User", "Date"]
        self.current_user = getpass.getuser()
        self.refresh()

    def set_filter(self, text):
        self.filter_text = text
        self.refresh()

    def set_advanced_filters(self, filters):
        self.filters = filters
        self.refresh()

    def refresh(self, folder_path=None):
        if folder_path:
            self.folder_path = folder_path
            
        self.beginResetModel()
        self.files = []
        
        # 1. Get files from physical directory
        physical_files = []
        if self.folder_path and os.path.exists(self.folder_path):
            try:
                files_in_dir = os.listdir(self.folder_path)
                for f in files_in_dir:
                    if f.lower().endswith(('.sldprt', '.sldasm', '.slddrw')):
                        full_path = os.path.normpath(os.path.abspath(os.path.join(self.folder_path, f)))
                        physical_files.append({
                            "name": f,
                            "path": full_path
                        })
            except Exception as e:
                print(f"Error reading directory: {e}")

        # 2. Get filtered files from Database (if advanced filters are active)
        db_filtered_paths = None
        if self.filters and any(self.filters.values()):
            if self.lock_controller:
                db_filtered_paths = set(self.lock_controller.search_metadata(self.filters))

        # 3. Combine and filter
        for f_data in physical_files:
            full_path = f_data["path"]
            
            # Filter by name (search bar)
            if self.filter_text and self.filter_text.lower() not in f_data["name"].lower():
                continue
                
            # Filter by database metadata
            if db_filtered_paths is not None and full_path not in db_filtered_paths:
                continue

            # Populate status and lock info
            lock_info = None
            status = "In Design"
            if self.lock_controller:
                lock_info = self.lock_controller.is_locked(full_path)
                status = self.lock_controller.get_status(full_path)
            
            self.files.append({
                "name": f_data["name"],
                "path": full_path,
                "lock_info": lock_info,
                "status": status
            })
            
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self.files)

    def columnCount(self, parent=QModelIndex()):
        return len(self.headers)

    def headerData(self, section, orientation, role):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.headers[section]
        return None

    def data(self, index, role):
        if not index.isValid():
            return None

        file_data = self.files[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0: return file_data["name"]
            if col == 1: 
                return "🔒 Locked" if file_data["lock_info"] else "✅ Available"
            if col == 2:
                return "✅ Approved" if file_data["status"] == "Approved" else file_data["status"]
            if col == 3:
                return file_data["lock_info"]["user_id"] if file_data["lock_info"] else ""
            if col == 4:
                return file_data["lock_info"]["locked_at"] if file_data["lock_info"] else ""
        
        if role == Qt.ItemDataRole.BackgroundRole:
            if file_data["lock_info"]:
                if file_data["lock_info"]["user_id"] == self.current_user:
                    return QColor(212, 244, 221) # Light Green
                else:
                    return QColor(248, 215, 218) # Light Red
        
        return None
