TABLES = [
    """
    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        path TEXT NOT NULL UNIQUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS locks (
        file_path TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        locked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        machine_id TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_path TEXT NOT NULL,
        action TEXT NOT NULL,
        user_id TEXT NOT NULL,
        version TEXT,
        comment TEXT,
        project_name TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS file_status (
        file_path TEXT PRIMARY KEY,
        status TEXT DEFAULT 'In Design'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS file_references (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        parent_path TEXT NOT NULL,
        child_path TEXT NOT NULL,
        UNIQUE(parent_path, child_path)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS file_metadata (
        file_path TEXT PRIMARY KEY,
        description TEXT,
        material TEXT,
        weight REAL,
        revision TEXT DEFAULT '00',
        treatment TEXT,
        last_synced_hash TEXT,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """
]
