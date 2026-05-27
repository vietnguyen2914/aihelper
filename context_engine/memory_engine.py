"""
Structured Cognitive Memory Engine — persistent engineering intelligence.

Stores architectural decisions, debugging history, and developer preferences
in a local SQLite database with FTS5 full-text search.

This is the central knowledge store. Editors consume knowledge through
the Knowledge Dispatcher (knowledge_dispatcher.py), which writes formatted
knowledge into each editor's native config files.

Design principles:
- SQLite + FTS5: zero new dependencies, local-first
- Event-sourced: raw events from scheduler, derived insights here
- Git-native: all entries attach to project, branch, or commit
- Multi-agent: single shared DB at ~/.aihelper/memory/, all editors read it
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# ── Database location ──────────────────────────────────────────

MEMORY_ROOT = Path.home() / ".aihelper" / "memory"
MEMORY_ROOT.mkdir(parents=True, exist_ok=True)

# Global registry of open connections (one per DB file)
_connections: Dict[str, sqlite3.Connection] = {}
_lock = threading.Lock()


def _db_path(project_root: Optional[Path] = None) -> Path:
    """Get the memory DB path for a project. Falls back to global store."""
    if project_root:
        key = _project_key(project_root)
        return MEMORY_ROOT / f"{key}.db"
    return MEMORY_ROOT / "global.db"


def _project_key(project_root: Path) -> str:
    """Generate a stable key for the project."""
    resolved = str(project_root.resolve())
    import hashlib
    return hashlib.sha1(resolved.encode()).hexdigest()[:16]


def get_memory_db(project_root: Optional[Path] = None) -> sqlite3.Connection:
    """Get or create a memory DB connection."""
    path = _db_path(project_root)
    key = str(path)

    with _lock:
        if key in _connections:
            try:
                _connections[key].execute("SELECT 1")
                return _connections[key]
            except sqlite3.Error:
                del _connections[key]

        conn = sqlite3.connect(str(key), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _init_schema(conn)
        _connections[key] = conn
        return conn


def close_all() -> None:
    """Close all open memory DB connections."""
    with _lock:
        for conn in _connections.values():
            try:
                conn.close()
            except sqlite3.Error:
                pass
        _connections.clear()


# ── Schema ──────────────────────────────────────────────────────

def _init_schema(conn: sqlite3.Connection) -> None:
    """Create tables and FTS5 indexes if they don't exist."""
    conn.executescript("""
        -- Architectural decisions
        CREATE TABLE IF NOT EXISTS architectural_decisions (
            id TEXT PRIMARY KEY,
            choice TEXT NOT NULL,
            reason TEXT,
            alternatives TEXT,
            related_files TEXT,
            confidence REAL DEFAULT 0.5,
            source_session TEXT,
            tags TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        -- Debugging history
        CREATE TABLE IF NOT EXISTS debugging_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symptom TEXT NOT NULL,
            root_cause TEXT,
            fix_commit TEXT,
            affected_modules TEXT,
            error_signature TEXT,
            resolution TEXT,
            resolved_at TEXT,
            recurrence_count INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        );

        -- Developer preferences
        CREATE TABLE IF NOT EXISTS developer_preferences (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            category TEXT,
            confidence REAL DEFAULT 0.5,
            source TEXT,
            updated_at TEXT NOT NULL
        );

        -- Session insights (compressed summaries)
        CREATE TABLE IF NOT EXISTS session_insights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            insight_type TEXT NOT NULL,
            summary TEXT NOT NULL,
            related_files TEXT,
            importance REAL DEFAULT 0.5,
            created_at TEXT NOT NULL
        );
    """)

    # FTS5 virtual tables for full-text search
    try:
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS decisions_fts
            USING fts5(id, choice, reason, alternatives, tags, content='architectural_decisions',
                       content_rowid='rowid')
        """)
    except sqlite3.OperationalError:
        pass  # FTS5 might not be compiled in

    try:
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS debugging_fts
            USING fts5(symptom, root_cause, resolution, content='debugging_history',
                       content_rowid='rowid')
        """)
    except sqlite3.OperationalError:
        pass

    conn.commit()


# ── Triggers to sync FTS ───────────────────────────────────────

