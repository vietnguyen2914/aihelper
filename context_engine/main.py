from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter
from typing import Any, Dict

try:
    from .build_prompt import build_prompt, rewrite_prompt
    from .detect_feature import detect_feature_matches, detect_features
    from .discovery import discover_feature_from_codebase
    from .intent_detector import detect_intent
    from .ollama_fallback import build_discovery_prompt, build_manual_fallback_prompt, generate_with_ollama
    from .kb_updater import update_ai_kb
    from .learning import feedback_summary, record_feedback
    from .load_context import load_context_bundle
    from .rebuild_index import rebuild_indexes
except ImportError:
    from build_prompt import build_prompt, rewrite_prompt
    from detect_feature import detect_feature_matches, detect_features
    from discovery import discover_feature_from_codebase
    from intent_detector import detect_intent
    from ollama_fallback import build_discovery_prompt, build_manual_fallback_prompt, generate_with_ollama
    from kb_updater import update_ai_kb
    from learning import feedback_summary, record_feedback
    from load_context import load_context_bundle
    from rebuild_index import rebuild_indexes


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
        ollama_output, ollama_ready = generate_with_ollama(discovery_prompt)

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
    analyze_parser.add_argument("--format", choices=("json", "prompt"), default="json")

    feedback_parser = subparsers.add_parser("feedback", help="Record prompt quality feedback.")
    feedback_parser.add_argument("user_prompt", help="The original prompt.")
    feedback_parser.add_argument("--intent", required=True)
    feedback_parser.add_argument("--features", nargs="*", default=[])
    feedback_parser.add_argument("--accepted", action="store_true")
    feedback_parser.add_argument("--rating", type=int, default=0)
    feedback_parser.add_argument("--notes", default="")
    feedback_parser.add_argument("--project-root", default=None)

    summary_parser = subparsers.add_parser("feedback-summary", aliases=["feedback_summary"], help="Print feedback summary.")
    summary_parser.add_argument("--project-root", default=None)

    rebuild_parser = subparsers.add_parser(
        "rebuild-index",
        aliases=["rebuild_index"],
        help="Rebuild ai/index from ai/features and ai/flows.",
    )
    rebuild_parser.add_argument("--project-root", default=None)

    parser.add_argument("legacy_prompt", nargs="?", help=argparse.SUPPRESS)
    parser.add_argument("--project-root", dest="legacy_project_root", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--format", dest="legacy_format", choices=("json", "prompt"), default="json", help=argparse.SUPPRESS)
    parser.add_argument("--max-context-chars", dest="legacy_max_context_chars", type=int, default=12000, help=argparse.SUPPRESS)
    parser.add_argument("--auto-update-kb", dest="legacy_auto_update_kb", action="store_true", help=argparse.SUPPRESS)

    args = parser.parse_args()
    command = args.command or "analyze"

    if command == "analyze":
        user_prompt = getattr(args, "user_prompt", None) or args.legacy_prompt
        if not user_prompt:
            parser.error("a user prompt is required")
        target_root = Path((getattr(args, "project_root", None) or args.legacy_project_root) or Path.cwd()).resolve()
        output_format = getattr(args, "format", None) or args.legacy_format
        result = analyze_request(
            user_prompt,
            max_context_chars=getattr(args, "max_context_chars", None) or args.legacy_max_context_chars,
            root=target_root,
            auto_update_kb=bool(getattr(args, "auto_update_kb", False) or args.legacy_auto_update_kb),
        )
        if result.get("mode") == "prompt_only" and result.get("prompt_fallback"):
            print("Ollama is unavailable. Paste the following prompt into GPT or Claude:\n")
            print(result["prompt_fallback"])
            return 0
        if output_format == "prompt":
            print(result["final_prompt"])
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if command == "feedback":
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
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0

    if command == "rebuild-index":
        target_root = Path(args.project_root or Path.cwd()).resolve()
        print(json.dumps(rebuild_indexes(target_root), indent=2, ensure_ascii=False))
        return 0

    target_root = Path(args.project_root or Path.cwd()).resolve()
    print(json.dumps(feedback_summary(root=target_root), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
