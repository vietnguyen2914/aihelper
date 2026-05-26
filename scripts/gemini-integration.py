#!/usr/bin/env python3
"""Gemini / Antigravity MCP integration for aihelper.

Configures Gemini's MCP server to connect to the aihelper daemon.
Works on macOS, Linux, and Windows.

Usage:
    python3 scripts/gemini-integration.py
    python3 scripts/gemini-integration.py --dry-run
"""

from __future__ import annotations

import argparse
from pathlib import Path

from integration_common import (
    IS_WINDOWS,
    merge_settings,
    detect_binary,
    mcp_server_path,
    add_dry_run_arg,
)


def _gemini_config() -> Path:
    """Return the OS-appropriate Gemini MCP config path."""
    if IS_WINDOWS:
        import os
        return Path(os.environ.get("APPDATA", "")) / "Gemini/config/mcp_config.json"
    return Path.home() / ".gemini/config/mcp_config.json"


def mcp_entry(python_cmd: str, server_path: str) -> dict:
    return {"command": python_cmd, "args": [server_path]}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Gemini/Antigravity MCP configuration for aihelper."
    )
    add_dry_run_arg(parser)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    server = mcp_server_path()
    if not server.exists():
        print(f"[WARN] MCP server not found at: {server}")
        print("[INFO] Skipping Gemini integration (MCP server unavailable).")
        return 0

    config = {"mcpServers": {"aihelper": mcp_entry("python" if IS_WINDOWS else "python3", str(server))}}
    merge_settings(_gemini_config(), config, args.dry_run)

    if detect_binary("gemini") is None:
        print("[INFO] Gemini CLI not found in PATH. Config generated for future use.")
    else:
        print("[OK] Gemini CLI detected.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