def _ensure_fts_triggers(conn: sqlite3.Connection) -> None:
    """Create triggers to keep FTS indexes in sync."""
    try:
        conn.executescript("""
            CREATE TRIGGER IF NOT EXISTS decisions_ai AFTER INSERT ON architectural_decisions BEGIN
                INSERT INTO decisions_fts(rowid, id, choice, reason, alternatives, tags)
                VALUES (new.rowid, new.id, new.choice, new.reason, new.alternatives, new.tags);
            END;

            CREATE TRIGGER IF NOT EXISTS decisions_ad AFTER DELETE ON architectural_decisions BEGIN
                INSERT INTO decisions_fts(decisions_fts, rowid, id, choice, reason, alternatives, tags)
                VALUES ('delete', old.rowid, old.id, old.choice, old.reason, old.alternatives, old.tags);
            END;

            CREATE TRIGGER IF NOT EXISTS decisions_au AFTER UPDATE ON architectural_decisions BEGIN
                INSERT INTO decisions_fts(decisions_fts, rowid, id, choice, reason, alternatives, tags)
                VALUES ('delete', old.rowid, old.id, old.choice, old.reason, old.alternatives, old.tags);
                INSERT INTO decisions_fts(rowid, id, choice, reason, alternatives, tags)
                VALUES (new.rowid, new.id, new.choice, new.reason, new.alternatives, new.tags);
            END;

            CREATE TRIGGER IF NOT EXISTS debugging_ai AFTER INSERT ON debugging_history BEGIN
                INSERT INTO debugging_fts(rowid, symptom, root_cause, resolution)
                VALUES (new.rowid, new.symptom, new.root_cause, new.resolution);
            END;

            CREATE TRIGGER IF NOT EXISTS debugging_ad AFTER DELETE ON debugging_history BEGIN
                INSERT INTO debugging_fts(debugging_fts, rowid, symptom, root_cause, resolution)
                VALUES ('delete', old.rowid, old.symptom, old.root_cause, old.resolution);
            END;

            CREATE TRIGGER IF NOT EXISTS debugging_au AFTER UPDATE ON debugging_history BEGIN
                INSERT INTO debugging_fts(debugging_fts, rowid, symptom, root_cause, resolution)
                VALUES ('delete', old.rowid, old.symptom, old.root_cause, old.resolution);
                INSERT INTO debugging_fts(rowid, symptom, root_cause, resolution)
                VALUES (new.rowid, new.symptom, new.root_cause, new.resolution);
            END;
        """)
    except sqlite3.OperationalError:
        pass


# ── Architectural Decisions ─────────────────────────────────────

def add_decision(
    decision_id: str,
    choice: str,
    reason: str = "",
    alternatives: Optional[List[str]] = None,
    related_files: Optional[List[str]] = None,
    confidence: float = 0.5,
    tags: Optional[List[str]] = None,
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Record an architectural decision."""
    db = get_memory_db(project_root)
    now = datetime.now(timezone.utc).isoformat()

    db.execute("""
        INSERT OR REPLACE INTO architectural_decisions
        (id, choice, reason, alternatives, related_files, confidence, tags, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM architectural_decisions WHERE id=?), ?), ?)
    """, (
        decision_id, choice, reason,
        json.dumps(alternatives or []),
        json.dumps(related_files or []),
        confidence,
        json.dumps(tags or []),
        decision_id, now, now,
    ))
    db.commit()
    _ensure_fts_triggers(db)

    return {
        "id": decision_id,
        "choice": choice,
        "reason": reason,
        "alternatives": alternatives or [],
        "related_files": related_files or [],
        "confidence": confidence,
        "tags": tags or [],
        "updated_at": now,
    }


def get_decision(decision_id: str, project_root: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Get a specific architectural decision."""
    db = get_memory_db(project_root)
    row = db.execute("SELECT * FROM architectural_decisions WHERE id=?", (decision_id,)).fetchone()
    if not row:
        return None
    return _row_to_dict(row)


