from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTextEdit, QPushButton, QHBoxLayout, QLineEdit, QFormLayout

class CheckInDialog(QDialog):
    def __init__(self, file_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Check-In: {file_name}")
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Comment for {file_name}:"))
        
        self.comment_edit = QTextEdit()
        layout.addWidget(self.comment_edit)
        
        buttons = QHBoxLayout()
        self.btn_ok = QPushButton("Check-In")
        self.btn_cancel = QPushButton("Cancel")
        
        buttons.addWidget(self.btn_ok)
        buttons.addWidget(self.btn_cancel)
        layout.addLayout(buttons)
        
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)

    def get_comment(self):
        return self.comment_edit.toPlainText().strip()

class NewProjectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Project Wizard")
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        self.client_edit = QLineEdit()
        self.name_edit = QLineEdit()
        self.order_edit = QLineEdit()
        
        form.addRow("Client:", self.client_edit)
        form.addRow("Project Name:", self.name_edit)
        form.addRow("Order Number:", self.order_edit)
        
        layout.addLayout(form)
        
        buttons = QHBoxLayout()
        self.btn_create = QPushButton("Create Project")
        self.btn_cancel = QPushButton("Cancel")
        
        buttons.addWidget(self.btn_create)
        buttons.addWidget(self.btn_cancel)
        layout.addLayout(buttons)
        
        self.btn_create.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)

    def get_data(self):
        return {
            "client": self.client_edit.text().strip(),
            "name": self.name_edit.text().strip(),
            "order": self.order_edit.text().strip()
        }
