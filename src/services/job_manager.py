
import threading
import time
from typing import List, Callable, Dict, Optional

class JobManager:
    """
    Orchestrates multiple export services in sequence.
    Handles global cancellation and progress tracking.
    """
    def __init__(self, services: Dict[str, any]):
        self.services = services
        self._stop_event = threading.Event()
        self._is_running = False
        self._current_service = None
        self._on_progress: Optional[Callable[[float, str], None]] = None

    def set_progress_callback(self, callback: Callable[[float, str], None]):
        self._on_progress = callback

    def _report_progress(self, percent: float, message: str):
        if self._on_progress:
            self._on_progress(percent, message)

    def run_sequence(self, asm_path: str, output_dir: str, config: Dict[str, any], on_finish_all: Callable = None):
        """Runs DXF, STEP and BOM in order."""
        if self._is_running:
            return
        
        self._is_running = True
        self._stop_event.clear()
        
        def _execute():
            try:
                # Calculate weights for progress (simple 33% each if enabled)
                steps = []
                if config.get('dxf', {}).get('enabled'): steps.append('dxf')
                if config.get('step', {}).get('enabled'): steps.append('step')
                if config.get('listas', {}).get('enabled'): steps.append('listas')
                
                total_steps = len(steps)
                if total_steps == 0:
                    self._report_progress(100, "Nada para processar.")
                    return

                for i, step in enumerate(steps):
                    if self._stop_event.is_set():
                        break
                    
                    start_pct = (i / total_steps) * 100
                    end_pct = ((i + 1) / total_steps) * 100
                    
                    msg = f"A processar {step.upper()}..."
                    self._report_progress(start_pct, msg)
                    
                    if step == 'dxf':
                        dxf_cfg = config.get('dxf', {})
                        self._run_service_sync(
                            self.services['dxf'], 
                            asm_path, 
                            output_dir, 
                            dxf_cfg.get('selected_processes', {'laser': True, 'protecoes': True}),
                            dxf_cfg.get('gen_excel', True)
                        )
                    elif step == 'step':
                        step_cfg = config.get('step', {})
                        self._run_service_sync(
                            self.services['step'], 
                            asm_path, 
                            output_dir,
                            step_cfg.get('selected_processes', {'router': True, 'cnc': True, 'torno': True}),
                            step_cfg.get('gen_excel', True)
                        )
                    elif step == 'listas':
                        listas_cfg = config.get('listas', {})
                        self._run_service_sync(
                            self.services['listas'], 
                            asm_path, 
                            output_dir,
                            listas_cfg.get('include_bom', True),
                            listas_cfg.get('include_perfis', True)
                        )
                    
                    self._report_progress(end_pct, f"{step.upper()} Concluído.")

                if self._stop_event.is_set():
                    self._report_progress(100, "Cancelado pelo utilizador.")
                else:
                    self._report_progress(100, "Processo completo.")

            except Exception as e:
                if self.services['dxf']._callbacks.get('log'):
                    self.services['dxf']._callbacks['log'](f"Erro no JobManager: {e}", "ERROR")
            finally:
                self._is_running = False
                if on_finish_all:
                    on_finish_all()

        threading.Thread(target=_execute, daemon=True).start()

    def _run_service_sync(self, service, *args):
        """
        Runs a service and waits for it to finish.
        """
        self._current_service = service
        finished = threading.Event()
        original_finish = service._callbacks.get('finish')
        
        def wrapped_finish(ok, err):
            if original_finish: original_finish(ok, err)
            finished.set()
            
        service.set_callbacks(on_finish=wrapped_finish)
        
        # Start the service
        if service == self.services['dxf']:
            service.run_export(*args)
        elif service == self.services['step']:
            service.run_export(*args)
        elif service == self.services['listas']:
            service.run_generate(*args)
            
        # Wait for finish OR stop event
        while not finished.is_set() and not self._stop_event.is_set():
            time.sleep(0.1)
            
        # If stopped, tell the service to stop too
        if self._stop_event.is_set():
            service.stop()
        
        self._current_service = None

    def stop(self):
        self._stop_event.set()
        if self._current_service:
            self._current_service.stop()
        self._is_running = False
