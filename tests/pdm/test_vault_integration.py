
import os
import shutil
import sqlite3
import unittest
from src.services.pdm_service import PdmService
from src.core.solidworks import SolidWorksClient

class TestVaultIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create a clean test environment
        cls.test_dir = os.path.abspath(".tmp/test_vault")
        if os.path.exists(cls.test_dir):
            shutil.rmtree(cls.test_dir)
        os.makedirs(cls.test_dir)
        
        cls.db_path = os.path.join(cls.test_dir, "test_pdm.db")
        # Initialize service (we use a mock or headless SW client if possible, 
        # but for non-CAD files it won't even call SW)
        cls.sw = SolidWorksClient() # head-less or just not connected
        cls.pdm = PdmService(cls.sw, db_path=cls.db_path)

    def test_01_non_cad_lifecycle(self):
        """Tests Check-In/Check-Out of a non-CAD file (TXT)."""
        file_path = os.path.join(self.test_dir, "manual_instrucoes.txt")
        with open(file_path, "w") as f:
            f.write("Conteúdo inicial do manual.")
            
        print(f"\n[TEST] A testar ficheiro não-CAD: {os.path.basename(file_path)}")
        
        # 1. Check-Out
        user = "TestUser"
        success, msg = self.pdm.check_out(file_path, user)
        self.assertTrue(success, f"Check-Out falhou: {msg}")
        self.assertTrue(os.path.exists(file_path + ".lock"), "Ficheiro .lock não criado.")
        self.assertTrue(os.path.exists(file_path + ".locked"), "Ficheiro .locked não criado.")
        
        # 2. Check-In (Version 1)
        comment = "Primeira versão do manual."
        success, msg = self.pdm.check_in(file_path, user, comment)
        self.assertTrue(success, f"Check-In falhou: {msg}")
        
        # 3. Verify .versions folder
        versions_dir = os.path.join(self.test_dir, ".versions")
        self.assertTrue(os.path.exists(versions_dir), "Pasta .versions não criada.")
        
        versioned_file = os.path.join(versions_dir, "manual_instrucoes_v01.txt")
        self.assertTrue(os.path.exists(versioned_file), "Ficheiro versionado v01 não encontrado.")
        
        # 4. Check SQL History
        history = self.pdm.get_history(file_path=file_path)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['version'], "1")
        self.assertEqual(history[0]['comment'], comment)
        print(" -> Sucesso: Ficheiro TXT versionado e registado no SQL.")

    def test_02_where_used_indexing(self):
        """Tests the dependency tracking (Where Used) via SQL."""
        parent = os.path.join(self.test_dir, "Montagem_Principal.SLDASM")
        child = os.path.join(self.test_dir, "Peca_Base.SLDPRT")
        
        print(f"\n[TEST] A testar 'Onde é Usado' para: {os.path.basename(child)}")
        
        # Simulate SolidWorks reference extraction
        # (In real usage, this happens during Check-In of the assembly)
        self.pdm._update_references(parent, [child])
        
        # Verify
        parents = self.pdm.get_where_used(child)
        self.assertIn(parent, parents)
        self.assertEqual(len(parents), 1)
        print(f" -> Sucesso: Vinculação SQL confirmada. {os.path.basename(child)} é usado em {os.path.basename(parent)}.")

    def test_03_global_locks_view(self):
        """Tests if the dashboard can see all active locks."""
        file2 = os.path.join(self.test_dir, "outro_ficheiro.pdf")
        with open(file2, "w") as f: f.write("PDF data")
        
        self.pdm.check_out(file2, "OutroUser")
        
        locks = self.pdm.get_checked_out_files()
        self.assertGreaterEqual(len(locks), 1)
        users = [l['user'] for l in locks]
        self.assertIn("OutroUser", users)
        print(f" -> Sucesso: Dashboard consegue listar {len(locks)} bloqueios ativos.")

if __name__ == "__main__":
    unittest.main()
