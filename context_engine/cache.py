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


def build_file_index(project_root: Path) -> Dict[str, Any]:
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


def build_cache(project_root: Path) -> Dict[str, Any]:
    project_root = project_root.resolve()
    paths = cache_paths(project_root)
    paths["root"].mkdir(parents=True, exist_ok=True)
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


def discover_project_roots(github_root: Path = Path("/Users/vietnguyen/github"), extra_roots: List[Path] | None = None) -> List[Path]:
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
            warm_project(project_root)
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
    github_root: Path = Path("/Users/vietnguyen/github"),
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
