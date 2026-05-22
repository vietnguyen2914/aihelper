from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter
from typing import Any, Dict

try:
    from .cache_persistence import cache_persist_status, persist_all_projects, restore_cache, persist_cache
    from .daemon import daemon_call, daemon_status, is_daemon_running, start_daemon, stop_daemon, run_daemon
    from .warmup import warm_all_projects
    from .confidence import score_patch
    from .editor_context import get_editor_context
    from .lsp_bridge import find_definition, find_all_references, get_document_symbols
    from .build_prompt import build_prompt, rewrite_prompt
    from .cache import build_cache, cache_status, clean_cache, warm_project, watch_all_projects, watch_cache
    from .detect_feature import detect_feature_matches, detect_features
    from .discovery import discover_feature_from_codebase
    from .intent_detector import detect_intent
    from .ollama_fallback import build_discovery_prompt, build_manual_fallback_prompt, call_ollama, generate_with_ollama, ollama_health
    from .patch_engine import apply_unified_patch, build_patch_plan, validate_files
    from .prompt_blocks import build_prompt_blocks, load_prompt_blocks
    from .router import route_task
    from .semantic_diff import semantic_diff_summary
    from .symbols import dependency_context, find_symbols, symbol_context
    from .working_memory import recall, remember
    from .kb_updater import update_ai_kb
    from .learning import feedback_summary, record_feedback
    from .load_context import load_context_bundle
    from .rebuild_index import rebuild_indexes
except ImportError:
    from cache_persistence import cache_persist_status, persist_all_projects, restore_cache, persist_cache
    from daemon import daemon_call, daemon_status, is_daemon_running, start_daemon, stop_daemon, run_daemon
    from warmup import warm_all_projects
    from confidence import score_patch
    from editor_context import get_editor_context
    from lsp_bridge import find_definition, find_all_references, get_document_symbols
    from build_prompt import build_prompt, rewrite_prompt
    from cache import build_cache, cache_status, clean_cache, warm_project, watch_all_projects, watch_cache
    from detect_feature import detect_feature_matches, detect_features
    from discovery import discover_feature_from_codebase
    from intent_detector import detect_intent
    from ollama_fallback import build_discovery_prompt, build_manual_fallback_prompt, call_ollama, generate_with_ollama, ollama_health
    from patch_engine import apply_unified_patch, build_patch_plan, validate_files
    from prompt_blocks import build_prompt_blocks, load_prompt_blocks
    from router import route_task
    from semantic_diff import semantic_diff_summary
    from symbols import dependency_context, find_symbols, symbol_context
    from working_memory import recall, remember
    from kb_updater import update_ai_kb
    from learning import feedback_summary, record_feedback
    from load_context import load_context_bundle
    from rebuild_index import rebuild_indexes


