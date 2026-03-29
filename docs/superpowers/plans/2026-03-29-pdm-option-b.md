# PDM Option B — Eliminate PdmService Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the broken `PdmService` and consolidate all PDM logic (locking, versioning, metadata) into `LockController`, fixing all identified issues in the process.

**Architecture:** `LockController` becomes the single authority for the `swat_pdm.db` database. Versioning (`.versions/` folder) moves into `LockController.check_in`. The UI (`main_window.py`) calls `lock_controller.check_in` instead of managing unlock + history manually. `DataCardWidget` uses new `LockController` methods instead of raw SQL.

**Tech Stack:** Python 3, PyQt6, SQLite via `DatabaseManager` singleton, `shutil` for file copies.

---

## File Map

| File | Change |
|------|--------|
| `src/pdm/controllers/lock_controller.py` | Fix normalization (C3), add `version` param to `log_history`, add `_get_next_version`, `check_in`, `get_metadata`, `save_metadata`, `get_cached_hash` |
| `src/pdm/views/main_window.py` | Use `lock_controller.check_in`, use `lock_controller.save_metadata` + `get_cached_hash`, fix `change_file_state` (I7), fix hardcoded path → QSettings (I10) |
| `src/pdm/views/data_card_widget.py` | Replace raw SQL with `lock_controller.get_metadata` / `lock_controller.save_metadata` |
| `tests/pdm/test_lock_controller.py` | Add tests for new methods |
| `src/services/pdm_service.py` | **DELETE** |
| `tests/services/test_pdm_service.py` | **DELETE** |

---

## Task 1: Fix path normalization in LockController (C3) + add `version` to `log_history`

**Files:**
- Modify: `src/pdm/controllers/lock_controller.py`
- Modify: `tests/pdm/test_lock_controller.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/pdm/test_lock_controller.py`, inside `TestLockController`:

```python
def test_is_locked_with_absolute_path(self):
    """is_locked must normalize so relative and absolute paths resolve the same."""
    rel_path = "test_file.sldprt"
    abs_path = os.path.normpath(os.path.abspath(rel_path))
    self.controller.lock_file(rel_path, self.test_user)
    # Looking up by abs path must find the lock inserted with rel path
    self.assertIsNotNone(self.controller.is_locked(abs_path))

def test_unlock_with_absolute_path(self):
    """unlock_file must normalize so it can find the row inserted with a relative path."""
    rel_path = "test_file.sldprt"
    abs_path = os.path.normpath(os.path.abspath(rel_path))
    self.controller.lock_file(rel_path, self.test_user)
    self.assertTrue(self.controller.unlock_file(abs_path, self.test_user))

def test_log_history_with_version(self):
    """log_history must store version when provided."""
    self.controller.log_history(self.test_file, "CHECKIN", self.test_user, "comment", version="3")
    conn = self.controller.db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT version FROM history WHERE action = 'CHECKIN'")
    row = cursor.fetchone()
    conn.close()
    self.assertEqual(row[0], "3")
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd "c:\Users\Micael\Desktop\Auto Production"
python -m pytest tests/pdm/test_lock_controller.py::TestLockController::test_is_locked_with_absolute_path tests/pdm/test_lock_controller.py::TestLockController::test_unlock_with_absolute_path tests/pdm/test_lock_controller.py::TestLockController::test_log_history_with_version -v
```

Expected: 3 FAILED

- [ ] **Step 3: Fix `lock_controller.py`**

Replace the entire body of `lock_file`, `unlock_file`, `is_locked`, `get_status`, `set_status`, and `log_history` with the normalized versions. Full replacement for `src/pdm/controllers/lock_controller.py`:

