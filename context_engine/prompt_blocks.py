from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

try:
    from .cache import cache_paths, cache_status, load_cached_context
    from .common import safe_load_json, safe_write_json
except ImportError:
    from cache import cache_paths, cache_status, load_cached_context
    from common import safe_load_json, safe_write_json


def _block_dir(project_root: Path) -> Path:
    return cache_paths(project_root.resolve())["root"] / "prompt_blocks"


def _git_summary(project_root: Path) -> Dict[str, Any]:
    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=str(project_root),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    files = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return {"changed_file_count": len(files), "changed_files": files[:80]}


def build_prompt_blocks(project_root: Path) -> Dict[str, Any]:
    root = project_root.resolve()
    if not cache_status(root).get("fresh"):
        try:
            from .cache import build_cache
        except ImportError:
            from cache import build_cache

        build_cache(root)
    cached = load_cached_context(root, max_symbols=80)
    blocks = {
        "architecture_summary": {
            "kind_counts": cached.get("repo_summary", {}).get("kind_counts", {}),
            "important_files": cached.get("repo_summary", {}).get("important_files", [])[:40],
        },
        "db_summary": cached.get("db_schema_summary", {}),
        "active_service_summary": {
            "project_root": str(root),
            "file_count": cached.get("repo_summary", {}).get("file_count", 0),
            "extension_counts": cached.get("repo_summary", {}).get("extension_counts", {}),
        },
        "symbol_summary": {"symbols": cached.get("symbols", [])[:40]},
        "recent_git_changes": _git_summary(root),
    }
    out_dir = _block_dir(root)
    for name, payload in blocks.items():
        safe_write_json(out_dir / f"{name}.json", payload)
    manifest = {"built_at": datetime.now(timezone.utc).isoformat(), "blocks": sorted(blocks)}
    safe_write_json(out_dir / "manifest.json", manifest)
    return {"project_root": str(root), "block_dir": str(out_dir), "manifest": manifest}


def load_prompt_blocks(project_root: Path, names: List[str] | None = None) -> Dict[str, Any]:
    root = project_root.resolve()
    out_dir = _block_dir(root)
    manifest = safe_load_json(out_dir / "manifest.json", default={}) or {}
    requested = names or manifest.get("blocks", [])
    blocks = {}
    for name in requested:
        payload = safe_load_json(out_dir / f"{name}.json", default=None)
        if payload is not None:
            blocks[name] = payload
    return {"project_root": str(root), "manifest": manifest, "blocks": blocks}
