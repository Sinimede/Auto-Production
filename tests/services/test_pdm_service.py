
import os
import unittest
from unittest.mock import MagicMock
import shutil
import sqlite3
from src.services.pdm_service import PdmService

class TestPdmService(unittest.TestCase):
    def setUp(self):
        self.db_path = "test_pdm.db"
        self.sw_mock = MagicMock()
        # open_doc must return (doc, was_opened)
        self.sw_mock.open_doc.return_value = (MagicMock(), False)
        self.service = PdmService(self.sw_mock, db_path=self.db_path)
        self.test_file = "test_document.txt"
        with open(self.test_file, "w") as f:
            f.write("test content")
        
    def tearDown(self):
        if os.path.exists(self.test_file):
            os.remove(self.test_file)
        if os.path.exists(self.test_file + ".lock"):
            os.remove(self.test_file + ".lock")
        if os.path.exists(self.test_file + ".locked"):
            os.remove(self.test_file + ".locked")
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        # Clean up .versions folder
        if os.path.exists(".versions"):
            shutil.rmtree(".versions")

    def test_check_in_non_cad_file(self):
        """
        Test that checking in a non-CAD file (like .txt) works without SolidWorks logic.
        """
        user = "test_user"
        
        # 1. Check-Out first
        success, msg = self.service.check_out(self.test_file, user)
        self.assertTrue(success, msg)
        
        # 2. Check-In
        success, msg = self.service.check_in(self.test_file, user, "first version")
        
        self.assertTrue(success, f"Check-in failed: {msg}")
        self.assertFalse(self.sw_mock.open_doc.called, "SolidWorks should not be called for .txt files")

    def test_check_in_version_increment(self):
        """
        Test that checking in a non-CAD file multiple times increments the version in history.
        """
        user = "test_user"
        
        # Version 1
        self.service.check_out(self.test_file, user)
        self.service.check_in(self.test_file, user, "v1")
        
        # Version 2
        with open(self.test_file, "w") as f: f.write("new content")
        self.service.check_out(self.test_file, user)
        self.service.check_in(self.test_file, user, "v2")
        
        history = self.service.get_history(file_path=self.test_file)
        print(f"\nDebug History: {history}")
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]['version'], "2") 
        
        # Check if files are in .versions
        self.assertTrue(os.path.exists(".versions/test_document_v01.txt"))
        self.assertTrue(os.path.exists(".versions/test_document_v02.txt"))

    def test_check_in_assembly_references(self):
        """
        Test that checking in a SolidWorks assembly tracks its dependencies.
        """
        asm_file = "assembly.sldasm"
        part_file = os.path.abspath("part.sldprt")
        with open(asm_file, "w") as f: f.write("asm")
        
        # Mock SW to return dependencies
        self.sw_mock.get_dependencies.return_value = [part_file]
        
        user = "test_user"
        self.service.check_out(asm_file, user)
        success, msg = self.service.check_in(asm_file, user, "asm version")
        self.assertTrue(success, msg)
        
        # Verify references in DB
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT child_path FROM file_references WHERE parent_path = ?", (os.path.abspath(asm_file),))
        row = cursor.fetchone()
        conn.close()
        
        self.assertIsNotNone(row)
        self.assertEqual(row[0], part_file)
        
        if os.path.exists(asm_file): os.remove(asm_file)
        if os.path.exists(asm_file + ".lock"): os.remove(asm_file + ".lock")

    def test_get_where_used(self):
        """
        Test that get_where_used returns all parent files that reference a child.
        """
        asm_file = os.path.abspath("main_assembly.sldasm")
        part_file = os.path.abspath("component.sldprt")
        
        # Manually insert reference for testing
        self.service._update_references(asm_file, [part_file])
        
        parents = self.service.get_where_used(part_file)
        self.assertIn(asm_file, parents)

if __name__ == "__main__":
    unittest.main()
