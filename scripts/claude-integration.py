#!/usr/bin/env python3
"""Claude Desktop/CLI integration for aihelper.

Generates Claude-friendly aihelper instructions.
Failsafe: writes config files even if Claude CLI is not installed.
Re-runnable: skips writing when content is identical.

Usage:
    python3 scripts/claude-integration.py --path /path/to/project
    python3 scripts/claude-integration.py --dry-run
"""

from __future__ import annotations

import argparse
from pathlib import Path

from integration_common import (
    write_text,
    detect_binary,
    resolve_project_root,
    add_dry_run_arg,
    add_path_arg,
)

CLAUDE_INSTRUCTIONS = """# Claude + aihelper Integration Instructions

Before using Claude for project or code reasoning, apply aihelper's local context workflow:

- Run `aihelper route "<task>"` first to choose the best tool and token budget.
- Use `aihelper context --max-context-chars 2000` for most tasks.
- Extend to `--max-context-chars 4000` only for multi-file or cross-service changes.
- Prefer `aihelper symbol find <symbol>` and `aihelper diff-summary` instead of raw grep or full repo scans.
- Do not exceed 5000 chars without explicit user permission.

Use this file as a reference or paste it into Claude Desktop / Claude CLI system instructions.
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Claude integration instructions for aihelper."
    )
    add_dry_run_arg(parser)
    add_path_arg(parser)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = resolve_project_root(args.path)
    if project_root is None:
        return 1

    global_config = Path.home() / ".claude" / "aihelper-claude-instructions.md"
    write_text(global_config, CLAUDE_INSTRUCTIONS, args.dry_run)

    project_file = project_root / ".github" / "claude-instructions.md"
    write_text(project_file, CLAUDE_INSTRUCTIONS, args.dry_run)

    if detect_binary("claude", "claude.exe", "anthropic") is None:
        print("[INFO] Claude CLI not found; instructions generated for manual use.")
    else:
        print("[OK] Claude CLI detected or instructions generated for use.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
