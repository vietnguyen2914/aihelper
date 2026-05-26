#!/usr/bin/env python3
"""Zed editor MCP integration for aihelper.

Configures Zed's MCP server to connect to the aihelper daemon.
Works on macOS and Linux (Zed does not run on Windows).

Usage:
    python3 scripts/zed-integration.py
    python3 scripts/zed-integration.py --dry-run
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from integration_common import (
    IS_MACOS,
    merge_settings,
    detect_binary,
    mcp_server_path,
    add_dry_run_arg,
)


def _zed_settings() -> Path:
    """Return the OS-appropriate Zed settings.json path."""
    if IS_MACOS:
        fallback = Path.home() / "Library/Application Support/Zed/settings.json"
        if fallback.exists():
            return fallback
    return Path.home() / ".config/zed/settings.json"


def mcp_entry(server_path: str) -> dict:
    return {"command": "python3", "args": [server_path]}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Zed MCP configuration for aihelper."
    )
    add_dry_run_arg(parser)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    server = mcp_server_path()
    if not server.exists():
        print(f"[WARN] MCP server not found at: {server}")
        print("[INFO] Skipping Zed integration (MCP server unavailable).")
        return 0

    config = {"mcp_servers": {"aihelper": mcp_entry(str(server))}}
    merge_settings(_zed_settings(), config, args.dry_run)

    # Detect Zed editor availability (informational only)
    if detect_binary("zed") is None:
        print("[INFO] Zed binary not found in PATH. Config generated for future use.")
    else:
        print("[OK] Zed binary detected.")

    # macOS app bundle detection
    if IS_MACOS:
        for app in ("/Applications/Zed.app", "/Applications/Zed Preview.app"):
            if os.path.isdir(app):
                print(f"[OK] Zed app detected at: {app}")
                break

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