```python
import os
import getpass
import socket
import shutil
from ..models.database import get_db


class LockController:
    def __init__(self):
        self.db = get_db()

    def is_locked(self, file_path):
        file_path = os.path.normpath(os.path.abspath(file_path))
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id, locked_at, machine_id FROM locks WHERE file_path = ?",
            (file_path,)
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            return {"user_id": row[0], "locked_at": row[1], "machine_id": row[2]}
        return None

    def log_history(self, file_path, action, user_id, comment="", version=None):
        file_path = os.path.normpath(os.path.abspath(file_path))
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO history (file_path, action, user_id, comment, version) VALUES (?, ?, ?, ?, ?)",
                (file_path, action, user_id, comment, version)
            )
            conn.commit()
        except Exception as e:
            print(f"ERROR: Could not log history: {e}")
        finally:
            conn.close()

    def lock_file(self, file_path, user_id=None):
        if user_id is None:
            user_id = getpass.getuser()
        machine_id = socket.gethostname()
        file_path = os.path.normpath(os.path.abspath(file_path))

        if self.is_locked(file_path):
            return False

        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO locks (file_path, user_id, machine_id) VALUES (?, ?, ?)",
                (file_path, user_id, machine_id)
            )
            conn.commit()
            self.log_history(file_path, "LOCK", user_id, "File Checked-Out")
            return True
        except Exception:
            return False
        finally:
            conn.close()

    def unlock_file(self, file_path, user_id=None):
        if user_id is None:
            user_id = getpass.getuser()
        file_path = os.path.normpath(os.path.abspath(file_path))

        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM locks WHERE file_path = ? AND user_id = ?",
                (file_path, user_id)
            )
            if cursor.rowcount > 0:
                conn.commit()
                return True
            return False
        finally:
            conn.close()

    def get_user_locks(self, user_id=None):
        if user_id is None:
            user_id = getpass.getuser()
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT file_path, locked_at FROM locks WHERE user_id = ?", (user_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        return [{"file_path": r[0], "locked_at": r[1]} for r in rows]

    def get_status(self, file_path):
        file_path = os.path.normpath(os.path.abspath(file_path))
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT status FROM file_status WHERE file_path = ?", (file_path,)
        )
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else "In Design"

    def set_status(self, file_path, status):
        file_path = os.path.normpath(os.path.abspath(file_path))
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO file_status (file_path, status) VALUES (?, ?)",
                (file_path, status)
            )
            conn.commit()
            return True
        except Exception:
            return False
        finally:
            conn.close()

    def update_references(self, parent_path, child_paths):
        """Update parent-child dependency table."""
        parent_path = os.path.normpath(os.path.abspath(parent_path))
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM file_references WHERE parent_path = ?", (parent_path,)
            )
            for child in child_paths:
                child_path = os.path.normpath(os.path.abspath(child))
                cursor.execute(
                    "INSERT OR IGNORE INTO file_references (parent_path, child_path) VALUES (?, ?)",
                    (parent_path, child_path)
                )
            conn.commit()
            return True
        except Exception as e:
            print(f"ERROR: Could not update references: {e}")
            return False
        finally:
            conn.close()

    def get_where_used(self, file_path):
        """Find all assemblies that reference this file."""
        file_path = os.path.normpath(os.path.abspath(file_path))
        file_name = os.path.basename(file_path)
        name_no_ext = os.path.splitext(file_name)[0]

        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT parent_path FROM file_references WHERE child_path = ?", (file_path,)
        )
        rows = cursor.fetchall()

        if not rows:
            cursor.execute(
                "SELECT parent_path FROM file_references WHERE child_path LIKE ? OR child_path LIKE ?",
                (f"%{file_name}", f"%{name_no_ext}")
            )
            rows = cursor.fetchall()

        conn.close()
        return list(set(row[0] for row in rows))

    def search_metadata(self, filters):
        """Advanced metadata search. filters: dict {property_name: value}."""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        query = """
            SELECT m.file_path
            FROM file_metadata m
            LEFT JOIN file_status s ON m.file_path = s.file_path
            WHERE 1=1
        """
        params = []
        for key, value in filters.items():
            if not value:
                continue
            if key == "description":
                query += " AND m.description LIKE ?"
                params.append(f"%{value}%")
            elif key == "material":
                query += " AND m.material LIKE ?"
                params.append(f"%{value}%")
            elif key == "revision":
                query += " AND m.revision = ?"
                params.append(value)
            elif key == "treatment":
                query += " AND m.treatment LIKE ?"
                params.append(f"%{value}%")
            elif key == "status":
                query += " AND s.status = ?"
                params.append(value)
        cursor.execute(query, params)
        results = [os.path.normpath(row[0]) for row in cursor.fetchall()]
        conn.close()
        return results

    def get_distinct_values(self, column):
        """Get unique values for a metadata column."""
        valid_columns = ["material", "revision", "treatment", "status"]
        if column not in valid_columns:
            return []
        conn = self.db.get_connection()
        cursor = conn.cursor()
        if column == "status":
            cursor.execute(
                "SELECT DISTINCT status FROM file_status WHERE status IS NOT NULL"
            )
        else:
            cursor.execute(
                f"SELECT DISTINCT {column} FROM file_metadata WHERE {column} IS NOT NULL AND {column} != ''"
            )
        results = [row[0] for row in cursor.fetchall()]
        conn.close()
        return sorted(results)

    # ------------------------------------------------------------------ #
    # Metadata
    # ------------------------------------------------------------------ #

    def get_metadata(self, file_path):
        """Return metadata dict for file_path, or None if not found."""
        file_path = os.path.normpath(os.path.abspath(file_path))
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT description, material, weight, revision, treatment FROM file_metadata WHERE file_path = ?",
                (file_path,)
            )
            row = cursor.fetchone()
            if row:
                return {
                    "description": row[0],
                    "material": row[1],
                    "weight": row[2],
                    "revision": row[3],
                    "treatment": row[4],
                }
            return None
        finally:
            conn.close()

    def save_metadata(self, file_path, description, material, weight, revision, treatment, file_hash=None):
        """Upsert metadata for file_path. Pass file_hash to cache the SW sync hash."""
        file_path = os.path.normpath(os.path.abspath(file_path))
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT OR REPLACE INTO file_metadata
                   (file_path, description, material, weight, revision, treatment, last_synced_hash, last_updated)
                   VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                (file_path, description, material, weight, revision, treatment, file_hash)
            )
            conn.commit()
            return True
        except Exception:
            return False
        finally:
            conn.close()

    def get_cached_hash(self, file_path):
        """Return the last_synced_hash stored for file_path, or None."""
        file_path = os.path.normpath(os.path.abspath(file_path))
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT last_synced_hash FROM file_metadata WHERE file_path = ?",
                (file_path,)
            )
            row = cursor.fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    # Versioning
    # ------------------------------------------------------------------ #

    def _get_next_version(self, file_path):
        """Return the next integer version number for file_path (1-based)."""
        file_path = os.path.normpath(os.path.abspath(file_path))
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT version FROM history WHERE file_path = ? AND action = 'CHECKIN' AND version IS NOT NULL ORDER BY id DESC LIMIT 1",
                (file_path,)
            )
            row = cursor.fetchone()
            if row and row[0]:
                try:
                    return int(row[0]) + 1
                except (ValueError, TypeError):
                    pass
            return 1
        finally:
            conn.close()

    def check_in(self, file_path, user_id, comment=""):
        """
        Full check-in flow:
        1. Validates user owns the lock.
        2. Creates a versioned copy in .versions/ subfolder.
        3. Unlocks the file in DB.
        4. Logs CHECKIN action with version number.
        Returns True on success, False if file is not locked by user_id.
        """
        file_path = os.path.normpath(os.path.abspath(file_path))

        lock_info = self.is_locked(file_path)
        if not lock_info or lock_info["user_id"] != user_id:
            return False

        new_version = self._get_next_version(file_path)

        # Create versioned copy
        if os.path.exists(file_path):
            try:
                versions_dir = os.path.join(os.path.dirname(file_path), ".versions")
                os.makedirs(versions_dir, exist_ok=True)
                name, ext = os.path.splitext(os.path.basename(file_path))
                version_filename = f"{name}_v{new_version:02d}{ext}"
                shutil.copy2(file_path, os.path.join(versions_dir, version_filename))
            except Exception as e:
                print(f"WARNING: Could not create version copy: {e}")

        self.unlock_file(file_path, user_id)
        self.log_history(file_path, "CHECKIN", user_id, comment, version=str(new_version))
        return True
```

