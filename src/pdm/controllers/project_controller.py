import os
import shutil
from ..models.database import get_db

class ProjectController:
    def __init__(self, root_path=None):
        self.db = get_db()
        self.root_path = root_path or os.getcwd()

    def set_root_path(self, new_path):
        if os.path.exists(new_path):
            self.root_path = new_path
            print(f"DEBUG: ProjectController root_path updated to: {self.root_path}")

    def create_project(self, client, name, order_num):
        project_folder_name = f"{client}_{name}_{order_num}"
        project_path = os.path.join(self.root_path, project_folder_name)
        
        if os.path.exists(project_path):
            raise Exception(f"Project folder already exists: {project_folder_name}")
            
        try:
            # Create Folder Structure
            os.makedirs(os.path.join(project_path, "01-Engineering"))
            os.makedirs(os.path.join(project_path, "02-Production"))
            os.makedirs(os.path.join(project_path, "03-Documentation"))
            
            # Copy Templates from assets if they exist
            assets_path = os.path.join(self.root_path, "assets")
            # In a real scenario, we'd copy specific .prtdot/.asmdot files
            # For now, let's just ensure the folders exist
            
            # Register in Database
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO projects (name, path) VALUES (?, ?)",
                (project_folder_name, project_path)
            )
            conn.commit()
            conn.close()
            
            return project_path
        except Exception as e:
            if os.path.exists(project_path):
                shutil.rmtree(project_path)
            raise e
