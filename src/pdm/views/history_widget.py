from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QHeaderView
from PyQt6.QtCore import Qt
import os
from ..models.database import get_db

class HistoryWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        
        self.label = QLabel("File History")
        self.label.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.layout.addWidget(self.label)
        
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Action", "User", "Date", "Comment"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        
        self.layout.addWidget(self.table)
        
    def load_history(self, file_path):
        """Load history for a specific file path from the database."""
        self.table.setRowCount(0)
        
        if not file_path:
            return

        normalized_path = os.path.normpath(os.path.abspath(file_path))
        
        try:
            db = get_db()
            conn = db.get_connection()
            cursor = conn.cursor()
            
            query = "SELECT action, user_id, timestamp, comment FROM history WHERE file_path = ? ORDER BY timestamp DESC"
            cursor.execute(query, (normalized_path,))
            rows = cursor.fetchall()
            
            self.table.setRowCount(len(rows))
            for i, (action, user_id, timestamp, comment) in enumerate(rows):
                self.table.setItem(i, 0, QTableWidgetItem(str(action)))
                self.table.setItem(i, 1, QTableWidgetItem(str(user_id)))
                self.table.setItem(i, 2, QTableWidgetItem(str(timestamp)))
                self.table.setItem(i, 3, QTableWidgetItem(str(comment)))
            
            conn.close()
            
        except Exception as e:
            print(f"Error loading history: {e}")
            self.table.setRowCount(1)
            self.table.setItem(0, 0, QTableWidgetItem("Error"))
            self.table.setItem(0, 3, QTableWidgetItem(str(e)))

    def clear(self):
        self.table.setRowCount(0)