def _format_markdown_scalar(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "none"
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return str(value)


def _append_markdown_value(lines: list[str], key: str, value: Any, indent: int = 0) -> None:
    prefix = "  " * indent + f"- **{key}**:"
    if isinstance(value, dict):
        lines.append(prefix)
        if not value:
            lines.append("  " * (indent + 1) + "- _empty_")
            return
        for nested_key, nested_value in value.items():
            _append_markdown_value(lines, nested_key, nested_value, indent + 1)
        return

    if isinstance(value, list):
        lines.append(prefix)
        if not value:
            lines.append("  " * (indent + 1) + "- _empty_")
            return
        for item in value:
            if isinstance(item, dict):
                lines.append("  " * (indent + 1) + "-")
                for nested_key, nested_value in item.items():
                    _append_markdown_value(lines, nested_key, nested_value, indent + 2)
            else:
                lines.append("  " * (indent + 1) + f"- {_format_markdown_scalar(item)}")
        return

    lines.append(f"{prefix} {_format_markdown_scalar(value)}")


def render_markdown(title: str, data: Dict[str, Any]) -> str:
    lines = [f"# {title}"]
    for key, value in data.items():
        _append_markdown_value(lines, key, value)
    return "\n".join(lines)


def render_analyze_markdown(result: Dict[str, Any]) -> str:
    lines = ["# aihelper analysis"]

    lines.append("## Overview")
    lines.append(f"- **Input**: {result.get('input', '')}")
    lines.append(f"- **Runtime**: {_format_markdown_scalar(result.get('runtime_ms', 0))} ms")
    if result.get("mode"):
        lines.append(f"- **Mode**: {result.get('mode', '')}")

    lines.append("## Detected Intent")
    detected_intent = result.get("detected_intent")
    if isinstance(detected_intent, dict):
        lines.append("```json")
        lines.append(json.dumps(detected_intent, indent=2, ensure_ascii=False))
        lines.append("```")
    else:
        lines.append(f"- {_format_markdown_scalar(detected_intent)}")

    lines.append("## Detected Features")
    detected_features = result.get("detected_features", [])
    if detected_features:
        for feature in detected_features:
            service = feature.get("service", "unknown service")
            name = feature.get("feature", "unknown feature")
            score = feature.get("score", 0)
            keywords = feature.get("matched_keywords", [])
            keyword_text = ", ".join(str(keyword) for keyword in keywords) if keywords else "none"
            lines.append(f"- **{service}**: {name} (score {_format_markdown_scalar(score)}, keywords: {keyword_text})")
    else:
        lines.append("- _none detected_")

    lines.append("## Selected Context")
    selected_context = result.get("selected_context", {})
    if isinstance(selected_context, dict) and selected_context:
        lines.append("```json")
        lines.append(json.dumps(selected_context, indent=2, ensure_ascii=False))
        lines.append("```")
    else:
        lines.append("- _none_")

    lines.append("## Final Prompt")
    lines.append("```text")
    lines.append(result.get("final_prompt", ""))
    lines.append("```")

    lines.append("## Rewritten Prompt")
    lines.append("```text")
    lines.append(result.get("rewritten_prompt", ""))
    lines.append("```")

    execution_steps = result.get("execution_steps", [])
    lines.append("## Execution Steps")
    if execution_steps:
        for index, step in enumerate(execution_steps, start=1):
            if isinstance(step, dict):
                step_name = step.get("step", f"step-{index}")
                details = step.get("details")
                output = step.get("output")
                lines.append(f"{index}. **{step_name}**")
                if details:
                    lines.append(f"   - {details}")
                if output is not None:
                    lines.append("   - Output:")
                    lines.append("```json")
                    lines.append(json.dumps(output, indent=2, ensure_ascii=False))
                    lines.append("```")
            else:
                lines.append(f"{index}. {_format_markdown_scalar(step)}")
    else:
        lines.append("- _none_")

    lines.append("## Knowledge Base")
    _append_markdown_value(lines, "kb_update", result.get("kb_update", {}))

    lines.append("## Feedback Summary")
    _append_markdown_value(lines, "feedback_summary", result.get("feedback_summary", {}))

    if result.get("discovery_result") is not None:
        lines.append("## Discovery Result")
        lines.append("```json")
        lines.append(json.dumps(result.get("discovery_result"), indent=2, ensure_ascii=False))
        lines.append("```")

    return "\n".join(lines)


def analyze_request(
    user_prompt: str,
    max_context_chars: int = 12000,
    root: Path | None = None,
    auto_update_kb: bool = False,
) -> Dict[str, Any]:
    start = perf_counter()
    root = root.resolve() if root else Path.cwd().resolve()
    intent = detect_intent(user_prompt, root=root)
    detected_feature_names = detect_features(user_prompt, root=root)
    discovery_result = None
    kb_update = {"updated": False, "reason": "not_needed"}
    discovery_prompt = None
    prompt_fallback = None

    def compact_route_context(route: Dict[str, Any]) -> Dict[str, Any]:
        cached = route.get("cached_context", {}) or {}
        repo_summary = cached.get("repo_summary", {}) or {}
        db_summary = cached.get("db_schema_summary", {}) or {}
        blocks = load_prompt_blocks(root)
        block_data = blocks.get("blocks", {}) if isinstance(blocks, dict) else {}
        return {
            "cache": {
                "fresh": bool(route.get("cache", {}).get("fresh")),
                "manifest": route.get("cache", {}).get("status", {}),
            },
            "repo_summary": {
                "file_count": repo_summary.get("file_count", 0),
                "kind_counts": repo_summary.get("kind_counts", {}),
                "important_files": (repo_summary.get("important_files") or [])[:20],
            },
            "db_schema_summary": {
                "table_count": db_summary.get("table_count", 0),
                "tables": (db_summary.get("tables") or [])[:20],
            },
            "prompt_blocks": {
                "available": sorted(block_data.keys()),
                "recent_changed_files": (
                    block_data.get("recent_git_changes", {}).get("changed_files", [])[:10]
                    if isinstance(block_data.get("recent_git_changes"), dict)
                    else []
                ),
            },
        }

    def attach_route_hints(payload: Dict[str, Any], route: Dict[str, Any]) -> Dict[str, Any]:
        payload["route"] = route
        payload["recommended_next_tools"] = route.get("recommended_next_tools", [])
        payload["recommended_model"] = route.get("recommended_model", {})
        payload["token_budget"] = route.get("token_budget", {})
        if route.get("cache", {}).get("fresh"):
            payload["aihelper_cache"] = route.get("cached_context", {})
            blocks = load_prompt_blocks(root)
            if blocks.get("blocks"):
                payload["prompt_blocks"] = blocks
        return payload

    if not detected_feature_names:
        discovery_result = discover_feature_from_codebase(user_prompt, root=root)
        discovery_prompt = build_discovery_prompt(user_prompt, root=root)
        ollama_output, ollama_ready = call_ollama(discovery_prompt, model_type="medium")

        if ollama_ready and isinstance(ollama_output, str):
            try:
                parsed = json.loads(ollama_output)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                discovery_result = parsed
                if auto_update_kb:
                    kb_update = update_ai_kb(discovery_result, root=root)
                route = route_task(user_prompt, project_root=root)
                result = {
                    "input": user_prompt,
                    "detected_intent": intent,
                    "detected_features": [],
                    "selected_context": {
                        "target_root": str(root.resolve()) if root else "",
                        "services": [],
                        "ext_overrides": [],
                        "context_limit_chars": max_context_chars,
                        "truncated": False,
                    },
                    "final_prompt": build_prompt(user_prompt, {"target_root": str(root.resolve()) if root else "", "services": []}),
                    "rewritten_prompt": user_prompt,
                    "execution_steps": [
                        {
                            "step": "discover_feature",
                            "output": discovery_result,
                        }
                    ],
                    "discovery_result": discovery_result,
                    "kb_update": kb_update,
                    "feedback_summary": feedback_summary(root=root),
                    "runtime_ms": round((perf_counter() - start) * 1000.0, 3),
                    "mode": "ollama_discovery",
                    "discovery_prompt": discovery_prompt,
                }
                return attach_route_hints(result, route)

        prompt_fallback = build_manual_fallback_prompt(user_prompt, root=root)
        route = route_task(user_prompt, project_root=root)
        result = {
            "input": user_prompt,
            "detected_intent": intent,
            "detected_features": [],
            "selected_context": {
                "target_root": str(root.resolve()) if root else "",
                "services": [],
                "ext_overrides": [],
                "context_limit_chars": max_context_chars,
                "truncated": False,
            },
            "final_prompt": build_prompt(user_prompt, {"target_root": str(root.resolve()) if root else "", "services": []}),
            "rewritten_prompt": user_prompt,
            "execution_steps": [
                {"step": "discover", "details": "No indexed feature matched. Use the short discovery prompt with GPT or Claude."}
            ],
            "discovery_result": discovery_result,
            "kb_update": kb_update,
            "feedback_summary": feedback_summary(root=root),
            "runtime_ms": round((perf_counter() - start) * 1000.0, 3),
            "mode": "prompt_only",
            "prompt_fallback": prompt_fallback,
        }
        return attach_route_hints(result, route)

    feature_matches = detect_feature_matches(user_prompt, root=root, top_n=3)
    context = load_context_bundle(feature_matches, max_chars=max_context_chars, root=root)
    route = route_task(user_prompt, project_root=root)
    if route.get("cache", {}).get("fresh"):
        context["aihelper_cache"] = compact_route_context(route)
    context["recommended_next_tools"] = route.get("recommended_next_tools", [])
    context["recommended_model"] = route.get("recommended_model", {})
    context["token_budget"] = route.get("token_budget", {})
    rewritten = rewrite_prompt(user_prompt, intent, feature_matches, context)
    final_prompt = build_prompt(user_prompt, context)

    try:
        from .planner import build_execution_plan
    except ImportError:
        from planner import build_execution_plan

    execution_steps = build_execution_plan(user_prompt, intent, feature_matches, context)
    result = {
        "input": user_prompt,
        "detected_intent": intent,
        "detected_features": [
            {
                "service": item["service"],
                "service_root": item["service_root"],
                "feature": item["feature"],
                "score": item["score"],
                "matched_keywords": item["matched_keywords"],
            }
            for item in feature_matches
        ],
        "selected_context": context,
        "final_prompt": final_prompt,
        "rewritten_prompt": rewritten,
        "execution_steps": execution_steps,
        "discovery_result": discovery_result,
        "kb_update": kb_update,
        "feedback_summary": feedback_summary(root=root),
        "runtime_ms": round((perf_counter() - start) * 1000.0, 3),
    }
    return attach_route_hints(result, route)



def doctor() -> Dict[str, Any]:
    """Run diagnostic checks on the aihelper installation.

    Checks: daemon, socket, watchman, ollama, models, cache, ramdisk, permissions.
    """
    import os, shutil, subprocess, socket, json, time
    from pathlib import Path

    results = {}
    all_ok = True

    def check(name: str, fn, critical: bool = False) -> None:
        nonlocal all_ok
        try:
            ok = fn()
            results[name] = {"status": "ok" if ok else "fail", "critical": critical}
            if not ok: all_ok = False
        except Exception as e:
            results[name] = {"status": "error", "message": str(e)[:100], "critical": critical}
            all_ok = False

    check("python3", lambda: bool(shutil.which("python3")))
    check("git", lambda: bool(shutil.which("git")))
    check("watchman", lambda: bool(shutil.which("watchman")), critical=False)
    check("ollama", lambda: bool(shutil.which("ollama")), critical=False)
    check("socket_dir", lambda: Path.home().joinpath(".aihelper").exists())

    # ── Daemon check ────────────────────────────────────────────────
    sock_path = Path.home() / ".aihelper" / "aihelper.sock"
    check("daemon_socket", lambda: sock_path.exists())
    if sock_path.exists():
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(1)
            sock.connect(str(sock_path))
            sock.sendall(json.dumps({"method": "health", "params": {}, "id": 1}).encode() + b"\n")
            resp = sock.recv(4096)
            data = json.loads(resp.decode())
            sock.close()
            results["daemon_health"] = {"status": "ok" if data.get("result",{}).get("status") == "ok" else "degraded"}
        except Exception as e:
            results["daemon_health"] = {"status": "error", "message": str(e)[:100]}

    # ── Cache check ─────────────────────────────────────────────────
    check("cache_writable", lambda: (Path.cwd() / ".ai-cache" / "aihelper" / "manifest.json").parent.exists(), critical=False)

    # ── MCP server check ────────────────────────────────────────────
    mcp_path = Path(__file__).parent / "mcp_server.py"
    check("mcp_server", lambda: mcp_path.exists())

    # ── Models check ────────────────────────────────────────────────
    def _check_models() -> bool:
        """Check that at least the minimal hot-tier models are pulled."""
        if not shutil.which("ollama"):
            return False
        try:
            result = subprocess.run(
                ["ollama", "list"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=10,
            )
            if result.returncode != 0:
                return False
            out = result.stdout.lower()
            # At least one hot-tier model should be present
            hot_models = ["deepseek-coder", "phi4-mini", "qwen3.5"]
            found = any(m in out for m in hot_models)
            if not found:
                # Also check by exact name
                lines = result.stdout.strip().split("\n")
                found = len(lines) > 1  # header + at least one model
            return found
        except Exception:
            return False
    check("models_pulled", _check_models, critical=False)

    # ── Ramdisk check ───────────────────────────────────────────────
    def _check_ramdisk() -> bool:
        """Check if a RAM disk is mounted (optional performance feature)."""
        if not shutil.which("mount"):
            return False
        try:
            result = subprocess.run(
                ["mount"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=5,
            )
            return "/Volumes/ramdisk" in result.stdout or "/Volumes/aihelper" in result.stdout
        except Exception:
            return False
    check("ramdisk", _check_ramdisk, critical=False)

    # ── Permissions check ───────────────────────────────────────────
    def _check_permissions() -> bool:
        """Check that key paths have correct permissions."""
        aihelper_home = Path.home() / ".aihelper"
        if not aihelper_home.exists():
            return False
        # Socket should be readable/writable
        if sock_path.exists():
            mode = sock_path.stat().st_mode
            # Should be 0o600 (owner only)
            if mode & 0o077:  # group/other have some access
                pass  # lenient — warn but don't fail
        # Log dir should be writable
        log_dir = aihelper_home / "logs"
        if log_dir.exists():
            if not os.access(str(log_dir), os.W_OK):
                return False
        # Cache dir should be writable
        persist_dir = aihelper_home / "persist"
        if persist_dir.exists():
            if not os.access(str(persist_dir), os.W_OK):
                return False
        return True
    check("permissions", _check_permissions)

    # ── Log directory check ─────────────────────────────────────────
    log_dir = Path.home() / ".aihelper" / "logs"
    check("log_dir", lambda: log_dir.exists() and any(log_dir.iterdir()) if log_dir.exists() else False, critical=False)

    results["overall"] = "ok" if all_ok else "issues_found"
    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Portable AI helper that reads the current project's ai indexes and returns feature-aware execution context."
    )
    subparsers = parser.add_subparsers(dest="command")

    analyze_parser = subparsers.add_parser("analyze", help="Analyze a raw prompt.")
    analyze_parser.add_argument("user_prompt", nargs="?", help="The raw user request to analyze.")
    analyze_parser.add_argument("--max-context-chars", type=int, default=12000)
    analyze_parser.add_argument("--auto-update-kb", action="store_true")
    analyze_parser.add_argument("--project-root", default=None)
    analyze_parser.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)
    analyze_parser.add_argument("--format", choices=("json", "markdown", "prompt"), default="markdown")

    feedback_parser = subparsers.add_parser("feedback", help="Record prompt quality feedback.")
    feedback_parser.add_argument("user_prompt", help="The original prompt.")
    feedback_parser.add_argument("--intent", required=True)
    feedback_parser.add_argument("--features", nargs="*", default=[])
    feedback_parser.add_argument("--accepted", action="store_true")
    feedback_parser.add_argument("--rating", type=int, default=0)
    feedback_parser.add_argument("--notes", default="")
    feedback_parser.add_argument("--project-root", default=None)
    feedback_parser.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

    summary_parser = subparsers.add_parser("feedback-summary", aliases=["feedback_summary"], help="Print feedback summary.")
    summary_parser.add_argument("--project-root", default=None)
    summary_parser.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

    rebuild_parser = subparsers.add_parser(
        "rebuild-index",
        aliases=["rebuild_index"],
        help="Rebuild ai/index from ai/features and ai/flows.",
    )
    rebuild_parser.add_argument("--project-root", default=None)
    rebuild_parser.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

    cache_parser = subparsers.add_parser("cache", help="Build, inspect, or clean the per-repository aihelper cache.")
    cache_subparsers = cache_parser.add_subparsers(dest="cache_command")
    for name in ("build", "status", "clean", "warm"):
        sub = cache_subparsers.add_parser(name)
        sub.add_argument("--project-root", default=None)
        sub.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)
    cache_watch_parser = cache_subparsers.add_parser("watch")
    cache_watch_parser.add_argument("--project-root", default=None)
    cache_watch_parser.add_argument("--interval", type=float, default=2.0)
    cache_watch_parser.add_argument("--persist-interval", type=int, default=28800, help="Persist cache to SSD every N seconds (0=disabled)")
    cache_watch_parser.add_argument("--once", action="store_true")
    cache_watch_parser.add_argument("--max-cycles", type=int, default=0)
    cache_watch_parser.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)
    cache_watch_all_parser = cache_subparsers.add_parser("watch-all")
    cache_watch_all_parser.add_argument("--github-root", default="$HOME/github")
    cache_watch_all_parser.add_argument("--extra-project", action="append", default=[])
    cache_watch_all_parser.add_argument("--interval", type=float, default=2.0)
    cache_watch_all_parser.add_argument("--persist-interval", type=int, default=28800, help="Persist all caches to SSD every N seconds (default 300=5min, 0=disabled)")
    cache_watch_all_parser.add_argument("--once", action="store_true")
    cache_watch_all_parser.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

    # ── Persist / Restore ──────────────────────────────────────────────
    cache_persist_parser = cache_subparsers.add_parser("persist", help="Persist RAM-based cache to SSD.")
    cache_persist_parser.add_argument("--project-root", default=None)
    cache_persist_parser.add_argument("--all", action="store_true", help="Persist all known projects")
    cache_persist_parser.add_argument("--github-root", default="$HOME/github")
    cache_persist_parser.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

    cache_restore_parser = cache_subparsers.add_parser("restore", help="Restore persisted cache from SSD to RAM.")
    cache_restore_parser.add_argument("--project-root", default=None)
    cache_restore_parser.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

    cache_persist_status_parser = cache_subparsers.add_parser("persist-status", help="Show cache persistence status.")
    cache_persist_status_parser.add_argument("--project-root", default=None)
    cache_persist_status_parser.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

    blocks_parser = subparsers.add_parser("prompt-blocks", aliases=["prompt_blocks"], help="Build or inspect precompiled prompt blocks.")
    blocks_subparsers = blocks_parser.add_subparsers(dest="blocks_command")
    for name in ("build", "show"):
        sub = blocks_subparsers.add_parser(name)
        sub.add_argument("--project-root", default=None)
        sub.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

    diff_parser = subparsers.add_parser("diff-summary", aliases=["diff_summary"], help="Generate a compact semantic git diff summary.")
    diff_parser.add_argument("--project-root", default=None)
    diff_parser.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

    memory_parser = subparsers.add_parser("memory", help="Record or recall local working memory for a project.")
    memory_subparsers = memory_parser.add_subparsers(dest="memory_command")
    memory_add = memory_subparsers.add_parser("add")
    memory_add.add_argument("topic")
    memory_add.add_argument("note")
    memory_add.add_argument("--tag", dest="tags", action="append", default=[])
    memory_add.add_argument("--project-root", default=None)
    memory_add.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)
    memory_recall = memory_subparsers.add_parser("recall")
    memory_recall.add_argument("query", nargs="?", default="")
    memory_recall.add_argument("--limit", type=int, default=10)
    memory_recall.add_argument("--project-root", default=None)
    memory_recall.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

    symbol_parser = subparsers.add_parser("symbol", help="Find symbols from the local aihelper cache.")
    symbol_subparsers = symbol_parser.add_subparsers(dest="symbol_command")
    for name in ("find", "context"):
        sub = symbol_subparsers.add_parser(name)
        sub.add_argument("query")
        sub.add_argument("--project-root", default=None)
        sub.add_argument("--limit", type=int, default=20)
        sub.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

    deps_parser = subparsers.add_parser("deps", help="Show dependency/import context for a symbol or file.")
    deps_parser.add_argument("query")
    deps_parser.add_argument("--project-root", default=None)
    deps_parser.add_argument("--limit", type=int, default=50)
    deps_parser.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

    route_parser = subparsers.add_parser("route", help="Route a task to the cheapest useful tools.")
    route_parser.add_argument("task", nargs="?")
    route_parser.add_argument("--project-root", default=None)
    route_parser.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

    patch_parser = subparsers.add_parser("patch-plan", aliases=["patch_plan"], help="Create a proposal-only patch template for exact files.")
    patch_parser.add_argument("task")
    patch_parser.add_argument("--file", dest="files", action="append", default=[])
    patch_parser.add_argument("--project-root", default=None)
    patch_parser.add_argument("--style", choices=("unified", "search-replace"), default="unified")
    patch_parser.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

    patch_apply_parser = subparsers.add_parser("patch-apply", aliases=["patch_apply"], help="Dry-run or apply a unified patch with validation.")
    patch_apply_parser.add_argument("--patch-file", required=True)
    patch_apply_parser.add_argument("--project-root", default=None)
    patch_apply_parser.add_argument("--apply", action="store_true")
    patch_apply_parser.add_argument("--no-validate", action="store_true")
    patch_apply_parser.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

    validate_parser = subparsers.add_parser("validate-files", aliases=["validate_files"], help="Run lightweight syntax/build validation for exact files.")
    validate_parser.add_argument("files", nargs="+")
    validate_parser.add_argument("--project-root", default=None)
    validate_parser.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

    ollama_parser = subparsers.add_parser("ollama", help="Inspect or prewarm local Ollama models.")
    ollama_subparsers = ollama_parser.add_subparsers(dest="ollama_command")
    ollama_health_parser = ollama_subparsers.add_parser("health", help="Print Ollama availability and resolved model defaults.")
    ollama_health_parser.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)
    ollama_prewarm_parser = ollama_subparsers.add_parser("prewarm", help="Preload a small local model with keep_alive.")
    ollama_prewarm_parser.add_argument("--model-type", choices=("tiny", "medium", "large"), default="medium")
    ollama_prewarm_parser.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

    # ── Doctor ────────────────────────────────────────────────────────
    doctor_parser = subparsers.add_parser("doctor", help="Run diagnostic checks on the installation.")
    doctor_parser.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

    # ── Daemon ─────────────────────────────────────────────────────────
    daemon_parser = subparsers.add_parser("daemon", help="Manage the aihelper persistent daemon.")
    daemon_subparsers = daemon_parser.add_subparsers(dest="daemon_command")
    daemon_start = daemon_subparsers.add_parser("start", help="Start the daemon.")
    daemon_start.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)
    daemon_stop = daemon_subparsers.add_parser("stop", help="Stop the daemon.")
    daemon_stop.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)
    daemon_status_parser = daemon_subparsers.add_parser("status", help="Show daemon status.")
    daemon_status_parser.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)
    daemon_serve = daemon_subparsers.add_parser("serve", help=argparse.SUPPRESS)  # Internal use only

    # ── Editor Context ────────────────────────────────────────────────
    editor_ctx_parser = subparsers.add_parser("editor-context", aliases=["editor_context"],
        help="Detect active editor, open file, and git context.")
    editor_ctx_parser.add_argument("--project-root", default=None)
    editor_ctx_parser.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

    # ── LSP ────────────────────────────────────────────────────────────
    lsp_parser = subparsers.add_parser("lsp", help="Query language servers for symbols, definitions, references.")
    lsp_subparsers = lsp_parser.add_subparsers(dest="lsp_command")
    lsp_def = lsp_subparsers.add_parser("definition", help="Go to definition via LSP.")
    lsp_def.add_argument("file_path")
    lsp_def.add_argument("--line", type=int, default=1)
    lsp_def.add_argument("--character", type=int, default=1)
    lsp_def.add_argument("--project-root", default=None)
    lsp_def.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)
    lsp_ref = lsp_subparsers.add_parser("references", help="Find references via LSP.")
    lsp_ref.add_argument("file_path")
    lsp_ref.add_argument("--line", type=int, default=1)
    lsp_ref.add_argument("--character", type=int, default=1)
    lsp_ref.add_argument("--project-root", default=None)
    lsp_ref.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)
    lsp_sym = lsp_subparsers.add_parser("symbols", help="Document symbols via LSP.")
    lsp_sym.add_argument("file_path")
    lsp_sym.add_argument("--project-root", default=None)
    lsp_sym.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

    # ── Confidence ─────────────────────────────────────────────────────
    conf_parser = subparsers.add_parser("confidence", help="Score a patch for auto-apply confidence.")
    conf_parser.add_argument("--patch-file", help="Path to patch file (or read from stdin)")
    conf_parser.add_argument("--files", nargs="*", default=[], help="Files affected by the patch")
    conf_parser.add_argument("--project-root", default=None)
    conf_parser.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

    # ── Structural Diff ────────────────────────────────────────────────
    sdiff_parser = subparsers.add_parser("structural-diff", aliases=["structural_diff"],
        help="AST-aware structural patch analysis.")
    sdiff_parser.add_argument("--patch-file", help="Path to unified diff patch")
    sdiff_parser.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

    # ── Hierarchical Context ───────────────────────────────────────────
    hctx_parser = subparsers.add_parser("hierarchical-context", aliases=["hierarchical_context"],
        help="Progressive context expansion (module→package→repo).")
    hctx_parser.add_argument("--project-root", default=None)
    hctx_parser.add_argument("--focus-file", default=None, help="File currently being edited")
    hctx_parser.add_argument("--focus-symbol", default=None, help="Symbol of interest")
    hctx_parser.add_argument("--level", type=int, default=1, choices=(1,2,3),
        help="Expansion level: 1=module, 2=package, 3=repo")
    hctx_parser.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

    # ── Scheduler ──────────────────────────────────────────────────────
    sched_parser = subparsers.add_parser("scheduler", help="Semantic scheduler: snapshot, predict, record.")
    sched_subparsers = sched_parser.add_subparsers(dest="scheduler_command")
    sched_snap = sched_subparsers.add_parser("snapshot", help="Full scheduler context snapshot.")
    sched_snap.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)
    sched_pred = sched_subparsers.add_parser("predict", help="Predict next user actions.")
    sched_pred.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)
    sched_rec = sched_subparsers.add_parser("record", help="Record a signal (edit, query, error).")
    sched_rec.add_argument("--type", required=True, choices=("edit","symbol_query","branch","build_error","route"))
    sched_rec.add_argument("--file-path", default=None)
    sched_rec.add_argument("--symbol", default=None)
    sched_rec.add_argument("--branch", default=None)
    sched_rec.add_argument("--error", default=None)
    sched_rec.add_argument("--task", default=None)
    sched_rec.add_argument("--project-root", default=None)
    sched_rec.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

    # ── Intent Route ────────────────────────────────────────────────────
    intent_parser = subparsers.add_parser("intent-route", aliases=["intent_route"],
        help="Route by coding intent (bugfix/refactor/migration etc).")
    intent_parser.add_argument("task", nargs="?")
    intent_parser.add_argument("--project-root", default=None)
    intent_parser.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

    # ── Capability Route ───────────────────────────────────────────────
    capability_parser = subparsers.add_parser("capability-route", aliases=["capability_route"],
        help="Classify input and select auxiliary local capability pipeline.")
    capability_parser.add_argument("input", nargs="?")
    capability_parser.add_argument("--file-path", default=None)
    capability_parser.add_argument("--project-root", default=None)
    capability_parser.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

    # ── Telemetry ───────────────────────────────────────────────────────
    telemetry_parser = subparsers.add_parser("telemetry", help="Show daemon telemetry and metrics.")
    telemetry_parser.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

    # ── Subsystem Health ────────────────────────────────────────────────
    health_parser = subparsers.add_parser("health", help="Check subsystem health (watchman, ramdisk, ollama).")
    health_parser.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

    # ── Diagnostics ────────────────────────────────────────────────────
    diag_parser = subparsers.add_parser("diagnostics", help="Collect compiler/linter diagnostics for files.")
    diag_parser.add_argument("files", nargs="*", default=[], help="Files to check")
    diag_parser.add_argument("--file-path", default=None, help="Single file to check")
    diag_parser.add_argument("--project-root", default=None)
    diag_parser.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

    # ── Impact Graph ───────────────────────────────────────────────────
    impact_parser = subparsers.add_parser("impact-graph", aliases=["impact_graph"],
        help="Build rename impact graph for safe refactors.")
    impact_parser.add_argument("symbol", help="Symbol to analyze")
    impact_parser.add_argument("--project-root", default=None)
    impact_parser.add_argument("--max-depth", type=int, default=3)
    impact_parser.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

    # ── Classify Operation ─────────────────────────────────────────────
    classify_parser = subparsers.add_parser("classify-op", aliases=["classify_op"],
        help="Classify changes into semantic operation types.")
    classify_parser.add_argument("--patch-file", help="Path to unified diff patch")
    classify_parser.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

    # ── Degradation Status ─────────────────────────────────────────────
    degrade_parser = subparsers.add_parser("degradation", help="Show subsystem degradation status.")
    degrade_parser.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

    # ── Warmup ─────────────────────────────────────────────────────────
    warmup_parser = subparsers.add_parser("warmup", help="Pre-warm all project caches.")
    warmup_parser.add_argument("--github-root", default=None)
    warmup_parser.add_argument("--extra-project", action="append", default=[])
    warmup_parser.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

    argv = sys.argv[1:]
    known_commands = {
        "analyze",
        "daemon",
        "doctor",
        "editor-context",
        "editor_context",
        "lsp",
        "confidence",
        "structural-diff",
        "structural_diff",
        "hierarchical-context",
        "hierarchical_context",
        "scheduler",
        "intent-route",
        "intent_route",
        "capability-route",
        "capability_route",
        "telemetry",
        "health",
        "diagnostics",
        "impact-graph",
        "impact_graph",
        "classify-op",
        "classify_op",
        "degradation",
        "warmup",
        "persist",
        "restore",
        "feedback",
        "feedback-summary",
        "feedback_summary",
        "rebuild-index",
        "rebuild_index",
        "ollama",
        "cache",
        "prompt-blocks",
        "prompt_blocks",
        "diff-summary",
        "diff_summary",
        "memory",
        "symbol",
        "deps",
        "route",
        "patch-plan",
        "patch_plan",
        "patch-apply",
        "patch_apply",
        "validate-files",
        "validate_files",
    }
    if not argv or argv[0] in {"-h", "--help", "help"}:
        parser.print_help()
        return 0

    if argv[0] in {"feedback_summary", "rebuild_index"}:
        argv = [argv[0].replace("_", "-"), *argv[1:]]
    if argv[0] == "patch_plan":
        argv = ["patch-plan", *argv[1:]]
    if argv[0] == "patch_apply":
        argv = ["patch-apply", *argv[1:]]
    if argv[0] == "validate_files":
        argv = ["validate-files", *argv[1:]]
    if argv[0] == "prompt_blocks":
        argv = ["prompt-blocks", *argv[1:]]
    if argv[0] == "diff_summary":
        argv = ["diff-summary", *argv[1:]]
    if argv[0] == "editor_context":
        argv = ["editor-context", *argv[1:]]
    if argv[0] == "structural_diff":
        argv = ["structural-diff", *argv[1:]]
    if argv[0] == "hierarchical_context":
        argv = ["hierarchical-context", *argv[1:]]
    if argv[0] == "intent_route":
        argv = ["intent-route", *argv[1:]]
    if argv[0] == "capability_route":
        argv = ["capability-route", *argv[1:]]
    if argv[0] == "impact_graph":
        argv = ["impact-graph", *argv[1:]]
    if argv[0] == "classify_op":
        argv = ["classify-op", *argv[1:]]

    def _try_daemon_proxy(method: str, params: dict) -> dict | None:
        """Try to proxy a request through the daemon. Returns None if daemon unavailable."""
        try:
            from .daemon import is_daemon_running, daemon_call
        except ImportError:
            from daemon import is_daemon_running, daemon_call
        if not is_daemon_running():
            return None
        result = daemon_call(method, params)
        if "error" in result:
            return None
        return result

    def _parse_analyze_args(values: list[str]) -> argparse.Namespace:
        args, extras = analyze_parser.parse_known_args(values)
        if any(token.startswith("-") for token in extras):
            analyze_parser.error(f"unrecognized arguments: {' '.join(extras)}")
        if extras:
            prompt_bits = [args.user_prompt] if getattr(args, "user_prompt", None) else []
            prompt_bits.extend(extras)
            args.user_prompt = " ".join(bit for bit in prompt_bits if bit)
        return args

    if argv[0] == "analyze":
        args = _parse_analyze_args(argv[1:])
        user_prompt = args.user_prompt
        if not user_prompt:
            parser.error("a user prompt is required")
        target_root = Path(args.project_root or Path.cwd()).resolve()
        output_format = args.format
        json_requested = bool(args.json)
        result = analyze_request(
            user_prompt,
            max_context_chars=args.max_context_chars,
            root=target_root,
            auto_update_kb=bool(args.auto_update_kb),
        )
        if result.get("mode") == "prompt_only" and result.get("prompt_fallback"):
            print("Ollama is unavailable. Paste the following prompt into GPT or Claude:\n")
            print(result["prompt_fallback"])
            return 0
        if output_format == "prompt":
            print(result["final_prompt"])
        elif json_requested or output_format == "json":
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(render_analyze_markdown(result))
        return 0

    if argv[0] == "feedback":
        args = feedback_parser.parse_args(argv[1:])
        target_root = Path(args.project_root or Path.cwd()).resolve()
        summary = record_feedback(
            user_prompt=args.user_prompt,
            detected_intent=args.intent,
            detected_features=args.features,
            accepted=bool(args.accepted),
            rating=args.rating,
            notes=args.notes,
            root=target_root,
        )
        if bool(args.json):
            print(json.dumps(summary, indent=2, ensure_ascii=False))
        else:
            print(render_markdown("Feedback Summary", summary))
        return 0

    if argv[0] == "feedback-summary":
        args = summary_parser.parse_args(argv[1:])
        target_root = Path(args.project_root or Path.cwd()).resolve()
        result = feedback_summary(root=target_root)
        if bool(args.json):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(render_markdown("Feedback Summary", result))
        return 0

    if argv[0] == "rebuild-index":
        args = rebuild_parser.parse_args(argv[1:])
        target_root = Path(args.project_root or Path.cwd()).resolve()
        result = rebuild_indexes(target_root)
        if bool(args.json):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(render_markdown("Rebuild Index", result))
        return 0

    if argv[0] == "cache":
        args = cache_parser.parse_args(argv[1:])
        if args.cache_command == "build":
            target_root = Path(args.project_root or Path.cwd()).resolve()
            result = _try_daemon_proxy("cache_build", {"project_root": str(target_root)})
            if result is None:
                result = build_cache(target_root)
        elif args.cache_command == "status":
            target_root = Path(args.project_root or Path.cwd()).resolve()
            result = _try_daemon_proxy("cache_status", {"project_root": str(target_root), "include_diff": True})
            if result is None:
                result = cache_status(target_root, include_diff=True)
        elif args.cache_command == "clean":
            target_root = Path(args.project_root or Path.cwd()).resolve()
            result = clean_cache(target_root)
        elif args.cache_command == "warm":
            target_root = Path(args.project_root or Path.cwd()).resolve()
            result = warm_project(target_root)
        elif args.cache_command == "watch":
            target_root = Path(args.project_root or Path.cwd()).resolve()
            result = watch_cache(target_root, interval=args.interval, once=bool(args.once), max_cycles=args.max_cycles)
            persist_interval = getattr(args, 'persist_interval', 0)
            if persist_interval > 0:
                import threading
                stop_event = threading.Event()
                from .cache_persistence import persist_on_interval
                persist_thread = threading.Thread(
                    target=lambda: persist_on_interval(target_root, persist_interval, stop_event),
                    daemon=True,
                )
                persist_thread.start()
        elif args.cache_command == "watch-all":
            result = watch_all_projects(
                github_root=Path(args.github_root).expanduser().resolve(),
                extra_roots=[Path(item).expanduser().resolve() for item in args.extra_project],
                interval=args.interval,
                once=bool(args.once),
            )
            persist_interval = getattr(args, 'persist_interval', 28800)
            if persist_interval > 0:
                import threading
                stop_event = threading.Event()
                from .cache_persistence import persist_on_interval as _persist_on_interval
                def _persist_loop():
                    import time
                    while not stop_event.is_set():
                        time.sleep(persist_interval)
                        try:
                            persist_all_projects(github_root=Path(args.github_root).expanduser().resolve())
                        except Exception:
                            pass
                persist_thread = threading.Thread(target=_persist_loop, daemon=True)
                persist_thread.start()
        elif args.cache_command == "persist":
            if getattr(args, 'all', False):
                result = _try_daemon_proxy("persist", {"all": True, "github_root": str(Path(args.github_root).expanduser().resolve())})
                if result is None:
                    result = persist_all_projects(github_root=Path(args.github_root).expanduser().resolve())
            else:
                target_root = Path(args.project_root or Path.cwd()).resolve()
                result = _try_daemon_proxy("persist", {"project_root": str(target_root)})
                if result is None:
                    result = persist_cache(target_root)
        elif args.cache_command == "restore":
            target_root = Path(args.project_root or Path.cwd()).resolve()
            result = _try_daemon_proxy("restore", {"project_root": str(target_root)})
            if result is None:
                result = restore_cache(target_root)
        elif args.cache_command == "persist-status":
            target_root = Path(args.project_root or Path.cwd()).resolve()
            result = _try_daemon_proxy("persist_status", {"project_root": str(target_root)})
            if result is None:
                result = cache_persist_status(target_root)
        else:
            cache_parser.error("missing cache command: build, status, clean, warm, watch, watch-all, persist, restore, or persist-status")
        if bool(args.json):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(render_markdown(f"Cache {args.cache_command.title()}", result))
        return 0

    if argv[0] == "prompt-blocks":
        args = blocks_parser.parse_args(argv[1:])
        target_root = Path(args.project_root or Path.cwd()).resolve()
        if args.blocks_command == "build":
            result = build_prompt_blocks(target_root)
        elif args.blocks_command == "show":
            result = _try_daemon_proxy("prompt_blocks", {"project_root": str(target_root)})
            if result is None:
                result = load_prompt_blocks(target_root)
        else:
            blocks_parser.error("missing prompt-blocks command: build or show")
        if bool(args.json):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(render_markdown("Prompt Blocks", result))
        return 0

    if argv[0] == "diff-summary":
        args = diff_parser.parse_args(argv[1:])
        target_root = Path(args.project_root or Path.cwd()).resolve()
        result = _try_daemon_proxy("diff_summary", {"project_root": str(target_root)})
        if result is None:
            result = semantic_diff_summary(target_root)
        if bool(args.json):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(render_markdown("Semantic Diff Summary", result))
        return 0

    if argv[0] == "memory":
        args = memory_parser.parse_args(argv[1:])
        target_root = Path(args.project_root or Path.cwd()).resolve()
        if args.memory_command == "add":
            result = remember(target_root, args.topic, args.note, tags=args.tags)
        elif args.memory_command == "recall":
            result = recall(target_root, args.query, limit=args.limit)
        else:
            memory_parser.error("missing memory command: add or recall")
        if bool(args.json):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(render_markdown("Working Memory", result))
        return 0

    if argv[0] == "symbol":
        args = symbol_parser.parse_args(argv[1:])
        target_root = Path(args.project_root or Path.cwd()).resolve()
        if args.symbol_command == "find":
            result = _try_daemon_proxy("symbol_find", {"query": args.query, "project_root": str(target_root), "limit": args.limit})
            if result is None:
                result = find_symbols(args.query, target_root, limit=args.limit)
        elif args.symbol_command == "context":
            result = _try_daemon_proxy("symbol_context", {"query": args.query, "project_root": str(target_root), "limit": args.limit})
            if result is None:
                result = symbol_context(args.query, target_root, limit=args.limit)
        else:
            symbol_parser.error("missing symbol command: find or context")
        if bool(args.json):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(render_markdown(f"Symbol {args.symbol_command.title()}", result))
        return 0

    if argv[0] == "deps":
        args = deps_parser.parse_args(argv[1:])
        target_root = Path(args.project_root or Path.cwd()).resolve()
        result = dependency_context(args.query, target_root, limit=args.limit)
        if bool(args.json):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(render_markdown("Dependency Context", result))
        return 0

    if argv[0] == "route":
        args = route_parser.parse_args(argv[1:])
        if not args.task:
            route_parser.error("a task is required")
        target_root = Path(args.project_root or Path.cwd()).resolve()
        # Try daemon proxy first
        result = _try_daemon_proxy("route", {"task": args.task, "project_root": str(target_root)})
        if result is None:
            result = route_task(args.task, project_root=target_root)
        if bool(args.json):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(render_markdown("aihelper Route", result))
        return 0

    if argv[0] == "patch-plan":
        args = patch_parser.parse_args(argv[1:])
        target_root = Path(args.project_root or Path.cwd()).resolve()
        result = build_patch_plan(args.task, args.files, target_root, style=args.style)
        if bool(args.json):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(render_markdown("Patch Plan", result))
        return 0

    if argv[0] == "patch-apply":
        args = patch_apply_parser.parse_args(argv[1:])
        target_root = Path(args.project_root or Path.cwd()).resolve()
        patch_text = Path(args.patch_file).expanduser().read_text(encoding="utf-8")
        result = apply_unified_patch(patch_text, target_root, dry_run=not bool(args.apply), validate=not bool(args.no_validate))
        if bool(args.json):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(render_markdown("Patch Apply", result))
        return 0

    if argv[0] == "validate-files":
        args = validate_parser.parse_args(argv[1:])
        target_root = Path(args.project_root or Path.cwd()).resolve()
        result = validate_files(args.files, target_root)
        if bool(args.json):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(render_markdown("Validate Files", result))
        return 0

    if argv[0] == "doctor":
        args = doctor_parser.parse_args(argv[1:])
        result = doctor()
        if bool(args.json):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            lines = ["# aihelper Doctor"]
            for name, info in result.items():
                if isinstance(info, dict):
                    st = info.get("status", "unknown")
                else:
                    st = str(info)
                icon = {"ok": "✅", "fail": "❌", "error": "⚠️"}.get(st, "❓")
                lines.append(f"- **{name}**: {icon} {st}")
                if isinstance(info, dict) and info.get("message"):
                    lines.append(f"  - _{info['message']}_")
            print("\n".join(lines))
        return 0

    if argv[0] == "ollama":
        args = ollama_parser.parse_args(argv[1:])
        if args.ollama_command == "health":
            result = ollama_health()
            if bool(args.json):
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print(render_markdown("Ollama Health", result))
            return 0
        if args.ollama_command == "prewarm":
            prompt = '{"ok": true, "task": "prewarm"}'
            output, ready = call_ollama(prompt, model_type=args.model_type)
            result = {
                "ready": ready,
                "model_type": args.model_type,
                "output_preview": output[:200] if isinstance(output, str) else "",
                "health": ollama_health(),
            }
            if bool(args.json):
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print(render_markdown("Ollama Prewarm", result))
            return 0
        ollama_parser.error("missing ollama command: health or prewarm")


    if argv[0] == "editor-context" or argv[0] == "editor_context":
        args = editor_ctx_parser.parse_args(argv[1:])
        target_root = Path(args.project_root or Path.cwd()).resolve()
        result = _try_daemon_proxy("editor_context", {"project_root": str(target_root)})
        if result is None:
            result = get_editor_context(target_root)
        if bool(args.json):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(render_markdown("Editor Context", result))
        return 0

    if argv[0] == "lsp":
        args = lsp_parser.parse_args(argv[1:])
        target_root = Path(args.project_root or Path.cwd()).resolve()
        if args.lsp_command == "definition":
            result = _try_daemon_proxy("lsp_definition", {
                "file_path": args.file_path, "line": args.line,
                "character": args.character, "project_root": str(target_root),
                "query": "",
            })
            if result is None:
                result = find_definition("", args.file_path, args.line, args.character, target_root)
        elif args.lsp_command == "references":
            result = _try_daemon_proxy("lsp_references", {
                "file_path": args.file_path, "line": args.line,
                "character": args.character, "project_root": str(target_root),
            })
            if result is None:
                result = find_all_references(args.file_path, args.line, args.character, target_root)
        elif args.lsp_command == "symbols":
            result = _try_daemon_proxy("lsp_symbols", {
                "file_path": args.file_path, "project_root": str(target_root),
            })
            if result is None:
                result = get_document_symbols(args.file_path, target_root)
        else:
            lsp_parser.error("missing lsp command: definition, references, or symbols")
        if bool(args.json):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(render_markdown("LSP", result))
        return 0

    if argv[0] == "confidence":
        args = conf_parser.parse_args(argv[1:])
        target_root = Path(args.project_root or Path.cwd()).resolve()
        # Read patch content
        patch_content = ""
        if args.patch_file:
            try:
                with open(args.patch_file) as f:
                    patch_content = f.read()
            except OSError:
                pass
        elif not __import__('sys').stdin.isatty():
            patch_content = __import__('sys').stdin.read()
        
        if not patch_content:
            conf_parser.error("no patch content provided (use --patch-file or pipe stdin)")
        
        result = _try_daemon_proxy("confidence", {
            "patch_content": patch_content, "files": args.files,
            "project_root": str(target_root),
        })
        if result is None:
            result = score_patch(patch_content, target_root, args.files)
        if bool(args.json):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(render_markdown("Confidence Score", result))
        return 0

    if argv[0] == "warmup":
        args = warmup_parser.parse_args(argv[1:])
        result = _try_daemon_proxy("warmup_status", {})
        if result is None:
            result = warm_all_projects(
                github_root=Path(args.github_root).expanduser().resolve(),
                extra_roots=[Path(item).expanduser().resolve() for item in args.extra_project],
            )
        if bool(args.json):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(render_markdown("Warmup", result))
        return 0

    if argv[0] == "structural-diff":
        args = sdiff_parser.parse_args(argv[1:])
        patch_text = ""
        if args.patch_file:
            try:
                with open(args.patch_file) as f:
                    patch_text = f.read()
            except OSError:
                pass
        elif not sys.stdin.isatty():
            patch_text = sys.stdin.read()
        if not patch_text:
            sdiff_parser.error("no patch provided (use --patch-file or pipe stdin)")
        result = _try_daemon_proxy("structural_diff", {"patch_text": patch_text})
        if result is None:
            from structural_diff import analyze_patch
            result = analyze_patch(patch_text)
        if bool(args.json):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(render_markdown("Structural Diff", result))
        return 0

    if argv[0] == "hierarchical-context":
        args = hctx_parser.parse_args(argv[1:])
        target_root = Path(args.project_root or Path.cwd()).resolve()
        result = _try_daemon_proxy("hierarchical_context", {
            "project_root": str(target_root),
            "focus_file": args.focus_file,
            "focus_symbol": args.focus_symbol,
            "expansion_level": args.level,
        })
        if result is None:
            from structural_diff import build_hierarchical_context
            result = build_hierarchical_context(target_root, args.focus_file, args.focus_symbol, args.level)
        if bool(args.json):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(render_markdown("Hierarchical Context", result))
        return 0

    if argv[0] == "scheduler":
        args = sched_parser.parse_args(argv[1:])
        if args.scheduler_command == "snapshot":
            result = _try_daemon_proxy("scheduler_snapshot", {})
            if result is None:
                from scheduler import get_scheduler
                result = get_scheduler().get_context_snapshot()
        elif args.scheduler_command == "predict":
            result = _try_daemon_proxy("scheduler_predict", {})
            if result is None:
                from scheduler import get_scheduler
                result = {"predictions": get_scheduler().predict_next_actions()}
        elif args.scheduler_command == "record":
            params = {"type": args.type}
            if args.file_path: params["file_path"] = args.file_path
            if args.symbol: params["symbol"] = args.symbol
            if args.branch: params["branch"] = args.branch
            if args.error: params["error"] = args.error
            if args.task: params["task"] = args.task
            if args.project_root: params["project_root"] = args.project_root
            result = _try_daemon_proxy("scheduler_record", params)
            if result is None:
                from scheduler import handle_scheduler_record
                result = handle_scheduler_record(params)
        else:
            sched_parser.error("missing scheduler command: snapshot, predict, or record")
        if bool(args.json):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(render_markdown("Scheduler", result))
        return 0

    if argv[0] == "intent-route":
        args = intent_parser.parse_args(argv[1:])
        if not args.task:
            intent_parser.error("a task is required")
        target_root = Path(args.project_root or Path.cwd()).resolve()
        result = _try_daemon_proxy("intent_route", {"task": args.task, "project_root": str(target_root)})
        if result is None:
            from intent_router import route_with_intent
            result = route_with_intent(args.task, str(target_root))
        if bool(args.json):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(render_markdown("Intent Route", result))
        return 0

    if argv[0] == "capability-route":
        args = capability_parser.parse_args(argv[1:])
        input_text = args.input or ""
        target_root = Path(args.project_root or Path.cwd()).resolve()
        result = _try_daemon_proxy("capability_route", {
            "input": input_text,
            "file_path": args.file_path,
            "project_root": str(target_root),
        })
        if result is None:
            from capability_router import select_pipeline
            result = select_pipeline(input_text, args.file_path)
        if bool(args.json):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(render_markdown("Capability Route", result))
        return 0

    if argv[0] == "telemetry":
        args = telemetry_parser.parse_args(argv[1:])
        result = _try_daemon_proxy("telemetry", {})
        if result is None:
            from telemetry import get_telemetry
            result = get_telemetry().get_snapshot()
        if bool(args.json):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(render_markdown("Telemetry", result))
        return 0

    if argv[0] == "health":
        args = health_parser.parse_args(argv[1:])
        result = _try_daemon_proxy("subsystem_health", {})
        if result is None:
            from subsystem_health import get_subsystem_manager
            mgr = get_subsystem_manager()
            for sub in mgr.subsystems.values():
                sub.check()
            result = mgr.health_report()
        if bool(args.json):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(render_markdown("Subsystem Health", result))
        return 0

    if argv[0] == "diagnostics":
        args = diag_parser.parse_args(argv[1:])
        target_root = Path(args.project_root or Path.cwd()).resolve()
        params = {"project_root": str(target_root)}
        if args.file_path:
            params["file_path"] = args.file_path
        if args.files:
            params["files"] = args.files
        result = _try_daemon_proxy("diagnostics", params)
        if result is None:
            from diagnostics import collect_diagnostics, collect_project_diagnostics
            if args.files:
                result = collect_project_diagnostics(target_root, args.files)
            elif args.file_path:
                result = collect_diagnostics(args.file_path, target_root)
            else:
                diag_parser.error("provide --file-path or files")
        if bool(args.json):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(render_markdown("Diagnostics", result))
        return 0

    if argv[0] == "impact-graph":
        args = impact_parser.parse_args(argv[1:])
        target_root = Path(args.project_root or Path.cwd()).resolve()
        result = _try_daemon_proxy("impact_graph", {
            "symbol": args.symbol, "project_root": str(target_root),
            "max_depth": args.max_depth,
        })
        if result is None:
            from impact_graph import build_impact_graph
            result = build_impact_graph(args.symbol, target_root, args.max_depth)
        if bool(args.json):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(render_markdown("Impact Graph", result))
        return 0

    if argv[0] == "classify-op":
        args = classify_parser.parse_args(argv[1:])
        patch_text = ""
        if args.patch_file:
            try:
                with open(args.patch_file) as f:
                    patch_text = f.read()
            except OSError:
                pass
        elif not sys.stdin.isatty():
            patch_text = sys.stdin.read()
        if not patch_text:
            classify_parser.error("no patch provided (use --patch-file or pipe stdin)")
        from structural_diff import _parse_diff_changes
        changes = _parse_diff_changes(patch_text)
        result = _try_daemon_proxy("classify_operation", {"changes": changes})
        if result is None:
            from impact_graph import classify_operation
            result = {"operation_type": classify_operation(changes), "change_count": len(changes)}
        if bool(args.json):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(render_markdown("Classify Operation", result))
        return 0

    if argv[0] == "degradation":
        args = degrade_parser.parse_args(argv[1:])
        result = _try_daemon_proxy("degradation_status", {})
        if result is None:
            from degradation import get_degradation_manager
            result = get_degradation_manager().status_report()
        if bool(args.json):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(render_markdown("Degradation Status", result))
        return 0

    if argv[0] == "daemon":
        args = daemon_parser.parse_args(argv[1:])
        if args.daemon_command == "start":
            result = start_daemon()
        elif args.daemon_command == "stop":
            result = stop_daemon()
        elif args.daemon_command == "status":
            result = daemon_status()
        elif args.daemon_command == "serve":
            run_daemon()
            return 0
        else:
            daemon_parser.error("missing daemon command: start, stop, or status")
        if bool(args.json):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(render_markdown("Daemon", result))
        return 0

    if argv[0] in known_commands:
        parser.error(f"unknown command: {argv[0]}")

    if len(argv) == 1 and not argv[0].startswith("-"):
        args = _parse_analyze_args(argv)
        target_root = Path(args.project_root or Path.cwd()).resolve()
        result = analyze_request(
            args.user_prompt,
            max_context_chars=args.max_context_chars,
            root=target_root,
            auto_update_kb=bool(args.auto_update_kb),
        )
        if result.get("mode") == "prompt_only" and result.get("prompt_fallback"):
            print("Ollama is unavailable. Paste the following prompt into GPT or Claude:\n")
            print(result["prompt_fallback"])
            return 0
        if args.format == "prompt":
            print(result["final_prompt"])
        elif bool(args.json) or args.format == "json":
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(render_analyze_markdown(result))
        return 0

    parser.error(f"unknown command: {argv[0]}")


if __name__ == "__main__":
    raise SystemExit(main())
