from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter
from typing import Any, Dict

try:
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
    cache_watch_parser.add_argument("--once", action="store_true")
    cache_watch_parser.add_argument("--max-cycles", type=int, default=0)
    cache_watch_parser.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)
    cache_watch_all_parser = cache_subparsers.add_parser("watch-all")
    cache_watch_all_parser.add_argument("--github-root", default="/Users/vietnguyen/github")
    cache_watch_all_parser.add_argument("--extra-project", action="append", default=[])
    cache_watch_all_parser.add_argument("--interval", type=float, default=2.0)
    cache_watch_all_parser.add_argument("--once", action="store_true")
    cache_watch_all_parser.add_argument("--json", "-json", action="store_true", default=False, help=argparse.SUPPRESS)

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

    argv = sys.argv[1:]
    known_commands = {
        "analyze",
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
            result = build_cache(target_root)
        elif args.cache_command == "status":
            target_root = Path(args.project_root or Path.cwd()).resolve()
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
        elif args.cache_command == "watch-all":
            result = watch_all_projects(
                github_root=Path(args.github_root).expanduser().resolve(),
                extra_roots=[Path(item).expanduser().resolve() for item in args.extra_project],
                interval=args.interval,
                once=bool(args.once),
            )
        else:
            cache_parser.error("missing cache command: build, status, clean, warm, watch, or watch-all")
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
            result = find_symbols(args.query, target_root, limit=args.limit)
        elif args.symbol_command == "context":
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