def list_decisions(
    project_root: Optional[Path] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """List all architectural decisions."""
    db = get_memory_db(project_root)
    rows = db.execute(
        "SELECT * FROM architectural_decisions ORDER BY updated_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def delete_decision(decision_id: str, project_root: Optional[Path] = None) -> bool:
    """Delete an architectural decision."""
    db = get_memory_db(project_root)
    db.execute("DELETE FROM architectural_decisions WHERE id=?", (decision_id,))
    db.commit()
    return db.total_changes > 0


# ── Debugging History ──────────────────────────────────────────

def add_debug_entry(
    symptom: str,
    root_cause: str = "",
    fix_commit: str = "",
    affected_modules: Optional[List[str]] = None,
    error_signature: str = "",
    resolution: str = "",
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Record a debugging session outcome."""
    db = get_memory_db(project_root)
    now = datetime.now(timezone.utc).isoformat()

    # Check for recurrence
    existing = db.execute(
        "SELECT id, recurrence_count FROM debugging_history WHERE error_signature=? AND error_signature!='' ORDER BY id DESC LIMIT 1",
        (error_signature,),
    ).fetchone()

    if existing and error_signature:
        db.execute(
            "UPDATE debugging_history SET recurrence_count=?, resolved_at=? WHERE id=?",
            (existing["recurrence_count"] + 1, now, existing["id"]),
        )
        db.commit()
        return {"id": existing["id"], "recurrence": True, "count": existing["recurrence_count"] + 1}

    cursor = db.execute("""
        INSERT INTO debugging_history
        (symptom, root_cause, fix_commit, affected_modules, error_signature, resolution, resolved_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        symptom, root_cause, fix_commit,
        json.dumps(affected_modules or []),
        error_signature, resolution, now, now,
    ))
    db.commit()
    _ensure_fts_triggers(db)

    return {
        "id": cursor.lastrowid,
        "symptom": symptom,
        "root_cause": root_cause,
        "fix_commit": fix_commit,
        "affected_modules": affected_modules or [],
        "resolved_at": now,
    }


def list_debugs(
    project_root: Optional[Path] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """List debugging history."""
    db = get_memory_db(project_root)
    rows = db.execute(
        "SELECT * FROM debugging_history ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


# ── Developer Preferences ──────────────────────────────────────

def set_preference(
    key: str,
    value: str,
    category: str = "",
    confidence: float = 0.5,
    source: str = "",
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Set a developer preference."""
    db = get_memory_db(project_root)
    now = datetime.now(timezone.utc).isoformat()

    db.execute("""
        INSERT OR REPLACE INTO developer_preferences (key, value, category, confidence, source, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (key, value, category, confidence, source, now))
    db.commit()

    return {"key": key, "value": value, "category": category, "updated_at": now}


def get_preference(key: str, project_root: Optional[Path] = None) -> Optional[str]:
    """Get a specific preference value."""
    db = get_memory_db(project_root)
    row = db.execute("SELECT value FROM developer_preferences WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def list_preferences(
    project_root: Optional[Path] = None,
    category: str = "",
) -> Dict[str, str]:
    """List all preferences, optionally filtered by category."""
    db = get_memory_db(project_root)
    if category:
        rows = db.execute(
            "SELECT key, value FROM developer_preferences WHERE category=? ORDER BY key",
            (category,),
        ).fetchall()
    else:
        rows = db.execute("SELECT key, value FROM developer_preferences ORDER BY key").fetchall()
    return {r["key"]: r["value"] for r in rows}


def all_preferences_detail(
    project_root: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """List all preferences with full detail."""
    db = get_memory_db(project_root)
    rows = db.execute("SELECT * FROM developer_preferences ORDER BY category, key").fetchall()
    return [_row_to_dict(r) for r in rows]


# ── Session Insights ───────────────────────────────────────────

def add_session_insight(
    insight_type: str,
    summary: str,
    related_files: Optional[List[str]] = None,
    importance: float = 0.5,
    session_id: str = "",
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Record a compressed session insight."""
    db = get_memory_db(project_root)
    now = datetime.now(timezone.utc).isoformat()

    cursor = db.execute("""
        INSERT INTO session_insights
        (session_id, insight_type, summary, related_files, importance, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        session_id, insight_type, summary,
        json.dumps(related_files or []),
        importance, now,
    ))
    db.commit()

    return {
        "id": cursor.lastrowid,
        "insight_type": insight_type,
        "summary": summary[:200],
        "created_at": now,
    }


# ── Unified Search ─────────────────────────────────────────────

def search_knowledge(
    query: str,
    project_root: Optional[Path] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    """Search across all knowledge types using FTS5 + LIKE fallback."""
    db = get_memory_db(project_root)
    results: Dict[str, List[Dict[str, Any]]] = {
        "decisions": [],
        "debugs": [],
        "preferences": [],
    }

    search_term = f"%{query}%"

    # Try FTS5 first
    try:
        fts_rows = db.execute(
            "SELECT id, choice, reason FROM decisions_fts WHERE decisions_fts MATCH ? LIMIT ?",
            (query, limit),
        ).fetchall()
        if fts_rows:
            results["decisions"] = [
                {"id": r["id"], "choice": r["choice"], "reason": r["reason"][:200] if r["reason"] else ""}
                for r in fts_rows
            ]
    except sqlite3.OperationalError:
        pass

    if not results["decisions"]:
        dec_rows = db.execute(
            "SELECT id, choice, reason FROM architectural_decisions WHERE choice LIKE ? OR reason LIKE ? OR alternatives LIKE ? LIMIT ?",
            (search_term, search_term, search_term, limit),
        ).fetchall()
        results["decisions"] = [
            {"id": r["id"], "choice": r["choice"], "reason": r["reason"][:200] if r["reason"] else ""}
            for r in dec_rows
        ]

    # Debugging history
    try:
        fts_rows = db.execute(
            "SELECT rowid, symptom, root_cause FROM debugging_fts WHERE debugging_fts MATCH ? LIMIT ?",
            (query, limit),
        ).fetchall()
        if fts_rows:
            results["debugs"] = [
                {"id": r["rowid"], "symptom": r["symptom"][:200], "root_cause": (r["root_cause"] or "")[:200]}
                for r in fts_rows
            ]
    except sqlite3.OperationalError:
        pass

    if not results["debugs"]:
        dbg_rows = db.execute(
            "SELECT id, symptom, root_cause FROM debugging_history WHERE symptom LIKE ? OR root_cause LIKE ? OR resolution LIKE ? LIMIT ?",
            (search_term, search_term, search_term, limit),
        ).fetchall()
        results["debugs"] = [
            {"id": r["id"], "symptom": r["symptom"][:200], "root_cause": (r["root_cause"] or "")[:200]}
            for r in dbg_rows
        ]

    # Preferences
    pref_rows = db.execute(
        "SELECT key, value FROM developer_preferences WHERE key LIKE ? OR value LIKE ? OR category LIKE ? LIMIT ?",
        (search_term, search_term, search_term, limit),
    ).fetchall()
    results["preferences"] = {r["key"]: r["value"] for r in pref_rows}

    return results


def get_all_knowledge(
    project_root: Optional[Path] = None,
    max_decisions: int = 10,
    max_debugs: int = 10,
) -> Dict[str, Any]:
    """Get all structured knowledge for context injection."""
    return {
        "decisions": list_decisions(project_root, limit=max_decisions),
        "debugs": list_debugs(project_root, limit=max_debugs),
        "preferences": list_preferences(project_root),
    }


# ── Helpers ────────────────────────────────────────────────────

def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """Convert a sqlite3.Row to a dict, parsing JSON fields."""
    result = dict(row)
    for field in ("alternatives", "related_files", "affected_modules", "tags"):
        if field in result and isinstance(result[field], str):
            try:
                result[field] = json.loads(result[field])
            except (json.JSONDecodeError, TypeError):
                pass
    return result


# ── Daemon handlers ────────────────────────────────────────────

def handle_knowledge_add_decision(params: Dict[str, Any]) -> Dict[str, Any]:
    project_root = Path(params.get("project_root", str(Path.cwd()))) if params.get("project_root") else None
    return add_decision(
        decision_id=params.get("id", ""),
        choice=params.get("choice", ""),
        reason=params.get("reason", ""),
        alternatives=params.get("alternatives"),
        related_files=params.get("files") or params.get("related_files"),
        confidence=params.get("confidence", 0.5),
        tags=params.get("tags"),
        project_root=project_root,
    )


def handle_knowledge_add_debug(params: Dict[str, Any]) -> Dict[str, Any]:
    project_root = Path(params.get("project_root", str(Path.cwd()))) if params.get("project_root") else None
    return add_debug_entry(
        symptom=params.get("symptom", ""),
        root_cause=params.get("root_cause", ""),
        fix_commit=params.get("fix_commit", ""),
        affected_modules=params.get("affected_modules"),
        error_signature=params.get("error_signature", ""),
        resolution=params.get("resolution", ""),
        project_root=project_root,
    )


def handle_knowledge_set_preference(params: Dict[str, Any]) -> Dict[str, Any]:
    project_root = Path(params.get("project_root", str(Path.cwd()))) if params.get("project_root") else None
    return set_preference(
        key=params.get("key", ""),
        value=params.get("value", ""),
        category=params.get("category", ""),
        confidence=params.get("confidence", 0.5),
        source=params.get("source", ""),
        project_root=project_root,
    )


def handle_knowledge_recall(params: Dict[str, Any]) -> Dict[str, Any]:
    project_root = Path(params.get("project_root", str(Path.cwd()))) if params.get("project_root") else None
    query = params.get("query", "")
    if query:
        return search_knowledge(query, project_root=project_root, limit=params.get("limit", 10))
    return get_all_knowledge(
        project_root=project_root,
        max_decisions=params.get("max_decisions", 10),
        max_debugs=params.get("max_debugs", 10),
    )


def handle_knowledge_dispatch(params: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch knowledge to active editor's native config."""
    project_root = Path(params.get("project_root", str(Path.cwd()))) if params.get("project_root") else None
    try:
        from .knowledge_dispatcher import dispatch_knowledge
    except ImportError:
        from knowledge_dispatcher import dispatch_knowledge
    return dispatch_knowledge(project_root=project_root)
