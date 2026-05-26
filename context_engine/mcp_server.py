from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

try:
    from .cache import cache_status
    from .daemon import daemon_call, is_daemon_running
    from .main import analyze_request
    from .patch_engine import build_patch_plan
    from .prompt_blocks import build_prompt_blocks, load_prompt_blocks
    from .router import route_task
    from .semantic_diff import semantic_diff_summary
    from .symbols import symbol_context
    from .working_memory import recall
    from .capability_router import select_pipeline
except ImportError:
    from cache import cache_status
    from daemon import daemon_call, is_daemon_running
    from main import analyze_request
    from patch_engine import build_patch_plan
    from prompt_blocks import build_prompt_blocks, load_prompt_blocks
    from router import route_task
    from semantic_diff import semantic_diff_summary
    from symbols import symbol_context
    from working_memory import recall
    from capability_router import select_pipeline


SERVER_INFO = {
    "name": "aihelper",
    "version": "1.0.0",
}


def _response(message_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "result": result}


def _error(message_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}}


def _context_tool_schema() -> Dict[str, Any]:
    return {
        "name": "aihelper_context",
        "description": (
            "Build a compact feature-aware prompt from a target repository's ai/ indexes. "
            "Use before broad code inspection to reduce token use."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The coding, analysis, or documentation task to contextualize.",
                },
                "project_root": {
                    "type": "string",
                    "description": "Target repository root. Defaults to the current working directory.",
                },
                "max_context_chars": {
                    "type": "integer",
                    "description": "Maximum JSON context size to include.",
                    "default": 6000,
                },
                "format": {
                    "type": "string",
                    "enum": ["prompt", "json"],
                    "default": "prompt",
                },
            },
            "required": ["task"],
        },
    }


def _symbol_tool_schema() -> Dict[str, Any]:
    return {
        "name": "aihelper_symbol_lookup",
        "description": "Find symbol definitions and nearby import/dependency context from the local aihelper cache.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Symbol, class, function, method, or file hint to look up."},
                "project_root": {"type": "string", "description": "Target repository root. Defaults to current working directory."},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
    }


def _cache_status_tool_schema() -> Dict[str, Any]:
    return {
        "name": "aihelper_cache_status",
        "description": "Inspect whether the target repository has a fresh aihelper persistent cache.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_root": {"type": "string", "description": "Target repository root. Defaults to current working directory."}
            },
        },
    }


def _route_tool_schema() -> Dict[str, Any]:
    return {
        "name": "aihelper_route",
        "description": "Route a task to the smallest useful set of tools and target symbols before broad file reads.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "The coding, analysis, or verification task."},
                "project_root": {"type": "string", "description": "Target repository root. Defaults to current working directory."},
            },
            "required": ["task"],
        },
    }


def _patch_tool_schema() -> Dict[str, Any]:
    return {
        "name": "aihelper_patch_plan",
        "description": "Create a proposal-only patch template for exact target files. Does not modify files.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "The change to make."},
                "files": {"type": "array", "items": {"type": "string"}, "description": "Exact relative files to patch."},
                "project_root": {"type": "string", "description": "Target repository root. Defaults to current working directory."},
                "style": {"type": "string", "enum": ["unified", "search-replace"], "default": "unified"},
            },
            "required": ["task"],
        },
    }


def _prompt_blocks_tool_schema() -> Dict[str, Any]:
    return {
        "name": "aihelper_prompt_blocks",
        "description": "Build or load precompiled prompt blocks such as architecture, DB, symbol, and recent git summaries.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_root": {"type": "string", "description": "Target repository root. Defaults to current working directory."},
                "build": {"type": "boolean", "default": False},
            },
        },
    }


def _diff_tool_schema() -> Dict[str, Any]:
    return {
        "name": "aihelper_diff_summary",
        "description": "Generate a compact semantic summary of current git diff without returning full source patches.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_root": {"type": "string", "description": "Target repository root. Defaults to current working directory."}
            },
        },
    }


def _memory_tool_schema() -> Dict[str, Any]:
    return {
        "name": "aihelper_memory_recall",
        "description": "Recall lightweight local working memory for the target repository.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "default": ""},
                "project_root": {"type": "string", "description": "Target repository root. Defaults to current working directory."},
                "limit": {"type": "integer", "default": 10},
            },
        },
    }


def _capability_route_tool_schema() -> Dict[str, Any]:
    return {
        "name": "aihelper_capability_route",
        "description": "Classify an input and select a local capability pipeline before sending work to cloud models.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input": {"type": "string", "description": "Prompt, stack trace, diff header, or content hint to classify."},
                "file_path": {"type": "string", "description": "Optional file path for extension-based routing."},
                "project_root": {"type": "string", "description": "Target repository root. Defaults to current working directory."},
            },
        },
    }


