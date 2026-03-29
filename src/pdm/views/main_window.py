from PyQt6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QSplitter, QFrame, QLabel, QVBoxLayout, QTreeView, QTableView, QMenu, QMessageBox, QToolBar, QFileDialog, QLineEdit, QTabWidget, QListWidget
from PyQt6.QtGui import QAction, QFileSystemModel
from PyQt6.QtCore import Qt, QDir, QSettings
import os
import subprocess
from src.pdm.views.file_table_model import FileTableModel
from src.pdm.controllers.lock_controller import LockController
from src.pdm.controllers.project_controller import ProjectController
from src.pdm.views.dialogs import CheckInDialog, NewProjectDialog
from src.pdm.views.history_widget import HistoryWidget
from src.pdm.views.data_card_widget import DataCardWidget
from src.pdm.views.search_panel import AdvancedSearchPanel
from src.core.solidworks import SolidWorksClient

class SWATMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SWAT-PDM Professional")
        self.resize(1280, 850)
        
        self.lock_controller = LockController()
        self.project_controller = ProjectController()
        self.sw_client = SolidWorksClient()
        
        # Toolbar
        self.toolbar = QToolBar("Main Toolbar")
        self.toolbar.setMovable(False)
        self.toolbar.setIconSize(self.toolbar.iconSize() * 1.2)
        self.addToolBar(self.toolbar)
        
        change_root_act = QAction("📂 Change Root", self)
        change_root_act.triggered.connect(self.on_change_root)
        self.toolbar.addAction(change_root_act)
        
        refresh_act = QAction("🔄 Refresh", self)
        refresh_act.triggered.connect(self.on_refresh)
        self.toolbar.addAction(refresh_act)
        
        self.toolbar.addSeparator()

        self.open_sw_act = QAction("🛠️ Open in SW", self)
        self.open_sw_act.triggered.connect(self.on_open_request)
        self.open_sw_act.setEnabled(False)
        self.toolbar.addAction(self.open_sw_act)

        self.toolbar.addSeparator()

        new_project_act = QAction("📁 New Project", self)
        new_project_act.triggered.connect(self.on_new_project)
        self.toolbar.addAction(new_project_act)
        
        # Central Widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main Horizontal Layout
        layout = QHBoxLayout(central_widget)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Splitter
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(self.splitter)
        
        # 1. Left Panel (Tree)
        self.left_panel = QFrame()
        self.left_panel.setFrameShape(QFrame.Shape.StyledPanel)
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        # Project Tree
        self.tree_model = QFileSystemModel()
        settings = QSettings("SWAT", "PDM")
        root_path = settings.value("root_path", r"C:\Users\Micael\Desktop\Auto Production - Cópia")
        if not os.path.exists(root_path):
            root_path = os.getcwd()
        
        self.tree_model.setRootPath(root_path)
        self.tree_model.setFilter(QDir.Filter.Dirs | QDir.Filter.NoDotAndDotDot)
        
        self.tree_view = QTreeView()
        self.tree_view.setModel(self.tree_model)
        self.tree_view.setRootIndex(self.tree_model.index(root_path))
        self.tree_view.setHeaderHidden(True)
        # Hide columns except Name
        for i in range(1, self.tree_model.columnCount()):
            self.tree_view.hideColumn(i)
            
        header_tree = QLabel("  PROJECT EXPLORER")
        header_tree.setStyleSheet("background-color: #2c3e50; color: white; font-weight: bold; padding: 5px;")
        left_layout.addWidget(header_tree)
        left_layout.addWidget(self.tree_view)
        self.splitter.addWidget(self.left_panel)
        
        # 2. Center Panel (Table)
        self.center_panel = QFrame()
        self.center_panel.setFrameShape(QFrame.Shape.StyledPanel)
        center_layout = QVBoxLayout(self.center_panel)
        center_layout.setContentsMargins(0, 0, 0, 0)
        
        # Search Bar
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("🔍 Search files by name...")
        self.search_bar.setStyleSheet("padding: 6px; border: 1px solid #ccc; margin: 2px;")
        self.search_bar.textChanged.connect(self.on_search_changed)
        
        # Advanced Search Panel
        self.adv_search_panel = AdvancedSearchPanel(self.lock_controller)
        self.adv_search_panel.filters_changed.connect(self.on_advanced_filters_changed)
        
        self.file_model = FileTableModel(folder_path=root_path, lock_controller=self.lock_controller)
        self.file_view = QTableView()
        self.file_view.setModel(self.file_model)
        self.file_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.file_view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.file_view.horizontalHeader().setStretchLastSection(True)
        self.file_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_view.customContextMenuRequested.connect(self.on_table_context_menu)
        self.file_view.doubleClicked.connect(self.on_open_request)
        
        header_files = QLabel("  FILE VAULT")
        header_files.setStyleSheet("background-color: #34495e; color: white; font-weight: bold; padding: 5px;")
        center_layout.addWidget(header_files)
        center_layout.addWidget(self.search_bar)
        center_layout.addWidget(self.adv_search_panel)
        center_layout.addWidget(self.file_view)
        self.splitter.addWidget(self.center_panel)
        
        # Connections
        self.tree_view.clicked.connect(self.on_tree_clicked)
        self.file_view.selectionModel().selectionChanged.connect(self.on_selection_changed)
        
        # 3. Right Panel (Details Tab Widget)
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.South)
        
        self.data_card = DataCardWidget(self.lock_controller)
        self.data_card.sync_requested.connect(self.on_sync_data_card)
        self.history_widget = HistoryWidget()
        self.where_used_list = QListWidget()
        
        self.tabs.addTab(self.data_card, "📇 Data Card")
        self.tabs.addTab(self.where_used_list, "🔍 Where Used")
        self.tabs.addTab(self.history_widget, "📜 History")
        
        self.splitter.addWidget(self.tabs)
        
        # Initial Sizes
        self.splitter.setSizes([220, 700, 360])
        
        # StatusBar
        self.statusBar().showMessage("Ready.")
        self.statusBar().setStyleSheet("background-color: #f8f9fa; color: #333; border-top: 1px solid #ddd;")

    def show_message(self, message, timeout=5000):
        """Show success/info message in status bar."""
        self.statusBar().setStyleSheet("background-color: #d4edda; color: #155724; border-top: 1px solid #c3e6cb;")
        self.statusBar().showMessage(message, timeout)

    def show_error(self, message, timeout=8000):
        """Show error message in status bar with distinct style."""
        self.statusBar().setStyleSheet("background-color: #f8d7da; color: #721c24; border-top: 1px solid #f5c6cb;")
        self.statusBar().showMessage(f"ERROR: {message}", timeout)

    def on_search_changed(self, text):
        self.file_model.set_filter(text)

    def on_advanced_filters_changed(self, filters):
        self.file_model.set_advanced_filters(filters)

    def on_change_root(self):
        new_dir = QFileDialog.getExistingDirectory(self, "Select Root Directory", self.tree_model.rootPath())
        if new_dir:
            normalized_dir = os.path.normpath(new_dir)
            QSettings("SWAT", "PDM").setValue("root_path", normalized_dir)
            self.tree_model.setRootPath(normalized_dir)
            self.tree_view.setRootIndex(self.tree_model.index(normalized_dir))
            self.project_controller.set_root_path(normalized_dir)
            self.file_model.refresh(normalized_dir)

    def on_tree_clicked(self, index):
        path = self.tree_model.filePath(index)
        self.file_model.refresh(path)

    def on_selection_changed(self, selected, deselected):
        indices = self.file_view.selectionModel().selectedRows()
        if indices:
            index = indices[0]
            file_data = self.file_model.files[index.row()]
            file_path = file_data['path']
            
            # Update Toolbar
            self.open_sw_act.setEnabled(True)
            
            # Update Tabs
            self.data_card.load_file(file_path)
            self.history_widget.load_history(file_path)
            self.update_where_used(file_path)
        else:
            self.open_sw_act.setEnabled(False)
            self.data_card.clear()
            self.history_widget.clear()
            self.where_used_list.clear()

    def on_open_request(self):
        """Handler for toolbar button or double-click."""
        indices = self.file_view.selectionModel().selectedRows()
        if not indices: return
        
        index = indices[0]
        file_data = self.file_model.files[index.row()]
        self.open_and_checkout(file_data)

    def update_where_used(self, file_path):
        self.where_used_list.clear()
        parents = self.lock_controller.get_where_used(file_path)
        if parents:
            for p in parents:
                self.where_used_list.addItem(os.path.basename(p))
        else:
            self.where_used_list.addItem("(Not used in any assembly)")

    def on_new_project(self):
        dialog = NewProjectDialog(self)
        if dialog.exec():
            data = dialog.get_data()
            try:
                new_path = self.project_controller.create_project(
                    data["client"], data["name"], data["order"]
                )
                QMessageBox.information(self, "Success", f"Project created at: {new_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def on_table_context_menu(self, pos):
        index = self.file_view.indexAt(pos)
        if not index.isValid():
            return

        file_data = self.file_model.files[index.row()]
        file_name = file_data["name"].lower().strip()
        current_status = file_data["status"]
        
        menu = QMenu()
        
        # PDM Actions
        open_act = menu.addAction("🛠️ Open")
        open_act.triggered.connect(lambda: self.open_and_checkout(file_data))
        
        menu.addSeparator()

        if not file_data["lock_info"]:
            check_out_act = menu.addAction("🔓 Check-Out")
            check_out_act.triggered.connect(lambda: self.check_out_file(file_data))
        elif file_data["lock_info"]["user_id"] == self.file_model.current_user:
            check_in_act = menu.addAction("🔒 Check-In")
            check_in_act.triggered.connect(lambda: self.check_in_file(file_data))
            
        menu.addSeparator()

        # Workflow State Machine
        wf_menu = menu.addMenu("🔄 Change Workflow State")
        states = ["In Design", "Pending Approval", "Approved"]
        for state in states:
            act = wf_menu.addAction(f"To: {state}")
            act.setEnabled(current_status != state)
            act.triggered.connect(lambda checked, s=state: self.change_file_state(file_data, s))

        menu.addSeparator()

        where_used_act = menu.addAction("🔍 Where Used?")
        where_used_act.triggered.connect(lambda: self.on_where_used(file_data))

        menu.addSeparator()
        
        if file_name.endswith('.sldasm'):
            export_act = menu.addAction("🚀 Export (Legacy)...")
            export_act.triggered.connect(lambda: self.launch_legacy_exporter(file_data))
            
        menu.exec(self.file_view.viewport().mapToGlobal(pos))

    def change_file_state(self, file_data, new_state):
        path = os.path.normpath(file_data["path"])
        if self.lock_controller.set_status(path, new_state):
            self.lock_controller.log_history(path, "STATE_CHANGE", self.file_model.current_user, f"State changed to {new_state}")
            
            if new_state == "Approved":
                if os.path.exists(path):
                    try:
                        self.sw_client.set_read_only(path, True)
                    except Exception:
                        pass
                QMessageBox.information(self, "Workflow", f"File {file_data['name']} is now APPROVED.")
            else:
                if os.path.exists(path):
                    try:
                        self.sw_client.set_read_only(path, False)
                    except Exception:
                        pass
            
            self.file_model.refresh()
        else:
            QMessageBox.warning(self, "Error", "Could not change state.")

    def on_refresh(self):
        self.file_model.refresh()

    def launch_legacy_exporter(self, file_data):
        try:
            script_path = os.path.abspath(os.path.join(os.getcwd(), "tools/exporter/main.py"))
            subprocess.Popen(["python", script_path, "--path", file_data["path"]])
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to launch legacy exporter: {str(e)}")

    def check_out_file(self, file_data):
        path = file_data["path"]
        if self.lock_controller.lock_file(path):
            try:
                self.sw_client.set_read_only(path, False)
                self.file_model.refresh()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not set file to writable: {str(e)}")
        else:
            QMessageBox.warning(self, "Locked", "File is already locked by another user.")

    def open_and_checkout(self, file_data):
        """
        PDM Logic for opening files:
        - Free -> Auto Check-Out + Open Editable
        - Locked by Me -> Open Editable
        - Locked by Other -> Warning + Open Read-Only
        """
        path = os.path.normpath(file_data["path"])
        lock_info = self.lock_controller.is_locked(path)
        current_user = self.file_model.current_user

        # 1. Lock Handling
        if not lock_info:
            # FREE -> Attempt Auto Check-Out
            if self.lock_controller.lock_file(path):
                try:
                    self.sw_client.set_read_only(path, False)
                    self.file_model.refresh()
                    print(f"Auto Check-Out performed for {file_data['name']}")
                except Exception as e:
                    print(f"Warning: Could not set file to writable: {e}")
            else:
                # Race condition: someone locked it in the last millisecond
                QMessageBox.warning(self, "Locked", "File was just locked by another user. Opening Read-Only.")
                try: self.sw_client.set_read_only(path, True)
                except: pass
        
        elif lock_info["user_id"] == current_user:
            # LOCKED BY ME -> Ensure writable
            try: self.sw_client.set_read_only(path, False)
            except: pass
        
        else:
            # LOCKED BY OTHER -> Warning
            QMessageBox.warning(self, "Locked by " + lock_info["user_id"], 
                                f"This file is currently checked-out by {lock_info['user_id']}.\n"
                                "It will be opened in READ-ONLY mode.")
            try: self.sw_client.set_read_only(path, True)
            except: pass

        # 2. Open in SolidWorks (Robust launch)
        try:
            self.sw_client.launch_sw_with_file(path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to launch SolidWorks: {str(e)}")

    def check_in_file(self, file_data):
        path = os.path.normpath(file_data["path"])
        dialog = CheckInDialog(file_data["name"], self)
        if dialog.exec():
            comment = dialog.get_comment()

            # Sync SW dependencies and metadata before unlocking
            if path.lower().endswith(('.sldasm', '.sldprt')):
                try:
                    deps = self.sw_client.get_dependencies(path)
                    if deps:
                        self.lock_controller.update_references(path, deps)
                    props = self.sw_client.get_custom_properties(path)
                    if props:
                        self.sync_metadata_from_sw(path, props)
                except Exception as e:
                    print(f"SW Sync Warning: {e}")

            if self.lock_controller.check_in(path, self.file_model.current_user, comment):
                try:
                    self.sw_client.set_read_only(path, True)
                except:
                    pass
                self.file_model.refresh()
                QMessageBox.information(self, "Success", f"File {file_data['name']} checked-in.")
            else:
                QMessageBox.warning(self, "Error", "Check-In failed. Make sure the file is checked-out by you.")

    def sync_metadata_from_sw(self, file_path, props):
        description = props.get("Description", props.get("Descrição", ""))
        material = props.get("Material", "")
        weight = props.get("Weight", props.get("Peso", 0))
        revision = props.get("Revision", props.get("Revisão", "00"))
        treatment = props.get("Treatment", props.get("Tratamento", ""))
        file_hash = self.sw_client.get_file_hash(file_path)
        self.lock_controller.save_metadata(
            file_path, description, material, weight, revision, treatment, file_hash=file_hash
        )

    def on_where_used(self, file_data):
        self.tabs.setCurrentIndex(1) # Switch to Where Used tab

    def on_sync_data_card(self, file_path):
        """Fetches metadata from SolidWorks and updates the Data Card."""
        try:
            # 1. Hashing Check (Avoid work if file hasn't changed since last sync)
            current_hash = self.sw_client.get_file_hash(file_path)
            cached_hash = self.lock_controller.get_cached_hash(file_path)

            if cached_hash and current_hash == cached_hash:
                # No change since last sync
                self.data_card.load_file(file_path)
                # QMessageBox.information(self, "Success", "Metadata is already up to date (cached).")
                return

            # 2. Check if file is open in SW (if it is, we MUST use the slow method to get real-time values)
            is_open = False
            if self.sw_client.sw:
                is_open = self.sw_client.sw.GetOpenDocumentByName(file_path) is not None

            if not is_open:
                # 3. Use Fast Method (olefile) for closed files
                props = self.sw_client.get_custom_properties_fast(file_path)
                if props:
                    self.sync_metadata_from_sw(file_path, props)
                    self.data_card.load_file(file_path)
                    if len(props) >= 3: return

            # 4. Fallback to Slow Method (SolidWorks COM)
            if not self.sw_client.sw:
                self.sw_client.connect()

            props = self.sw_client.get_custom_properties(file_path)
            if props:
                self.sync_metadata_from_sw(file_path, props)
                self.data_card.load_file(file_path)
                # QMessageBox.information(self, "Success", "Metadata synced from SolidWorks successfully.")
            else:
                QMessageBox.warning(self, "Warning", "No custom properties found. Make sure the file is a valid SolidWorks document.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to sync with SolidWorks: {str(e)}")
