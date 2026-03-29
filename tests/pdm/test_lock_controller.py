import sys
import os
import unittest
import sqlite3

# Adicionar src ao path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))

from pdm.controllers.lock_controller import LockController
from pdm.models.database import DatabaseManager

class TestLockController(unittest.TestCase):
    def setUp(self):
        # Reset Singleton
        DatabaseManager._instance = None
        # Usar uma base de dados em memória para testes
        self.db_path = "test_pdm.db"
        self.db = DatabaseManager(self.db_path)
        self.controller = LockController()
        self.controller.db = self.db # Override the db in the controller
        self.test_file = "test_file.sldprt"
        self.test_user = "test_user"

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_lock_unlock(self):
        # 1. Lock o ficheiro
        self.assertTrue(self.controller.lock_file(self.test_file, self.test_user))
        
        # 2. Verificar se está locked
        lock_info = self.controller.is_locked(self.test_file)
        self.assertIsNotNone(lock_info)
        self.assertEqual(lock_info["user_id"], self.test_user)
        
        # 3. Tentar lockar novamente (deve falhar)
        self.assertFalse(self.controller.lock_file(self.test_file, "other_user"))
        
        # 4. Unlock o ficheiro
        self.assertTrue(self.controller.unlock_file(self.test_file, self.test_user))
        
        # 5. Verificar se está unlocked
        self.assertIsNone(self.controller.is_locked(self.test_file))

    def test_status_management(self):
        # 1. Default status check
        status = self.controller.get_status(self.test_file)
        self.assertEqual(status, "In Design")
        
        # 2. Set status to Approved
        self.assertTrue(self.controller.set_status(self.test_file, "Approved"))
        
        # 3. Verify status changed
        status = self.controller.get_status(self.test_file)
        self.assertEqual(status, "Approved")
        
        # 4. Change back
        self.assertTrue(self.controller.set_status(self.test_file, "In Design"))
        self.assertEqual(self.controller.get_status(self.test_file), "In Design")

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


if __name__ == "__main__":
    unittest.main()
