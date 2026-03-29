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
