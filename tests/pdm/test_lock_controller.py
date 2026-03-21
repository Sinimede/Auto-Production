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

if __name__ == "__main__":
    unittest.main()
