#!/usr/bin/env python3
"""Codex CLI integration for aihelper.

Generates ~/.codex/config.json with aihelper-first instructions and
registers the aihelper MCP server via `codex mcp add` (v0.133.0+).

Failsafe: writes config even if Codex CLI is not installed.
          Skips MCP registration if `codex` binary is missing.
Re-runnable: skips writing when content is unchanged; codex mcp add
             is idempotent (overwrites with same values).

Usage:
    python3 scripts/codex-integration.py
    python3 scripts/codex-integration.py --dry-run
"""

from __future__ import annotations

import argparse
from pathlib import Path

from integration_common import (
    IS_WINDOWS,
    write_json,
    safe_run,
    detect_binary,
    mcp_server_path,
    add_dry_run_arg,
)

CODEX_CONFIG = {
    "developer_instructions": (
        "CRITICAL: Before every response, run aihelper_route and aihelper_context "
        "tools first to compress project context. Never scan full repos. Use symbol "
        "lookups instead of grep. Respect the token budget from aihelper_route. "
        "Default to 2000 max_context_chars for context tool calls. Only escalate to "
        "full file reads when aihelper context is insufficient. This applies "
        "regardless of which model is being used."
    ),
    "model_auto_compact_token_limit": 4000,
    "model_context_window": 32000,
    "model_verbosity": "concise",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Codex integration config for aihelper."
    )
    add_dry_run_arg(parser)
    return parser.parse_args()


def _register_mcp_server(dry_run: bool) -> bool:
    """Register the aihelper MCP server via `codex mcp add`.

    Uses stdio transport pointing at the aihelper MCP server script.
    Returns True if registration succeeded (or would succeed in dry-run).
    """
    server = mcp_server_path()
    if not server.exists():
        print(f"[WARN] MCP server not found at: {server}")
        print("[INFO] Skipping Codex MCP registration.")
        return False

    codex_bin = detect_binary("codex")
    if codex_bin is None:
        print("[INFO] Codex CLI not found; skipping MCP server registration.")
        return False

    python = "python" if IS_WINDOWS else "python3"

    if dry_run:
        print(f"[DRY-RUN] Would run: {codex_bin} mcp add aihelper -- {python} {server}")
        return True

    result = safe_run([codex_bin, "mcp", "add", "aihelper", "--", python, str(server)])
    if result is None:
        print("[WARN] Failed to register aihelper MCP server with Codex.")
        return False

    print(f"[OK] Registered aihelper MCP server via: {codex_bin} mcp add")
    return True


def main() -> int:
    args = parse_args()

    # Step 1: Write ~/.codex/config.json (always, failsafe)
    config_path = Path.home() / ".codex" / "config.json"
    write_json(config_path, CODEX_CONFIG, args.dry_run)

    # Step 2: Register MCP server via `codex mcp add` (failsafe)
    _register_mcp_server(args.dry_run)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
