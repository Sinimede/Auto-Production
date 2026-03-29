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


if __name__ == "__main__":
    unittest.main()
