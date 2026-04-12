from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter
from typing import Any, Dict

try:
    from .build_prompt import build_prompt, rewrite_prompt
    from .detect_feature import detect_feature_matches, detect_features
    from .discovery import discover_feature_from_codebase
    from .intent_detector import detect_intent
    from .ollama_fallback import build_discovery_prompt, build_manual_fallback_prompt, call_ollama, generate_with_ollama
    from .kb_updater import update_ai_kb
    from .learning import feedback_summary, record_feedback
    from .load_context import load_context_bundle
    from .rebuild_index import rebuild_indexes
except ImportError:
    from build_prompt import build_prompt, rewrite_prompt
    from detect_feature import detect_feature_matches, detect_features
    from discovery import discover_feature_from_codebase
    from intent_detector import detect_intent
    from ollama_fallback import build_discovery_prompt, build_manual_fallback_prompt, call_ollama, generate_with_ollama
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
    intent = detect_intent(user_prompt, root=root)
    detected_feature_names = detect_features(user_prompt, root=root)
    discovery_result = None
    kb_update = {"updated": False, "reason": "not_needed"}
    discovery_prompt = None
    prompt_fallback = None

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
                return result

        prompt_fallback = build_manual_fallback_prompt(user_prompt, root=root)
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
        return result

    feature_matches = detect_feature_matches(user_prompt, root=root, top_n=3)
    context = load_context_bundle(feature_matches, max_chars=max_context_chars, root=root)
    rewritten = rewrite_prompt(user_prompt, intent, feature_matches, context)
    final_prompt = build_prompt(user_prompt, context)

    try:
        from .planner import build_execution_plan
    except ImportError:
        from planner import build_execution_plan

    execution_steps = build_execution_plan(user_prompt, intent, feature_matches, context)
    return {
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

    argv = sys.argv[1:]
    known_commands = {"analyze", "feedback", "feedback-summary", "feedback_summary", "rebuild-index", "rebuild_index"}
    if not argv or argv[0] in {"-h", "--help", "help"}:
        parser.print_help()
        return 0

    if argv[0] in {"feedback_summary", "rebuild_index"}:
        argv = [argv[0].replace("_", "-"), *argv[1:]]

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
