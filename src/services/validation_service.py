
import openpyxl
from openpyxl.styles import PatternFill

class ValidationService:
    """
    Service for applying production rules and formatting to Excel BOMs.
    """
    def __init__(self, log_fn=None):
        self._log = log_fn

    def validate_excel(self, file_path: str):
        """
        Applies production rules to the Excel file.
        """
        try:
            workbook = openpyxl.load_workbook(file_path)
            sheet = workbook.active
        except Exception as e:
            if self._log: self._log(f"Erro ao abrir Excel para validação: {e}")
            return

        header_row = self._find_header_row(sheet)
        if not header_row:
            if self._log: self._log(f"Aviso: Cabeçalho não encontrado em {file_path}. Validação ignorada.")
            return

        header = [cell.value for cell in sheet[header_row]]
        
        try:
            corte_col = header.index("Corte/Fabrico") + 1
            mat_col = header.index("Material") + 1
            trat_col = header.index("Tratamento Superficial") + 1
        except ValueError:
            # Not all DXF excels have all columns (e.g. Protecoes might miss some)
            if self._log: self._log(f"Aviso: Colunas de validação não encontradas em {file_path}.")
            return

        red_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
        violations = 0

        for row_idx in range(header_row + 1, sheet.max_row + 1):
            corte = str(sheet.cell(row=row_idx, column=corte_col).value or "").upper()
            material = str(sheet.cell(row=row_idx, column=mat_col).value or "").strip()
            tratamento = str(sheet.cell(row=row_idx, column=trat_col).value or "").strip()
            
            # Rule 1: LASER + AL5083
            if "LASER" in corte and "AL5083" in material.upper():
                sheet.cell(row=row_idx, column=mat_col).fill = red_fill
                violations += 1
            
            # Rule 2: Empty Material
            if not material:
                sheet.cell(row=row_idx, column=mat_col).fill = red_fill
                violations += 1

            # Rule 5: Empty Treatment
            exception_mats = ["al5380", "pe", "bronze", "cobre", "copper", "pla"]
            if not tratamento and material.lower() not in exception_mats:
                sheet.cell(row=row_idx, column=trat_col).fill = red_fill
                violations += 1

        if violations > 0:
            workbook.save(file_path)
            if self._log: self._log(f"  VALIDAÇÃO: {violations} violações marcadas em {file_path}")

    def _find_header_row(self, sheet):
        # Look for headers like 'Pos' or 'Qt' in first 10 rows, any column
        for r in range(1, 11):
            for c in range(1, 10):
                val = str(sheet.cell(row=r, column=c).value or "").lower()
                if any(k in val for k in ["pos", "item", "qt", "qty"]):
                    return r
        return None
