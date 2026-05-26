#!/usr/bin/env python3
"""
Common utilities for aihelper integration scripts.

Shared across all editor/agent integration scripts to eliminate duplication.
Provides idempotent JSON/text file I/O, deep-merge, path resolution, OS
detection, subprocess safety, and a consistent CLI helper.

Usage (within integration scripts):
    from integration_common import (
        IS_WINDOWS, IS_MACOS, IS_LINUX,
        python_cmd, aihelper_root, mcp_server_path,
        load_json, write_json, merge_settings, write_text,
        ensure_extension_recommendation, safe_run, detect_binary,
        add_dry_run_arg, add_path_arg, resolve_project_root,
        get_home_config_path,
    )
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# OS detection — single source of truth
# ---------------------------------------------------------------------------

IS_WINDOWS: bool = sys.platform == "win32"
IS_MACOS: bool = sys.platform == "darwin"
IS_LINUX: bool = sys.platform == "linux"
IS_POSIX: bool = IS_MACOS or IS_LINUX


def python_cmd() -> str:
    """Return the Python command name for the current OS.

    - Windows: ``python``
    - macOS/Linux: ``python3``
    """
    return "python" if IS_WINDOWS else "python3"


def home() -> Path:
    """Return the current user's home directory (cross-platform)."""
    if IS_WINDOWS:
        return Path(os.environ.get("USERPROFILE", str(Path.home())))
    return Path.home()


# ---------------------------------------------------------------------------
# aihelper path resolution
# ---------------------------------------------------------------------------


def _script_dir() -> Path:
    """Return the directory containing *this* module (``scripts/``)."""
    return Path(__file__).resolve().parent


def aihelper_root() -> Path:
    """Resolve the aihelper repository root from ``scripts/``."""
    return _script_dir().parent


def mcp_server_path() -> Path:
    """Return the absolute path to the aihelper MCP server entry point."""
    return aihelper_root() / "context_engine" / "mcp_server.py"


def get_home_config_path(*components: str) -> Path:
    """Build a path under the user's home directory.

    On Windows, uses ``~`` (USERPROFILE). On POSIX, uses ``$HOME``.
    """
    return Path.home().joinpath(*components)


def get_appdata_config_path(app_name: str, *subdirs: str) -> Path:
    """Build an OS-appropriate config directory path.

    - Windows: ``%APPDATA%/<app_name>/<subdirs>``
    - macOS: ``~/Library/Application Support/<app_name>/<subdirs>``
    - Linux: ``~/.config/<app_name>/<subdirs>``
    """
    if IS_WINDOWS:
        base = Path(os.environ.get("APPDATA", ""))
    elif IS_MACOS:
        base = Path.home() / "Library/Application Support"
    else:
        base = Path.home() / ".config"
    return base / app_name / "/".join(subdirs)


# ---------------------------------------------------------------------------
# JSON I/O (idempotent)
# ---------------------------------------------------------------------------


def load_json(path: Path) -> dict:
    """Load a JSON dict from *path*; return ``{}`` on any failure."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def write_json(path: Path, data: dict, dry_run: bool) -> None:
    """Write *data* as JSON to *path* only if it differs from the current content.

    Creates parent directories as needed. No-op when ``dry_run=True``.
    """
    content = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if dry_run:
        print(f"[DRY-RUN] Would write: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and load_json(path) == data:
        print(f"[SKIP] No change: {path}")
        return
    path.write_text(content, encoding="utf-8")
    print(f"[OK] Written: {path}")


def merge_settings(path: Path, overrides: dict, dry_run: bool) -> None:
    """Deep-merge *overrides* into the JSON file at *path*.

    Existing keys in the file are preserved unless *overrides* explicitly
    sets them to a different value. No-op when ``dry_run=True``.
    """
    data = load_json(path)

    def _deep_merge(base: dict, overlay: dict) -> None:
        for key, value in overlay.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                _deep_merge(base[key], value)
            else:
                base[key] = value

    old = json.dumps(data, indent=2, ensure_ascii=False)
    _deep_merge(data, overrides)
    new = json.dumps(data, indent=2, ensure_ascii=False)
    if old == new:
        print(f"[SKIP] No change: {path}")
        return
    if dry_run:
        print(f"[DRY-RUN] Would write: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new + "\n", encoding="utf-8")
    print(f"[OK] Written: {path}")


# ---------------------------------------------------------------------------
# Text I/O (idempotent)
# ---------------------------------------------------------------------------


def write_text(path: Path, text: str, dry_run: bool) -> None:
    """Write *text* to *path* only if content differs.

    Creates parent directories as needed. No-op when ``dry_run=True``.
    """
    if dry_run:
        print(f"[DRY-RUN] Would write: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        print(f"[SKIP] No change: {path}")
        return
    path.write_text(text, encoding="utf-8")
    print(f"[OK] Written: {path}")


# ---------------------------------------------------------------------------
# VS Code extension recommendation (idempotent)
# ---------------------------------------------------------------------------


def ensure_extension_recommendation(path: Path, extension_id: str, dry_run: bool) -> None:
    """Append *extension_id* to the ``recommendations`` array in the JSON at *path*.

    No-op if already present or when ``dry_run=True``.
    """
    data = load_json(path)
    recommendations = data.get("recommendations", [])
    if extension_id not in recommendations:
        recommendations.append(extension_id)
        data["recommendations"] = recommendations
        write_json(path, data, dry_run)
    else:
        print(f"[SKIP] No change: {path}")


# ---------------------------------------------------------------------------
# Subprocess helpers (failsafe)
# ---------------------------------------------------------------------------


def safe_run(args: list[str], **kwargs) -> subprocess.CompletedProcess | None:
    """Run a subprocess; return ``None`` on any failure.

    Keyword arguments are forwarded to ``subprocess.run``.
    Defaults: ``capture_output=True, text=True, check=True``.
    """
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("text", True)
    kwargs.setdefault("check", True)
    try:
        return subprocess.run(args, **kwargs)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Binary detection (cross-platform)
# ---------------------------------------------------------------------------


def detect_binary(*names: str) -> str | None:
    """Return the first existing path for any of *names*

    On Windows, ``.exe`` is tried in addition to each name.
    """
    for name in names:
        path = shutil.which(name)
        if path:
            return path
        if IS_WINDOWS and not name.endswith(".exe"):
            path = shutil.which(f"{name}.exe")
            if path:
                return path
    return None


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------


def add_dry_run_arg(parser: argparse.ArgumentParser) -> None:
    """Add a standard ``--dry-run`` flag to *parser*."""
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing files",
    )


def add_path_arg(
    parser: argparse.ArgumentParser,
    default: str = ".",
    help_text: str = "Project root path",
) -> None:
    """Add a standard ``--path`` argument to *parser*."""
    parser.add_argument(
        "--path",
        default=default,
        help=help_text,
    )


def resolve_project_root(path_str: str) -> Path | None:
    """Expand and resolve *path_str*; return ``None`` if it doesn't exist."""
    root = Path(path_str).expanduser().resolve()
    if not root.exists():
        print(f"[WARN] Project root does not exist: {root}")
        return None
    return root
