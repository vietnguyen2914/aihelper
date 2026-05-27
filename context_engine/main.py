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
    max_context_chars: int = 6000,
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

    # Enforce token budget: if token_budget says max_context_tokens,
    # convert to chars (conservatively: 1 token ≈ 2.5 chars for code)
    budget = route.get("token_budget", {})
    max_tokens = budget.get("max_context_tokens", 6000)
    max_chars_budget = max_tokens * 4  # generous: 1 token ≈ 4 chars for Asian text
    if len(final_prompt) > max_chars_budget:
        # Rebuild prompt with tighter context limit
        tighter_limit = max(500, max_chars_budget - 1000)  # leave room for wrappers
        context = load_context_bundle(feature_matches, max_chars=tighter_limit, root=root)
        final_prompt = build_prompt(user_prompt, context, max_total_chars=max_chars_budget)

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

    Checks: daemon, local IPC endpoint, watchman, ollama, models, cache, ramdisk, permissions.
    """
    import os, platform, shutil, subprocess
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
    results["platform"] = {"status": "ok", "name": platform.system() or os.name}

    # ── Daemon check ────────────────────────────────────────────────
    status = daemon_status()
    endpoint_exists = bool(status.get("tcp_endpoint_exists") if status.get("transport") == "tcp" else status.get("socket_exists"))
    results["daemon_endpoint"] = {
        "status": "ok" if endpoint_exists else "fail",
        "transport": status.get("transport"),
        "socket": status.get("socket"),
        "tcp_endpoint": status.get("tcp_endpoint"),
    }
    results["daemon_health"] = {
        "status": "ok" if status.get("running") else "fail",
        "transport": status.get("transport"),
        "pid": status.get("pid"),
    }

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
        # Unix socket should be owner-only when present. Windows uses TCP loopback.
        sock_path = Path.home() / ".aihelper" / "aihelper.sock"
        if platform.system() != "Windows" and sock_path.exists():
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


def _handle_affected_cli(argv: list, parser: Any) -> int:
    """Handle 'aihelper affected' command (v0.0.7)."""
    import json as _json
    import sys as _sys
    from pathlib import Path as _Path

    args = parser.parse_args(argv[1:])
    root = _Path(args.project_root).resolve() if args.project_root else _Path.cwd()

    files = list(args.files)
    if args.stdin and not _sys.stdin.isatty():
        stdin_files = _sys.stdin.read().strip().splitlines()
        files.extend(f for f in stdin_files if f.strip())

    if not files:
        print("Error: No files provided. Use: aihelper affected file1.py file2.py", file=_sys.stderr)
        return 1

    try:
        from .affected import find_affected_tests
    except ImportError:
        from affected import find_affected_tests
    result = find_affected_tests(files, root, max_depth=args.depth, test_filter=args.filter)

    if args.json:
        print(_json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("## Affected Tests\n")
        extra = f" +{len(files) - 5} more" if len(files) > 5 else ""
        print(f"Changed: {', '.join(files[:5])}{extra}")
        print(f"Affected tests: {result['affected_count']}")
        if result.get('affected_tests'):
            for t in result['affected_tests'][:20]:
                print(f"  - {t}")
            if result['affected_count'] > 20:
                print(f"  ... and {result['affected_count'] - 20} more")
        print(f"\n{result.get('recommendation', '')}")
    return 0


def _handle_upgrade(argv: list, parser: Any) -> int:
    """Auto-upgrade all visible projects (v0.0.7).

    For each project under ~/github (or --extra-project):
    1. Run cache build (which auto-syncs to SQLite)
    2. Verify SQLite graph was created
    3. Report results
    """
    import json as _json
    from pathlib import Path as _Path

    # Resolve project roots
    try:
        from .cache import discover_project_roots, build_cache, cache_status
        from .graph_db import get_db
    except ImportError:
        from cache import discover_project_roots, build_cache, cache_status
        from graph_db import get_db

    github_root = _Path.home() / "github"
    extra_roots = []
    for i, arg in enumerate(argv[1:], 1):
        if arg == "--github-root" and i < len(argv) - 1:
            github_root = _Path(argv[i + 1]).expanduser().resolve()
        elif arg == "--extra-project" and i < len(argv) - 1:
            extra_roots.append(_Path(argv[i + 1]).expanduser().resolve())

    is_json = "--json" in argv or "-json" in argv
    roots = discover_project_roots(github_root=github_root, extra_roots=extra_roots)

    results = {"version": "0.0.7", "projects_scanned": len(roots), "projects": []}
    for root in roots:
        r = {"project": str(root), "status": "skipped"}
        try:
            status = cache_status(root)
            r["had_cache"] = status.get("fresh", False)
            # Rebuild cache (this triggers SQLite sync)
            build_cache(root)
            # Verify SQLite
            db = get_db(root)
            stats = db.get_stats()
            r["status"] = "upgraded"
            r["symbols"] = stats.get("symbol_count", 0)
            r["edges"] = stats.get("edge_count", 0)
            r["sqlite_mb"] = stats.get("db_size_mb", 0)
        except Exception as exc:
            r["status"] = f"error: {exc}"
        results["projects"].append(r)

    upgraded = sum(1 for p in results["projects"] if p["status"] == "upgraded")
    results["upgraded_count"] = upgraded

    if is_json:
        print(_json.dumps(results, indent=2, ensure_ascii=False))
    else:
        print(f"## aihelper v0.0.7 Upgrade\n")
        print(f"Scanned {len(roots)} projects, upgraded {upgraded}\n")
        for p in results["projects"]:
            status = p["status"]
            marker = "✅" if status == "upgraded" else "⚠️"
            detail = ""
            if status == "upgraded":
                detail = f" ({p.get('symbols', 0)} symbols, {p.get('edges', 0)} edges, {p.get('sqlite_mb', 0)}MB SQLite)"
            print(f"{marker} {p['project']}{detail}")
        print(f"\nSQLite knowledge graph is now active in all upgraded projects.")
        print(f"Try: `aihelper graph status` or `aihelper graph callers --symbol main`")
    return 0


def _handle_graph(argv: list, graph_parser: Any) -> int:
    """Handle graph query subcommands (v0.0.7)."""
    import json as _json
    from pathlib import Path as _Path

    try:
        from .graph_query import (
            handle_callers, handle_callees, handle_trace,
            handle_impact, handle_explore
        )
        from .graph_db import get_db
    except ImportError:
        from graph_query import (
            handle_callers, handle_callees, handle_trace,
            handle_impact, handle_explore
        )
        from graph_db import get_db

    args = graph_parser.parse_args(argv[1:])
    cmd = getattr(args, 'graph_command', None)
    root = _Path(args.project_root).resolve() if args.project_root else _Path.cwd()

    if cmd == "status":
        db = get_db(root)
        result = db.get_stats()
    elif cmd == "callers":
        if not args.symbol:
            print("Error: --symbol required for callers", file=__import__('sys').stderr)
            return 1
        result = handle_callers({"symbol": args.symbol, "depth": args.depth or 1}, root)
    elif cmd == "callees":
        if not args.symbol:
            print("Error: --symbol required for callees", file=__import__('sys').stderr)
            return 1
        result = handle_callees({"symbol": args.symbol, "depth": args.depth or 1}, root)
    elif cmd == "trace":
        if not args.from_sym or not args.to_sym:
            print("Error: --from AND --to required for trace", file=__import__('sys').stderr)
            return 1
        result = handle_trace({"from": args.from_sym, "to": args.to_sym}, root)
    elif cmd == "impact":
        if not args.symbol:
            print("Error: --symbol required for impact", file=__import__('sys').stderr)
            return 1
        result = handle_impact({"symbol": args.symbol, "depth": args.depth or 3}, root)
    elif cmd == "explore":
        if not args.query:
            print("Error: --query required for explore", file=__import__('sys').stderr)
            return 1
        result = handle_explore({"query": args.query, "max_files": args.max_files}, root)
    else:
        print(f"Unknown graph command: {cmd}", file=__import__('sys').stderr)
        return 1

    if bool(getattr(args, 'json', False)):
        print(_json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(_json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Portable AI helper that reads the current project's ai indexes and returns feature-aware execution context."
    )
    subparsers = parser.add_subparsers(dest="command")

    analyze_parser = subparsers.add_parser("analyze", help="Analyze a raw prompt.")
    analyze_parser.add_argument("user_prompt", nargs="?", help="The raw user request to analyze.")
    analyze_parser.add_argument("--max-context-chars", type=int, default=6000)
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

    # ── Workflow Runtime Engine (v0.0.9) ─────────────────────────
    workflow_parser = subparsers.add_parser("workflow", help="Execute deterministic engineering workflows.")
    workflow_subparsers = workflow_parser.add_subparsers(dest="workflow_command")
    workflow_run = workflow_subparsers.add_parser("run", help="Run a named workflow.")
    workflow_run.add_argument("name", help="Workflow name (tdd, diagnose, release-check, architecture-review, refactor-safety)")
    workflow_run.add_argument("--target", help="Target file or symbol")
    workflow_run.add_argument("--error", help="Error description for diagnose workflow")
    workflow_run.add_argument("--params", default="{}", help="JSON params for the workflow")
    workflow_run.add_argument("--project-root", default=None)
    workflow_run.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)
    workflow_list = workflow_subparsers.add_parser("list", help="List available workflows.")
    workflow_list.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

    # ── Verification Runtime (v0.0.9) ───────────────────────────
    verify_parser = subparsers.add_parser("verify", help="Run deterministic verification checks.")
    verify_parser.add_argument("check", nargs="?", help="Check name: architecture, auth-safety, regression-risk, dependency-health")
    verify_parser.add_argument("--target", help="Target symbol for regression-risk check")
    verify_parser.add_argument("--project-root", default=None)
    verify_parser.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

    # ── Context Compressor (v0.0.9) ─────────────────────────────
    compress_parser = subparsers.add_parser("compress", help="Build distilled cognition package for frontier models.")
    compress_parser.add_argument("question", nargs="?", help="The question for the frontier model")
    compress_parser.add_argument("--target", help="Target symbol or module")
    compress_parser.add_argument("--project-root", default=None)
    compress_parser.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

    # ── Tier Router (v0.0.9) ────────────────────────────────────
    tier_parser = subparsers.add_parser("tier-route", aliases=["tier_route"],
        help="Classify a task into the correct execution tier.")
    tier_parser.add_argument("task", nargs="?", help="Task to classify")
    tier_parser.add_argument("--project-root", default=None)
    tier_parser.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

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

    # ── Knowledge Engine ───────────────────────────────────────────────
    knowledge_parser = subparsers.add_parser("knowledge", help="Manage persistent engineering knowledge: decisions, debug history, preferences.")
    knowledge_subparsers = knowledge_parser.add_subparsers(dest="knowledge_command")
    # add-decision
    k_add_dec = knowledge_subparsers.add_parser("add-decision", help="Record an architectural decision.")
    k_add_dec.add_argument("id", help="Unique decision identifier (e.g. auth-provider)")
    k_add_dec.add_argument("--choice", required=True, help="The chosen approach")
    k_add_dec.add_argument("--reason", default="", help="Why this choice was made")
    k_add_dec.add_argument("--alternatives", nargs="*", default=[], help="Rejected alternatives")
    k_add_dec.add_argument("--files", nargs="*", default=[], help="Related files")
    k_add_dec.add_argument("--project-root", default=None)
    k_add_dec.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)
    # add-debug
    k_add_dbg = knowledge_subparsers.add_parser("add-debug", help="Record a debugging outcome.")
    k_add_dbg.add_argument("--symptom", required=True, help="What went wrong")
    k_add_dbg.add_argument("--root-cause", default="", help="The underlying cause")
    k_add_dbg.add_argument("--fix-commit", default="", help="Commit that fixed it")
    k_add_dbg.add_argument("--modules", nargs="*", default=[], help="Affected modules")
    k_add_dbg.add_argument("--project-root", default=None)
    k_add_dbg.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)
    # set-preference
    k_set_pref = knowledge_subparsers.add_parser("set-preference", help="Store a developer preference.")
    k_set_pref.add_argument("key", help="Preference name (e.g. package_manager)")
    k_set_pref.add_argument("value", help="Preference value (e.g. pnpm)")
    k_set_pref.add_argument("--category", default="", help="Category: backend, frontend, infra, general")
    k_set_pref.add_argument("--project-root", default=None)
    k_set_pref.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)
    # recall
    k_recall = knowledge_subparsers.add_parser("recall", help="Search stored knowledge.")
    k_recall.add_argument("query", nargs="?", default="", help="Search term")
    k_recall.add_argument("--limit", type=int, default=10)
    k_recall.add_argument("--project-root", default=None)
    k_recall.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)
    # dispatch
    k_dispatch = knowledge_subparsers.add_parser("dispatch", help="Dispatch knowledge to all editor configs.")
    k_dispatch.add_argument("--project-root", default=None)
    k_dispatch.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)
    # list
    k_list = knowledge_subparsers.add_parser("list", help="List all knowledge of a type.")
    k_list.add_argument("--type", dest="list_type", choices=("decisions", "debugs", "preferences"), default="decisions")
    k_list.add_argument("--project-root", default=None)
    k_list.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

    # ── Graph Query Tools (v0.0.7) ────────────────────────────────────
    graph_parser = subparsers.add_parser("graph", help="SQLite knowledge graph queries.")
    graph_sub = graph_parser.add_subparsers(dest="graph_command")
    for cmd in ("callers", "callees", "trace", "impact", "explore", "status"):
        sp = graph_sub.add_parser(cmd)
        sp.add_argument("--symbol", default=None)
        sp.add_argument("--from", dest="from_sym", default=None)
        sp.add_argument("--to", dest="to_sym", default=None)
        sp.add_argument("--query", default=None)
        sp.add_argument("--depth", type=int, default=None)
        sp.add_argument("--max-files", type=int, default=8)
        sp.add_argument("--project-root", default=None)
        sp.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

    # ── Upgrade (v0.0.7) ──────────────────────────────────────────────
    upgrade_parser = subparsers.add_parser("upgrade", help="Auto-upgrade all visible projects to latest aihelper version.")
    upgrade_parser.add_argument("--github-root", default="$HOME/github")
    upgrade_parser.add_argument("--extra-project", action="append", default=[])
    upgrade_parser.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

    # ── Affected (v0.0.7) ────────────────────────────────────────────
    affected_parser = subparsers.add_parser("affected", help="Find test files affected by changed source files.")
    affected_parser.add_argument("files", nargs="*", default=[], help="Changed source files")
    affected_parser.add_argument("--stdin", action="store_true", help="Read file list from stdin")
    affected_parser.add_argument("-d", "--depth", type=int, default=5, help="Max dependency traversal depth")
    affected_parser.add_argument("-f", "--filter", help="Custom glob to identify test files")
    affected_parser.add_argument("--project-root", default=None)
    affected_parser.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

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
        "knowledge",
        "graph",
        "upgrade",
        "affected",
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
        "workflow",
        "verify",
        "compress",
        "tier-route",
        "tier_route",
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
                github_root=Path(args.github_root).expanduser().resolve() if args.github_root else Path.home() / "github",
                extra_roots=[Path(item).expanduser().resolve() for item in args.extra_project],
            )
        if bool(args.json):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(render_markdown("Warmup", result))
        return 0

    if argv[0] == "knowledge":
        args = knowledge_parser.parse_args(argv[1:])
        target_root = Path(args.project_root or Path.cwd()).resolve() if hasattr(args, 'project_root') else Path.cwd()
        
        if args.knowledge_command == "add-decision":
            result = _try_daemon_proxy("knowledge_add_decision", {
                "id": args.id, "choice": args.choice, "reason": args.reason,
                "alternatives": args.alternatives, "files": args.files,
                "project_root": str(target_root),
            })
            if result is None:
                from .memory_engine import add_decision
                result = add_decision(args.id, args.choice, args.reason, args.alternatives, args.files, project_root=target_root)
        elif args.knowledge_command == "add-debug":
            result = _try_daemon_proxy("knowledge_add_debug", {
                "symptom": args.symptom, "root_cause": args.root_cause,
                "fix_commit": args.fix_commit, "affected_modules": args.modules,
                "project_root": str(target_root),
            })
            if result is None:
                from .memory_engine import add_debug_entry
                result = add_debug_entry(args.symptom, args.root_cause, args.fix_commit, args.modules, project_root=target_root)
        elif args.knowledge_command == "set-preference":
            result = _try_daemon_proxy("knowledge_set_preference", {
                "key": args.key, "value": args.value, "category": args.category,
                "project_root": str(target_root),
            })
            if result is None:
                from .memory_engine import set_preference
                result = set_preference(args.key, args.value, args.category, project_root=target_root)
        elif args.knowledge_command == "recall":
            query = getattr(args, 'query', '')
            result = _try_daemon_proxy("knowledge_recall", {
                "query": query, "limit": args.limit, "project_root": str(target_root),
            })
            if result is None:
                from .memory_engine import search_knowledge, get_all_knowledge
                if query:
                    result = search_knowledge(query, project_root=target_root, limit=args.limit)
                else:
                    result = get_all_knowledge(project_root=target_root)
        elif args.knowledge_command == "dispatch":
            result = _try_daemon_proxy("knowledge_dispatch", {"project_root": str(target_root)})
            if result is None:
                from .knowledge_dispatcher import dispatch_knowledge
                result = dispatch_knowledge(project_root=target_root)
        elif args.knowledge_command == "list":
            from .memory_engine import list_decisions, list_debugs, all_preferences_detail
            if args.list_type == "decisions":
                result = {"decisions": list_decisions(project_root=target_root)}
            elif args.list_type == "debugs":
                result = {"debugs": list_debugs(project_root=target_root)}
            else:
                result = {"preferences": all_preferences_detail(project_root=target_root)}
        else:
            knowledge_parser.error("missing knowledge command: add-decision, add-debug, set-preference, recall, dispatch, or list")
        
        if bool(args.json):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(render_markdown("Knowledge", result))
        return 0

    if argv[0] == "upgrade":
        return _handle_upgrade(argv, upgrade_parser)

    if argv[0] == "affected":
        return _handle_affected_cli(argv, affected_parser)

    if argv[0] == "graph":
        return _handle_graph(argv, graph_parser)

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

    if argv[0] == "workflow":
        args = workflow_parser.parse_args(argv[1:])
        if args.workflow_command == "list":
            target_root = Path(args.project_root or Path.cwd()).resolve()
            result = _try_daemon_proxy("workflow_run", {"name": "list", "project_root": str(target_root)})
            if result is None:
                from .workflow_engine import WorkflowEngine
                result = {"workflows": WorkflowEngine(target_root).list_workflows()}
        elif args.workflow_command == "run":
            target_root = Path(args.project_root or Path.cwd()).resolve()
            params = json.loads(args.params) if args.params else {}
            if args.target:
                params["target"] = args.target
            if args.error:
                params["error"] = args.error
            result = _try_daemon_proxy("workflow_run", {"name": args.name, "params": params, "project_root": str(target_root)})
            if result is None:
                from .workflow_engine import WorkflowEngine
                wf_result = WorkflowEngine(target_root).run(args.name, params)
                result = {
                    "workflow": wf_result.workflow,
                    "success": wf_result.success,
                    "phases": len(wf_result.phases),
                    "total_tokens": wf_result.total_tokens,
                    "total_duration_ms": wf_result.total_duration_ms,
                    "ai_calls": wf_result.ai_calls,
                    "deterministic_steps": wf_result.deterministic_steps,
                    "summary": wf_result.summary,
                }
        else:
            workflow_parser.error("missing workflow command: run or list")
        if bool(args.json):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(render_markdown("Workflow", result))
        return 0

    if argv[0] == "verify":
        args = verify_parser.parse_args(argv[1:])
        target_root = Path(args.project_root or Path.cwd()).resolve()
        if not args.check:
            verify_parser.error("a check name is required (architecture, auth-safety, regression-risk, dependency-health)")
        result = _try_daemon_proxy("verify", {"check": args.check, "target": args.target or "", "project_root": str(target_root)})
        if result is None:
            from .verify import handle_verify
            result = handle_verify({"check": args.check, "target": args.target or "", "project_root": str(target_root)})
        if bool(args.json):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(render_markdown("Verify", result))
        return 0

    if argv[0] == "compress":
        args = compress_parser.parse_args(argv[1:])
        target_root = Path(args.project_root or Path.cwd()).resolve()
        result = _try_daemon_proxy("compress_context", {"question": args.question or "", "target": args.target or "", "project_root": str(target_root)})
        if result is None:
            from .compressor import handle_compress_context
            result = handle_compress_context({"question": args.question or "", "target": args.target or "", "project_root": str(target_root)})
        if bool(args.json):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(render_markdown("Compressed Context", result))
        return 0

    if argv[0] in ("tier-route", "tier_route"):
        args = tier_parser.parse_args(argv[1:])
        target_root = Path(args.project_root or Path.cwd()).resolve()
        result = _try_daemon_proxy("tier_route", {"task": args.task or "", "project_root": str(target_root)})
        if result is None:
            from .tier_router import handle_tier_route
            result = handle_tier_route({"task": args.task or "", "project_root": str(target_root)})
        if bool(args.json):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(render_markdown("Tier Route", result))
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
