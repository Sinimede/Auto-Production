from PyQt6.QtWidgets import QWidget, QVBoxLayout, QFormLayout, QLineEdit, QLabel, QPushButton, QComboBox, QGroupBox, QHBoxLayout, QMessageBox
from PyQt6.QtCore import Qt, pyqtSignal
import os

class DataCardWidget(QWidget):
    metadata_saved = pyqtSignal(str) # Emits file_path when saved
    sync_requested = pyqtSignal(str) # Emits file_path to trigger SW sync

    def __init__(self, lock_controller):
        super().__init__()
        self.lock_controller = lock_controller
        self.current_file = None
        self.is_editable = False
        
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Group: File Info
        group_info = QGroupBox("File Information")
        info_layout = QFormLayout()
        self.lbl_filename = QLabel("None")
        self.lbl_filename.setStyleSheet("font-weight: bold; color: #555;")
        self.lbl_path = QLabel("-")
        self.lbl_path.setWordWrap(True)
        self.lbl_path.setStyleSheet("font-size: 10px; color: #888;")
        
        info_layout.addRow("Name:", self.lbl_filename)
        info_layout.addRow("Path:", self.lbl_path)
        group_info.setLayout(info_layout)
        layout.addWidget(group_info)
        
        # Group: Custom Properties (Data Card)
        group_props = QGroupBox("Data Card (SolidWorks Properties)")
        self.form_layout = QFormLayout()
        
        self.txt_description = QLineEdit()
        self.txt_material = QLineEdit()
        self.txt_weight = QLineEdit()
        self.txt_revision = QLineEdit()
        self.txt_revision.setPlaceholderText("e.g. 00, A, B")
        self.txt_treatment = QLineEdit()
        
        self.form_layout.addRow("Description:", self.txt_description)
        self.form_layout.addRow("Material:", self.txt_material)
        self.form_layout.addRow("Weight (kg):", self.txt_weight)
        self.form_layout.addRow("Revision:", self.txt_revision)
        self.form_layout.addRow("Treatment:", self.txt_treatment)
        
        group_props.setLayout(self.form_layout)
        layout.addWidget(group_props)
        
        # Buttons Layout
        btns_layout = QHBoxLayout()
        
        # Sync Button
        self.btn_sync = QPushButton("🔄 Sync from SW")
        self.btn_sync.setFixedHeight(35)
        self.btn_sync.setStyleSheet("background-color: #34495e; color: white; border-radius: 4px;")
        self.btn_sync.clicked.connect(self.on_sync)
        btns_layout.addWidget(self.btn_sync)
        
        # Save Button
        self.btn_save = QPushButton("💾 Save Data Card")
        self.btn_save.setFixedHeight(35)
        self.btn_save.setStyleSheet("background-color: #2c3e50; color: white; font-weight: bold; border-radius: 4px;")
        self.btn_save.clicked.connect(self.on_save)
        self.btn_save.setEnabled(False)
        btns_layout.addWidget(self.btn_save)
        
        layout.addLayout(btns_layout)
        
        layout.addStretch()
        
        self.set_editable(False)

    def set_editable(self, editable):
        self.is_editable = editable
        self.txt_description.setReadOnly(not editable)
        self.txt_material.setReadOnly(not editable)
        self.txt_weight.setReadOnly(not editable)
        self.txt_revision.setReadOnly(not editable)
        self.txt_treatment.setReadOnly(not editable)
        self.btn_save.setEnabled(editable)
        
        # Style adjustment
        style = "background-color: #fff;" if editable else "background-color: #f5f5f5; color: #666;"
        for widget in [self.txt_description, self.txt_material, self.txt_weight, self.txt_revision, self.txt_treatment]:
            widget.setStyleSheet(style)

    def load_file(self, file_path):
        self.current_file = file_path
        self.lbl_filename.setText(os.path.basename(file_path))
        self.lbl_path.setText(file_path)
        
        # 1. Check if editable (must be checked-out by current user)
        lock_info = self.lock_controller.is_locked(file_path)
        current_user = os.getlogin()
        is_owner = bool(lock_info and lock_info["user_id"] == current_user)
        self.set_editable(is_owner)
        
        # 2. Load metadata from DB
        metadata = self.get_metadata_from_db(file_path)
        if metadata:
            self.txt_description.setText(metadata.get("description", ""))
            self.txt_material.setText(metadata.get("material", ""))
            self.txt_weight.setText(str(metadata.get("weight", "")))
            self.txt_revision.setText(metadata.get("revision", "00"))
            self.txt_treatment.setText(metadata.get("treatment", ""))
        else:
            # Clear fields if no metadata
            for widget in [self.txt_description, self.txt_material, self.txt_weight, self.txt_revision, self.txt_treatment]:
                widget.clear()
            self.txt_revision.setText("00")

    def get_metadata_from_db(self, file_path):
        conn = self.lock_controller.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT description, material, weight, revision, treatment FROM file_metadata WHERE file_path = ?", (file_path,))
            row = cursor.fetchone()
            if row:
                return {
                    "description": row[0],
                    "material": row[1],
                    "weight": row[2],
                    "revision": row[3],
                    "treatment": row[4]
                }
            return None
        finally:
            conn.close()

    def on_sync(self):
        if self.current_file:
            self.sync_requested.emit(self.current_file)

    def on_save(self):
        if not self.current_file:
            return
            
        data = {
            "description": self.txt_description.text(),
            "material": self.txt_material.text(),
            "weight": self.txt_weight.text(),
            "revision": self.txt_revision.text(),
            "treatment": self.txt_treatment.text()
        }
        
        # Update DB
        conn = self.lock_controller.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO file_metadata 
                (file_path, description, material, weight, revision, treatment, last_updated) 
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (self.current_file, data["description"], data["material"], data["weight"], data["revision"], data["treatment"]))
            conn.commit()
            
            self.lock_controller.log_history(self.current_file, "METADATA_UPDATE", os.getlogin(), "Updated Data Card properties")
            QMessageBox.information(self, "Success", "Data Card saved successfully.")
            self.metadata_saved.emit(self.current_file)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save metadata: {str(e)}")
        finally:
            conn.close()

    def clear(self):
        self.current_file = None
        self.lbl_filename.setText("None")
        self.lbl_path.setText("-")
        for widget in [self.txt_description, self.txt_material, self.txt_weight, self.txt_revision, self.txt_treatment]:
            widget.clear()
        self.set_editable(False)
