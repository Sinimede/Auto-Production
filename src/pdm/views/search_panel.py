from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QComboBox, QFrame)
from PyQt6.QtCore import pyqtSignal, Qt

class FilterTag(QFrame):
    """A small tag representing an active filter (e.g., 'Material: PVC [x]')."""
    removed = pyqtSignal(str) # Emits the property name to be removed

    def __init__(self, prop_name, display_name, value):
        super().__init__()
        self.prop_name = prop_name
        self.setObjectName("FilterTag")
        self.setStyleSheet("""
            #FilterTag {
                background-color: #e1f5fe;
                border: 1px solid #03a9f4;
                border-radius: 4px;
                padding: 2px 5px;
            }
            QLabel { color: #01579b; font-size: 11px; font-weight: bold; }
            QPushButton { 
                border: none; background: transparent; color: #d32f2f; 
                font-weight: bold; padding: 0 2px;
            }
            QPushButton:hover { color: #f44336; }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)
        layout.setSpacing(5)
        
        self.label = QLabel(f"{display_name}: {value}")
        layout.addWidget(self.label)
        
        self.btn_close = QPushButton("×")
        self.btn_close.setFixedWidth(15)
        self.btn_close.clicked.connect(lambda: self.removed.emit(self.prop_name))
        layout.addWidget(self.btn_close)

class AdvancedSearchPanel(QWidget):
    """Panel that manages active filter tags and adding new ones."""
    filters_changed = pyqtSignal(dict)

    def __init__(self, lock_controller):
        super().__init__()
        self.lock_controller = lock_controller
        self.active_filters = {}
        
        # UI Property Mappings
        self.prop_map = {
            "Description": "description",
            "Material": "material",
            "Revision": "revision",
            "Treatment": "treatment",
            "Status": "status"
        }
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(2, 2, 2, 2)
        main_layout.setSpacing(5)
        
        # 1. Input Area
        input_layout = QHBoxLayout()
        input_layout.setSpacing(5)
        
        self.combo_prop = QComboBox()
        self.combo_prop.addItems(self.prop_map.keys())
        self.combo_prop.setFixedWidth(100)
        self.combo_prop.currentTextChanged.connect(self.on_prop_changed)
        
        # Value Input (can be QLineEdit or QComboBox depending on property)
        self.edit_value = QLineEdit()
        self.edit_value.setPlaceholderText("Filter value...")
        self.edit_value.returnPressed.connect(self.add_filter)
        
        self.combo_value = QComboBox()
        self.combo_value.setEditable(True)
        self.combo_value.setVisible(False)
        self.combo_value.lineEdit().returnPressed.connect(self.add_filter)
        
        self.btn_add = QPushButton("+ Add Filter")
        self.btn_add.setStyleSheet("""
            QPushButton { background-color: #2ecc71; color: white; border-radius: 3px; padding: 4px 8px; font-weight: bold; }
            QPushButton:hover { background-color: #27ae60; }
        """)
        self.btn_add.clicked.connect(self.add_filter)
        
        input_layout.addWidget(QLabel("Add Criterion:"))
        input_layout.addWidget(self.combo_prop)
        input_layout.addWidget(self.edit_value)
        input_layout.addWidget(self.combo_value)
        input_layout.addWidget(self.btn_add)
        input_layout.addStretch()
        
        main_layout.addLayout(input_layout)
        
        # 2. Tags Area (Active Filters)
        self.tags_container = QWidget()
        self.tags_layout = QHBoxLayout(self.tags_container)
        self.tags_layout.setContentsMargins(0, 0, 0, 0)
        self.tags_layout.setSpacing(5)
        self.tags_layout.addStretch()
        
        main_layout.addWidget(self.tags_container)
        
        # Initialize
        self.on_prop_changed(self.combo_prop.currentText())

    def on_prop_changed(self, text):
        """Update value input based on selected property (e.g., show dropdown for Status)."""
        prop_key = self.prop_map[text]
        
        if prop_key in ["status", "material", "revision"]:
            # Use ComboBox for known values
            values = self.lock_controller.get_distinct_values(prop_key)
            self.combo_value.clear()
            self.combo_value.addItems(values)
            self.combo_value.setVisible(True)
            self.edit_value.setVisible(False)
        else:
            self.combo_value.setVisible(False)
            self.edit_value.setVisible(True)

    def add_filter(self):
        prop_display = self.combo_prop.currentText()
        prop_key = self.prop_map[prop_display]
        
        if self.combo_value.isVisible():
            value = self.combo_value.currentText()
        else:
            value = self.edit_value.text()
            
        if not value: return
        
        # Add to dictionary
        self.active_filters[prop_key] = value
        self.refresh_tags()
        self.filters_changed.emit(self.active_filters)
        
        # Clear inputs
        self.edit_value.clear()
        self.combo_value.setEditText("")

    def remove_filter(self, prop_key):
        if prop_key in self.active_filters:
            del self.active_filters[prop_key]
            self.refresh_tags()
            self.filters_changed.emit(self.active_filters)

    def refresh_tags(self):
        # Clear layout (keep stretch)
        while self.tags_layout.count() > 1:
            item = self.tags_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Add current filters as tags
        # Insert before the stretch (at index 0)
        for i, (prop_key, value) in enumerate(self.active_filters.items()):
            # Find display name
            display_name = [k for k, v in self.prop_map.items() if v == prop_key][0]
            tag = FilterTag(prop_key, display_name, value)
            tag.removed.connect(self.remove_filter)
            self.tags_layout.insertWidget(i, tag)

    def clear_all(self):
        self.active_filters = {}
        self.refresh_tags()
        self.filters_changed.emit(self.active_filters)
