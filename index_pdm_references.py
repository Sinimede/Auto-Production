import os
import sys
import time

# Adicionar src ao path para importar os componentes do PDM
sys.path.append(os.path.abspath(os.path.join(os.getcwd(), 'src')))

from src.core.solidworks import SolidWorksClient
from src.pdm.controllers.lock_controller import LockController

def index_folder(target_dir):
    sw = SolidWorksClient()
    lc = LockController()
    
    if not os.path.exists(target_dir):
        print(f"Erro: Pasta nao encontrada: {target_dir}")
        return

    try:
        print("Conectando ao SolidWorks...")
        sw.connect()
    except Exception as e:
        print(f"Erro ao conectar ao SolidWorks: {e}")
        return

    print(f"Iniciando indexacao de: {target_dir}")
    
    asm_files = []
    for root, dirs, files in os.walk(target_dir):
        for file in files:
            if file.lower().endswith('.sldasm'):
                asm_files.append(os.path.join(root, file))

    total = len(asm_files)
    print(f"Encontradas {total} montagens para indexar.")

    for i, asm_path in enumerate(asm_files):
        print(f"[{i+1}/{total}] Indexando: {os.path.basename(asm_path)}")
        try:
            # Obter dependencias sem precisar de abrir o ficheiro (GetDocumentDependencies2)
            deps = sw.get_dependencies(asm_path)
            if deps:
                # Atualizar na base de dados
                lc.update_references(asm_path, deps)
                print(f"   -> {len(deps)} referencias guardadas.")
            else:
                print("   -> Nenhuma referencia encontrada.")
        except Exception as e:
            print(f"   -> Erro ao indexar {os.path.basename(asm_path)}: {e}")
        
        # Pequena pausa para nao sobrecarregar o COM
        time.sleep(0.1)

    print("\nIndexacao concluida com sucesso!")

if __name__ == "__main__":
    target = r"C:\Users\Micael\Desktop\Auto Production - Cópia"
    index_folder(target)