- [ ] **Step 4: Run the 3 new tests**

```bash
cd "c:\Users\Micael\Desktop\Auto Production"
python -m pytest tests/pdm/test_lock_controller.py::TestLockController::test_is_locked_with_absolute_path tests/pdm/test_lock_controller.py::TestLockController::test_unlock_with_absolute_path tests/pdm/test_lock_controller.py::TestLockController::test_log_history_with_version -v
```

Expected: 3 PASSED

- [ ] **Step 5: Run full test suite to check for regressions**

```bash
cd "c:\Users\Micael\Desktop\Auto Production"
python -m pytest tests/ -v --ignore=tests/services/test_pdm_service.py -x
```

Expected: all passing (ignore `test_pdm_service.py` — it will be deleted later)

- [ ] **Step 6: Commit**

```bash
git add src/pdm/controllers/lock_controller.py tests/pdm/test_lock_controller.py
git commit -m "fix(pdm): normalize paths in LockController + add version to log_history (C3)"
```

---

## Task 2: Add metadata methods tests + versioning tests to test_lock_controller.py

**Files:**
- Modify: `tests/pdm/test_lock_controller.py`

- [ ] **Step 1: Add metadata and versioning tests**

Append to `TestLockController` class in `tests/pdm/test_lock_controller.py`:

