from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

try:
    from .main import analyze_request
except ImportError:
    from main import analyze_request


SERVER_INFO = {
    "name": "aihelper",
    "version": "1.0.0",
}


def _response(message_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "result": result}


def _error(message_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}}


def _tool_schema() -> Dict[str, Any]:
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


def _call_tool(arguments: Dict[str, Any]) -> Dict[str, Any]:
    task = str(arguments.get("task", "")).strip()
    if not task:
        raise ValueError("task is required")

    project_root = arguments.get("project_root")
    root = Path(project_root).expanduser().resolve() if isinstance(project_root, str) and project_root.strip() else Path.cwd()
    max_context_chars = int(arguments.get("max_context_chars") or 6000)
    output_format = str(arguments.get("format") or "prompt")

    result = analyze_request(task, max_context_chars=max_context_chars, root=root)
    text = result["final_prompt"] if output_format == "prompt" else json.dumps(result, indent=2, ensure_ascii=False)
    return {"content": [{"type": "text", "text": text}]}


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
        return _response(message_id, {"tools": [_tool_schema()]})

    if method == "tools/call":
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        name = params.get("name")
        if name != "aihelper_context":
            return _error(message_id, -32602, f"unknown tool: {name}")
        try:
            result = _call_tool(params.get("arguments") if isinstance(params.get("arguments"), dict) else {})
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
