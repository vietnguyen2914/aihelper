#!/usr/bin/env python3
"""OpenCode MCP integration for aihelper.

Configures OpenCode's MCP server to connect to the aihelper daemon.
Works on macOS, Linux, and Windows.

Usage:
    python3 scripts/opencode-integration.py
    python3 scripts/opencode-integration.py --dry-run
"""

from __future__ import annotations

import argparse
from pathlib import Path

from integration_common import (
    IS_WINDOWS,
    IS_MACOS,
    merge_settings,
    detect_binary,
    mcp_server_path,
    add_dry_run_arg,
)


def _opencode_config() -> Path:
    """Return the OS-appropriate OpenCode config path."""
    if IS_WINDOWS:
        import os
        return Path(os.environ.get("APPDATA", "")) / "opencode/opencode.json"
    if IS_MACOS:
        fallback = Path.home() / "Library/Application Support/opencode/opencode.json"
        if fallback.exists():
            return fallback
    return Path.home() / ".config/opencode/opencode.json"


def mcp_entry(python_cmd: str, server_path: str) -> dict:
    return {"command": python_cmd, "args": [server_path]}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate OpenCode MCP configuration for aihelper."
    )
    add_dry_run_arg(parser)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    server = mcp_server_path()
    if not server.exists():
        print(f"[WARN] MCP server not found at: {server}")
        print("[INFO] Skipping OpenCode integration (MCP server unavailable).")
        return 0

    config = {"mcpServers": {"aihelper": mcp_entry("python" if IS_WINDOWS else "python3", str(server))}}
    merge_settings(_opencode_config(), config, args.dry_run)

    if detect_binary("opencode") is None:
        print("[INFO] OpenCode binary not found in PATH. Config generated for future use.")
    else:
        print("[OK] OpenCode binary detected.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
