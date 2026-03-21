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

    def lock_file(self, file_path, user_id=None):
        if user_id is None:
            user_id = getpass.getuser()
        machine_id = socket.gethostname()
        
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
            return True
        except Exception:
            return False
        finally:
            conn.close()

    def unlock_file(self, file_path, user_id=None):
        if user_id is None:
            user_id = getpass.getuser()
            
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM locks WHERE file_path = ? AND user_id = ?", (file_path, user_id))
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
        cursor.execute("SELECT file_path, locked_at FROM locks WHERE user_id = ?", (user_id,))
        rows = cursor.fetchall()
        conn.close()
        return [{"file_path": r[0], "locked_at": r[1]} for r in rows]
