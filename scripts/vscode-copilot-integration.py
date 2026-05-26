#!/usr/bin/env python3
"""VS Code + GitHub Copilot Chat integration for aihelper.

Generates workspace settings, extension recommendations, global and
project-level copilot instructions, and optionally detects/installs
the Copilot extension. Failsafe and re-runnable.

Usage:
    python3 scripts/vscode-copilot-integration.py --path /path/to/project
    python3 scripts/vscode-copilot-integration.py --dry-run --path /path/to/project
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path

from integration_common import (
    IS_WINDOWS,
    IS_MACOS,
    IS_LINUX,
    write_json,
    write_text,
    merge_settings,
    ensure_extension_recommendation,
    load_json,
    safe_run,
    detect_binary,
    resolve_project_root,
    add_dry_run_arg,
    add_path_arg,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CO_INSTRUCTIONS_CONTENT = """# Local Agent Instructions: Token Budget Protocol

Applies to ALL agents: Claude, Gemini, DeepSeek, Codex, Copilot, Ollama.

## Mandatory: Use aihelper context compression FIRST

Before scanning repos, running grep, or reading multiple files:

1. `aihelper route "<task>"` — identify tools + token budget
2. `aihelper context --max-context-chars 2000` — compact project overview
3. `aihelper symbol_lookup <symbol>` — instead of grep
4. `aihelper diff_summary` — instead of full git diffs

## Token Budget

| Operation | Max Context Chars | Max Tokens |
|-----------|------------------:|-----------:|
| Quick lookup / autocomplete | 500 | ~125 |
| Single-file change | 2,000 | ~500 |
| Multi-file change | 4,000 | ~1,000 |
| Architecture / design | 8,000 | ~2,000 |
| Debugging | 5,000 | ~1,250 |

