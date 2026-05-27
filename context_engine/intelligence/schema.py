"""SQLite schema for the Engineering Intelligence Layer. Single source of truth."""
import sqlite3

SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS architectural_decisions (
        id TEXT PRIMARY KEY, choice TEXT NOT NULL, reason TEXT,
        alternatives TEXT, related_files TEXT,
        confidence REAL DEFAULT 0.5, source TEXT DEFAULT 'manual',
        frequency INTEGER DEFAULT 1, last_seen TEXT,
        status TEXT DEFAULT 'active', supersedes TEXT,
        contradiction_count INTEGER DEFAULT 0,
        source_session TEXT, tags TEXT,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS debugging_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symptom TEXT NOT NULL, root_cause TEXT, fix_commit TEXT,
        affected_modules TEXT, error_signature TEXT, resolution TEXT,
        resolved_at TEXT, recurrence_count INTEGER DEFAULT 0,
        confidence REAL DEFAULT 0.5, source TEXT DEFAULT 'manual',
        frequency INTEGER DEFAULT 1, last_seen TEXT,
        status TEXT DEFAULT 'active', created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS developer_preferences (
        key TEXT PRIMARY KEY, value TEXT NOT NULL, category TEXT,
        confidence REAL DEFAULT 0.5, source TEXT DEFAULT 'manual',
        frequency INTEGER DEFAULT 1, last_seen TEXT,
        status TEXT DEFAULT 'active', updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS session_insights (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT, insight_type TEXT NOT NULL,
        summary TEXT NOT NULL, related_files TEXT,
        importance REAL DEFAULT 0.5, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS knowledge_conflicts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_type TEXT NOT NULL, entity_key TEXT NOT NULL,
        old_value TEXT, new_value TEXT,
        detected_at TEXT NOT NULL, resolved BOOLEAN DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS memory_graph_links (
        memory_type TEXT NOT NULL, memory_id TEXT NOT NULL,
        graph_node TEXT NOT NULL, relationship TEXT NOT NULL,
        PRIMARY KEY (memory_type, memory_id, graph_node, relationship)
    );
"""

V2_MIGRATIONS = [
    ("architectural_decisions", [
        "source TEXT DEFAULT 'manual'", "frequency INTEGER DEFAULT 1",
        "last_seen TEXT", "status TEXT DEFAULT 'active'",
        "supersedes TEXT", "contradiction_count INTEGER DEFAULT 0",
    ]),
    ("debugging_history", [
        "confidence REAL DEFAULT 0.5", "source TEXT DEFAULT 'manual'",
        "frequency INTEGER DEFAULT 1", "last_seen TEXT",
        "status TEXT DEFAULT 'active'",
    ]),
    ("developer_preferences", [
        "frequency INTEGER DEFAULT 1", "last_seen TEXT",
        "status TEXT DEFAULT 'active'",
    ]),
]

FTS_SQL = """
    CREATE VIRTUAL TABLE IF NOT EXISTS decisions_fts
        USING fts5(id, choice, reason, alternatives, tags,
                   content='architectural_decisions', content_rowid='rowid');
    CREATE VIRTUAL TABLE IF NOT EXISTS debugging_fts
        USING fts5(symptom, root_cause, resolution,
                   content='debugging_history', content_rowid='rowid');
"""

TRIGGERS_SQL = """
    CREATE TRIGGER IF NOT EXISTS d_ai AFTER INSERT ON architectural_decisions BEGIN INSERT INTO decisions_fts(rowid,id,choice,reason,alternatives,tags) VALUES(new.rowid,new.id,new.choice,new.reason,new.alternatives,new.tags); END;
    CREATE TRIGGER IF NOT EXISTS d_ad AFTER DELETE ON architectural_decisions BEGIN INSERT INTO decisions_fts(decisions_fts,rowid,id,choice,reason,alternatives,tags) VALUES('delete',old.rowid,old.id,old.choice,old.reason,old.alternatives,old.tags); END;
    CREATE TRIGGER IF NOT EXISTS d_au AFTER UPDATE ON architectural_decisions BEGIN INSERT INTO decisions_fts(decisions_fts,rowid,id,choice,reason,alternatives,tags) VALUES('delete',old.rowid,old.id,old.choice,old.reason,old.alternatives,old.tags); INSERT INTO decisions_fts(rowid,id,choice,reason,alternatives,tags) VALUES(new.rowid,new.id,new.choice,new.reason,new.alternatives,new.tags); END;
    CREATE TRIGGER IF NOT EXISTS db_ai AFTER INSERT ON debugging_history BEGIN INSERT INTO debugging_fts(rowid,symptom,root_cause,resolution) VALUES(new.rowid,new.symptom,new.root_cause,new.resolution); END;
    CREATE TRIGGER IF NOT EXISTS db_ad AFTER DELETE ON debugging_history BEGIN INSERT INTO debugging_fts(debugging_fts,rowid,symptom,root_cause,resolution) VALUES('delete',old.rowid,old.symptom,old.root_cause,old.resolution); END;
    CREATE TRIGGER IF NOT EXISTS db_au AFTER UPDATE ON debugging_history BEGIN INSERT INTO debugging_fts(debugging_fts,rowid,symptom,root_cause,resolution) VALUES('delete',old.rowid,old.symptom,old.root_cause,old.resolution); INSERT INTO debugging_fts(rowid,symptom,root_cause,resolution) VALUES(new.rowid,new.symptom,new.root_cause,new.resolution); END;
"""

def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    migrate(conn)
    try: conn.executescript(FTS_SQL)
    except sqlite3.OperationalError: pass
    try: conn.executescript(TRIGGERS_SQL)
    except sqlite3.OperationalError: pass
    conn.commit()

def migrate(conn: sqlite3.Connection) -> None:
    for table, columns in V2_MIGRATIONS:
        existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for col_def in columns:
            col_name = col_def.split()[0]
            if col_name not in existing:
                try: conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
                except sqlite3.OperationalError: pass
    conn.commit()
