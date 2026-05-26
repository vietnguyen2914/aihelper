from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

try:
    from .common import normalize_identifier, safe_load_json, safe_write_json
except ImportError:
    from common import normalize_identifier, safe_load_json, safe_write_json


AIHELPER_CACHE_VERSION = "2.0"
CACHE_DIR = Path(".ai-cache") / "aihelper"
DEFAULT_EXTENSIONS = {
    ".java",
    ".kt",
    ".kts",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".py",
    ".php",
    ".sql",
    ".yml",
    ".yaml",
    ".json",
    ".md",
}
IGNORED_PARTS = {
    ".git",
    ".ai-cache",
    ".cache",
    ".idea",
    ".vscode",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "target",
    "vendor",
    "coverage",
}


def cache_root(project_root: Path) -> Path:
    return project_root.resolve() / CACHE_DIR


def cache_paths(project_root: Path) -> Dict[str, Path]:
    root = cache_root(project_root)
    return {
        "root": root,
        "manifest": root / "manifest.json",
        "file_index": root / "file_index.json",
        "repo_summary": root / "repo_summary.json",
        "symbol_graph": root / "symbol_graph.json",
        "dependency_graph": root / "dependency_graph.json",
        "db_schema_summary": root / "db_schema_summary.json",
    }


def _is_ignored(path: Path, project_root: Path) -> bool:
    try:
        relative = path.relative_to(project_root)
    except ValueError:
        return True
    return any(part in IGNORED_PARTS for part in relative.parts)


