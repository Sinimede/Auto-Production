import sqlite3
import os

DB_PATH = "swat_pdm.db"

def migrate():
    if not os.path.exists(DB_PATH):
        print(f"Database {DB_PATH} not found. Skipping migration.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Add version column to file_metadata
    try:
        cursor.execute("ALTER TABLE file_metadata ADD COLUMN version INTEGER DEFAULT 1")
        print("Added 'version' column to 'file_metadata'.")
    except sqlite3.OperationalError:
        print("'version' column already exists in 'file_metadata'.")

    # 2. Add last_synced_hash if missing (from previous plan)
    try:
        cursor.execute("ALTER TABLE file_metadata ADD COLUMN last_synced_hash TEXT")
        print("Added 'last_synced_hash' column to 'file_metadata'.")
    except sqlite3.OperationalError:
        print("'last_synced_hash' column already exists in 'file_metadata'.")

    # 3. Add version column to history if missing (it's in schema but might be missing in old DBs?)
    # The schema.py defines it, but if the DB was created with an old schema, it might be missing.
    try:
        cursor.execute("ALTER TABLE history ADD COLUMN version TEXT")
        print("Added 'version' column to 'history'.")
    except sqlite3.OperationalError:
        print("'version' column already exists in 'history'.")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    migrate()
