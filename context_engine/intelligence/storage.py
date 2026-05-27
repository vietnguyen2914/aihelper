"""Database connection pool. Single writer, multiple readers via WAL."""
import sqlite3, threading, hashlib
from pathlib import Path
from typing import Dict, Optional
from .schema import init_schema

DB_ROOT = Path.home() / ".aihelper" / "memory"
DB_ROOT.mkdir(parents=True, exist_ok=True)
_conns: Dict[str, sqlite3.Connection] = {}
_lock = threading.Lock()

def _key(project_root: Optional[Path]) -> str:
    if project_root:
        return hashlib.sha1(str(project_root.resolve()).encode()).hexdigest()[:16]
    return "global"

def _path(project_root: Optional[Path] = None) -> Path:
    return DB_ROOT / f"{_key(project_root)}.db"

def get_db(project_root: Optional[Path] = None) -> sqlite3.Connection:
    path = str(_path(project_root))
    with _lock:
        if path in _conns:
            try: _conns[path].execute("SELECT 1"); return _conns[path]
            except sqlite3.Error: del _conns[path]
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        init_schema(conn)
        _conns[path] = conn
        return conn

def close_all() -> None:
    with _lock:
        for c in _conns.values():
            try: c.close()
            except sqlite3.Error: pass
        _conns.clear()
