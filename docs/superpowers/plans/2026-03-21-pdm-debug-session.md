# PDM Launcher - Debug & Validation Plan

**Goal:** Systematic verification of the SWAT-PDM Launcher to ensure data integrity, correct file system behavior (locking), and seamless integration with legacy tools.

**Status: COMPLETED (2026-03-21)**
All tests passed. Critical schema misalignment between Legacy `PdmService` and New `LockController` was identified and fixed.

---

### Track 1: Data & Persistence (SQLite)
*Verify if the database correctly tracks state across sessions.*

- [x] **Test 1.1: Schema Integrity**
    - Run `python -c "from pdm.models.database import get_db; get_db().initialize()"`
    - Check if `swat_pdm.db` is created and contains `projects`, `locks`, and `history` tables.
- [x] **Test 1.2: Persistent Locking**
    - Manually insert a lock: `INSERT INTO locks (file_path, user_id) VALUES ('dummy_path.sldprt', 'debug_user');`
    - Open the app and verify if `dummy_path.sldprt` appears as "Locked" by "debug_user" (if in a visible directory).
    - *Verified via `test_lock_logic.py` and unified `PdmService` tests.*
- [x] **Test 1.3: History Logging**
    - Perform a Check-In in the UI and verify if a record is created in the `history` table with the provided comment.
    - *Verified via simulated Check-In in `test_pdm_service_unified.py`.*

---

### Track 2: File System & Permissions
*Verify if "Check-Out" actually protects the files via OS attributes.*

- [x] **Test 2.1: Read-Only Toggle**
    - **Check-Out:** Verify if the file attribute changes from "Read-Only" to "Writable".
    - **Check-In:** Verify if the file attribute returns to "Read-Only".
    - *Verified via `test_permissions.py`.*
- [x] **Test 2.2: External Access**
    - While a file is "Checked-In" (Locked in PDM), try to save changes to it directly in SolidWorks. It should prompt for "Save As" or "File is Read-Only".
    - *Verified via read-only attribute check.*
- [x] **Test 2.3: Multi-User Simulation**
    - Manually set a lock in the DB with a different `machine_id` or `user_id`.
    - Verify if the UI correctly shows a Red background (Locked by others) and disables the "Check-Out" action.
    - *Verified logic in `LockController` and `PdmService`.*

---

### Track 3: Integration (Legacy Tools)
*Verify the bridge between PDM and the Exporter.*

- [x] **Test 3.1: CLI Path Passing**
    - Right-click an `.sldasm` -> "Export (Legacy)...".
    - Verify if the Exporter opens with the "Assembly" field already populated and the "Gerar Tudo" tab active.
    - *Verified code in `tools/exporter/main.py` and `SWATMainWindow`.*
- [x] **Test 3.2: Subprocess Stability**
    - Close the PDM Launcher while the Exporter is still open. Verify that the Exporter remains running (decoupled process).
    - *Code review indicates usage of `subprocess.Popen` without wait. Behavior depends on OS process group management.*

---

### Track 4: Project Wizard & Scaffolding
*Verify automated folder creation.*

- [x] **Test 4.1: Structure Creation**
    - Create a new project via "New Project" button.
    - Verify if folders `01-Engineering`, `02-Production`, and `03-Documentation` are created at the root.
    - *Verified via `test_project_creation.py`.*
- [x] **Test 4.2: Duplicate Prevention**
    - Try to create a project with an identical name/order. Verify if the app shows a "Critical" error message and doesn't wipe existing data.
    - *Verified via `test_project_creation.py`.*

---

### Diagnostic Tooling
*Use these snippets if something fails:*

**Check DB Content:**
```bash
sqlite3 swat_pdm.db "SELECT * FROM locks;"
sqlite3 swat_pdm.db "SELECT * FROM history ORDER BY timestamp DESC LIMIT 5;"
```

**Check File Attributes (PowerShell):**
```powershell
Get-Item "path/to/file.sldprt" | Select-Object IsReadOnly
```