## NEVER
- Run `find .`, `grep -r`, `rg -r` on a full project without aihelper first
- Read >3 raw files without `aihelper_context` first
- Send raw file dumps to cloud models without aihelper compression
- Exceed token budget — aihelper engine hard-enforces it
"""

DEFAULT_WORKSPACE_SETTINGS = {
    "github.copilot.enable": True,
    "github.copilot.autocomplete.enable": True,
    "github.copilot.inlineSuggest.enable": True,
}

CO_INSTRUCTIONS_RELATIVE = ".github/copilot-instructions.md"
CO_INSTRUCTIONS_ABS = os.path.expanduser("~/.github/copilot-instructions.md")

CANDIDATE_EXTENSION_IDS = [
    "GitHub.copilot",
    "GitHub.copilot-chat",
    "GitHub.copilot-nightly",
    "github.copilot",
    "github.copilot-chat",
]

# ---------------------------------------------------------------------------
# VS Code path discovery (OS-specific)
# ---------------------------------------------------------------------------


def detect_vscode_cli() -> str | None:
    """Return the path to ``code`` (or variants), or None."""
    return detect_binary("code", "code-insiders", "code.cmd", "code-oss")


def find_vscode_user_settings() -> Path | None:
    """Locate VS Code user settings.json across all platforms."""
    candidates: list[Path] = []

    if IS_MACOS:
        candidates.append(Path.home() / "Library/Application Support/Code/User/settings.json")
        candidates.append(Path.home() / "Library/Application Support/Code - Insiders/User/settings.json")
    if IS_LINUX or IS_MACOS:
        candidates.append(Path.home() / ".config/Code/User/settings.json")
        candidates.append(Path.home() / ".config/Code - Insiders/User/settings.json")
        candidates.append(Path.home() / ".config/VSCodium/User/settings.json")
        xdg = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
        candidates.append(Path(xdg) / "Code/User/settings.json")
        # Flatpak (Linux)
        candidates.append(Path.home() / ".var/app/com.visualstudio.code/config/Code/User/settings.json")
    if IS_WINDOWS:
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            candidates.append(Path(appdata) / "Code/User/settings.json")

    for p in candidates:
        if p and p.exists():
            return p
    return None


def find_vscode_extensions_dirs() -> list[Path]:
    """Return all existing VS Code extension directories."""
    home = Path.home()
    dirs: list[Path] = []
    seen: set[str] = set()

    # User-level
    user_paths = [home / ".vscode/extensions", home / ".vscode-insiders/extensions"]
    if IS_LINUX or IS_MACOS:
        user_paths.extend([
            home / ".vscode-server/extensions",
            home / ".vscode-server-insiders/extensions",
        ])
        xdg_data = os.environ.get("XDG_DATA_HOME", str(home / ".local/share"))
        user_paths.append(Path(xdg_data) / "code/extensions")
        user_paths.append(home / ".var/app/com.visualstudio.code/config/Code/extensions")
    if IS_WINDOWS:
        userprofile = os.environ.get("USERPROFILE")
        if userprofile:
            user_paths.append(Path(userprofile) / ".vscode/extensions")
            user_paths.append(Path(userprofile) / ".vscode-insiders/extensions")

    for p in user_paths:
        if p.exists() and str(p) not in seen:
            dirs.append(p)
            seen.add(str(p))

    # Built-in — macOS
    if IS_MACOS:
        for app_dir in ("/Applications/Visual Studio Code.app", "/Applications/Visual Studio Code - Insiders.app"):
            p = Path(app_dir) / "Contents/Resources/app/extensions"
            if p.exists() and str(p) not in seen:
                dirs.append(p)
                seen.add(str(p))

    # Built-in — Windows
    if IS_WINDOWS:
        for var in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            root = os.environ.get(var, "")
            if not root:
                continue
            for candidate in (Path(root) / "Microsoft VS Code/resources/app/extensions",
                              Path(root) / "Programs/Microsoft VS Code/resources/app/extensions"):
                if candidate.exists() and str(candidate) not in seen:
                    dirs.append(candidate)
                    seen.add(str(candidate))

    # Built-in — Linux
    if IS_LINUX:
        linux_builtin = Path("/usr/share/code/resources/app/extensions")
        if linux_builtin.exists() and str(linux_builtin) not in seen:
            dirs.append(linux_builtin)

    return dirs

# ---------------------------------------------------------------------------
# Copilot detection
# ---------------------------------------------------------------------------


def detect_via_cli(code_cli: str) -> str | None:
    """Check ``code --list-extensions`` for any known Copilot extension ID."""
    result = safe_run([code_cli, "--list-extensions"], timeout=30)
    if result is None:
        return None
    installed = result.stdout.splitlines()
    for cid in CANDIDATE_EXTENSION_IDS:
        if cid in installed:
            return cid
    return None


def detect_via_extensions_dir() -> str | None:
    """Scan VS Code extension directories for copilot folders."""
    for ext_dir in find_vscode_extensions_dirs():
        try:
            for entry in ext_dir.iterdir():
                name_lower = entry.name.lower()
                if name_lower == "copilot":
                    print(f"[OK] Copilot extension directory detected: {entry}")
                    return entry.name
                for cand in CANDIDATE_EXTENSION_IDS + ["copilot"]:
                    if cand.lower() in name_lower or name_lower.startswith(cand.lower()):
                        print(f"[OK] Copilot extension directory detected: {entry}")
                        return entry.name
        except Exception:
            continue
    return None


def detect_copilot(code_cli: str | None) -> str | None:
    """Try all strategies; return extension ID/dir name or None."""
    if code_cli:
        found = detect_via_cli(code_cli)
        if found:
            print(f"[OK] GitHub Copilot detected via CLI: {found}")
            return found
    found = detect_via_extensions_dir()
    if found:
        return found
    return None

# ---------------------------------------------------------------------------
# Integration tasks
# ---------------------------------------------------------------------------


def _write_workspace_settings(project_root: Path, dry_run: bool) -> None:
    settings = dict(DEFAULT_WORKSPACE_SETTINGS)
    settings["github.copilot.chat.codeGeneration.instructions"] = [
        {"file": CO_INSTRUCTIONS_ABS},
        {"file": str(project_root / CO_INSTRUCTIONS_RELATIVE)},
    ]
    merge_settings(project_root / ".vscode/settings.json", settings, dry_run)


def _write_workspace_extensions(project_root: Path, dry_run: bool) -> None:
    ext_path = project_root / ".vscode/extensions.json"
    for eid in ("GitHub.copilot", "GitHub.copilot-chat"):
        ensure_extension_recommendation(ext_path, eid, dry_run)


def _write_user_settings(dry_run: bool) -> None:
    user_settings = find_vscode_user_settings()
    if user_settings is None:
        print("[INFO] VS Code user settings not detected; workspace config generated only.")
        return
    merge_settings(user_settings, {"github.copilot.chat.codeGeneration.instructions": [{"file": CO_INSTRUCTIONS_ABS}]}, dry_run)


def _ensure_instructions_file(project_root: Path, dry_run: bool) -> None:
    global_file = Path(CO_INSTRUCTIONS_ABS)
    write_text(global_file, CO_INSTRUCTIONS_CONTENT, dry_run)

    project_file = project_root / CO_INSTRUCTIONS_RELATIVE
    project_content = (
        f"# {project_root.name} \u2014 Local Project Instructions\n\n"
        f"## Context Budget\n"
        f"- Use `aihelper context --max-context-chars 2000` for most tasks\n"
        f"- Extend to `--max-context-chars 4000` only for multi-file changes\n"
        f"- Never exceed 5000 chars without explicit user permission\n"
    )
    write_text(project_file, project_content, dry_run)


def _try_auto_install(code_cli: str | None, dry_run: bool) -> bool:
    if code_cli is None:
        return False
    for target in ("GitHub.copilot", "GitHub.copilot-chat"):
        if dry_run:
            print(f"[DRY-RUN] Would install extension: {target}")
            return True
        print(f"[INFO] Attempting to install: {target}")
        result = safe_run([code_cli, "--install-extension", target], timeout=60)
        if result is not None and result.returncode == 0:
            print(f"[OK] Installed: {target}")
            return True
        print(f"[WARN] Failed to install: {target}")
    return False

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate VS Code Copilot integration settings for aihelper."
    )
    add_path_arg(parser)
    add_dry_run_arg(parser)
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Skip auto-install attempt even if Copilot is not detected",
    )
    return parser.parse_args()

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    args = parse_args()
    project_root = resolve_project_root(args.path)
    if project_root is None:
        return 1

    code_cli = detect_vscode_cli()
    copilot_id = detect_copilot(code_cli)

    _write_workspace_settings(project_root, args.dry_run)
    _write_workspace_extensions(project_root, args.dry_run)
    _write_user_settings(args.dry_run)
    _ensure_instructions_file(project_root, args.dry_run)

    if copilot_id is None and not args.skip_install:
        installed = _try_auto_install(code_cli, args.dry_run)
        if installed and not args.dry_run:
            print("[OK] Copilot extension installed. Restart VS Code to activate.")
            return 0

    if copilot_id is None:
        if code_cli:
            print("[INFO] GitHub Copilot extension not detected. Install it manually:\n  code --install-extension GitHub.copilot")
        else:
            print("[INFO] VS Code CLI not found and Copilot not detected.\n  Install the GitHub Copilot extension via VS Code Extensions view.")
    else:
        print(f"[OK] Copilot integration configured (detected: {copilot_id}).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
