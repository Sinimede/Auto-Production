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
        self.headers = ["Name", "Status", "Lifecycle", "User", "Date"]
        self.current_user = getpass.getuser()
        self.refresh()

    def set_filter(self, text):
        self.filter_text = text
        self.refresh()

    def refresh(self, folder_path=None):
        if folder_path:
            self.folder_path = folder_path
            
        self.beginResetModel()
        self.files = []
        if self.folder_path and os.path.exists(self.folder_path):
            files_in_dir = os.listdir(self.folder_path)
            for f in files_in_dir:
                if f.lower().endswith(('.sldprt', '.sldasm', '.slddrw')):
                    full_path = os.path.normpath(os.path.abspath(os.path.join(self.folder_path, f)))
                    lock_info = None
                    status = "In Design"
                    if self.lock_controller:
                        lock_info = self.lock_controller.is_locked(full_path)
                        status = self.lock_controller.get_status(full_path)
                    
                    self.files.append({
                        "name": f,
                        "path": full_path,
                        "lock_info": lock_info,
                        "status": status
                    })
        
        # Apply Filter
        if self.filter_text:
            self.files = [f for f in self.files if self.filter_text.lower() in f['name'].lower()]
            
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
