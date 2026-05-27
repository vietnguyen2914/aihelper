"""
RAM cache persistence — sync .ai-cache from RAM disk to SSD and restore on boot.

When .ai-cache is a symlink to /Volumes/ramdisk/projects/<name>/.ai-cache,
the cache is volatile and lost on reboot. This module:
1. Persists cache to ~/.aihelper/persist/<project_key>/ before shutdown
2. Restores from SSD to RAM disk on boot/cache build
3. Supports periodic auto-sync in watch mode
"""
from __future__ import annotations

import atexit
import json
import os
import shutil
import signal
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

try:
    from .common import safe_write_json
except ImportError:
    from common import safe_write_json


PERSIST_ROOT = Path.home() / ".aihelper" / "persist"
RAMDISK_PREFIX = "/Volumes/ramdisk"


def _is_ramdisk_symlink(project_root: Path) -> bool:
    """Check if .ai-cache is a symlink pointing to RAM disk."""
    cache_link = project_root.resolve() / ".ai-cache"
    if not cache_link.is_symlink():
        return False
    target = os.readlink(str(cache_link))
    return target.startswith(RAMDISK_PREFIX)


def _project_persist_key(project_root: Path) -> str:
    """Generate a stable key for persistence directory naming."""
    resolved = str(project_root.resolve())
    # Use a filesystem-safe key derived from the project path
    key = resolved.replace("/", "-").replace(" ", "_").lstrip("-")
    # Truncate for sanity
    if len(key) > 120:
        import hashlib
        hash_suffix = hashlib.sha1(resolved.encode()).hexdigest()[:12]
        key = key[:100] + "-" + hash_suffix
    return key


def persist_path(project_root: Path) -> Path:
    return PERSIST_ROOT / _project_persist_key(project_root)


