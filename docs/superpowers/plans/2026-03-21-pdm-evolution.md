# SWAT-PDM Evolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the basic Lock/Unlock system into a professional PDM with History, Search, and Status Management.

**Architecture:** Extend the existing PyQt6 UI and SQLite database to support file history logging, dynamic filtering in the table model, and a state machine for file approval.

**Tech Stack:** Python 3.11, PyQt6, SQLite.

---

### Task 1: Search & Filter Infrastructure

**Files:**
- Modify: `src/pdm/views/main_window.py`
- Modify: `src/pdm/views/file_table_model.py`

- [x] **Step 1: Add Search Bar to UI**
  Add a `QLineEdit` above the table in `main_window.py`.
  ```python
  self.search_bar = QLineEdit()
  self.search_bar.setPlaceholderText("🔍 Search files...")
  self.search_bar.textChanged.connect(self.on_search_changed)
  center_layout.insertWidget(1, self.search_bar)
  ```

- [x] **Step 2: Implement Filter Logic in Model**
  Update `FileTableModel` to store a `filter_text` and only show matching files in `rowCount` and `data`.

- [x] **Step 3: Connect Search to Model**
  In `main_window.py`, implement `on_search_changed(self, text)` to call `self.file_model.set_filter(text)`.

---

### Task 2: File History & Details Panel

**Files:**
- Modify: `src/pdm/views/main_window.py`
- Create: `src/pdm/views/history_widget.py`

- [x] **Step 1: Create History View**
  Create a simple list or table widget to show records from the `history` table in the database.

- [x] **Step 2: Integrate with Right Panel**
  Replace the "Details" label in `main_window.py` with the new `HistoryWidget`.

- [x] **Step 3: Connect Selection Change**
  When a file is clicked in the central table, trigger `history_widget.load_history(file_path)`.

---

### Task 3: Lifecycle Status (Workflow)

**Files:**
- Modify: `src/pdm/models/schema.py`
- Modify: `src/pdm/views/main_window.py`
- Modify: `src/pdm/controllers/lock_controller.py`

- [x] **Step 1: Update Database Schema**
  Add a `status` column to the `locks` or a new `file_status` table (default: 'In Design').
  ```sql
  ALTER TABLE locks ADD COLUMN status TEXT DEFAULT 'In Design';
  ```

- [x] **Step 2: Add "Approve" Action**
  Add "✅ Approve for Production" to the context menu in `main_window.py`.
  Logic: Sets status to 'Approved' and makes the file read-only for everyone.

- [x] **Step 3: Visual Feedback**
  Update `FileTableModel` to show the status (In Design / Approved) with different icons or colors.

---

### Task 4: Cleanup & Polish

- [x] **Step 1: Remove Debug Prints**
  Clean up all `print("DEBUG: ...")` added during the previous session.

- [x] **Step 2: Final Validation**
  Run `run_pdm.bat` and verify:
  1. Search filters the table.
  2. Clicking a file shows its Check-In history.
  3. Approving a file changes its status.
