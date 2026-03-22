import sqlite3
import os
import sys

# Adicionar src ao path
sys.path.append(os.path.abspath(os.path.join(os.getcwd(), 'src')))

def debug_where_used():
    db_path = "swat_pdm.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("--- CONTEÚDO DA TABELA DE REFERÊNCIAS (Primeiras 10) ---")
    cursor.execute("SELECT parent_path, child_path FROM file_references LIMIT 10;")
    rows = cursor.fetchall()
    for parent, child in rows:
        print(f"PAI:   {parent}")
        print(f"FILHO: {child}")
        print("-" * 20)

    # Testar uma pesquisa manual para uma peça que sabemos que existe
    # Vamos pegar na primeira peça da lista de referências
    if rows:
        test_child = rows[0][1]
        test_child_name = os.path.basename(test_child)
        print(f"\n--- TESTANDO PESQUISA PARA: {test_child_name} ---")
        
        # Pesquisa Exata
        cursor.execute("SELECT parent_path FROM file_references WHERE child_path = ?", (test_child,))
        print(f"Busca Exata: {'ENCONTRADO' if cursor.fetchall() else 'FALHOU'}")
        
        # Pesquisa LIKE
        cursor.execute("SELECT parent_path FROM file_references WHERE child_path LIKE ?", (f"%{test_child_name}",))
        print(f"Busca LIKE:  {'ENCONTRADO' if cursor.fetchall() else 'FALHOU'}")
    else:
        print("\nAVISO: A tabela file_references está VAZIA!")

    conn.close()

if __name__ == "__main__":
    debug_where_used()
