"""
graph_db.py — SQLite + FTS5 knowledge graph storage.

Mục tiêu: Thay thế JSON file storage bằng SQLite để:
1. FTS5 full-text search — sub-ms symbol lookup
2. WAL mode — concurrent reads không block writer
3. Typed edges — call graph, type hierarchy
4. Indexed queries — ORDER BY, LIMIT, filter by kind/file
5. Atomic transactions — không lo corrupt cache
6. Zero external dependencies — Python built-in sqlite3

Architecture:
    symbols        — all code symbols (functions, classes, methods, ...)
    symbols_fts    — FTS5 virtual table for full-text search
    edges          — relationships between symbols (calls, imports, extends, ...)
    files          — tracked source file metadata
    unresolved_refs — references awaiting resolution after extraction
"""
from __future__ import annotations

import hashlib
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

CACHE_DIR = Path(".ai-cache") / "aihelper"

# ── Schema ────────────────────────────────────────────────────────

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA cache_size=-8000;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS symbols (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    qualified_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    language TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    start_column INTEGER DEFAULT 0,
    end_column INTEGER DEFAULT 0,
    signature TEXT,
    docstring TEXT,
    visibility TEXT,
    is_exported INTEGER DEFAULT 0,
    is_async INTEGER DEFAULT 0,
    is_static INTEGER DEFAULT 0,
    is_abstract INTEGER DEFAULT 0,
    decorators TEXT,
    fingerprint TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    target TEXT NOT NULL,
    kind TEXT NOT NULL,
    line INTEGER,
    provenance TEXT DEFAULT 'regex',
    FOREIGN KEY (source) REFERENCES symbols(id) ON DELETE CASCADE,
    FOREIGN KEY (target) REFERENCES symbols(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,
    language TEXT NOT NULL,
    size INTEGER NOT NULL,
    modified_at INTEGER NOT NULL,
    indexed_at INTEGER NOT NULL,
    node_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS unresolved_refs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_node_id TEXT NOT NULL,
    reference_name TEXT NOT NULL,
    reference_kind TEXT NOT NULL,
    line INTEGER NOT NULL,
    col INTEGER DEFAULT 0,
    file_path TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL DEFAULT 'unknown',
    FOREIGN KEY (from_node_id) REFERENCES symbols(id) ON DELETE CASCADE
);

-- FTS5 full-text search
CREATE VIRTUAL TABLE IF NOT EXISTS symbols_fts USING fts5(
    name,
    qualified_name,
    docstring,
    signature,
    content='symbols',
    content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS symbols_ai AFTER INSERT ON symbols BEGIN
    INSERT INTO symbols_fts(rowid, name, qualified_name, docstring, signature)
    VALUES (NEW.rowid, NEW.name, NEW.qualified_name, NEW.docstring, NEW.signature);
END;

CREATE TRIGGER IF NOT EXISTS symbols_ad AFTER DELETE ON symbols BEGIN
    INSERT INTO symbols_fts(symbols_fts, rowid, name, qualified_name, docstring, signature)
    VALUES ('delete', OLD.rowid, OLD.name, OLD.qualified_name, OLD.docstring, OLD.signature);
END;

CREATE TRIGGER IF NOT EXISTS symbols_au AFTER UPDATE ON symbols BEGIN
    INSERT INTO symbols_fts(symbols_fts, rowid, name, qualified_name, docstring, signature)
    VALUES ('delete', OLD.rowid, OLD.name, OLD.qualified_name, OLD.docstring, OLD.signature);
    INSERT INTO symbols_fts(rowid, name, qualified_name, docstring, signature)
    VALUES (NEW.rowid, NEW.name, NEW.qualified_name, NEW.docstring, NEW.signature);
END;

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_symbols_kind ON symbols(kind);
CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
CREATE INDEX IF NOT EXISTS idx_symbols_qname ON symbols(qualified_name);
CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_path);
CREATE INDEX IF NOT EXISTS idx_symbols_file_line ON symbols(file_path, start_line);
CREATE INDEX IF NOT EXISTS idx_symbols_language ON symbols(language);
CREATE INDEX IF NOT EXISTS idx_edges_source_kind ON edges(source, kind);
CREATE INDEX IF NOT EXISTS idx_edges_target_kind ON edges(target, kind);
CREATE INDEX IF NOT EXISTS idx_edges_kind ON edges(kind);
CREATE INDEX IF NOT EXISTS idx_files_language ON files(language);
CREATE INDEX IF NOT EXISTS idx_files_modified ON files(modified_at);
CREATE INDEX IF NOT EXISTS idx_unresolved_from ON unresolved_refs(from_node_id);
CREATE INDEX IF NOT EXISTS idx_unresolved_name ON unresolved_refs(reference_name);
CREATE INDEX IF NOT EXISTS idx_unresolved_file ON unresolved_refs(file_path);

-- Project metadata
CREATE TABLE IF NOT EXISTS project_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);
"""

# ── Database Manager ──────────────────────────────────────────────

class GraphDatabase:
    """SQLite-backed knowledge graph — zero dependency ngoài Python stdlib."""

    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve()
        self.db_path = self.project_root / CACHE_DIR / "aihelper.db"
        self._local = threading.local()
        self._init_db()

    def _init_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._get_conn()
        conn.executescript(SCHEMA_SQL)
        conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(self.db_path))
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA foreign_keys=ON")
        return self._local.conn

    # ── File Operations ───────────────────────────────────────────

    def upsert_file(self, path: str, content_hash: str, language: str,
                    size: int, modified_at: float, node_count: int = 0):
        conn = self._get_conn()
        now = int(time.time() * 1000)
        conn.execute("""
            INSERT INTO files (path, content_hash, language, size, modified_at, indexed_at, node_count)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                content_hash=excluded.content_hash,
                language=excluded.language,
                size=excluded.size,
                modified_at=excluded.modified_at,
                indexed_at=excluded.indexed_at,
                node_count=excluded.node_count
        """, (path, content_hash, language, size, int(modified_at * 1000), now, node_count))
        conn.commit()

    def delete_file(self, path: str) -> int:
        conn = self._get_conn()
        c = conn.execute("DELETE FROM files WHERE path = ?", (path,))
        conn.commit()
        return c.rowcount

    def get_file(self, path: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM files WHERE path = ?", (path,)).fetchone()
        return dict(row) if row else None

    def get_all_files(self) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        return [dict(r) for r in conn.execute("SELECT * FROM files ORDER BY path").fetchall()]

    # ── Symbol CRUD ───────────────────────────────────────────────

    def insert_symbols_batch(self, symbols: List[Dict[str, Any]]):
        if not symbols:
            return
        conn = self._get_conn()
        now = int(time.time() * 1000)
        rows = []
        for s in symbols:
            sid = s.get("id", "")
            if not sid:
                sid = hashlib.sha1(
                    f"{s.get('file_path','')}::{s.get('name','')}".encode()
                ).hexdigest()[:16]
            rows.append((
                sid,
                s.get("kind", "unknown"),
                s.get("name", ""),
                s.get("qualified_name", s.get("name", "")),
                s.get("file_path", ""),
                s.get("language", "unknown"),
                s.get("start_line", 1),
                s.get("end_line", 1),
                s.get("start_column", 0),
                s.get("end_column", 0),
                s.get("signature", ""),
                s.get("docstring"),
                s.get("visibility"),
                int(s.get("is_exported", False)),
                int(s.get("is_async", False)),
                int(s.get("is_static", False)),
                int(s.get("is_abstract", False)),
                s.get("decorators"),
                s.get("fingerprint", ""),
                now,
            ))
        conn.executemany("""
            INSERT OR REPLACE INTO symbols
            (id, kind, name, qualified_name, file_path, language,
             start_line, end_line, start_column, end_column,
             signature, docstring, visibility,
             is_exported, is_async, is_static, is_abstract,
             decorators, fingerprint, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, rows)
        conn.commit()

    def insert_edges_batch(self, edges: List[Dict[str, Any]]):
        if not edges:
            return
        conn = self._get_conn()
        rows = []
        for e in edges:
            rows.append((
                e.get("source", ""),
                e.get("target", ""),
                e.get("kind", "references"),
                e.get("line"),
                e.get("provenance", "regex"),
            ))
        conn.executemany("""
            INSERT INTO edges (source, target, kind, line, provenance)
            VALUES (?, ?, ?, ?, ?)
        """, rows)
        conn.commit()

    def insert_unresolved_batch(self, refs: List[Dict[str, Any]]):
        if not refs:
            return
        conn = self._get_conn()
        rows = []
        for r in refs:
            rows.append((
                r.get("from_node_id", ""),
                r.get("reference_name", ""),
                r.get("reference_kind", "calls"),
                r.get("line", 1),
                r.get("col", 0),
                r.get("file_path", ""),
                r.get("language", "unknown"),
            ))
        conn.executemany("""
            INSERT INTO unresolved_refs
            (from_node_id, reference_name, reference_kind, line, col, file_path, language)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, rows)
        conn.commit()

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM symbols WHERE id = ?", (node_id,)).fetchone()
        return dict(row) if row else None

    def get_nodes_by_file(self, file_path: str) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        return [dict(r) for r in conn.execute(
            "SELECT * FROM symbols WHERE file_path = ? ORDER BY start_line", (file_path,)
        ).fetchall()]

    def get_nodes_by_kind(self, kind: str) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        return [dict(r) for r in conn.execute(
            "SELECT * FROM symbols WHERE kind = ? ORDER BY name", (kind,)
        ).fetchall()]

    def get_children(self, node_id: str) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        return [dict(r) for r in conn.execute("""
            SELECT s.* FROM symbols s
            JOIN edges e ON e.target = s.id
            WHERE e.source = ? AND e.kind = 'contains'
            ORDER BY s.start_line
        """, (node_id,)).fetchall()]

    # ── FTS5 Search ───────────────────────────────────────────────

    def search_symbols(self, query: str, kind: Optional[str] = None,
                       language: Optional[str] = None,
                       file_pattern: Optional[str] = None,
                       limit: int = 20,
                       offset: int = 0) -> List[Dict[str, Any]]:
        """FTS5 full-text search — sub-millisecond."""
        conn = self._get_conn()
        safe_query = query.replace('"', '""').strip()
        if not safe_query:
            return []

        # Prefix search: append * for partial match
        fts_query = f'"{safe_query}"*' if " " not in safe_query else safe_query

        params: List[Any] = [fts_query]
        sql = """
            SELECT s.* FROM symbols s
            JOIN symbols_fts fts ON s.rowid = fts.rowid
            WHERE symbols_fts MATCH ?
        """
        if kind:
            sql += " AND s.kind = ?"
            params.append(kind)
        if language:
            sql += " AND s.language = ?"
            params.append(language)
        if file_pattern:
            sql += " AND s.file_path LIKE ?"
            params.append(f"%{file_pattern}%")

        sql += " ORDER BY rank LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def search_by_name(self, name: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Exact / prefix name lookup (nhanh hơn FTS5 cho simple query)."""
        conn = self._get_conn()
        rows = conn.execute("""
            SELECT * FROM symbols
            WHERE name = ? OR name LIKE ?
            ORDER BY CASE WHEN name = ? THEN 0 ELSE 1 END, name
            LIMIT ?
        """, (name, f"{name}%", name, limit)).fetchall()
        return [dict(r) for r in rows]

    # ── Graph Traversal ───────────────────────────────────────────

    def get_outgoing_edges(self, node_id: str,
                           edge_kinds: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        if edge_kinds:
            placeholders = ",".join("?" * len(edge_kinds))
            rows = conn.execute(
                f"SELECT * FROM edges WHERE source = ? AND kind IN ({placeholders})",
                [node_id] + edge_kinds
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM edges WHERE source = ?", (node_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_incoming_edges(self, node_id: str,
                           edge_kinds: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        if edge_kinds:
            placeholders = ",".join("?" * len(edge_kinds))
            rows = conn.execute(
                f"SELECT * FROM edges WHERE target = ? AND kind IN ({placeholders})",
                [node_id] + edge_kinds
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM edges WHERE target = ?", (node_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_callers(self, symbol_id: str, max_depth: int = 1) -> List[Dict[str, Any]]:
        """BFS: tìm tất cả symbols gọi symbol này."""
        conn = self._get_conn()
        if max_depth <= 1:
            rows = conn.execute("""
                SELECT s.*, e.line as call_line
                FROM edges e
                JOIN symbols s ON e.source = s.id
                WHERE e.target = ? AND e.kind = 'calls'
                ORDER BY s.name
            """, (symbol_id,)).fetchall()
            return [dict(r) for r in rows]

        rows = conn.execute("""
            WITH RECURSIVE caller_chain(depth, source_id) AS (
                SELECT 1, source FROM edges
                WHERE target = ? AND kind = 'calls'
                UNION ALL
                SELECT c.depth + 1, e.source
                FROM edges e
                JOIN caller_chain c ON e.target = c.source_id
                WHERE e.kind = 'calls' AND c.depth < ?
            )
            SELECT DISTINCT s.*, cc.depth
            FROM caller_chain cc
            JOIN symbols s ON s.id = cc.source_id
            ORDER BY cc.depth, s.name
        """, (symbol_id, max_depth)).fetchall()
        return [dict(r) for r in rows]

    def get_callees(self, symbol_id: str, max_depth: int = 1) -> List[Dict[str, Any]]:
        """BFS: tìm tất cả symbols được symbol này gọi."""
        conn = self._get_conn()
        if max_depth <= 1:
            rows = conn.execute("""
                SELECT s.*, e.line as call_line
                FROM edges e
                JOIN symbols s ON e.target = s.id
                WHERE e.source = ? AND e.kind = 'calls'
                ORDER BY s.name
            """, (symbol_id,)).fetchall()
            return [dict(r) for r in rows]

        rows = conn.execute("""
            WITH RECURSIVE callee_chain(depth, target_id) AS (
                SELECT 1, target FROM edges
                WHERE source = ? AND kind = 'calls'
                UNION ALL
                SELECT c.depth + 1, e.target
                FROM edges e
                JOIN callee_chain c ON e.source = c.target_id
                WHERE e.kind = 'calls' AND c.depth < ?
            )
            SELECT DISTINCT s.*, cc.depth
            FROM callee_chain cc
            JOIN symbols s ON s.id = cc.target_id
            ORDER BY cc.depth, s.name
        """, (symbol_id, max_depth)).fetchall()
        return [dict(r) for r in rows]

    def find_path(self, from_id: str, to_id: str,
                  edge_kinds: Optional[List[str]] = None,
                  max_depth: int = 7) -> Optional[List[Dict[str, Any]]]:
        """BFS shortest path giữa hai symbols."""
        conn = self._get_conn()
        edge_kinds = edge_kinds or ["calls"]
        placeholders = ",".join("?" * len(edge_kinds))

        rows = conn.execute(f"""
            WITH RECURSIVE
            bfs(depth, node_id, path_ids) AS (
                SELECT 0, ?, ''
                UNION ALL
                SELECT b.depth + 1, e.target, b.path_ids || ',' || e.target
                FROM bfs b
                JOIN edges e ON e.source = b.node_id AND e.kind IN ({placeholders})
                WHERE b.depth < ?
                  AND b.path_ids NOT LIKE '%' || e.target || '%'
            )
            SELECT s.*, b.depth
            FROM bfs b
            JOIN symbols s ON s.id = b.node_id
            WHERE b.node_id = ?
            ORDER BY b.depth
            LIMIT 1
        """, [from_id] + edge_kinds + [max_depth, to_id]).fetchall()

        if not rows:
            return None
        return [dict(r) for r in rows]

    def get_impact_radius(self, symbol_id: str, max_depth: int = 3) -> List[Dict[str, Any]]:
        """Transitive closure của callers + importers."""
        conn = self._get_conn()
        rows = conn.execute("""
            WITH RECURSIVE impact(depth, node_id) AS (
                SELECT 0, ?
                UNION
                SELECT i.depth + 1, e.source
                FROM impact i
                JOIN edges e ON e.target = i.node_id
                WHERE e.kind IN ('calls', 'imports', 'references')
                  AND i.depth < ?
            )
            SELECT DISTINCT s.*, i.depth
            FROM impact i
            JOIN symbols s ON s.id = i.node_id
            ORDER BY i.depth, s.file_path
        """, (symbol_id, max_depth)).fetchall()
        return [dict(r) for r in rows]

    def get_type_hierarchy(self, symbol_id: str) -> Dict[str, Any]:
        """Lấy ancestors + descendants."""
        conn = self._get_conn()
        ancestors = conn.execute("""
            WITH RECURSIVE hierarchy(depth, node_id) AS (
                SELECT 0, ?
                UNION ALL
                SELECT h.depth + 1, e.target
                FROM hierarchy h
                JOIN edges e ON e.source = h.node_id
                WHERE e.kind IN ('extends', 'implements')
            )
            SELECT s.*, h.depth FROM hierarchy h
            JOIN symbols s ON s.id = h.node_id
            WHERE h.depth > 0
        """, (symbol_id,)).fetchall()

        descendants = conn.execute("""
            WITH RECURSIVE hierarchy(depth, node_id) AS (
                SELECT 0, ?
                UNION ALL
                SELECT h.depth + 1, e.source
                FROM hierarchy h
                JOIN edges e ON e.target = h.node_id
                WHERE e.kind IN ('extends', 'implements')
            )
            SELECT s.*, h.depth FROM hierarchy h
            JOIN symbols s ON s.id = h.node_id
            WHERE h.depth > 0
        """, (symbol_id,)).fetchall()

        return {
            "ancestors": [dict(r) for r in ancestors],
            "descendants": [dict(r) for r in descendants],
        }

    def find_dead_code(self, kinds: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Tìm symbols không có incoming edges."""
        conn = self._get_conn()
        target_kinds = kinds or ["function", "method", "class"]
        placeholders = ",".join("?" * len(target_kinds))
        rows = conn.execute(f"""
            SELECT s.* FROM symbols s
            WHERE s.kind IN ({placeholders})
            AND s.id NOT IN (
                SELECT DISTINCT target FROM edges
                WHERE kind IN ('calls', 'references', 'imports')
            )
            AND (s.visibility IS NULL OR s.visibility != 'private')
            ORDER BY s.file_path, s.name
        """, target_kinds).fetchall()
        return [dict(r) for r in rows]

    def find_circular_deps(self) -> List[List[str]]:
        """Tìm circular dependencies (file-level)."""
        conn = self._get_conn()
        rows = conn.execute("""
            WITH RECURSIVE dep_chain(path, current, depth) AS (
                SELECT e.source || '→' || e.target, e.target, 1
                FROM edges e
                WHERE e.kind IN ('imports', 'calls')
                UNION ALL
                SELECT d.path || '→' || e.target, e.target, d.depth + 1
                FROM dep_chain d
                JOIN edges e ON e.source = d.current
                WHERE e.kind IN ('imports', 'calls')
                  AND d.depth < 10
                  AND d.path NOT LIKE '%' || e.target || '%'
            )
            SELECT DISTINCT path FROM dep_chain
            WHERE depth > 1
        """).fetchall()
        return [r["path"].split("→") for r in rows if r["path"].count("→") >= 2]

    def get_file_dependencies(self, file_path: str) -> List[str]:
        conn = self._get_conn()
        node_ids = [r["id"] for r in conn.execute(
            "SELECT id FROM symbols WHERE file_path = ?", (file_path,)
        ).fetchall()]
        if not node_ids:
            return []
        placeholders = ",".join("?" * len(node_ids))
        rows = conn.execute(f"""
            SELECT DISTINCT s.file_path
            FROM edges e
            JOIN symbols s ON s.id = e.target
            WHERE e.source IN ({placeholders}) AND e.kind = 'imports'
        """, node_ids).fetchall()
        return sorted(set(r["file_path"] for r in rows))

    def get_file_dependents(self, file_path: str) -> List[str]:
        conn = self._get_conn()
        node_ids = [r["id"] for r in conn.execute(
            "SELECT id FROM symbols WHERE file_path = ?", (file_path,)
        ).fetchall()]
        if not node_ids:
            return []
        placeholders = ",".join("?" * len(node_ids))
        rows = conn.execute(f"""
            SELECT DISTINCT s.file_path
            FROM edges e
            JOIN symbols s ON s.id = e.source
            WHERE e.target IN ({placeholders}) AND e.kind = 'imports'
        """, node_ids).fetchall()
        return sorted(set(r["file_path"] for r in rows))

    # ── Route / Framework Nodes ───────────────────────────────────

    def insert_route(self, method: str, path: str, handler_name: str,
                     file_path: str, line: int, framework: str):
        conn = self._get_conn()
        route_id = f"{file_path}::route::{path}"
        handler_id = f"{file_path}::{handler_name}"
        now = int(time.time() * 1000)
        conn.execute("""
            INSERT OR REPLACE INTO symbols
            (id, kind, name, qualified_name, file_path, language, start_line, end_line, fingerprint, updated_at)
            VALUES (?, 'route', ?, ?, ?, 'yaml', ?, ?, ?, ?)
        """, (route_id, f"{method} {path}", f"{method} {path}", file_path, line, line,
              hashlib.sha1(f"route:{method}:{path}".encode()).hexdigest(), now))
        conn.execute("""
            INSERT INTO edges (source, target, kind, line, provenance)
            VALUES (?, ?, 'references', ?, 'framework')
        """, (route_id, handler_id, line))
        conn.commit()

    # ── Stats ─────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        conn = self._get_conn()
        db_size = self.db_path.stat().st_size if self.db_path.exists() else 0

        kind_rows = conn.execute(
            "SELECT kind, COUNT(*) as cnt FROM symbols GROUP BY kind"
        ).fetchall()
        lang_rows = conn.execute(
            "SELECT language, COUNT(*) as cnt FROM files GROUP BY language"
        ).fetchall()
        edge_rows = conn.execute(
            "SELECT kind, COUNT(*) as cnt FROM edges GROUP BY kind"
        ).fetchall()

        return {
            "symbol_count": conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0],
            "edge_count": conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0],
            "file_count": conn.execute("SELECT COUNT(*) FROM files").fetchone()[0],
            "db_size_bytes": db_size,
            "db_size_mb": round(db_size / 1024 / 1024, 2),
            "nodes_by_kind": {r["kind"]: r["cnt"] for r in kind_rows},
            "files_by_language": {r["language"]: r["cnt"] for r in lang_rows},
            "edges_by_kind": {r["kind"]: r["cnt"] for r in edge_rows},
            "journal_mode": conn.execute("PRAGMA journal_mode").fetchone()[0],
        }

    def get_journal_mode(self) -> str:
        return self._get_conn().execute("PRAGMA journal_mode").fetchone()[0]

    # ── Maintenance ───────────────────────────────────────────────

    def clear(self):
        conn = self._get_conn()
        conn.execute("DELETE FROM edges")
        conn.execute("DELETE FROM unresolved_refs")
        conn.execute("DELETE FROM symbols")
        conn.execute("DELETE FROM files")
        conn.execute("DELETE FROM project_metadata")
        conn.commit()

    def optimize(self):
        conn = self._get_conn()
        conn.execute("PRAGMA optimize")
        conn.execute("PRAGMA analysis_limit=400")
        conn.execute("PRAGMA optimize")
        conn.commit()

    def warm_cache(self):
        conn = self._get_conn()
        conn.execute("SELECT COUNT(*) FROM symbols")
        conn.execute("SELECT COUNT(*) FROM edges")

    def close(self):
        if hasattr(self._local, "conn") and self._local.conn:
            try:
                self._local.conn.close()
            except Exception:
                pass
            self._local.conn = None


# ── Singleton Manager ─────────────────────────────────────────────

_db_instances: Dict[str, GraphDatabase] = {}

def get_db(project_root: Path) -> GraphDatabase:
    key = str(project_root.resolve())
    if key not in _db_instances:
        _db_instances[key] = GraphDatabase(project_root)
    return _db_instances[key]

def close_all():
    for db in _db_instances.values():
        db.close()
    _db_instances.clear()
