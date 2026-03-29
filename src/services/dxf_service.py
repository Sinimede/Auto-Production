
import os
from .base_service import BaseService
from .validation_service import ValidationService
from src.utils.dxf_cleaner import clean_dxf
from src.utils.excel_writer import generate_excel, PROCESS_CONFIG
from src.utils.path_utils import normalize_path

class DxfService(BaseService):
    """
    Service for orchestrating DXF exports.
    """
    def __init__(self, sw_client):
        super().__init__(sw_client)
        self.validator = ValidationService(log_fn=self._log)

    def run_export(self, asm_path: str, out_dir: str, selected_processes: dict, gen_excel: bool):
        """Starts the DXF export process in a background thread."""
        self.run_async(self._worker, asm_path, out_dir, selected_processes, gen_excel)

    def _worker(self, asm_path, out_dir, selected, gen_excel):
        ok_count = 0
        err_count = 0
        asm_doc = None
        was_opened_by_us = False

        try:
            self._log("\u2550" * 68)
            self._log("Serviço de Exportação DXF")
            self._set_status("A conectar ao SolidWorks...")
            self.sw.connect()

            self._log(f"A abrir assembly: {os.path.basename(asm_path)}")
            asm_doc, was_opened_by_us = self.sw.open_assembly_resolved(asm_path)

            self._log("A percorrer componentes...")
            all_parts = self.sw.get_all_parts(asm_doc)
            
            laser_parts = []
            protecoes_parts = []
            
            if selected.get('laser'):
                laser_parts = [p for p in all_parts if self.sw.is_laser_part(p)]
            if selected.get('protecoes'):
                protecoes_parts = [p for p in all_parts if self.sw.is_protecoes_part(p)]

            total = len(laser_parts) + len(protecoes_parts)
            self._log(f"  Peças a exportar: {total}")
            self._log("\u2500" * 68)

            if total == 0:
                self._log("Nenhuma peça encontrada para os processos selecionados.")
                self._finish(0, 0)
                return

            self._set_progress(0, total)
            progress_i = 0

            self._stop_event.clear()

            # Process Laser
            if laser_parts:
                self._log("  Processo: Laser")
                for part in laser_parts:
                    if self._stop_event.is_set():
                        self._log("Operação cancelada pelo utilizador.")
                        self._finish(ok_count, err_count)
                        return

                    success, msg = self._export_one(part, out_dir)
                    if success: ok_count += 1
                    else: err_count += 1
                    progress_i += 1
                    self._set_progress(progress_i, total)
                    self._log(msg)

            # Process Protecoes
            if protecoes_parts:
                self._log("  Processo: Proteções")
                for part in protecoes_parts:
                    if self._stop_event.is_set():
                        self._log("Operação cancelada pelo utilizador.")
                        self._finish(ok_count, err_count)
                        return

                    success, msg = self._export_one(part, out_dir)
                    if success: ok_count += 1
                    else: err_count += 1
                    progress_i += 1
                    self._set_progress(progress_i, total)
                    self._log(msg)

            # Generate Excel
            if gen_excel:
                from src.utils.path_utils import get_assets_dir
                if laser_parts:
                    self._generate_excel_report("laser", laser_parts, all_parts, out_dir)
                if protecoes_parts:
                    self._generate_excel_report("protecoes", protecoes_parts, all_parts, out_dir)

            self._set_status("Concluído.")
            self._finish(ok_count, err_count)

        except Exception as e:
            self._handle_error(e)
        finally:
            if was_opened_by_us and asm_doc:
                self.sw.close_doc(asm_path)

    def _export_one(self, part, out_dir):
        path = self.sw._safe_call(part, "GetPathName")
        base_name = os.path.splitext(os.path.basename(path))[0]
        raw_dxf = os.path.join(out_dir, f"{base_name}_raw.dxf")
        final_dxf = os.path.join(out_dir, f"{base_name}.dxf")
        
        self._set_status(f"A processar {base_name}...")
        
        try:
            self.sw.export_to_dxf(part, raw_dxf)
            removed = clean_dxf(raw_dxf, final_dxf)
            if os.path.exists(raw_dxf):
                os.remove(raw_dxf)
            
            circles_txt = f"{removed} círculo(s) removido(s)" if removed else "sem alterações"
            return True, f"  OK    {base_name}.dxf  [{circles_txt}]"
        except Exception as e:
            if os.path.exists(raw_dxf):
                os.remove(raw_dxf)
            return False, f"  ERROR {base_name} — {e}"

    def _generate_excel_report(self, process_key, parts, all_parts, out_dir):
        self._log(f"A gerar {process_key.capitalize()}.xlsx...")
        try:
            from src.utils.path_utils import get_assets_dir
            template_name, output_name, col_order, data_start_row = PROCESS_CONFIG[process_key]
            
            template_path = os.path.join(get_assets_dir(), template_name)
            rows = [self.sw.get_part_data(p, all_parts) for p in parts]
            out_path = os.path.join(out_dir, output_name)
            generate_excel(template_path, rows, out_path, col_order, data_start_row)
            self.validator.validate_excel(out_path)
            self._log(f"  OK    {output_name}")
        except Exception as e:
            self._log(f"  ERROR {process_key.capitalize()}.xlsx — {e}")
