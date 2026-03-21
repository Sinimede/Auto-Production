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
        self.headers = ["Name", "Status", "User", "Date"]
        self.current_user = getpass.getuser()
        self.refresh()

    def refresh(self, folder_path=None):
        if folder_path:
            self.folder_path = folder_path
            
        self.beginResetModel()
        self.files = []
        if self.folder_path and os.path.exists(self.folder_path):
            for f in os.listdir(self.folder_path):
                if f.lower().endswith(('.sldprt', '.sldasm', '.slddrw')):
                    full_path = os.path.join(self.folder_path, f)
                    lock_info = None
                    if self.lock_controller:
                        lock_info = self.lock_controller.is_locked(full_path)
                    
                    self.files.append({
                        "name": f,
                        "path": full_path,
                        "lock_info": lock_info
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
                return file_data["lock_info"]["user_id"] if file_data["lock_info"] else ""
            if col == 3:
                return file_data["lock_info"]["locked_at"] if file_data["lock_info"] else ""

        if role == Qt.ItemDataRole.BackgroundRole:
            if file_data["lock_info"]:
                if file_data["lock_info"]["user_id"] == self.current_user:
                    return QColor(212, 244, 221) # Light Green
                else:
                    return QColor(248, 215, 218) # Light Red
        
        return None
