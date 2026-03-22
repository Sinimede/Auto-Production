# SWAT-PDM Launcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a professional PyQt6-based PDM Launcher to manage projects, control file locking (Check-In/Check-Out), and orchestrate legacy tools.

**Architecture:**
- **UI:** PyQt6 (Main Window with Explorer-style layout).
- **Data:** SQLite (`swat_pdm.db`) for locking state and project metadata.
- **Integration:** Subprocess calls to existing Python scripts for heavy lifting (Export/DXF).

**Tech Stack:** Python 3.11+, PyQt6, SQLite3.

---

### Phase 1: Environment & Scaffolding

**Files:**
- Modify: `requirements.txt`
- Create: `src/pdm/__init__.py`
- Create: `src/pdm/app.py`
- Create: `run_pdm.bat`

- [x] **Task 1.1: Add Dependencies**
    - Add `PyQt6` to `requirements.txt`.
    - Run `pip install -r requirements.txt`.

- [x] **Task 1.2: Create Application Entry Point**
    - Create `src/pdm/app.py`:
        - Initialize `QApplication`.
        - Create a basic `QMainWindow` with title "SWAT-PDM".
        - Run the event loop.
    - Create `run_pdm.bat`:
        - Activates venv (if exists) or just runs `python src/pdm/app.py`.

- [x] **Task 1.3: Verify Environment**
    - Run `run_pdm.bat`.
    - **Success Criteria:** A blank window titled "SWAT-PDM" appears.

---

### Phase 2: Database Layer

**Files:**
- Create: `src/pdm/models/database.py`
- Create: `src/pdm/models/schema.py`

- [x] **Task 2.1: Database Connection Manager**
    - Create `src/pdm/models/database.py`:
        - Class `DatabaseManager` (Singleton or global instance).
        - Method `get_connection()`: Returns `sqlite3.Connection` to `swat_pdm.db`.
        - Method `initialize()`: Runs schema creation.

- [x] **Task 2.2: Define Schema**
    - Create `src/pdm/models/schema.py`:
        - Define SQL `CREATE TABLE IF NOT EXISTS` for:
            - `projects` (id, name, path, created_at)
            - `locks` (file_path PK, user_id, locked_at, machine_id)
            - `history` (id, file_path, action, user_id, version, comment, timestamp)
    - **Test:** Run a script calling `DatabaseManager.initialize()` and verify `swat_pdm.db` has tables.

---

### Phase 3: Core Logic (Controllers)

**Files:**
- Create: `src/pdm/controllers/lock_controller.py`
- Test: `tests/pdm/test_lock_controller.py`

- [x] **Task 3.1: Lock Controller Logic**
    - Create `src/pdm/controllers/lock_controller.py`:
        - `LockController` class.
        - `is_locked(file_path) -> dict | None`: Returns lock info or None.
        - `lock_file(file_path, user_id) -> bool`: Inserts into `locks` table. Handle constraints.
        - `unlock_file(file_path, user_id) -> bool`: Removes from `locks` table.
        - `get_user_locks(user_id) -> list`: Returns all files locked by user.

- [x] **Task 3.2: Unit Tests for Locking**
    - Create `tests/pdm/test_lock_controller.py`.
    - Test: Lock a file -> Verify `is_locked` returns true.
    - Test: Unlock file -> Verify `is_locked` returns false.
    - Test: Try to lock already locked file -> Verify failure/exception.

---

### Phase 4: UI - Main Window Skeleton

**Files:**
- Create: `src/pdm/views/main_window.py`
- Modify: `src/pdm/app.py`

- [x] **Task 4.1: Main Layout**
    - Implement `SWATMainWindow` in `src/pdm/views/main_window.py`.
    - Use `QSplitter` (Horizontal).
    - Add 3 placeholder widgets:
        - Left: `QLabel("Tree")`
        - Center: `QLabel("Table")`
        - Right: `QLabel("Details")`
    - Update `src/pdm/app.py` to use `SWATMainWindow`.

- [x] **Task 4.2: Styling & Assets**
    - Add basic stylesheet (optional) to make splitters visible.
    - Ensure window starts maximized.

---

### Phase 5: UI - File System & PDM Integration

**Files:**
- Modify: `src/pdm/views/main_window.py`
- Create: `src/pdm/views/file_table_model.py`

- [x] **Task 5.1: Project Tree (Left Panel)**
    - Replace Left Label with `QTreeView`.
    - Set model to `QFileSystemModel`.
    - Set root path to `C:\Users\Micael\Desktop\Auto Production` (or configured root).
    - **Filter:** Only show directories.

- [x] **Task 5.2: PDM Table Model (Center Panel)**
    - Create `src/pdm/views/file_table_model.py`:
        - Subclass `QAbstractTableModel`.
        - Init with `folder_path` and `lock_data` (from `LockController`).
        - Columns: Name, Status (Icon/Text), User, Date.
    - Replace Center Label with `QTableView`.
    - Connect Tree Click -> Update Table Model path.

- [x] **Task 5.3: Status Coloring**
    - Implement `data(role=Qt.ItemDataRole.BackgroundRole)` in the model.
    - Logic:
        - If file in `lock_data`:
            - If `user == current_user`: Green background.
            - Else: Red background.
        - Else: White/Transparent.

---

### Phase 6: Check-In/Check-Out Actions

**Files:**
- Modify: `src/pdm/views/main_window.py`
- Create: `src/pdm/views/dialogs.py`

- [x] **Task 6.1: Check-Out Action**
    - Add Context Menu to TableView: "Check Out".
    - Action:
        - Call `LockController.lock_file()`.
        - `os.chmod(path, stat.S_IWRITE)` (Remove Read-Only).
        - Refresh Table Model.

- [x] **Task 6.2: Check-In Action**
    - Add Context Menu: "Check In".
    - Create `CheckInDialog` in `src/pdm/views/dialogs.py` (Text area for comment).
    - Action:
        - Show Dialog -> Get Comment.
        - Call `LockController.unlock_file()`.
        - Insert into `history` table.
        - `os.chmod(path, stat.S_IREAD)` (Set Read-Only).
        - Refresh Table Model.

---

### Phase 7: Project Wizard

**Files:**
- Create: `src/pdm/controllers/project_controller.py`
- Create: `src/pdm/views/wizard_dialog.py`
- Modify: `src/pdm/views/main_window.py`

- [x] **Task 7.1: Project Controller**
    - `create_project(client, name, order_num)`:
        - Validate inputs.
        - Create folders: `path/01-Engineering`, etc.
        - Copy assets from `assets/` to new folder.
        - Insert into `projects` table.

- [x] **Task 7.2: Wizard UI**
    - `NewProjectDialog`: Form layout with QLineEdits.
    - Connect "Create" button to `ProjectController`.
    - Add Toolbar button "New Project" to `MainWindow`.

---

### Phase 8: Legacy Tool Launcher

**Files:**
- Modify: `tools/exporter/main.py`
- Modify: `src/pdm/views/main_window.py`

- [x] **Task 8.1: Update Legacy Tool CLI**
    - Modify `tools/exporter/main.py`:
        - Use `argparse` to check for `--path` argument.
        - If present, skip the file selection GUI and load that file immediately.

- [x] **Task 8.2: Launcher Integration**
    - Add Context Menu: "Export (Legacy)...".
    - Action:
        - `subprocess.Popen(["python", "tools/exporter/main.py", "--path", full_path])`.

---
