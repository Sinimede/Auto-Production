
import os
from .base_service import BaseService
from src.utils.excel_writer import generate_excel, PROCESS_CONFIG
from src.utils.path_utils import get_temp_dir

class StepService(BaseService):
    """
    Service for orchestrating STEP exports (Router, CNC, Torno).
    """
    def run_export(self, asm_path: str, out_dir: str, selected_processes: dict, gen_excel: bool):
        self.run_async(self._worker, asm_path, out_dir, selected_processes, gen_excel)

    def _worker(self, asm_path, out_dir, selected, gen_excel):
        ok_count = 0
        err_count = 0
        asm_doc = None
        was_opened_by_us = False

        try:
            self._log("\u2550" * 68)
            self._log("Serviço de Exportação STEP")
            self._set_status("A conectar ao SolidWorks...")
            self.sw.connect()

            self._log(f"A abrir assembly: {os.path.basename(asm_path)}")
            asm_doc, was_opened_by_us = self.sw.open_assembly(asm_path)

            self._log("A percorrer componentes...")
            all_parts = self.sw.get_all_parts(asm_doc)
            
            # Group parts by process
            process_parts = {
                "router": [p for p in all_parts if "router" in self.sw.get_corte_fabrico(p)] if selected.get("router") else [],
                "cnc":    [p for p in all_parts if "cnc" in self.sw.get_corte_fabrico(p)]    if selected.get("cnc") else [],
                "torno":  [p for p in all_parts if "torno" in self.sw.get_corte_fabrico(p)]  if selected.get("torno") else [],
            }

            total = sum(len(parts) for parts in process_parts.values())
            self._log(f"  Peças a exportar: {total}")
            self._log("\u2500" * 68)

            if total == 0:
                self._log("Nenhuma peça encontrada para os processos selecionados.")
                self._finish(0, 0)
                return

            self._set_progress(0, total)
            progress_i = 0

            for proc_key, parts in process_parts.items():
                if not parts: continue
                self._log(f"  Processo: {proc_key.upper()}")
                
                for part in parts:
                    success, msg = self._export_one(part, out_dir, proc_key == "router")
                    if success: ok_count += 1
                    else: err_count += 1
                    progress_i += 1
                    self._set_progress(progress_i, total)
                    self._log(msg)

            # Generate Excels
            if gen_excel:
                for proc_key, parts in process_parts.items():
                    if parts:
                        self._generate_excel_report(proc_key, parts, all_parts, out_dir)

            self._set_status("Concluído.")
            self._finish(ok_count, err_count)

        except Exception as e:
            self._handle_error(e)
        finally:
            if was_opened_by_us and asm_doc:
                self.sw.close_doc(asm_path)

    def _export_one(self, part, out_dir, is_router):
        path = self.sw._safe_call(part, "GetPathName")
        base_name = os.path.splitext(os.path.basename(path))[0]
        output_step = os.path.join(out_dir, f"{base_name}.step")
        
        self._set_status(f"A processar {base_name}...")
        
        tmp_path = None
        try:
            if is_router:
                # Router Flow: Copy to tmp -> Modify Dowels -> Export -> Cleanup
                tmp_path = self.sw.copy_part_to_tmp(path, get_temp_dir())
                tmp_doc, _ = self.sw.open_assembly(tmp_path) # Opens as part but using open_assembly helper
                
                # Dowel modification logic
                holes = self.sw.get_dowel_holes(tmp_doc)
                if holes:
                    for hole in holes:
                        self.sw.modify_dowel_diameter(tmp_doc, hole, 0.003) # 3mm pilot hole
                    self.sw.save_silent(tmp_doc)
                
                self.sw.export_to_step(tmp_doc, output_step)
                self.sw.close_doc(tmp_path)
                if os.path.exists(tmp_path): os.remove(tmp_path)
                
                mod_txt = f"{len(holes)} furos modificados" if holes else "sem furos de cavilha"
                return True, f"  OK    {base_name}.step  [{mod_txt}]"
            else:
                # Normal Flow
                self.sw.export_to_step(part, output_step)
                return True, f"  OK    {base_name}.step"
                
        except Exception as e:
            if tmp_path and os.path.exists(tmp_path): 
                try: self.sw.close_doc(tmp_path); os.remove(tmp_path)
                except: pass
            return False, f"  ERROR {base_name} — {e}"

    def _generate_excel_report(self, process_key, parts, all_parts, out_dir):
        self._log(f"A gerar {process_key.upper()}.xlsx...")
        try:
            from src.utils.path_utils import get_assets_dir
            template_name, output_name, col_order, data_start_row = PROCESS_CONFIG[process_key]
            template_path = os.path.join(get_assets_dir(), template_name)
            
            # Fallback for templates while assets/ is not populated (compatibility)
            if not os.path.exists(template_path):
                 from tools.exporter.paths import get_templates_dir
                 template_path = os.path.join(get_templates_dir(), template_name)

            rows = [self.sw.get_part_data(p, all_parts) for p in parts]
            generate_excel(template_path, rows, os.path.join(out_dir, output_name), col_order, data_start_row)
            self._log(f"  OK    {output_name}")
        except Exception as e:
            self._log(f"  ERROR {process_key.upper()}.xlsx — {e}")
