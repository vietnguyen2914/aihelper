from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

try:
    from .cache import cache_status, load_cached_context
    from .common import tokenize
    from .symbols import find_symbols
except ImportError:
    from cache import cache_status, load_cached_context
    from common import tokenize
    from symbols import find_symbols


DB_WORDS = {"sql", "database", "db", "table", "column", "schema", "migration", "mysql", "postgres", "sqlite"}
DOC_WORDS = {"docs", "documentation", "library", "api", "version", "framework", "guide", "context7"}
BROWSER_WORDS = {"browser", "playwright", "ui", "screenshot", "click", "localhost", "web", "visual"}
GIT_WORDS = {"commit", "diff", "branch", "merge", "pr", "pull", "status", "log"}
PATCH_WORDS = {"patch", "fix", "edit", "replace", "refactor", "implement", "update"}
ARCH_WORDS = {"architecture", "design", "plan", "strategy", "proposal", "system"}
REALTIME_WORDS = {"autocomplete", "inline", "quick", "small", "rename"}
DEBUG_WORDS = {"debug", "bug", "error", "trace", "failure", "regression"}


def route_model(task: str) -> Dict[str, Any]:
    tokens = set(tokenize(task))
    if tokens & ARCH_WORDS:
        return {
            "primary": "gpt-5/codex-cloud",
            "local_fallback": "qwen3.5:4b",
            "reason": "Architecture and synthesis benefit from stronger cloud reasoning.",
        }
    if tokens & DEBUG_WORDS:
        return {
            "primary": "codex",
            "local_fallback": "qwen3.5:4b",
            "reason": "Debugging benefits from repo-aware patch and validation loops.",
        }
    if tokens & REALTIME_WORDS:
        return {
            "primary": "deepseek-coder:1.3b",
            "local_fallback": "deepseek-coder:1.3b",
            "reason": "Realtime editor tasks should favor low latency local models.",
        }
    if tokens & PATCH_WORDS:
        return {
            "primary": "codex",
            "local_fallback": "deepseek-coder:1.3b",
            "reason": "Patch tasks should use diff-aware coding agents and tiny local fallback.",
        }
    return {
        "primary": "aihelper_context+codex",
        "local_fallback": "deepseek-coder:1.3b",
        "reason": "Default coding path uses compact context first, then targeted patching.",
    }


def token_budget(task: str) -> Dict[str, int | str]:
    tokens = set(tokenize(task))
    if tokens & REALTIME_WORDS:
        return {"max_context_tokens": 1000, "mode": "realtime"}
    if tokens & ARCH_WORDS:
        return {"max_context_tokens": 12000, "mode": "architecture"}
    if tokens & DEBUG_WORDS:
        return {"max_context_tokens": 8000, "mode": "debug"}
    if tokens & PATCH_WORDS:
        return {"max_context_tokens": 4000, "mode": "patch"}
    return {"max_context_tokens": 6000, "mode": "default"}


def route_task(task: str, project_root: Path | None = None, max_symbols: int = 8) -> Dict[str, Any]:
    root = (project_root or Path.cwd()).resolve()
    tokens = set(tokenize(task))
    lower = task.lower()
    routes: List[Dict[str, Any]] = []

    def add(tool: str, reason: str, priority: str = "normal") -> None:
        if not any(item["tool"] == tool for item in routes):
            routes.append({"tool": tool, "reason": reason, "priority": priority})

    add("aihelper_context", "Primary compact context route for coding tasks.", "high")
    if tokens & DB_WORDS:
        add("aihelper_db_schema", "Use local schema summary before live DB access.", "high")
    if tokens & DOC_WORDS:
        add("context7", "Use current upstream documentation for framework/API details.", "normal")
    if tokens & GIT_WORDS:
        add("git", "Use git status/diff/log for repository state.", "normal")
    if tokens & BROWSER_WORDS:
        add("browser-profile", "Enable browser automation only for UI/runtime verification.", "on-demand")
    if tokens & PATCH_WORDS:
        add("aihelper_patch_plan", "Generate exact-path patch proposal before editing.", "normal")

    symbol_matches: List[Dict[str, Any]] = []
    for raw in task.replace("`", " ").split():
        candidate = raw.strip(".,:;()[]{}\"'")
        if len(candidate) < 4:
            continue
        if any(ch.isupper() for ch in candidate) or "_" in candidate:
            symbol_matches.extend(find_symbols(candidate, root, limit=3).get("matches", []))
        if len(symbol_matches) >= max_symbols:
            break

    status = cache_status(root)
    cached = load_cached_context(root, max_symbols=max_symbols) if status.get("fresh") else {}
    return {
        "task": task,
        "project_root": str(root),
        "cache": {"fresh": bool(status.get("fresh")), "status": status.get("manifest", {})},
        "recommended_next_tools": routes,
        "recommended_model": route_model(task),
        "token_budget": token_budget(task),
        "target_symbols": symbol_matches[:max_symbols],
        "cached_context": cached,
        "filesystem_policy": "fallback_exact_path_only",
    }
