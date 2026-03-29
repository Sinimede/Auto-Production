import sqlite3
import os

def check_db():
    db_path = "swat_pdm.db"
    if not os.path.exists(db_path):
        print(f"Error: Database {db_path} not found.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("\n--- Tables ---")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    print(cursor.fetchall())

    print("\n--- Locks ---")
    cursor.execute("SELECT * FROM locks;")
    print(cursor.fetchall())

    print("\n--- File References (Where Used) ---")
    cursor.execute("SELECT * FROM file_references;")
    print(cursor.fetchall())

    print("\n--- File Status ---")
    cursor.execute("SELECT * FROM file_status LIMIT 5;")
    print(cursor.fetchall())
    
    conn.close()

if __name__ == "__main__":
    check_db()
