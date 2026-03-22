# SWAT-PDM Launcher Design

**Date:** 2026-03-20
**Status:** Draft
**Topic:** PDM System Architecture & Launcher

## 1. Overview
The **SWAT-PDM Launcher** is the new central entry point for the Auto Production suite. It replaces the current script-based workflow with a robust **PyQt6** application that manages projects, controls file access (Check-In/Check-Out), and launches legacy tools (Exporters) as needed.

## 2. Architecture: The "Launcher" Pattern

### 2.1 Core Components
*   **Framework:** `PyQt6` (for native OS integration, advanced tables, and modern UI).
*   **Database:** `swat_pdm.db` (SQLite) - Shared source of truth for file locks and project metadata.
*   **Legacy Integration:** Executes existing Tkinter tools (`tools/exporter/main.py`) via `subprocess` calls, passing file paths as arguments.

### 2.2 Directory Structure
```text
auto-production/
├── src/
│   ├── pdm/                # NEW: PDM-specific logic
│   │   ├── __init__.py
│   │   ├── app.py          # Entry point for PyQt6
│   │   ├── controllers/    # Logic: FileSystem, ProjectWizard, Launcher
│   │   ├── models/         # Database models (SQLAlchemy or raw SQLite)
│   │   └── views/          # PyQt6 Widgets (MainWindow, WizardDialog)
│   └── ... (existing core/services/ui)
├── tools/
│   └── ... (existing scripts)
└── run_pdm.bat             # New startup script
```

## 3. Features & Workflows

### 3.1 Project Creation (The Wizard)
**Trigger:** "New Project" button on Toolbar.
**UI:** Modal Dialog (PyQt6).
**Steps:**
1.  **Input:** Client Name, Project Name, Order Number.
2.  **Validation:** Checks if folder already exists in `\\Server\Projetos`.
3.  **Execution:**
    *   Creates directory structure:
        *   `01-Engineering/` (CAD files)
        *   `02-Production/` (Exports)
        *   `03-Documentation/`
    *   Copies templates (`.prtdot`, `.asmdot`) to `01-Engineering`.
    *   Registers project in `swat_pdm.db`.
4.  **Result:** Auto-navigates the File Explorer to the new project root.

### 3.2 File Management (Explorer)
**UI:** Standard 3-pane Layout.
*   **Left (Tree):** Directory tree filtered to Project folders.
*   **Center (Table):** File list with status columns.
    *   *Columns:* Name, Status, Revision, Locked By, Date.
    *   *Color Coding:*
        *   **Green:** Checked out by ME (Writable).
        *   **Red:** Checked out by OTHERS (Read-Only).
        *   **White:** Available (Read-Only).
*   **Right (Details):** Tabs for Preview, Properties, History.

### 3.3 Check-In / Check-Out Logic
**Constraint:** SolidWorks files are strictly controlled.

*   **Check-Out (Lock):**
    *   **Action:** User Double-Clicks or Right-Click -> "Check Out".
    *   **Logic:**
        1.  Check DB: Is file locked? If yes, abort with "Locked by [User]".
        2.  DB: Insert lock record (User, Timestamp).
        3.  OS: Remove "Read-Only" attribute from file.
        4.  App: Refresh View (Turn Green).
        5.  (Optional) Open in SolidWorks immediately.

*   **Check-In (Unlock):**
    *   **Action:** Right-Click -> "Check In".
    *   **Logic:**
        1.  Prompt: "Version Comment" (Required).
        2.  Logic:
            *   Read current version (e.g., `v01`).
            *   Increment version (e.g., `v02`).
            *   (Optional) Rename/Archive old version.
        3.  DB: Remove lock record.
        4.  DB: Add History record.
        5.  OS: Set "Read-Only" attribute.
        6.  App: Refresh View (Turn White).

### 3.4 Launching Legacy Tools
**Trigger:** Right-click on an Assembly (`.SLDASM`) -> "Export...".
**Action:**
*   Identifies the selected file path.
*   Constructs command: `python tools/exporter/main.py --path "C:\Projects\...\Assembly.SLDASM"`
*   Executes as non-blocking subprocess.

## 4. Database Schema (`swat_pdm.db`)
*   **projects:** `id, name, path, created_at`
*   **locks:** `file_path (PK), user_id, locked_at, machine_id`
*   **history:** `id, file_path, action (CHECKIN/CHECKOUT), user_id, version, comment, timestamp`

## 5. Technology Stack
*   **Language:** Python 3.11+
*   **GUI:** PyQt6
*   **DB:** SQLite (via `sqlite3` standard lib)
*   **OS Integration:** `os`, `shutil`, `subprocess`, `win32api` (for file attributes)

## 6. Migration Plan
1.  **Install PyQt6:** Add to `requirements.txt`.
2.  **Scaffold:** Create `src/pdm/` structure.
3.  **Database:** Run migration script to create new tables.
4.  **Develop:** Build Main Window -> Wizard -> Check-In/Out.
5.  **Link:** Update `tools/exporter/main.py` to accept CLI arguments.