def _callers_tool_schema() -> Dict[str, Any]:
    return {
        "name": "aihelper_callers",
        "description": "Find all symbols that call a specific function/method. Returns file:line for each caller. Multi-depth BFS via SQLite call graph.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Name of the function or method to find callers for"},
                "depth": {"type": "integer", "description": "How many levels of callers (default: 1)", "default": 1},
                "project_root": {"type": "string", "description": "Target repository root"},
            },
            "required": ["symbol"],
        },
    }


def _callees_tool_schema() -> Dict[str, Any]:
    return {
        "name": "aihelper_callees",
        "description": "Find all symbols called by a specific function/method. Uses SQLite call graph.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Name of the function or method"},
                "depth": {"type": "integer", "description": "How many levels of callees (default: 1)", "default": 1},
                "project_root": {"type": "string", "description": "Target repository root"},
            },
            "required": ["symbol"],
        },
    }


def _trace_tool_schema() -> Dict[str, Any]:
    return {
        "name": "aihelper_trace",
        "description": "Trace the call path between two symbols — 'how does X reach Y?'. BFS shortest path on call graph. Returns chain of function calls connecting them.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "from": {"type": "string", "description": "Starting symbol name"},
                "to": {"type": "string", "description": "Target symbol name"},
                "project_root": {"type": "string", "description": "Target repository root"},
            },
            "required": ["from", "to"],
        },
    }


def _impact_tool_schema() -> Dict[str, Any]:
    return {
        "name": "aihelper_impact",
        "description": "Analyze the impact radius of changing a symbol. Shows transitive callers and affected files via SQLite BFS.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Name of the symbol to analyze"},
                "depth": {"type": "integer", "description": "How many levels to traverse (default: 3)", "default": 3},
                "project_root": {"type": "string", "description": "Target repository root"},
            },
            "required": ["symbol"],
        },
    }


def _explore_tool_schema() -> Dict[str, Any]:
    return {
        "name": "aihelper_explore",
        "description": "Return source code for multiple related symbols in one call. Groups symbols by file, reads contiguous code sections with line numbers. Replaces multiple Read calls.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Symbol names or keywords (space-separated)"},
                "max_files": {"type": "integer", "description": "Max files to show source for (default: 8)", "default": 8},
                "project_root": {"type": "string", "description": "Target repository root"},
            },
            "required": ["query"],
        },
    }


def _graph_status_tool_schema() -> Dict[str, Any]:
    return {
        "name": "aihelper_graph_status",
        "description": "Get SQLite knowledge graph statistics: symbol count, edge count, nodes by kind, files by language, journal mode.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_root": {"type": "string", "description": "Target repository root"},
            },
        },
    }


def _tool_schemas() -> list[Dict[str, Any]]:
    return [
        _context_tool_schema(),
        _symbol_tool_schema(),
        _cache_status_tool_schema(),
        _route_tool_schema(),
        _patch_tool_schema(),
        _prompt_blocks_tool_schema(),
        _diff_tool_schema(),
        _memory_tool_schema(),
        _capability_route_tool_schema(),
        _callers_tool_schema(),
        _callees_tool_schema(),
        _trace_tool_schema(),
        _impact_tool_schema(),
        _explore_tool_schema(),
        _graph_status_tool_schema(),
    ]


def _target_root(arguments: Dict[str, Any]) -> Path:
    project_root = arguments.get("project_root")
    return Path(project_root).expanduser().resolve() if isinstance(project_root, str) and project_root.strip() else Path.cwd()


def _call_context(arguments: Dict[str, Any]) -> Dict[str, Any]:
    task = str(arguments.get("task", "")).strip()
    if not task:
        raise ValueError("task is required")

    root = _target_root(arguments)
    max_context_chars = int(arguments.get("max_context_chars") or 6000)
    output_format = str(arguments.get("format") or "prompt")

    result = analyze_request(task, max_context_chars=max_context_chars, root=root)
    text = result["final_prompt"] if output_format == "prompt" else json.dumps(result, indent=2, ensure_ascii=False)
    return {"content": [{"type": "text", "text": text}]}


def _json_content(data: Dict[str, Any]) -> Dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(data, indent=2, ensure_ascii=False)}]}


def _daemon_result(method: str, arguments: Dict[str, Any]) -> Dict[str, Any] | None:
    try:
        if not is_daemon_running():
            return None
        result = daemon_call(method, arguments)
    except Exception:
        return None
    if isinstance(result, dict) and result.get("error"):
        return None
    return result if isinstance(result, dict) else None


