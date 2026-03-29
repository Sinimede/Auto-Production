import sqlite3
import os

class DatabaseManager:
    _instance = None
    
    def __new__(cls, db_path="swat_pdm.db"):
        if cls._instance is None:
            cls._instance = super(DatabaseManager, cls).__new__(cls)
            cls._instance.db_path = db_path
            cls._instance.initialize()
        return cls._instance

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def initialize(self):
        from .schema import TABLES
        conn = self.get_connection()
        cursor = conn.cursor()
        for table_sql in TABLES:
            cursor.execute(table_sql)
        conn.commit()
        conn.close()

def get_db():
    return DatabaseManager()
