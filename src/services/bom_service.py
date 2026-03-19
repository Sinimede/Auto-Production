
import os
import re
from .base_service import BaseService
from src.utils.bom_writer import generate_bom, classify_commercial, is_known_brand
from src.utils.perfis_writer import generate_perfis

class BomService(BaseService):
    """
    Service for generating Bill of Materials (BOM) and Profile lists.
    """
    def run_generate(self, asm_path: str, out_dir: str, include_bom: bool, include_perfis: bool):
        self.run_async(self._worker, asm_path, out_dir, include_bom, include_perfis)

    def _worker(self, asm_path, out_dir, include_bom, include_perfis):
        asm_doc = None
        was_opened_by_us = False

        try:
            self._log("\u2550" * 68)
            self._log("Serviço de Listas (BOM)")
            self._set_status("A conectar ao SolidWorks...")
            self.sw.connect()

            self._log(f"A abrir assembly: {os.path.basename(asm_path)}")
            asm_doc, was_opened_by_us = self.sw.open_assembly(asm_path)

            if include_bom:
                self._generate_bom_flow(asm_doc, out_dir)
            
            if include_perfis:
                self._generate_perfis_flow(asm_doc, out_dir)

            self._set_status("Concluído.")
            self._finish(1, 0)

        except Exception as e:
            self._handle_error(e)
        finally:
            if was_opened_by_us and asm_doc:
                self.sw.close_doc(asm_path)

    def _generate_bom_flow(self, asm_doc, out_dir):
        self._log("A gerar Lista de Materiais...")
        bom_flat, warnings = self.sw.get_bom_components(asm_doc)
        for w in warnings:
            self._log(f"  AVISO {w}")

        unique = self.sw._deduplicate_by_path([bc.component for bc in bom_flat])
        
        # Re-map components to their original BomComponent info (type and path)
        path_to_bc = {os.path.normpath(bc.path).lower(): bc for bc in bom_flat}
        
        rows_producao = []
        rows_mecanico = []
        rows_eletrico = []
        rows_pneumatico = []
        warn_count = len(warnings)

        for comp in unique:
            path = self.sw._safe_call(comp, "GetPathName")
            norm_path = os.path.normpath(path).lower()
            bc = path_to_bc.get(norm_path)
            if not bc: continue

            model = self.sw._safe_call(comp, "GetModelDoc2")
            if not model:
                # Resolve if possible
                self.sw._safe_call(comp, "SetComponentState", 4)
                model = self.sw._safe_call(comp, "GetModelDoc2")
            
            if not model:
                self._log(f"  AVISO: Não foi possível carregar modelo para {path}")
                continue

            # Calculate quantity based on the full bom_flat
            qty = sum(1 for item in bom_flat if os.path.normpath(item.path).lower() == norm_path)
            
            row = {
                "qty": qty,
                "part_number": os.path.splitext(os.path.basename(path))[0],
                "Description": self.sw.get_custom_property(model, "Description"),
                "Corte_Fabrico": self.sw.get_custom_property(model, "Corte_Fabrico"),
                "Simetria": self.sw.get_custom_property(model, "Simetria"),
                "Material": self.sw.get_custom_property(model, "Material"),
                "TratSuperficial": self.sw.get_custom_property(model, "TratSuperficial"),
            }

            if bc.comp_type == "producao":
                row["A_Partir_de"] = self.sw.get_custom_property(model, "A_Partir_de")
                rows_producao.append(row)
            else:
                brand = row.get("Corte_Fabrico") or ""
                if not is_known_brand(brand):
                    self._log(f"  AVISO Fabricante desconhecido: '{brand}' \u2192 Mecânico")
                    warn_count += 1
                
                cat = classify_commercial(brand)
                {
                    "mecanico": rows_mecanico,
                    "eletrico": rows_eletrico,
                    "pneumatico": rows_pneumatico,
                }[cat].append(row)

        output_path = os.path.join(out_dir, "Lista de materiais.xlsx")
        generate_bom(rows_producao, rows_mecanico, rows_eletrico, rows_pneumatico, output_path)
        self._log(f"  OK    Lista de materiais.xlsx")
        self._log(f"  Resumo: P:{len(rows_producao)} M:{len(rows_mecanico)} E:{len(rows_eletrico)} Pn:{len(rows_pneumatico)} Avisos:{warn_count}")

    def _generate_perfis_flow(self, asm_doc, out_dir):
        self._log("A gerar Lista de Perfis...")
        perfis_parts = self.sw.get_perfis_parts(asm_doc)
        self._log(f"  Peças Perfil Alumínio encontradas: {len(perfis_parts)}")

        if not perfis_parts:
            return

        all_cut_list_items = []
        for part_path, assembly_qty in perfis_parts:
            items, warnings = self.sw.get_weldment_cut_list(part_path)
            for w in warnings:
                self._log(f"  AVISO [{os.path.basename(part_path)}]: {w}")
            
            # Multiply cut list qty by assembly instance count
            for item in items:
                all_cut_list_items.append({
                    "description": item.description,
                    "length_mm": item.length_mm,
                    "qty": item.qty * assembly_qty
                })

        if all_cut_list_items:
            output_path = os.path.join(out_dir, "Perfis de Alumínio.xlsx")
            from src.utils.path_utils import get_assets_dir
            template_path = os.path.join(get_assets_dir(), "Perfis-de-Alumínio_template.xlsx")
            
            if not os.path.exists(template_path):
                 from tools.exporter.paths import get_templates_dir
                 template_path = os.path.join(get_templates_dir(), "Perfis-de-Alumínio_template.xlsx")

            generate_perfis(all_cut_list_items, output_path, template_path)
            self._log(f"  OK    Perfis de Alumínio.xlsx ({len(all_cut_list_items)} itens)")
