"""
Editor-awareness module — detect active editor state for context-aware AI.

Detects:
- Active editor (Zed, VSCode, Codex)
- Currently open file
- Recent edits
- Git branch

Used by aihelper daemon to provide "look at the right place" context.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional


def detect_active_editor() -> Optional[str]:
    """Detect which editor is currently active."""
    editors = {
        "Zed": "Zed",
        "Code": "Visual Studio Code",
        "codex": "Codex",
    }
    
    try:
        # Check running processes
        result = subprocess.run(
            ["ps", "-ax", "-o", "comm="],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        )
        running = set(result.stdout.splitlines())
        
        for proc_name, editor_name in editors.items():
            if any(proc_name.lower() in p.lower() for p in running):
                return editor_name
    except Exception:
        pass
    
    # Fallback: check environment
    if os.environ.get("ZED_WORKTREE_ROOT"):
        return "Zed"
    if os.environ.get("VSCODE_CWD"):
        return "Visual Studio Code"
    
    return None


def get_zed_open_files(workspace_root: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Get currently open files in Zed editor."""
    # Zed stores session in ~/Library/Application Support/Zed/sessions/
    zed_session_dir = Path.home() / "Library" / "Application Support" / "Zed" / "sessions"
    
    if not zed_session_dir.exists():
        return []
    
    files = []
    try:
        for session_file in sorted(zed_session_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                with open(session_file) as f:
                    session = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue
            
            # Extract open workspaces and files
            workspaces = session.get("workspaces", {}) or session.get("windows", [])
            if isinstance(workspaces, dict):
                for ws_path, ws_data in workspaces.items():
                    if isinstance(ws_data, dict):
                        for pane in ws_data.get("panes", []):
                            for item in pane.get("items", []):
                                file_path = item.get("path") or item.get("file")
                                if file_path:
                                    files.append({
                                        "path": file_path,
                                        "workspace": ws_path,
                                        "active": item.get("active", False),
                                    })
            elif isinstance(workspaces, list):
                for window in workspaces:
                    if isinstance(window, dict):
                        for item in window.get("items", []):
                            file_path = item.get("path") or item.get("file")
                            if file_path:
                                files.append({"path": file_path, "active": False})
    except Exception:
        pass
    
    return files


def get_vscode_open_files(workspace_root: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Get currently open files in VSCode."""
    # VSCode stores state in storage.json
    vscode_state_dir = Path.home() / "Library" / "Application Support" / "Code" / "User" / "globalStorage"
    
    files = []
    try:
        # Check recently opened files via state database
        state_db = vscode_state_dir / "state.vscdb"
        if state_db.exists():
            # Read the SQLite database for recent files
            import sqlite3
            try:
                conn = sqlite3.connect(str(state_db))
                cursor = conn.execute(
                    "SELECT value FROM ItemTable WHERE key = 'history.recentlyOpenedPathsList'"
                )
                row = cursor.fetchone()
                if row:
                    try:
                        paths = json.loads(row[0])
                        entries = paths.get("entries", [])
                        for entry in entries[:20]:
                            if isinstance(entry, dict):
                                file_path = entry.get("folderUri") or entry.get("fileUri") or ""
                            else:
                                file_path = str(entry)
                            if file_path:
                                # Convert file:// URI
                                if file_path.startswith("file://"):
                                    from urllib.parse import urlparse, unquote
                                    parsed = urlparse(file_path)
                                    file_path = unquote(parsed.path)
                                files.append({"path": file_path, "active": False})
                    except json.JSONDecodeError:
                        pass
                conn.close()
            except (sqlite3.Error, sqlite3.OperationalError):
                pass
    except Exception:
        pass
    
    return files


def get_active_file() -> Optional[Dict[str, Any]]:
    """Get the currently active file in the user's editor."""
    editor = detect_active_editor()
    
    if editor == "Zed":
        zed_files = get_zed_open_files()
        active = [f for f in zed_files if f.get("active")]
        if active:
            return {"editor": "Zed", **active[0]}
        if zed_files:
            return {"editor": "Zed", **zed_files[0]}
    
    if editor == "Visual Studio Code":
        vscode_files = get_vscode_open_files()
        if vscode_files:
            return {"editor": "VSCode", **vscode_files[0]}
    
    # Check ZED_WORKTREE_ROOT env var (set by Zed when spawning processes)
    zed_root = os.environ.get("ZED_WORKTREE_ROOT")
    if zed_root:
        return {"editor": "Zed", "workspace": zed_root, "path": None}
    
    return None


def get_editor_context(project_root: Optional[Path] = None) -> Dict[str, Any]:
    """Get full editor context for AI consumption."""
    active = get_active_file()
    editor = detect_active_editor()
    
    # Get git branch
    git_branch = None
    try:
        cwd = project_root or Path.cwd()
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        )
        if result.returncode == 0:
            git_branch = result.stdout.strip()
    except Exception:
        pass
    
    return {
        "active_editor": editor,
        "active_file": active.get("path") if active else None,
        "workspace": active.get("workspace") if active else os.environ.get("ZED_WORKTREE_ROOT"),
        "git_branch": git_branch,
        "detected_at": __import__('time').strftime("%Y-%m-%dT%H:%M:%S"),
    }


# ── Daemon handler ───────────────────────────────────────────────

def handle_editor_context(params: Dict[str, Any]) -> Dict[str, Any]:
    """Daemon handler: return current editor context."""
    project_root = params.get("project_root")
    if project_root:
        project_root = Path(project_root)
    return get_editor_context(project_root)