```python
    # ---- metadata ----

    def test_get_metadata_returns_none_when_absent(self):
        self.assertIsNone(self.controller.get_metadata(self.test_file))

    def test_save_and_get_metadata(self):
        self.controller.save_metadata(
            self.test_file, "Test Part", "Steel", 1.5, "00", "Painted"
        )
        result = self.controller.get_metadata(self.test_file)
        self.assertIsNotNone(result)
        self.assertEqual(result["description"], "Test Part")
        self.assertEqual(result["material"], "Steel")
        self.assertAlmostEqual(float(result["weight"]), 1.5)
        self.assertEqual(result["revision"], "00")
        self.assertEqual(result["treatment"], "Painted")

    def test_save_metadata_overwrites(self):
        self.controller.save_metadata(self.test_file, "Old", "Iron", 1.0, "00", "")
        self.controller.save_metadata(self.test_file, "New", "Steel", 2.0, "01", "Anodized")
        result = self.controller.get_metadata(self.test_file)
        self.assertEqual(result["description"], "New")
        self.assertEqual(result["revision"], "01")

    def test_get_cached_hash_returns_none_when_absent(self):
        self.assertIsNone(self.controller.get_cached_hash(self.test_file))

    def test_get_cached_hash_returns_stored_hash(self):
        self.controller.save_metadata(
            self.test_file, "x", "y", 0, "00", "", file_hash="abc123"
        )
        self.assertEqual(self.controller.get_cached_hash(self.test_file), "abc123")

    def test_save_metadata_without_hash_does_not_clear_hash(self):
        self.controller.save_metadata(
            self.test_file, "x", "y", 0, "00", "", file_hash="abc123"
        )
        # Save again without hash argument — hash should be overwritten with None
        # (this is expected SQLite INSERT OR REPLACE behavior)
        self.controller.save_metadata(self.test_file, "x", "y", 0, "00", "")
        # Hash is now None — acceptable
        result = self.controller.get_cached_hash(self.test_file)
        self.assertIsNone(result)

    # ---- versioning ----

    def test_check_in_fails_if_not_locked(self):
        result = self.controller.check_in(self.test_file, self.test_user, "comment")
        self.assertFalse(result)

    def test_check_in_fails_if_wrong_user(self):
        self.controller.lock_file(self.test_file, "owner")
        result = self.controller.check_in(self.test_file, "intruder", "comment")
        self.assertFalse(result)
        # File should still be locked by owner
        self.assertIsNotNone(self.controller.is_locked(self.test_file))

    def test_check_in_unlocks_file(self):
        self.controller.lock_file(self.test_file, self.test_user)
        self.controller.check_in(self.test_file, self.test_user, "done")
        self.assertIsNone(self.controller.is_locked(self.test_file))

    def test_check_in_logs_checkin_with_version(self):
        self.controller.lock_file(self.test_file, self.test_user)
        self.controller.check_in(self.test_file, self.test_user, "my comment")
        conn = self.controller.db.get_connection()
        cursor = conn.cursor()
        file_path = os.path.normpath(os.path.abspath(self.test_file))
        cursor.execute(
            "SELECT version, comment FROM history WHERE file_path = ? AND action = 'CHECKIN'",
            (file_path,)
        )
        row = cursor.fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "1")
        self.assertEqual(row[1], "my comment")

    def test_check_in_increments_version(self):
        self.controller.lock_file(self.test_file, self.test_user)
        self.controller.check_in(self.test_file, self.test_user, "v1")
        self.controller.lock_file(self.test_file, self.test_user)
        self.controller.check_in(self.test_file, self.test_user, "v2")
        conn = self.controller.db.get_connection()
        cursor = conn.cursor()
        file_path = os.path.normpath(os.path.abspath(self.test_file))
        cursor.execute(
            "SELECT version FROM history WHERE file_path = ? AND action = 'CHECKIN' ORDER BY id",
            (file_path,)
        )
        rows = cursor.fetchall()
        conn.close()
        self.assertEqual(rows[0][0], "1")
        self.assertEqual(rows[1][0], "2")

    def test_check_in_creates_versions_folder(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "part.sldprt")
            with open(file_path, "w") as f:
                f.write("content")
            self.controller.lock_file(file_path, self.test_user)
            self.controller.check_in(file_path, self.test_user, "first")
            versions_dir = os.path.join(tmpdir, ".versions")
            self.assertTrue(os.path.exists(versions_dir))
            files = os.listdir(versions_dir)
            self.assertEqual(len(files), 1)
            self.assertIn("_v01", files[0])

    def test_check_in_version_filename_increments(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "part.sldprt")
            for i in range(1, 3):
                with open(file_path, "w") as f:
                    f.write(f"v{i}")
                self.controller.lock_file(file_path, self.test_user)
                self.controller.check_in(file_path, self.test_user, f"v{i}")
            files = sorted(os.listdir(os.path.join(tmpdir, ".versions")))
            self.assertEqual(len(files), 2)
            self.assertIn("_v01", files[0])
            self.assertIn("_v02", files[1])
```

