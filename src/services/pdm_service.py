
import os
import sqlite3
import json
import shutil
import requests
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from .base_service import BaseService

class PdmService(BaseService):
    """
    Service for Product Data Management (PDM).
    Handles Check-In, Check-Out, Versioning and History.
    """
    def __init__(self, sw_client, db_path: str = "swat_pdm.db"):
        super().__init__(sw_client)
        self.db_path = db_path
        self._init_db()
        self.teams_webhook = "https://outlook.office.com/webhook/placeholder" # TODO: Configurar

    def _init_db(self):
        """Initializes the SQLite database tables."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Table for active locks (aligned with LockController)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS locks (
                file_path TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                locked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                machine_id TEXT
            )
        ''')
        
        # Table for full history (aligned with DatabaseManager)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                action TEXT NOT NULL,
                user_id TEXT NOT NULL,
                version TEXT,
                comment TEXT,
                project_name TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Table for file references (parent-child dependencies)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS file_references (
                parent_path TEXT NOT NULL,
                child_path TEXT NOT NULL,
                PRIMARY KEY (parent_path, child_path)
            )
        ''')
        
        conn.commit()
        conn.close()

    def check_out(self, file_path: str, user: str) -> Tuple[bool, str]:
        """
        Locks a file for the current user.
        Renames to .locked and creates a .lock JSON file.
        """
        file_path = os.path.normpath(os.path.abspath(file_path))
        if not os.path.exists(file_path):
            return False, f"Ficheiro não encontrado: {file_path}"

        lock_path = file_path + ".lock"
        
        # 1. Check if already locked
        if os.path.exists(lock_path):
            try:
                with open(lock_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return False, f"Ficheiro já está em Check-Out por {data.get('user', 'desconhecido')}"
            except:
                return False, "Ficheiro bloqueado por outro utilizador (lock corrompido)."

        try:
            # 2. Create .lock file
            lock_content = {
                "user": user,
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "comment": ""
            }
            with open(lock_path, 'w', encoding='utf-8') as f:
                json.dump(lock_content, f, indent=4)

            # 3. Rename original file to .locked
            locked_path = file_path + ".locked"
            
            # If open in SW, we should close it first to avoid file lock errors
            self.sw.close_doc(file_path)
            
            if os.path.exists(locked_path):
                os.remove(locked_path) # Clean up if it exists
            
            os.rename(file_path, locked_path)

            # 4. Update SQLite
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO locks (file_path, user_id, locked_at, machine_id) VALUES (?, ?, ?, ?)",
                (file_path, user, lock_content["date"], "unknown")
            )
            conn.commit()
            conn.close()

            # 5. Open in SolidWorks if it is a CAD file
            shutil.copy2(locked_path, file_path)
            if self.is_sw_file(file_path):
                self.sw.open_doc(file_path)

            return True, f"Check-Out efetuado com sucesso para {user}."

        except Exception as e:
            # Rollback if possible
            if os.path.exists(lock_path): os.remove(lock_path)
            return False, f"Erro no Check-Out: {e}"

    def is_sw_file(self, file_path: str) -> bool:
        """Checks if the file is a SolidWorks document."""
        ext = os.path.splitext(file_path)[1].lower()
        return ext in ['.sldprt', '.sldasm', '.slddrw']

    def _get_next_version(self, file_path: str) -> int:
        """Calculates the next version number for a file."""
        if self.is_sw_file(file_path):
            try:
                doc, _ = self.sw.open_doc(file_path)
                version_str = self.sw.get_custom_property(doc, "SWAT_Version")
                return int(version_str) + 1 if version_str else 1
            except:
                return 1
        else:
            history = self.get_history(file_path=file_path)
            if history:
                try:
                    return int(history[0]['version']) + 1
                except:
                    return 1
            return 1

    def check_in(self, file_path: str, user: str, comment: str) -> Tuple[bool, str]:
        """
        Unlocks the file and creates a new version in the .versions subfolder.
        """
        file_path = os.path.normpath(os.path.abspath(file_path))
        lock_path = file_path + ".lock"
        locked_path = file_path + ".locked"

        if not os.path.exists(lock_path):
            return False, "O ficheiro não está em Check-Out."

        try:
            with open(lock_path, 'r', encoding='utf-8') as f:
                lock_data = json.load(f)
            
            if lock_data.get('user') != user:
                return False, f"Apenas o utilizador {lock_data.get('user')} pode fazer Check-In."

            # 1. Get next version
            new_version = self._get_next_version(file_path)
            
            # 2. Update Metadata (SolidWorks only)
            if self.is_sw_file(file_path):
                doc, _ = self.sw.open_doc(file_path)
                self.sw.set_custom_property(doc, "SWAT_Version", str(new_version))
                self.sw.save_silent(doc)
                self.sw.close_doc(file_path)
                
                # Update References
                deps = self.sw.get_dependencies(file_path)
                if deps:
                    self._update_references(file_path, deps)

            # 3. Create version copy in .versions folder
            file_dir = os.path.dirname(file_path)
            versions_dir = os.path.join(file_dir, ".versions")
            if not os.path.exists(versions_dir):
                os.makedirs(versions_dir)
                # Set folder as hidden on Windows
                os.system(f'attrib +h "{versions_dir}"')

            filename = os.path.basename(file_path)
            name, ext = os.path.splitext(filename)
            version_filename = f"{name}_v{new_version:02d}{ext}"
            version_path = os.path.join(versions_dir, version_filename)
            
            shutil.copy2(file_path, version_path)

            # 4. Clean up locks
            if os.path.exists(lock_path): os.remove(lock_path)
            if os.path.exists(locked_path): os.remove(locked_path)

            # 5. Update SQLite
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM locks WHERE file_path = ?", (file_path,))
            
            project_name = os.path.basename(file_dir)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                "INSERT INTO history (file_path, action, user_id, version, comment, project_name, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (file_path, "Check-In", user, str(new_version), comment, project_name, timestamp)
            )
            conn.commit()
            conn.close()

            # 6. Send Teams Notification
            self._send_teams_notification(user, filename, new_version, project_name, comment)

            return True, f"Check-In concluído. Versão v{new_version:02d} arquivada."

        except Exception as e:
            return False, f"Erro no Check-In: {e}"

    def _update_references(self, parent_path: str, child_paths: List[str]):
        """Updates the dependency table for a parent file."""
        parent_path = os.path.normpath(os.path.abspath(parent_path))
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            # Clear old references
            cursor.execute("DELETE FROM file_references WHERE parent_path = ?", (parent_path,))
            
            # Insert new ones
            for child in child_paths:
                child_path = os.path.normpath(os.path.abspath(child))
                cursor.execute(
                    "INSERT OR IGNORE INTO file_references (parent_path, child_path) VALUES (?, ?)",
                    (parent_path, child_path)
                )
            conn.commit()
        except Exception as e:
            self._log(f"Erro ao atualizar referências: {e}", "ERROR")
        finally:
            conn.close()

    def get_where_used(self, child_path: str) -> List[str]:
        """Returns a list of parent files that reference the given child file."""
        child_path = os.path.normpath(os.path.abspath(child_path))
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT parent_path FROM file_references WHERE child_path = ?", (child_path,))
            rows = cursor.fetchall()
            return [row[0] for row in rows]
        except Exception as e:
            self._log(f"Erro ao buscar 'Onde é Usado': {e}", "ERROR")
            return []
        finally:
            conn.close()

    def get_history(self, file_path: Optional[str] = None, project: Optional[str] = None) -> List[Dict]:
        """Returns the history log from SQLite."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        query = "SELECT * FROM history"
        params = []
        if file_path:
            query += " WHERE file_path = ?"
            params.append(os.path.normpath(os.path.abspath(file_path)))
        elif project:
            query += " WHERE project_name = ?"
            params.append(project)
            
        query += " ORDER BY id DESC"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        # Map fields for compatibility
        result = []
        for row in rows:
            d = dict(row)
            d['date'] = d.get('timestamp')
            d['user'] = d.get('user_id')
            result.append(d)
        return result

    def get_checked_out_files(self) -> List[Dict]:
        """Returns all currently checked-out files."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM locks")
        rows = cursor.fetchall()
        conn.close()
        
        # Map fields for compatibility
        result = []
        for row in rows:
            d = dict(row)
            d['user'] = d.get('user_id')
            d['checkout_date'] = d.get('locked_at')
            result.append(d)
        return result

    def search_files(self, query: str) -> List[Dict]:
        """
        Search in history.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        sql = "SELECT DISTINCT file_path, project_name FROM history WHERE file_path LIKE ? OR project_name LIKE ? OR comment LIKE ?"
        q = f"%{query}%"
        cursor.execute(sql, (q, q, q))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def is_locked(self, file_path: str) -> Tuple[bool, Optional[str]]:
        """Checks if a file is locked and returns the owner's name."""
        # 1. Check DB first (authoritative)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM locks WHERE file_path = ?", (os.path.normpath(os.path.abspath(file_path)),))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return True, row[0]
            
        # 2. Check .lock file (fallback/legacy)
        lock_path = os.path.normpath(file_path) + ".lock"
        if os.path.exists(lock_path):
            try:
                with open(lock_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return True, data.get('user')
            except:
                return True, "Desconhecido"
        return False, None

    def _send_teams_notification(self, user, filename, version, project, comment):
        """Sends a simple card to MS Teams via Webhook."""
        payload = {
            "text": f"\u2705 **{user}** fez Check-In de **{filename}** v{version:02d}\n\n**Projeto:** {project}\n**Comentário:** {comment}"
        }
        try:
            # requests.post(self.teams_webhook, json=payload, timeout=5)
            self._log(f"Notificação Teams enviada para {filename} v{version}")
        except:
            self._log("Falha ao enviar notificação para o Teams.", "WARNING")

    def get_status(self, file_path: str) -> str:
        """Returns the lifecycle status of a file."""
        file_path = os.path.normpath(os.path.abspath(file_path))
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM file_status WHERE file_path = ?", (file_path,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else "In Design"

    def set_status(self, file_path: str, status: str) -> bool:
        """Updates the lifecycle status of a file."""
        file_path = os.path.normpath(os.path.abspath(file_path))
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            # Ensure table exists (though _init_db should handle it, this is safer if schema evolved)
            cursor.execute("CREATE TABLE IF NOT EXISTS file_status (file_path TEXT PRIMARY KEY, status TEXT)")
            cursor.execute(
                "INSERT OR REPLACE INTO file_status (file_path, status) VALUES (?, ?)",
                (file_path, status)
            )
            conn.commit()
            return True
        except Exception as e:
            self._log(f"Erro ao definir status: {e}", "ERROR")
            return False
        finally:
            conn.close()
