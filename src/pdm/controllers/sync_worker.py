from PyQt6.QtCore import QThread, pyqtSignal, QObject
import os
import pythoncom
from src.core.solidworks import SolidWorksClient

class SyncWorker(QObject):
    finished = pyqtSignal(str, dict) # Path, ResultProps
    error = pyqtSignal(str, str) # Path, ErrorMsg
    progress = pyqtSignal(str, int, int) # Path, Current, Total

    def __init__(self, file_paths, lock_controller):
        super().__init__()
        self.file_paths = file_paths
        self.lock_controller = lock_controller
        self.is_cancelled = False

    def run(self):
        pythoncom.CoInitialize()
        try:
            sw_client = SolidWorksClient()
            total = len(self.file_paths)
            
            for i, path in enumerate(self.file_paths):
                if self.is_cancelled: break
                
                self.progress.emit(path, i + 1, total)
                try:
                    # 1. Check Hash
                    current_hash = sw_client.get_file_hash(path)
                    
                    # 2. Get Sync Logic
                    props = self._sync_file(sw_client, path)
                    
                    if props:
                        self.finished.emit(path, props)
                except Exception as e:
                    self.error.emit(path, str(e))
        finally:
            pythoncom.CoUninitialize()

    def _sync_file(self, sw_client, file_path):
        # 1. Hashing Check (Avoid work if file hasn't changed)
        # We don't have DB access directly for cache check here easily without thread safety,
        # but we can pass the hash back or do it in the worker.
        
        # 2. Check if file is open in SW
        is_open = False
        try:
            if not sw_client.sw: sw_client.connect()
            is_open = sw_client.sw.GetOpenDocumentByName(file_path) is not None
        except: pass

        if not is_open:
            # 3. Use Fast Method (olefile) for closed files
            props = sw_client.get_custom_properties_fast(file_path)
            if props and len(props) >= 3:
                return props

        # 4. Fallback to Slow Method (SolidWorks COM)
        if not sw_client.sw:
            sw_client.connect()

        return sw_client.get_custom_properties(file_path)

    def cancel(self):
        self.is_cancelled = True
