
import openpyxl
from openpyxl.styles import PatternFill

def apply_formatting_rules(file_path):
    """
    Applies formatting rules to the BOM Excel file.

    Rule 1: If "Corte/Fabrico" contains "LASER" and "Material" contains "AL5083",
            the "Material" cell is invalid (light red).
    Rule 2: If "Material" is empty, it is invalid (light red).
    Rule 3: If "Corte/Fabrico" contains "ROUTER", "Material" must be "AL5083 Retificado".
            Otherwise, it is invalid (light red).
    Rule 4: If "Material" is "AL5380" or "AL5380 Retificado", "Tratamento Superficial" 
            must be empty or "-". Otherwise, it is invalid (light red).
    Rule 5: "Tratamento Superficial" cannot be empty, unless the material is in the exception list.
            Otherwise, it is invalid (light red).
    """
    try:
        workbook = openpyxl.load_workbook(file_path)
        sheet = workbook.active
    except FileNotFoundError:
        print(f"Error: The file '{file_path}' was not found.")
        return

    header_row = None
    for r in range(1, 11):
        # Scan for "Pos" or "Qt" specifically in column 2 (index 2)
        cell_val = str(sheet.cell(row=r, column=2).value or "")
        if "Pos" in cell_val or "Qt" in cell_val:
            header_row = r
            header = [cell.value for cell in sheet[r]]
            break

    if header_row is None:
        print("Error: Could not find header row (scanning for 'Pos' or 'Qt' in the first 10 rows).")
        return
    
    try:
        corte_fabrico_col_name = "Corte/Fabrico"
        material_col_name = "Material"
        tratamento_col_name = "Tratamento Superficial"
        
        corte_fabrico_col = header.index(corte_fabrico_col_name) + 1
        material_col = header.index(material_col_name) + 1
        tratamento_col = header.index(tratamento_col_name) + 1
        
    except ValueError as e:
        print(f"Error: Column not found in the Excel file - {e}")
        print(f"Detected header: {header}")
        return

    red_fill = PatternFill(start_color="FFC7CE",
                           end_color="FFC7CE",
                           fill_type="solid")

    rows_with_violations = set()
    for row_index in range(header_row + 1, sheet.max_row + 1):
        corte_fabrico_cell = sheet.cell(row=row_index, column=corte_fabrico_col)
        material_cell = sheet.cell(row=row_index, column=material_col)
        tratamento_cell = sheet.cell(row=row_index, column=tratamento_col)
        
        # --- Material Rules ---

        # Rule 1
        if corte_fabrico_cell.value and "LASER" in str(corte_fabrico_cell.value).upper():
            if material_cell.value and "AL5083" in str(material_cell.value).upper():
                print(f"Violation in row {row_index}: (Rule 1) 'LASER' cut cannot have 'AL5083' material. Found '{material_cell.value}'.")
                material_cell.fill = red_fill
                rows_with_violations.add(row_index)
        
        # Rule 2
        if not material_cell.value:
            print(f"Violation in row {row_index}: (Rule 2) 'Material' cannot be empty.")
            material_cell.fill = red_fill
            rows_with_violations.add(row_index)

        # Rule 3
        if corte_fabrico_cell.value and "ROUTER" in str(corte_fabrico_cell.value).upper():
            correct_material = "AL5083 Retificado"
            if not material_cell.value or str(material_cell.value).strip().lower() != correct_material.lower():
                print(f"Violation in row {row_index}: (Rule 3) 'ROUTER' cut should have material '{correct_material}'. Found '{material_cell.value}'.")
                material_cell.fill = red_fill
                rows_with_violations.add(row_index)

        # --- Tratamento Superficial Rules ---
        material_value_str = str(material_cell.value or '').strip().lower()
        tratamento_value_str = str(tratamento_cell.value or '').strip()

        # Rule 4
        if material_value_str in ["al5380", "al5380 retificado"]:
            if tratamento_value_str and tratamento_value_str != "-":
                print(f"Violation in row {row_index}: (Rule 4) Material '{material_cell.value}' cannot have Tratamento '{tratamento_cell.value}'.")
                tratamento_cell.fill = red_fill
                rows_with_violations.add(row_index)

        # Rule 5
        exception_materials = ["al5380", "pe", "bronze", "cobre", "copper", "pla"]
        if not tratamento_value_str:
            if material_value_str not in exception_materials:
                print(f"Violation in row {row_index}: (Rule 5) 'Tratamento Superficial' cannot be empty for Material '{material_cell.value}'.")
                tratamento_cell.fill = red_fill
                rows_with_violations.add(row_index)


    changes_made = len(rows_with_violations)
    if changes_made == 0:
        print("No rule violations found. The file was not changed.")
    else:
        print(f"Found and marked violations in {changes_made} row(s).")

    try:
        workbook.save(file_path)
        print(f"Successfully saved '{file_path}'.")
    except Exception as e:
        print(f"Error saving the file: {e}")

if __name__ == "__main__":
    # The path to the generated Excel file
    bom_file_path = "Resultados/Lista de materiais.xlsx"
    apply_formatting_rules(bom_file_path)
