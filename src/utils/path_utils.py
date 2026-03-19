
import os
import sys

def normalize_path(path):
    """
    Normalizes a file system path for consistency.
    Converts to absolute path and normalizes separators.
    """
    if not path:
        return ""
    return os.path.normpath(os.path.abspath(path))

def get_project_root():
    """Returns the absolute path to the project root directory."""
    if getattr(sys, "frozen", False):
        # PyInstaller exe: root is where the .exe is
        return os.path.dirname(sys.executable)
    
    # Development: Assuming this file is in src/utils/
    current_file = os.path.abspath(__file__)
    # Go up two levels (src/utils/ -> src/ -> project_root)
    return os.path.dirname(os.path.dirname(os.path.dirname(current_file)))

def get_assets_dir():
    """Returns the path to the assets directory (formerly Templates)."""
    return os.path.join(get_project_root(), "assets")

def get_templates_dir():
    """Alias for get_assets_dir for backward compatibility."""
    return get_assets_dir()

def get_temp_dir():
    """Returns the path to the .tmp directory, creating it if necessary."""
    temp_dir = os.path.join(get_project_root(), ".tmp")
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
    return temp_dir
