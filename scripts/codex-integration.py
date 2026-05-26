#!/usr/bin/env python3
"""Codex CLI integration for aihelper.

Generates ~/.codex/config.json with aihelper-first instructions.
Failsafe: writes config even if Codex CLI is not installed.
Re-runnable: skips writing when content is unchanged.

Usage:
    python3 scripts/codex-integration.py
    python3 scripts/codex-integration.py --dry-run
"""

from __future__ import annotations

import argparse
from pathlib import Path

from integration_common import (
    write_json,
    detect_binary,
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


def main() -> int:
    args = parse_args()
    config_path = Path.home() / ".codex" / "config.json"
    write_json(config_path, CODEX_CONFIG, args.dry_run)

    if detect_binary("codex") is None:
        print("[INFO] Codex CLI not found; config generated for later use.")
    else:
        print("[OK] Codex CLI available or config file created.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