def _call_graph_tool(daemon_method: str, mode: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    from .graph_query import handle_callers, handle_callees, handle_trace, handle_impact, handle_explore
    handlers = {"callers": handle_callers, "callees": handle_callees, "trace": handle_trace, "impact": handle_impact, "explore": handle_explore}
    daemon_data = _daemon_result(daemon_method, {"arguments": arguments, "project_root": str(_target_root(arguments))})
    if daemon_data:
        return _json_content(daemon_data)
    return _json_content(handlers[mode](arguments, _target_root(arguments)))


def _call_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    if name == "aihelper_context":
        return _call_context(arguments)
    if name == "aihelper_symbol_lookup":
        query = str(arguments.get("query", "")).strip()
        if not query:
            raise ValueError("query is required")
        daemon_data = _daemon_result(
            "symbol_context",
            {"query": query, "project_root": str(_target_root(arguments)), "limit": int(arguments.get("limit") or 10)},
        )
        return _json_content(daemon_data or symbol_context(query, _target_root(arguments), limit=int(arguments.get("limit") or 10)))
    if name == "aihelper_cache_status":
        daemon_data = _daemon_result("cache_status", {"project_root": str(_target_root(arguments))})
        return _json_content(daemon_data or cache_status(_target_root(arguments)))
    if name == "aihelper_route":
        task = str(arguments.get("task", "")).strip()
        if not task:
            raise ValueError("task is required")
        daemon_data = _daemon_result("route", {"task": task, "project_root": str(_target_root(arguments))})
        return _json_content(daemon_data or route_task(task, project_root=_target_root(arguments)))
    if name == "aihelper_patch_plan":
        task = str(arguments.get("task", "")).strip()
        if not task:
            raise ValueError("task is required")
        files = arguments.get("files") if isinstance(arguments.get("files"), list) else []
        style = str(arguments.get("style") or "unified")
        return _json_content(build_patch_plan(task, [str(item) for item in files], _target_root(arguments), style=style))
    if name == "aihelper_prompt_blocks":
        root = _target_root(arguments)
        daemon_data = None if bool(arguments.get("build")) else _daemon_result("prompt_blocks", {"project_root": str(root)})
        data = daemon_data or (build_prompt_blocks(root) if bool(arguments.get("build")) else load_prompt_blocks(root))
        return _json_content(data)
    if name == "aihelper_diff_summary":
        daemon_data = _daemon_result("diff_summary", {"project_root": str(_target_root(arguments))})
        return _json_content(daemon_data or semantic_diff_summary(_target_root(arguments)))
    if name == "aihelper_memory_recall":
        daemon_data = _daemon_result(
            "memory_recall",
            {"project_root": str(_target_root(arguments)), "query": str(arguments.get("query") or ""), "limit": int(arguments.get("limit") or 10)},
        )
        return _json_content(daemon_data or recall(_target_root(arguments), str(arguments.get("query") or ""), limit=int(arguments.get("limit") or 10)))
    if name == "aihelper_capability_route":
        input_text = str(arguments.get("input") or "")
        file_path = str(arguments.get("file_path") or "") or None
        daemon_data = _daemon_result(
            "capability_route",
            {"project_root": str(_target_root(arguments)), "input": input_text, "file_path": file_path},
        )
        return _json_content(daemon_data or select_pipeline(input_text, file_path))
    # ── Graph Query Tools (v0.0.7) ────────────────────────────
    if name == "aihelper_callers":
        return _call_graph_tool("graph_callers", "callers", arguments)
    if name == "aihelper_callees":
        return _call_graph_tool("graph_callees", "callees", arguments)
    if name == "aihelper_trace":
        return _call_graph_tool("graph_trace", "trace", arguments)
    if name == "aihelper_impact":
        return _call_graph_tool("graph_impact", "impact", arguments)
    if name == "aihelper_explore":
        return _call_graph_tool("graph_explore", "explore", arguments)
    if name == "aihelper_graph_status":
        daemon_data = _daemon_result("graph_status", {"project_root": str(_target_root(arguments))})
        if daemon_data:
            return _json_content(daemon_data)
        from .graph_db import get_db
        db = get_db(_target_root(arguments))
        return _json_content(db.get_stats())
    raise ValueError(f"unknown tool: {name}")


def handle(message: Dict[str, Any]) -> Dict[str, Any] | None:
    method = message.get("method")
    message_id = message.get("id")

    if method == "initialize":
        return _response(
            message_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            },
        )

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        return _response(message_id, {"tools": _tool_schemas()})

    if method == "tools/call":
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        name = params.get("name")
        try:
            result = _call_tool(str(name), params.get("arguments") if isinstance(params.get("arguments"), dict) else {})
        except Exception as exc:
            return _error(message_id, -32000, str(exc))
        return _response(message_id, result)

    if message_id is None:
        return None
    return _error(message_id, -32601, f"unknown method: {method}")


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = handle(message)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
