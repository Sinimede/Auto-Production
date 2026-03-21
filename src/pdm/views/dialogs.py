from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTextEdit, QPushButton, QHBoxLayout

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