def persist_cache(project_root: Path) -> Dict:
    """Sync RAM-based .ai-cache/aihelper to SSD persistence directory."""
    project_root = project_root.resolve()
    cache_dir = project_root / ".ai-cache" / "aihelper"
    dest = persist_path(project_root) / "aihelper"

    if not cache_dir.exists():
        return {"persisted": False, "reason": "no_cache_dir", "project": str(project_root)}

    dest.parent.mkdir(parents=True, exist_ok=True)

    # Use rsync if available for efficiency, else shutil
    rsync = shutil.which("rsync")
    if rsync:
        import subprocess
        result = subprocess.run(
            [rsync, "-a", "--delete", str(cache_dir) + "/", str(dest) + "/"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False,
        )
        success = result.returncode == 0
    else:
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(cache_dir, dest, symlinks=False)
        success = True

    # Write metadata
    meta = {
        "project_root": str(project_root),
        "persisted_at": datetime.now(timezone.utc).isoformat(),
        "is_ramdisk": _is_ramdisk_symlink(project_root),
    }
    safe_write_json(dest / "persist_meta.json", meta)

    return {
        "persisted": success,
        "project": str(project_root),
        "dest": str(dest),
        "is_ramdisk": meta["is_ramdisk"],
        "persisted_at": meta["persisted_at"],
    }


def restore_cache(project_root: Path) -> Dict:
    """Restore cache from SSD persistence to RAM disk."""
    project_root = project_root.resolve()
    cache_dir = project_root / ".ai-cache" / "aihelper"
    src = persist_path(project_root) / "aihelper"

    if not src.exists():
        return {"restored": False, "reason": "no_persisted_cache", "project": str(project_root)}

    is_ramdisk = _is_ramdisk_symlink(project_root)

    cache_dir.parent.mkdir(parents=True, exist_ok=True)

    rsync = shutil.which("rsync")
    if rsync:
        import subprocess
        result = subprocess.run(
            [rsync, "-a", str(src) + "/", str(cache_dir) + "/"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False,
        )
        success = result.returncode == 0
    else:
        if cache_dir.exists():
            shutil.rmtree(cache_dir)
        shutil.copytree(src, cache_dir, symlinks=False)
        success = True

    # Verify manifest after restore
    manifest_path = cache_dir / "manifest.json"
    manifest_valid = manifest_path.exists()
    if manifest_valid:
        try:
            with open(manifest_path) as f:
                manifest = json.load(f)
            manifest_valid = bool(manifest.get("version"))
        except (json.JSONDecodeError, OSError):
            manifest_valid = False

    return {
        "restored": success and manifest_valid,
        "project": str(project_root),
        "source": str(src),
        "is_ramdisk": is_ramdisk,
        "manifest_valid": manifest_valid,
    }


def persist_all_projects(github_root: Optional[Path] = None) -> Dict:
    """Persist cache for all known projects."""
    if github_root is None:
        github_root = Path.home() / "github"

    results = []
    persisted = 0

    # Discover projects from persistence directory
    if PERSIST_ROOT.exists():
        for persist_dir in sorted(PERSIST_ROOT.iterdir()):
            if not persist_dir.is_dir():
                continue
            meta_path = persist_dir / "aihelper" / "persist_meta.json"
            if not meta_path.exists():
                continue
            try:
                with open(meta_path) as f:
                    meta = json.load(f)
                project_root = Path(meta.get("project_root", ""))
                if project_root.exists():
                    result = persist_cache(project_root)
                    results.append(result)
                    if result.get("persisted"):
                        persisted += 1
            except (json.JSONDecodeError, OSError):
                continue

    # Also try current projects from github_root
    if github_root.exists():
        for git_dir in sorted(github_root.glob("*/.git")):
            project = git_dir.parent
            if _is_ramdisk_symlink(project):
                result = persist_cache(project)
                if result.get("persisted") and not any(
                    r.get("project") == str(project) for r in results
                ):
                    results.append(result)
                    persisted += 1

    return {"persisted_count": persisted, "results": results}


def auto_persist_on_exit(github_root: Optional[Path] = None) -> None:
    """Register atexit and signal handlers to persist on shutdown."""
    registered = getattr(auto_persist_on_exit, "_registered", False)
    if registered:
        return
    auto_persist_on_exit._registered = True

    def _handler():
        try:
            persist_all_projects(github_root)
        except Exception:
            pass  # Don't break shutdown

    atexit.register(_handler)
    signal.signal(signal.SIGTERM, lambda s, f: _handler())
    signal.signal(signal.SIGINT, lambda s, f: (_handler(), exit(0)))


def persist_on_interval(project_root: Path, interval_seconds: int = 300, stop_event=None):
    """Background thread: periodically persist cache."""
    while stop_event is None or not stop_event.is_set():
        time.sleep(interval_seconds)
        try:
            persist_cache(project_root)
        except Exception:
            pass



def auto_restore_if_needed(project_root: Path) -> Dict:
    """Auto-restore cache from SSD if RAM cache is missing or empty.
    Call this early in cache build/watch to avoid full rebuild after reboot."""
    project_root = project_root.resolve()
    cache_dir = project_root / ".ai-cache" / "aihelper"
    manifest_path = cache_dir / "manifest.json"

    needs_restore = False
    reason = ""

    if not cache_dir.exists() or not any(cache_dir.iterdir()):
        needs_restore = True
        reason = "cache_missing_or_empty"
    elif not manifest_path.exists():
        needs_restore = True
        reason = "manifest_missing"
    else:
        # Check if persisted version is newer (SSD has fresher data from last session)
        persist_dir = persist_path(project_root) / "aihelper"
        persist_manifest = persist_dir / "persist_meta.json"
        if persist_manifest.exists():
            try:
                import json
                with open(persist_manifest) as f:
                    pm = json.load(f)
                with open(manifest_path) as f:
                    cm = json.load(f)
                persist_time = pm.get("persisted_at", "")
                cache_time = cm.get("built_at", "")
                # v0.1 fix: also verify persist files actually exist,
                # not just timestamp comparison
                has_persist_files = persist_dir.exists() and any(
                    f.suffix == '.json' and f.name != 'persist_meta.json'
                    for f in persist_dir.iterdir()
                ) if persist_dir.exists() else False
                if persist_time and cache_time and persist_time > cache_time and has_persist_files:
                    needs_restore = True
                    reason = "persist_newer_than_cache"
            except (json.JSONDecodeError, OSError):
                pass

    if needs_restore:
        result = restore_cache(project_root)
        result["auto_restore_reason"] = reason
        return result

    return {"restored": False, "reason": reason or "cache_fresh", "project": str(project_root)}

def cache_persist_status(project_root: Path) -> Dict:
    """Check persistence status for a project."""
    project_root = project_root.resolve()
    cache_dir = project_root / ".ai-cache" / "aihelper"
    persist_dir = persist_path(project_root) / "aihelper"

    is_ramdisk = _is_ramdisk_symlink(project_root)
    cache_exists = cache_dir.exists()
    persist_exists = persist_dir.exists()

    cache_manifest = None
    persist_manifest = None

    if cache_exists:
        manifest_path = cache_dir / "manifest.json"
        if manifest_path.exists():
            try:
                with open(manifest_path) as f:
                    cache_manifest = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass

    if persist_exists:
        meta_path = persist_dir / "persist_meta.json"
        if meta_path.exists():
            try:
                with open(meta_path) as f:
                    persist_manifest = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass

    return {
        "project": str(project_root),
        "is_ramdisk_symlink": is_ramdisk,
        "cache": {
            "exists": cache_exists,
            "built_at": cache_manifest.get("built_at") if cache_manifest else None,
            "version": cache_manifest.get("version") if cache_manifest else None,
        },
        "persist": {
            "exists": persist_exists,
            "persisted_at": persist_manifest.get("persisted_at") if persist_manifest else None,
        },
    }