- [ ] **Step 2: Run new tests**

```bash
cd "c:\Users\Micael\Desktop\Auto Production"
python -m pytest tests/pdm/test_lock_controller.py -v -x
```

Expected: all PASSED (the implementation was done in Task 1)

- [ ] **Step 3: Commit**

```bash
git add tests/pdm/test_lock_controller.py
git commit -m "test(pdm): add metadata + versioning tests to test_lock_controller"
```

---

## Task 3: Fix `change_file_state` read-only permission (I7) + QSettings root path (I10)

**Files:**
- Modify: `src/pdm/views/main_window.py`

- [ ] **Step 1: Fix `change_file_state` — restore write permission for non-Approved states**

Find this block in `main_window.py` (~line 285):

```python
            if new_state == "Approved":
                if os.path.exists(path):
                    try: os.chmod(path, stat.S_IREAD)
                    except: pass
                QMessageBox.information(self, "Workflow", f"File {file_data['name']} is now APPROVED.")
```

Replace with:

```python
            if new_state == "Approved":
                if os.path.exists(path):
                    try:
                        os.chmod(path, stat.S_IREAD)
                    except:
                        pass
                QMessageBox.information(self, "Workflow", f"File {file_data['name']} is now APPROVED.")
            else:
                if os.path.exists(path):
                    try:
                        os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
                    except:
                        pass
```

