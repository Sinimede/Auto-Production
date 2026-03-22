import os
import getpass
import socket
from ..models.database import get_db

class LockController:
    def __init__(self):
        self.db = get_db()

    def is_locked(self, file_path):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, locked_at, machine_id FROM locks WHERE file_path = ?", (file_path,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {
                "user_id": row[0],
                "locked_at": row[1],
                "machine_id": row[2]
            }
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

    def get_file_metadata(self, file_path):
        """Retrieve current metadata for a file."""
        file_path = os.path.normpath(os.path.abspath(file_path))
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT version, revision, last_synced_hash FROM file_metadata WHERE file_path = ?", (file_path,))
            row = cursor.fetchone()
            if row:
                return {"version": row[0], "revision": row[1], "hash": row[2]}
            return {"version": 1, "revision": "00", "hash": None}
        finally:
            conn.close()

    def increment_version(self, file_path):
        """Increment the version number in the database."""
        file_path = os.path.normpath(os.path.abspath(file_path))
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO file_metadata (file_path, version) VALUES (?, 2) "
                "ON CONFLICT(file_path) DO UPDATE SET version = version + 1",
                (file_path,)
            )
            conn.commit()
            
            # Return new version
            cursor.execute("SELECT version FROM file_metadata WHERE file_path = ?", (file_path,))
            return cursor.fetchone()[0]
        finally:
            conn.close()

    def lock_file(self, file_path, user_id=None):
        if user_id is None:
            user_id = getpass.getuser()
        machine_id = socket.gethostname()
        
        file_path = os.path.normpath(file_path)
        
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
        
        file_path = os.path.normpath(file_path)
            
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM locks WHERE file_path = ? AND user_id = ?", (file_path, user_id))
            if cursor.rowcount > 0:
                conn.commit()
                # Note: Unlock (Check-In) is logged in main_window.py with a comment
                return True
            return False
        finally:
            conn.close()

    def get_user_locks(self, user_id=None):
        if user_id is None:
            user_id = getpass.getuser()
            
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT file_path, locked_at FROM locks WHERE user_id = ?", (user_id,))
        rows = cursor.fetchall()
        conn.close()
        return [{"file_path": r[0], "locked_at": r[1]} for r in rows]

    def get_status(self, file_path):
        file_path = os.path.normpath(file_path)
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM file_status WHERE file_path = ?", (file_path,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else "In Design"

    def set_status(self, file_path, status):
        file_path = os.path.normpath(file_path)
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
        """Update the references in the database (parent-child dependencies)."""
        parent_path = os.path.normpath(os.path.abspath(parent_path))
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            # Clear old references for this parent
            cursor.execute("DELETE FROM file_references WHERE parent_path = ?", (parent_path,))
            
            # Insert new ones
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
        """Find all files that reference the given file (Where Used)."""
        file_path = os.path.normpath(os.path.abspath(file_path))
        file_name = os.path.basename(file_path)
        # Get name without extension (e.g., '18026.100.001' instead of '18026.100.001.SLDPRT')
        name_no_ext = os.path.splitext(file_name)[0]
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # 1. Try exact path match
        cursor.execute("SELECT parent_path FROM file_references WHERE child_path = ?", (file_path,))
        rows = cursor.fetchall()
        
        # 2. Try matching by base name (without extension)
        if not rows:
            # This covers cases where SW returns dependencies without extension or from a different root folder
            query = "SELECT parent_path FROM file_references WHERE child_path LIKE ? OR child_path LIKE ?"
            cursor.execute(query, (f"%{file_name}", f"%{name_no_ext}"))
            rows = cursor.fetchall()
            
        conn.close()
        # Return unique parent names/paths
        return list(set(row[0] for row in rows))
