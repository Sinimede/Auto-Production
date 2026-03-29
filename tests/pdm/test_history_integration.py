import sys
import os
import unittest
import sqlite3
from datetime import datetime

# Adicionar src ao path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))

from pdm.models.database import DatabaseManager

class TestHistoryIntegration(unittest.TestCase):
    def setUp(self):
        # Reset Singleton
        DatabaseManager._instance = None
        self.db_path = "test_pdm_history.db"
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        self.db = DatabaseManager(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_history_insertion_and_retrieval(self):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        file_path = "test_part.sldprt"
        user_id = "tester"
        action = "CHECKIN"
        comment = "Initial commit"
        
        # 1. Simulate Check-In insertion (logic from main_window.py)
        cursor.execute(
            "INSERT INTO history (file_path, action, user_id, comment) VALUES (?, ?, ?, ?)",
            (file_path, action, user_id, comment)
        )
        conn.commit()
        
        # 2. Verify record exists
        cursor.execute("SELECT * FROM history WHERE file_path = ?", (file_path,))
        row = cursor.fetchone()
        
        self.assertIsNotNone(row)
        # Schema: id, file_path, action, user_id, version, comment, project_name, timestamp
        self.assertEqual(row[1], file_path)
        self.assertEqual(row[2], action)
        self.assertEqual(row[3], user_id)
        self.assertEqual(row[5], comment)
        
        conn.close()

if __name__ == "__main__":
    unittest.main()