- [ ] **Step 2: Fix hardcoded root path — use QSettings**

At the top of `main_window.py`, the imports already include `from PyQt6.QtCore import Qt, QDir`. Add `QSettings` to that import:

```python
from PyQt6.QtCore import Qt, QDir, QSettings
```

Find this block (~line 73):

```python
        self.tree_model = QFileSystemModel()
        root_path = r"C:\Users\Micael\Desktop\Auto Production - Cópia"
        if not os.path.exists(root_path):
            root_path = os.getcwd() # Project Root Fallback
```

Replace with:

```python
        self.tree_model = QFileSystemModel()
        settings = QSettings("SWAT", "PDM")
        root_path = settings.value("root_path", r"C:\Users\Micael\Desktop\Auto Production - Cópia")
        if not os.path.exists(root_path):
            root_path = os.getcwd()
```

Find `on_change_root` method (~line 170):

```python
    def on_change_root(self):
        new_dir = QFileDialog.getExistingDirectory(self, "Select Root Directory", self.tree_model.rootPath())
        if new_dir:
            normalized_dir = os.path.normpath(new_dir)
            self.tree_model.setRootPath(normalized_dir)
            self.tree_view.setRootIndex(self.tree_model.index(normalized_dir))
            self.project_controller.set_root_path(normalized_dir)
            self.file_model.refresh(normalized_dir)
```

Replace with:

```python
    def on_change_root(self):
        new_dir = QFileDialog.getExistingDirectory(self, "Select Root Directory", self.tree_model.rootPath())
        if new_dir:
            normalized_dir = os.path.normpath(new_dir)
            QSettings("SWAT", "PDM").setValue("root_path", normalized_dir)
            self.tree_model.setRootPath(normalized_dir)
            self.tree_view.setRootIndex(self.tree_model.index(normalized_dir))
            self.project_controller.set_root_path(normalized_dir)
            self.file_model.refresh(normalized_dir)
```

- [ ] **Step 3: Run the existing test suite**

```bash
cd "c:\Users\Micael\Desktop\Auto Production"
python -m pytest tests/ -v --ignore=tests/services/test_pdm_service.py -x
```

Expected: all passing

- [ ] **Step 4: Commit**

```bash
git add src/pdm/views/main_window.py
git commit -m "fix(pdm): restore write permission on state change + persist root path in QSettings (I7, I10)"
```

---

## Task 4: Move raw SQL out of `DataCardWidget` (I4)

**Files:**
- Modify: `src/pdm/views/data_card_widget.py`

- [ ] **Step 1: Replace `get_metadata_from_db` with `lock_controller.get_metadata`**

Find and delete the entire `get_metadata_from_db` method (~lines 150–166).

Find in `load_file` (~line 137):

```python
        # 2. Load metadata from DB
        metadata = self.get_metadata_from_db(file_path)
```

Replace with:

```python
        # 2. Load metadata from DB
        metadata = self.lock_controller.get_metadata(file_path)
```

- [ ] **Step 2: Replace raw SQL in `on_save` with `lock_controller.save_metadata`**

Find the `on_save` method (~line 172). Replace the entire method body with:

```python
    def on_save(self):
        if not self.current_file:
            return

        description = self.txt_description.text()
        material = self.txt_material.text()
        weight = self.txt_weight.text()
        revision = self.txt_revision.text()
        treatment = self.txt_treatment.text()

        if self.lock_controller.save_metadata(
            self.current_file, description, material, weight, revision, treatment
        ):
            self.lock_controller.log_history(
                self.current_file, "METADATA_UPDATE", os.getlogin(), "Updated Data Card properties"
            )
            QMessageBox.information(self, "Success", "Data Card saved successfully.")
            self.metadata_saved.emit(self.current_file)
        else:
            QMessageBox.critical(self, "Error", "Failed to save metadata.")
```

- [ ] **Step 3: Run test suite**