def _iter_files(project_root: Path) -> Iterable[Path]:
    fd = shutil.which("fd")
    if fd:
        result = subprocess.run(
            [fd, "--type", "f", "--hidden", "--exclude", ".git", "--exclude", ".ai-cache"],
            cwd=str(project_root),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                path = (project_root / line).resolve()
                if path.suffix.lower() in DEFAULT_EXTENSIONS and not _is_ignored(path, project_root):
                    yield path
            return

    for path in project_root.rglob("*"):
        if path.is_file() and path.suffix.lower() in DEFAULT_EXTENSIONS and not _is_ignored(path, project_root):
            yield path


def _file_digest(path: Path, limit_bytes: int = 65536) -> str:
    digest = hashlib.sha1()
    try:
        with path.open("rb") as handle:
            digest.update(handle.read(limit_bytes))
    except OSError:
        return ""
    return digest.hexdigest()


def _semantic_digest(text: str, suffix: str) -> str:
    if suffix in {".md", ".json", ".yml", ".yaml"}:
        normalized = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    else:
        normalized_lines = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(("#", "//", "/*", "*")):
                continue
            normalized_lines.append(re.sub(r"\s+", " ", stripped))
        normalized = "\n".join(normalized_lines)
    return hashlib.sha1(normalized.encode("utf-8", errors="ignore")).hexdigest()


def load_cached_file_index(project_root: Path) -> Dict[str, Any]:
    """Load the cached file_index from JSON, return empty dict if not exists."""
    paths = cache_paths(project_root.resolve())
    return safe_load_json(paths["file_index"], default={}) or {}


def build_file_index_incremental(project_root: Path, diff: Dict[str, Any]) -> Dict[str, Any]:
    """Build file index for only changed files, merge with existing cache.

    This is the heart of incremental update:
    1. Load cached file_index
    2. Remove entries for deleted/changed files
    3. Build fresh entries for added/changed files
    4. Return merged result — no full filesystem scan.
    """
    cached = load_cached_file_index(project_root)
    existing = {item.get("path"): item for item in cached.get("files", [])}

    # Remove stale entries
    for path in diff.get("removed", []) + diff.get("changed", []) + diff.get("semantic_changed", []):
        existing.pop(path, None)

    # Build new entries only for changed files
    touched = set(diff.get("added", []) + diff.get("changed", []) + diff.get("semantic_changed", []))
    fresh_files: List[Dict[str, Any]] = []
    extension_counts: Dict[str, int] = {}

    for item in cached.get("files", []):
        fp = item.get("path", "")
        if fp not in touched:
            fresh_files.append(item)
            ext = item.get("extension", "")
            extension_counts[ext] = extension_counts.get(ext, 0) + 1

    for relative in sorted(touched):
        path = project_root / relative
        try:
            stat = path.stat()
        except OSError:
            continue
        ext = path.suffix.lower()
        text = _read_text(path, max_bytes=256000)
        extension_counts[ext] = extension_counts.get(ext, 0) + 1
        fresh_files.append({
            "path": relative,
            "name": path.name,
            "extension": ext,
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "sha1_head": _file_digest(path),
            "semantic_sha1": _semantic_digest(text, ext) if text else "",
        })

    return {"files": fresh_files, "extension_counts": extension_counts, "count": len(fresh_files)}


def build_symbol_graph_incremental(project_root: Path, file_index: Dict[str, Any],
                                    diff: Dict[str, Any], existing_symbol_graph: Dict[str, Any]) -> Dict[str, Any]:
    """Build symbol graph for only changed files, merge with existing.

    1. Remove symbols for changed/removed files
    2. Extract symbols only for added/changed files
    3. Rebuild by_name index
    4. Merge imports_by_file
    """
    from .common import normalize_identifier

    existing_symbols = existing_symbol_graph.get("symbols", [])
    existing_imports = existing_symbol_graph.get("imports_by_file", {})
    touched = set(diff.get("added", []) + diff.get("changed", []) + diff.get("semantic_changed", []))
    removed = set(diff.get("removed", []))

    # Filter out symbols from touched/removed files
    kept_symbols = [
        s for s in existing_symbols
        if s.get("file", "") not in touched and s.get("file", "") not in removed
    ]

    # Filter out imports from touched/removed files
    kept_imports = {
        k: v for k, v in existing_imports.items()
        if k not in touched and k not in removed
    }

    # Extract symbols and imports only for touched files
    new_symbols: List[Dict[str, Any]] = []
    new_imports: Dict[str, List[str]] = {}
    for item in file_index.get("files", []):
        relative = str(item.get("path", ""))
        if relative not in touched:
            continue
        suffix = str(item.get("extension", ""))
        if suffix not in {".java", ".kt", ".kts", ".ts", ".tsx", ".js", ".jsx", ".py", ".php"}:
            continue
        path = project_root / relative
        text = _read_text(path)
        if not text:
            continue
        imports: List[str] = []
        for line_no, line in enumerate(text.splitlines(), start=1):
            if len(imports) < 40 and IMPORT_PATTERN.search(line):
                imports.append(line.strip()[:240])
            for kind, pattern in SYMBOL_PATTERNS:
                match = pattern.search(line)
                if not match:
                    continue
                name = match.group(1)
                new_symbols.append({
                    "name": name,
                    "normalized": normalize_identifier(name),
                    "kind": kind.replace("python_", "").replace("php_", ""),
                    "file": relative,
                    "line": line_no,
                    "signature": line.strip()[:240],
                    "fingerprint": hashlib.sha1(f"{kind}:{name}:{line.strip()}".encode("utf-8")).hexdigest(),
                })
                break
        if imports:
            new_imports[relative] = imports

    # Merge
    all_symbols = kept_symbols + new_symbols
    all_imports = {**kept_imports, **new_imports}

    by_name: Dict[str, List[Dict[str, Any]]] = {}
    for symbol in all_symbols:
        by_name.setdefault(symbol["normalized"], []).append(symbol)

    return {"symbols": all_symbols, "by_name": by_name, "imports_by_file": all_imports, "count": len(all_symbols)}


def sync_sqlite_incremental(project_root: Path, diff: Dict[str, Any],
                             file_index: Dict[str, Any],
                             symbol_graph: Dict[str, Any],
                             dependency_graph: Dict[str, Any]) -> None:
    """Sync SQLite incrementally — only DELETE old + INSERT new for changed files.

    Instead of full clear + reinsert (which _sync_cache_to_sqlite does),
    this DELETEs symbols/edges for removed files, then INSERTs only files that changed.
    """
    from .graph_db import get_db
    import hashlib as _hashlib

    db = get_db(project_root)
    removed = set(diff.get("removed", []))
    touched = set(diff.get("added", []) + diff.get("changed", []) + diff.get("semantic_changed", []))
    all_affected = removed | touched

    if not all_affected:
        return

    # Step 1: Delete old data for affected files
    for fpath in all_affected:
        db.delete_file(fpath)

    # Step 2: Insert updated file records
    for item in file_index.get("files", []):
        fpath = item.get("path", "")
        if fpath not in all_affected:
            continue
        suffix = Path(fpath).suffix.lower()
        lm = {".py": "python", ".js": "javascript", ".mjs": "javascript",
              ".ts": "typescript", ".tsx": "tsx", ".java": "java",
              ".go": "go", ".rs": "rust", ".php": "php",
              ".c": "c", ".h": "c", ".cpp": "cpp", ".cc": "cpp",
              ".hpp": "cpp", ".rb": "ruby", ".swift": "swift",
              ".kt": "kotlin", ".kts": "kotlin", ".cs": "csharp",
              ".lua": "lua", ".dart": "dart", ".sql": "sql",
              ".json": "json", ".yml": "yaml", ".yaml": "yaml",
              ".md": "markdown", ".vue": "vue", ".svelte": "svelte"}
        language = lm.get(suffix, "unknown")
        db.upsert_file(fpath, item.get("semantic_sha1", ""), language,
                       item.get("size", 0), item.get("mtime_ns", 0))

    # Step 3: Insert symbols for touched files only
    new_syms = []
    for sym in symbol_graph.get("symbols", []):
        if sym.get("file", "") not in touched:
            continue
        new_syms.append({
            "id": f"{sym['file']}::{sym['name']}",
            "kind": sym.get("kind", "unknown"),
            "name": sym["name"],
            "qualified_name": f"{sym['file']}::{sym['name']}",
            "file_path": sym["file"],
            "language": _detect_language(sym["file"]),
            "start_line": sym.get("line", 1),
            "end_line": sym.get("line", 1),
            "signature": sym.get("signature", ""),
            "fingerprint": sym.get("fingerprint", ""),
        })
    if new_syms:
        db.insert_symbols_batch(new_syms)

    # Step 4: Insert file nodes for FK + edges
    edges_list = []
    for edge in dependency_graph.get("edges", []):
        from_file = edge.get("from", "")
        to_file = edge.get("to", "")
        if not from_file or not to_file:
            continue
        if from_file in all_affected or to_file in all_affected:
            edges_list.append({
                "source": from_file, "target": to_file,
                "kind": "imports", "provenance": "regex",
            })
    # Ensure file nodes exist for FK
    file_ids = set()
    for e in edges_list:
        file_ids.add(e["source"])
        file_ids.add(e["target"])
    for fid in file_ids:
        try:
            db.insert_symbols_batch([{
                "id": fid, "kind": "file",
                "name": fid.split("/")[-1] if "/" in fid else fid,
                "qualified_name": fid, "file_path": fid,
                "language": _detect_language(fid),
                "start_line": 1, "end_line": 1,
                "fingerprint": _hashlib.sha1(fid.encode()).hexdigest(),
            }])
        except Exception:
            pass
    if edges_list:
        try:
            db.insert_edges_batch(edges_list)
        except Exception:
            pass


def update_cache(project_root: Path) -> Dict[str, Any]:
    """Incremental cache update — only rebuilds data for changed files.

    Uses cache_diff() to detect changes, then incrementally updates:
    - file_index (JSON + SQLite files table)
    - symbol_graph (JSON + SQLite symbols table)
    - dependency_graph (JSON + SQLite edges table)

    Falls back to full build_cache if no existing cache exists.
    """
    project_root = project_root.resolve()
    paths = cache_paths(project_root)

    # If no cache exists, do full build
    status = cache_status(project_root)
    if not status.get("fresh"):
        return build_cache(project_root)

    # Incremental: detect what changed
    diff = cache_diff(project_root)
    if not diff.get("dirty"):
        # Nothing changed — fast path
        return {"manifest": status.get("manifest", {}),
                "cache_dir": str(paths["root"]), "updated": False}

    # Incremental: only build for changed files
    file_index = build_file_index_incremental(project_root, diff)
    existing_sg = safe_load_json(paths["symbol_graph"], default={}) or {}
    symbol_graph = build_symbol_graph_incremental(project_root, file_index, diff, existing_sg)
    dependency_graph = build_dependency_graph(file_index, symbol_graph)

    # Write JSON files (always full — JSON is backup; SQLite is primary)
    repo_summary = build_repo_summary(project_root, file_index)
    db_schema_summary = build_db_schema_summary(project_root, file_index)
    manifest = {
        "version": AIHELPER_CACHE_VERSION,
        "project_root": str(project_root),
        "built_at": datetime.now(timezone.utc).isoformat(),
        "file_count": file_index.get("count", 0),
        "symbol_count": symbol_graph.get("count", 0),
        "semantic_fingerprints": True,
        "incremental": True,
    }
    safe_write_json(paths["file_index"], file_index)
    safe_write_json(paths["repo_summary"], repo_summary)
    safe_write_json(paths["symbol_graph"], symbol_graph)
    safe_write_json(paths["dependency_graph"], dependency_graph)
    safe_write_json(paths["db_schema_summary"], db_schema_summary)
    safe_write_json(paths["manifest"], manifest)

    # Incremental SQLite sync
    try:
        sync_sqlite_incremental(project_root, diff, file_index, symbol_graph, dependency_graph)
        manifest["sqlite_synced"] = True
    except Exception:
        manifest["sqlite_synced"] = False

    return {"manifest": manifest, "cache_dir": str(paths["root"]),
            "updated": True, "changes": diff}


def build_file_index(project_root: Path) -> Dict[str, Any]:
    """Build full file index. Prefer update_cache() for incremental updates."""
    files: List[Dict[str, Any]] = []
    extension_counts: Dict[str, int] = {}
    for path in sorted(_iter_files(project_root), key=lambda item: str(item)):
        try:
            stat = path.stat()
            relative = str(path.relative_to(project_root))
        except OSError:
            continue
        extension = path.suffix.lower()
        text = _read_text(path, max_bytes=256000)
        extension_counts[extension] = extension_counts.get(extension, 0) + 1
        files.append(
            {
                "path": relative,
                "name": path.name,
                "extension": extension,
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "sha1_head": _file_digest(path),
                "semantic_sha1": _semantic_digest(text, extension) if text else "",
            }
        )
    return {"files": files, "extension_counts": extension_counts, "count": len(files)}


def _classify_file(path: str) -> str:
    lower = path.lower()
    if "controller" in lower or "/pages/" in lower or "/routes/" in lower:
        return "entrypoint"
    if "service" in lower or "manager" in lower:
        return "service"
    if "repository" in lower or "dao" in lower:
        return "data_access"
    if "entity" in lower or "model" in lower or "/domain/" in lower:
        return "model"
    if "migration" in lower or lower.endswith(".sql"):
        return "schema"
    if lower.endswith((".md", ".mdx")):
        return "docs"
    return "source"


def build_repo_summary(project_root: Path, file_index: Dict[str, Any]) -> Dict[str, Any]:
    files = file_index.get("files", [])
    by_kind: Dict[str, int] = {}
    important: List[Dict[str, Any]] = []
    for item in files:
        path = str(item.get("path", ""))
        kind = _classify_file(path)
        by_kind[kind] = by_kind.get(kind, 0) + 1
        if kind in {"entrypoint", "service", "model", "schema"} and len(important) < 80:
            important.append({"path": path, "kind": kind})
    return {
        "project_root": str(project_root),
        "file_count": len(files),
        "extension_counts": file_index.get("extension_counts", {}),
        "kind_counts": by_kind,
        "important_files": important,
    }


SYMBOL_PATTERNS = [
    ("class", re.compile(r"^\s*(?:export\s+)?(?:abstract\s+|final\s+)?class\s+([A-Za-z_][A-Za-z0-9_]*)")),
    ("interface", re.compile(r"^\s*(?:export\s+)?interface\s+([A-Za-z_][A-Za-z0-9_]*)")),
    ("enum", re.compile(r"^\s*(?:export\s+)?enum\s+([A-Za-z_][A-Za-z0-9_]*)")),
    ("function", re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")),
    ("method", re.compile(r"^\s*(?:public|private|protected|static|final|override|suspend)\s+(?:[A-Za-z0-9_<>, ?\[\].]+\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*\(")),
    ("python_class", re.compile(r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)")),
    ("python_function", re.compile(r"^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")),
    ("php_class", re.compile(r"^\s*(?:abstract\s+|final\s+)?class\s+([A-Za-z_][A-Za-z0-9_]*)")),
    ("php_function", re.compile(r"^\s*(?:public|private|protected)?\s*function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")),
    ("const", re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*[=:]")),
]
IMPORT_PATTERN = re.compile(r"^\s*(?:import\s+.+|from\s+[A-Za-z0-9_.]+\s+import\s+.+|use\s+[A-Za-z0-9_\\]+;|require\(.+\))")


def _read_text(path: Path, max_bytes: int = 512000) -> str:
    try:
        if path.stat().st_size > max_bytes:
            return ""
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def build_symbol_graph(project_root: Path, file_index: Dict[str, Any]) -> Dict[str, Any]:
    symbols: List[Dict[str, Any]] = []
    imports_by_file: Dict[str, List[str]] = {}
    for item in file_index.get("files", []):
        relative = str(item.get("path", ""))
        suffix = str(item.get("extension", ""))
        if suffix not in {".java", ".kt", ".kts", ".ts", ".tsx", ".js", ".jsx", ".py", ".php"}:
            continue
        path = project_root / relative
        text = _read_text(path)
        if not text:
            continue
        imports: List[str] = []
        for line_no, line in enumerate(text.splitlines(), start=1):
            if len(imports) < 40 and IMPORT_PATTERN.search(line):
                imports.append(line.strip()[:240])
            for kind, pattern in SYMBOL_PATTERNS:
                match = pattern.search(line)
                if not match:
                    continue
                name = match.group(1)
                symbols.append(
                    {
                        "name": name,
                        "normalized": normalize_identifier(name),
                        "kind": kind.replace("python_", "").replace("php_", ""),
                        "file": relative,
                        "line": line_no,
                        "signature": line.strip()[:240],
                        "fingerprint": hashlib.sha1(f"{kind}:{name}:{line.strip()}".encode("utf-8")).hexdigest(),
                    }
                )
                break
        if imports:
            imports_by_file[relative] = imports
    by_name: Dict[str, List[Dict[str, Any]]] = {}
    for symbol in symbols:
        by_name.setdefault(symbol["normalized"], []).append(symbol)
    return {"symbols": symbols, "by_name": by_name, "imports_by_file": imports_by_file, "count": len(symbols)}


def build_dependency_graph(file_index: Dict[str, Any], symbol_graph: Dict[str, Any]) -> Dict[str, Any]:
    edges: List[Dict[str, str]] = []
    for file_path, imports in symbol_graph.get("imports_by_file", {}).items():
        for import_line in imports[:40]:
            edges.append({"from": file_path, "to": import_line, "type": "import"})
    return {"edges": edges, "count": len(edges), "source": "import-lines"}


CREATE_TABLE_RE = re.compile(r"create\s+table\s+(?:if\s+not\s+exists\s+)?[`\"']?([A-Za-z0-9_.]+)[`\"']?\s*\((.*?)\)\s*;", re.IGNORECASE | re.DOTALL)
COLUMN_RE = re.compile(r"^\s*[`\"']?([A-Za-z_][A-Za-z0-9_]*)[`\"']?\s+([A-Za-z0-9_()]+)", re.IGNORECASE)


def build_db_schema_summary(project_root: Path, file_index: Dict[str, Any]) -> Dict[str, Any]:
    tables: Dict[str, Dict[str, Any]] = {}
    schema_files = [
        item for item in file_index.get("files", [])
        if str(item.get("extension")) == ".sql" or "migration" in str(item.get("path", "")).lower()
    ]
    for item in schema_files[:200]:
        relative = str(item.get("path", ""))
        text = _read_text(project_root / relative, max_bytes=1024 * 1024)
        for match in CREATE_TABLE_RE.finditer(text):
            table_name = match.group(1)
            body = match.group(2)
            columns: List[str] = []
            primary_key = ""
            foreign_keys: List[str] = []
            for raw_line in body.splitlines():
                line = raw_line.strip().rstrip(",")
                lower = line.lower()
                if lower.startswith("primary key"):
                    primary_key = line
                    continue
                if "foreign key" in lower or lower.startswith("constraint"):
                    foreign_keys.append(line[:240])
                    continue
                column_match = COLUMN_RE.search(line)
                if column_match and column_match.group(1).lower() not in {"primary", "foreign", "key", "constraint"}:
                    columns.append(column_match.group(1))
            tables[table_name] = {
                "columns": columns[:120],
                "primary_key": primary_key,
                "foreign_keys": foreign_keys[:40],
                "source": relative,
                "confidence": "sql_create_table",
            }
    return {"tables": tables, "count": len(tables), "source": "local-files"}


def cache_diff(project_root: Path) -> Dict[str, Any]:
    project_root = project_root.resolve()
    paths = cache_paths(project_root)
    cached = safe_load_json(paths["file_index"], default={}) or {}
    current = build_file_index(project_root)
    cached_by_path = {item.get("path"): item for item in cached.get("files", [])}
    current_by_path = {item.get("path"): item for item in current.get("files", [])}
    added = sorted(path for path in current_by_path if path not in cached_by_path)
    removed = sorted(path for path in cached_by_path if path not in current_by_path)
    changed = sorted(
        path
        for path, item in current_by_path.items()
        if path in cached_by_path
        and (
            item.get("semantic_sha1") != cached_by_path[path].get("semantic_sha1")
            or item.get("mtime_ns") != cached_by_path[path].get("mtime_ns")
        )
    )
    semantic_changed = sorted(
        path
        for path, item in current_by_path.items()
        if path in cached_by_path and item.get("semantic_sha1") != cached_by_path[path].get("semantic_sha1")
    )
    return {
        "project_root": str(project_root),
        "added": added,
        "removed": removed,
        "changed": changed,
        "semantic_changed": semantic_changed,
        "dirty": bool(added or removed or changed),
    }


def _watchman_available() -> bool:
    return bool(shutil.which("watchman"))


def _watchman_changed_files(project_root: Path, since: str | None = None) -> Dict[str, Any]:
    if not _watchman_available():
        return {"available": False, "files": [], "clock": ""}
    query: Dict[str, Any] = {
        "expression": [
            "allof",
            ["type", "f"],
            ["not", ["dirname", ".git"]],
            ["not", ["dirname", ".ai-cache"]],
        ],
        "fields": ["name"],
    }
    if since:
        query["since"] = since
    result = subprocess.run(
        ["watchman", "query", str(project_root), json.dumps(query)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        subprocess.run(["watchman", "watch-project", str(project_root)], text=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        result = subprocess.run(
            ["watchman", "query", str(project_root), json.dumps(query)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    if result.returncode != 0:
        return {"available": True, "error": result.stderr.strip(), "files": [], "clock": ""}
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"available": True, "error": "invalid_watchman_json", "files": [], "clock": ""}
    if payload.get("error"):
        subprocess.run(["watchman", "watch-project", str(project_root)], text=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        result = subprocess.run(
            ["watchman", "query", str(project_root), json.dumps(query)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"available": True, "error": "invalid_watchman_json", "files": [], "clock": ""}
    if payload.get("error"):
        return {"available": True, "error": str(payload.get("error")), "files": [], "clock": ""}
    return {
        "available": True,
        "files": [item.get("name") for item in payload.get("files", []) if isinstance(item, dict) and item.get("name")],
        "clock": payload.get("clock", ""),
    }


def _sync_cache_to_sqlite(project_root: Path, file_index: Dict, symbol_graph: Dict, dependency_graph: Dict) -> None:
    """Sync JSON cache → SQLite for graph queries (v0.0.7)."""
    from .graph_db import get_db
    import time
    import hashlib

    db = get_db(project_root)
    now = time.time()

    # Files
    for f in file_index.get("files", []):
        path = f.get("path", "")
        if not path:
            continue
        language = f.get("language", "unknown")
        if not language or language == "unknown":
            suffix = Path(path).suffix.lower()
            lang_map = {".py": "python", ".js": "javascript", ".ts": "typescript",
                        ".tsx": "tsx", ".java": "java", ".go": "go", ".rs": "rust",
                        ".php": "php", ".c": "c", ".cpp": "cpp", ".rb": "ruby",
                        ".swift": "swift", ".kt": "kotlin", ".cs": "csharp",
                        ".sql": "sql", ".json": "json", ".yml": "yaml", ".yaml": "yaml",
                        ".md": "markdown"}
            language = lang_map.get(suffix, "unknown")
        db.upsert_file(
            path=path,
            content_hash=f.get("semantic_sha1", ""),
            language=language,
            size=f.get("size", 0),
            modified_at=f.get("mtime", now),
            node_count=0,
        )

    # Symbols
    symbols_list = []
    for sym in symbol_graph.get("symbols", []):
        name = sym.get("name", "")
        fpath = sym.get("file", "")
        if not name or not fpath:
            continue
        sym_id = f"{fpath}::{name}"
        symbols_list.append({
            "id": sym_id,
            "kind": sym.get("kind", "unknown"),
            "name": name,
            "qualified_name": sym_id,
            "file_path": fpath,
            "language": _detect_language(fpath),
            "start_line": sym.get("line", 1),
            "end_line": sym.get("line", 1),
            "signature": sym.get("signature", ""),
            "fingerprint": sym.get("fingerprint", ""),
        })
    if symbols_list:
        db.insert_symbols_batch(symbols_list)

    # Edges — map file-level imports to symbol + file nodes
    edges_list = []
    for edge in dependency_graph.get("edges", []):
        from_file = edge.get("from", "")
        to_file = edge.get("to", "")
        if not from_file or not to_file:
            continue
        # File-level edge: from_file imports to_file
        edges_list.append({
            "source": from_file,
            "target": to_file,
            "kind": "imports",
            "provenance": "regex",
        })
    # Also insert file-level nodes so FK constraint passes
    file_ids = set()
    for e in edges_list:
        file_ids.add(e["source"])
        file_ids.add(e["target"])
    # Ensure file nodes exist
    for fid in file_ids:
        try:
            db.insert_symbols_batch([{
                "id": fid, "kind": "file",
                "name": fid.split("/")[-1] if "/" in fid else fid,
                "qualified_name": fid, "file_path": fid,
                "language": _detect_language(fid),
                "start_line": 1, "end_line": 1,
                "fingerprint": hashlib.sha1(fid.encode()).hexdigest(),
            }])
        except Exception:
            pass
    if edges_list:
        try:
            db.insert_edges_batch(edges_list)
        except Exception:
            pass  # FK may fail for external imports


def _detect_language(file_path: str) -> str:
    suffix = Path(file_path).suffix.lower()
    lang_map = {".py": "python", ".js": "javascript", ".mjs": "javascript",
                ".ts": "typescript", ".tsx": "tsx", ".java": "java",
                ".go": "go", ".rs": "rust", ".php": "php",
                ".c": "c", ".h": "c", ".cpp": "cpp", ".cc": "cpp", 
                ".hpp": "cpp", ".rb": "ruby", ".swift": "swift",
                ".kt": "kotlin", ".kts": "kotlin", ".cs": "csharp",
                ".lua": "lua", ".dart": "dart", ".sql": "sql",
                ".json": "json", ".yml": "yaml", ".yaml": "yaml",
                ".md": "markdown", ".vue": "vue", ".svelte": "svelte"}
    return lang_map.get(suffix, "unknown")


def build_cache(project_root: Path) -> Dict[str, Any]:
    project_root = project_root.resolve()
    paths = cache_paths(project_root)
    paths["root"].mkdir(parents=True, exist_ok=True)

    # Auto-restore from SSD if RAM cache was lost (e.g. after reboot)
    try:
        from .cache_persistence import auto_restore_if_needed
    except ImportError:
        from cache_persistence import auto_restore_if_needed
    restore_result = auto_restore_if_needed(project_root)
    if restore_result.get("restored"):
        # Cache restored from SSD — skip full rebuild
        manifest_path = paths["manifest"]
        if manifest_path.exists():
            import json
            try:
                with open(manifest_path) as f:
                    manifest = json.load(f)
                return {"manifest": manifest, "cache_dir": str(paths["root"]), "restored_from_persist": True}
            except (json.JSONDecodeError, OSError):
                pass

    file_index = build_file_index(project_root)
    repo_summary = build_repo_summary(project_root, file_index)
    symbol_graph = build_symbol_graph(project_root, file_index)
    dependency_graph = build_dependency_graph(file_index, symbol_graph)
    db_schema_summary = build_db_schema_summary(project_root, file_index)
    manifest = {
        "version": AIHELPER_CACHE_VERSION,
        "project_root": str(project_root),
        "built_at": datetime.now(timezone.utc).isoformat(),
        "file_count": file_index.get("count", 0),
        "symbol_count": symbol_graph.get("count", 0),
        "table_count": db_schema_summary.get("count", 0),
        "semantic_fingerprints": True,
    }
    safe_write_json(paths["file_index"], file_index)
    safe_write_json(paths["repo_summary"], repo_summary)
    safe_write_json(paths["symbol_graph"], symbol_graph)
    safe_write_json(paths["dependency_graph"], dependency_graph)
    safe_write_json(paths["db_schema_summary"], db_schema_summary)
    safe_write_json(paths["manifest"], manifest)

    # ── Sync to SQLite (v0.0.7) ─────────────────────────────────
    try:
        _sync_cache_to_sqlite(project_root, file_index, symbol_graph, dependency_graph)
        manifest["sqlite_synced"] = True
    except Exception:
        manifest["sqlite_synced"] = False

    return {"manifest": manifest, "cache_dir": str(paths["root"])}


def warm_project(project_root: Path) -> Dict[str, Any]:
    project_root = project_root.resolve()
    cache_result = build_cache(project_root)
    try:
        from .prompt_blocks import build_prompt_blocks
    except ImportError:
        from prompt_blocks import build_prompt_blocks
    block_result = build_prompt_blocks(project_root)
    return {"project_root": str(project_root), "cache": cache_result.get("manifest", {}), "prompt_blocks": block_result.get("manifest", {})}


def discover_project_roots(github_root: Path = Path.home() / "github", extra_roots: List[Path] | None = None) -> List[Path]:
    roots: List[Path] = []
    if github_root.exists():
        for git_dir in sorted(github_root.glob("*/.git")):
            roots.append(git_dir.parent.resolve())
    for extra in extra_roots or []:
        if extra.exists():
            roots.append(extra.resolve())
    unique: List[Path] = []
    seen = set()
    for root in roots:
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        unique.append(root)
    return unique


def cache_status(project_root: Path, include_diff: bool = False) -> Dict[str, Any]:
    paths = cache_paths(project_root.resolve())
    manifest = safe_load_json(paths["manifest"], default=None)
    existing = {key: path.exists() for key, path in paths.items() if key != "root"}
    result = {
        "cache_dir": str(paths["root"]),
        "exists": bool(manifest),
        "fresh": bool(manifest and manifest.get("version") == AIHELPER_CACHE_VERSION),
        "manifest": manifest or {},
        "files": existing,
    }
    if include_diff:
        result["diff"] = cache_diff(project_root.resolve()) if manifest else {}
    return result


def watch_cache(project_root: Path, interval: float = 2.0, once: bool = False, max_cycles: int = 0) -> Dict[str, Any]:
    project_root = project_root.resolve()
    if not cache_status(project_root).get("fresh"):
        build_cache(project_root)
    watchman = _watchman_changed_files(project_root)
    watchman_clock = str(watchman.get("clock") or "")
    use_watchman = bool(watchman.get("available") and watchman_clock)
    cycles = 0
    rebuilds = 0
    last_diff: Dict[str, Any] = {}
    while True:
        cycles += 1
        changed = _watchman_changed_files(project_root, since=watchman_clock) if use_watchman and not once else {}
        if changed.get("clock"):
            watchman_clock = str(changed.get("clock"))
        diff = cache_diff(project_root)
        if use_watchman:
            diff["watchman"] = {
                "enabled": True,
                "changed_files": changed.get("files", [])[:100] if changed else watchman.get("files", [])[:100],
                "clock": watchman_clock,
            }
        else:
            diff["watchman"] = {"enabled": False, "reason": watchman.get("error") or "unavailable"}
        last_diff = diff
        if diff.get("dirty"):
            update_cache(project_root)
            rebuilds += 1
        if once or (max_cycles and cycles >= max_cycles):
            return {
                "project_root": str(project_root),
                "cycles": cycles,
                "rebuilds": rebuilds,
                "last_diff": last_diff,
                "cache": cache_status(project_root).get("manifest", {}),
            }
        time.sleep(interval)


def watch_all_projects(
    github_root: Path = Path.home() / "github",
    extra_roots: List[Path] | None = None,
    interval: float = 2.0,
    once: bool = False,
) -> Dict[str, Any]:
    roots = discover_project_roots(github_root=github_root, extra_roots=extra_roots)
    if once:
        return {
            "project_count": len(roots),
            "projects": [str(root) for root in roots],
            "results": [watch_cache(root, interval=interval, once=True) for root in roots],
        }

    results: Dict[str, Any] = {"project_count": len(roots), "projects": [str(root) for root in roots]}

    def run(root: Path) -> None:
        watch_cache(root, interval=interval, once=False)

    for root in roots:
        thread = threading.Thread(target=run, args=(root,), daemon=True)
        thread.start()
    while True:
        time.sleep(3600)


def clean_cache(project_root: Path) -> Dict[str, Any]:
    root = cache_root(project_root.resolve())
    existed = root.exists()
    if existed:
        shutil.rmtree(root)
    # Reset SQLite singleton so next get_db() creates fresh connection
    try:
        from .graph_db import close_all as _close_all
    except ImportError:
        from graph_db import close_all as _close_all
    _close_all()
    return {"cache_dir": str(root), "removed": existed}


def load_cached_context(project_root: Path, max_symbols: int = 30) -> Dict[str, Any]:
    paths = cache_paths(project_root.resolve())
    manifest = safe_load_json(paths["manifest"], default={}) or {}
    repo_summary = safe_load_json(paths["repo_summary"], default={}) or {}
    symbol_graph = safe_load_json(paths["symbol_graph"], default={}) or {}
    db_schema = safe_load_json(paths["db_schema_summary"], default={}) or {}
    return {
        "cache": {
            "fresh": bool(manifest and manifest.get("version") == AIHELPER_CACHE_VERSION),
            "manifest": manifest,
        },
        "repo_summary": {
            "project_root": repo_summary.get("project_root", str(project_root.resolve())),
            "file_count": repo_summary.get("file_count", 0),
            "extension_counts": repo_summary.get("extension_counts", {}),
            "kind_counts": repo_summary.get("kind_counts", {}),
            "important_files": (repo_summary.get("important_files") or [])[:20],
        },
        "symbols": symbol_graph.get("symbols", [])[:max_symbols],
        "db_schema_summary": {
            "table_count": db_schema.get("count", 0),
            "tables": list((db_schema.get("tables") or {}).keys())[:20],
        },
    }