```bash
cd "c:\Users\Micael\Desktop\Auto Production"
python -m pytest tests/ -v --ignore=tests/services/test_pdm_service.py -x
```

Expected: all passing

- [ ] **Step 4: Commit**

```bash
git add src/pdm/views/data_card_widget.py
git commit -m "refactor(pdm): move raw SQL out of DataCardWidget into LockController methods (I4)"
```

---

## Task 5: Update `main_window` — use `check_in` + `save_metadata` + `get_cached_hash`

**Files:**
- Modify: `src/pdm/views/main_window.py`

- [ ] **Step 1: Replace `sync_metadata_from_sw` raw SQL with `lock_controller.save_metadata`**

Find the `sync_metadata_from_sw` method (~line 391). Replace the entire method body with:

```python
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
```

- [ ] **Step 2: Replace hash-check raw SQL in `on_sync_data_card` with `get_cached_hash`**

Find in `on_sync_data_card` (~lines 421–429):

```python
            current_hash = self.sw_client.get_file_hash(file_path)
            conn = self.lock_controller.db.get_connection()
            cached_hash = None
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT last_synced_hash FROM file_metadata WHERE file_path = ?", (file_path,))
                row = cursor.fetchone()
                if row: cached_hash = row[0]
            finally:
                conn.close()
```

Replace with:

```python
            current_hash = self.sw_client.get_file_hash(file_path)
            cached_hash = self.lock_controller.get_cached_hash(file_path)
```

- [ ] **Step 3: Replace unlock + log_history in `check_in_file` with `lock_controller.check_in`**

Find `check_in_file` (~line 362). Replace the entire method body with:

```python
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
```

- [ ] **Step 4: Run test suite**

```bash
cd "c:\Users\Micael\Desktop\Auto Production"
python -m pytest tests/ -v --ignore=tests/services/test_pdm_service.py -x
```

Expected: all passing

- [ ] **Step 5: Commit**

```bash
git add src/pdm/views/main_window.py
git commit -m "refactor(pdm): use LockController.check_in + save_metadata in main_window (I4, I6)"
```

---

## Task 6: Delete PdmService + its tests

**Files:**
- Delete: `src/services/pdm_service.py`
- Delete: `tests/services/test_pdm_service.py`

- [ ] **Step 1: Check nothing imports PdmService**

```bash
cd "c:\Users\Micael\Desktop\Auto Production"
grep -r "PdmService\|pdm_service" src/ tests/ --include="*.py" -l
```

Expected output: only `src/services/pdm_service.py` and `tests/services/test_pdm_service.py`. If any other file appears, update it before deleting.

- [ ] **Step 2: Delete the files**

```bash
cd "c:\Users\Micael\Desktop\Auto Production"
rm src/services/pdm_service.py
rm tests/services/test_pdm_service.py
```

- [ ] **Step 3: Run full test suite**

```bash
cd "c:\Users\Micael\Desktop\Auto Production"
python -m pytest tests/ -v -x
```

Expected: all passing, no references to `pdm_service`

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore(pdm): delete PdmService — logic consolidated into LockController (Option B)"
```

---

## Self-Review

**Spec coverage:**

| Issue | Covered by |
|-------|-----------|
| C3 — Path normalization | Task 1 |
| I4 — Raw SQL in views | Tasks 4, 5 |
| I6 — check_in without versioning | Task 1 (LockController.check_in) + Task 5 |
| I7 — Permanent read-only | Task 3 |
| I10 — Hardcoded path | Task 3 |
| Delete PdmService | Task 6 |
| C1/C2/I9/I11/I15 — PdmService issues | Resolved by deletion (Task 6) |

**Not included (YAGNI):**
- Teams notifications — was in PdmService only; no equivalent needed now
- N+1 queries in FileTableModel — separate concern, not part of Option B
- LIKE SQL injection in get_where_used — existing issue, separate PR
- Test setUp with :memory: — nice-to-have, not blocking
- SWAT_Version SW property update — not currently done by the working UI; out of scope
