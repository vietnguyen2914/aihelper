"""
Runtime Trace Viewer — CLI-queryable execution traces from the event bus.

Reads from the EventBus SQLite database and renders execution traces
in human-readable formats. Designed for both programmatic access
(daemon handlers) and interactive CLI use.

All imports from event_bus use try/except — this module is optional
and never blocks the runtime.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── Event type constants (mirrored from event_bus for standalone use) ──
_TRACE_EVENT_TYPES = frozenset({
    "workflow.started", "workflow.completed",
    "tier.selected", "frontier.escalation",
    "primitive.started", "primitive.completed",
    "cache.hit", "cache.miss",
    "cache.rebuilt", "cache.updated",
    "invalidation.triggered", "invalidation.propagated",
    "partition.created",
    "compression.reused", "compression.decayed",
    "optimizer.pass_applied",
    "cognition.package_compiled",
    "ollama.invoked", "frontier.invoked",
    "replay.verified",
})


# ── Query Functions ─────────────────────────────────────────────

def _get_bus():
    """Get the EventBus singleton (best-effort)."""
    try:
        from .event_bus import get_event_bus
        return get_event_bus()
    except Exception:
        return None


def _get_session_id() -> str:
    """Get current session ID (best-effort)."""
    try:
        from .event_bus import _SESSION_ID
        return _SESSION_ID
    except Exception:
        return "unknown"


def get_recent_trace(limit: int = 100) -> List[Dict[str, Any]]:
    """Get the last N events from the event bus.

    Args:
        limit: Maximum number of events to retrieve (default 100).

    Returns:
        List of event dicts with keys: id, timestamp, event_type, data (parsed), session_id.
    """
    bus = _get_bus()
    if bus is None:
        return []
    try:
        events = bus.get_events(limit=limit)
        for ev in events:
            try:
                ev["data"] = json.loads(ev.pop("data_json", "{}"))
            except Exception:
                ev["data"] = {}
        return events
    except Exception:
        return []


def get_session_trace(session_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get all events for a specific session.

    Args:
        session_id: The session UUID to query. If None, uses the current session.

    Returns:
        List of event dicts for the given session (most recent first).
    """
    bus = _get_bus()
    if bus is None:
        return []
    try:
        events = bus.get_events(limit=5000, session_id=session_id)
        for ev in events:
            try:
                ev["data"] = json.loads(ev.pop("data_json", "{}"))
            except Exception:
                ev["data"] = {}
        return events
    except Exception:
        return []


# ── Formatting ──────────────────────────────────────────────────

def format_trace(events: List[Dict[str, Any]], style: str = "compact") -> str:
    """Render events as a readable execution trace.

    Args:
        events: List of event dicts (from get_recent_trace or get_session_trace).
        style:
            "compact" — indented tree-like trace (default)
            "detailed" — includes full data payloads
            "oneline"  — one event per line with key info

    Returns:
        Formatted multi-line string.
    """
    if not events:
        return "(no events)"

    lines: List[str] = []
    # Reverse so oldest-first for chronological reading
    for ev in reversed(events):
        et = ev.get("event_type", "?")
        data = ev.get("data", {})
        ts = ev.get("timestamp", "")[:19] if ev.get("timestamp") else ""
        ts_prefix = f"[{ts}] " if ts else ""

        if style == "oneline":
            line = _format_oneline(et, data, ts_prefix)
            lines.append(line)
        elif style == "detailed":
            line = _format_detailed(et, data, ts_prefix)
            lines.append(line)
        else:
            # compact (default)
            line = _format_compact(et, data)
            lines.append(line)

    return "\n".join(lines)


def _format_compact(event_type: str, data: Dict[str, Any]) -> str:
    """Render a single event in compact tree-like format."""
    indent = ""
    if event_type.startswith("workflow."):
        pass  # no extra indent for workflow
    elif event_type.startswith("primitive.") or event_type == "cache.hit" or event_type == "cache.miss":
        indent = "  "
    else:
        indent = "    "

    if event_type == "workflow.started":
        return f"[workflow_start] {data.get('name', '?')}"
    elif event_type == "workflow.completed":
        return f"  [workflow_complete] {data.get('name', '?')} {data.get('duration_ms', 0)}ms"
    elif event_type == "tier.selected":
        return f"{indent}[tier_selected] {data.get('tier', '?')}"
    elif event_type == "frontier.escalation":
        return f"{indent}[frontier_escalation] {data.get('reason', '?')}"
    elif event_type == "primitive.started":
        return f"{indent}[primitive_start] {data.get('name', '?')}"
    elif event_type == "primitive.completed":
        dur = data.get("duration_ms", 0)
        cache = " (cache hit)" if data.get("cache_hit") else ""
        err = f" ERROR: {data.get('error', '')}" if data.get("error") else ""
        return f"{indent}[primitive_complete] {data.get('name', '?')} {dur}ms{cache}{err}"
    elif event_type == "cache.hit":
        return f"{indent}[cache_hit] {data.get('key', '?')}"
    elif event_type == "cache.miss":
        return f"{indent}[cache_miss] {data.get('key', '?')}"
    elif event_type == "cache.rebuilt":
        return f"{indent}[cache_rebuilt] {data.get('file_count', 0)} files, {data.get('symbol_count', 0)} symbols ({data.get('duration_ms', 0)}ms)"
    elif event_type == "cache.updated":
        return f"{indent}[cache_updated] {data.get('change_count', 0)} changes"
    elif event_type == "invalidation.triggered":
        return f"{indent}[invalidation] {data.get('file', '?')} ({data.get('change_type', '?')})"
    elif event_type == "invalidation.propagated":
        return f"{indent}[invalidation_propagated] {data.get('file', '?')}: {data.get('reason', '?')}"
    elif event_type == "partition.created":
        sizes = data.get("sizes", [])
        return f"{indent}[partition_created] {data.get('partition_count', 0)} partitions, sizes={sizes}, max_parallelism={data.get('max_parallelism', 0)}"
    elif event_type == "compression.reused":
        return f"{indent}[compression_reused] key={data.get('cache_key', '?')}"
    elif event_type == "compression.decayed":
        return f"{indent}[compression_decayed] {data.get('change_type', '?')} {data.get('previous_confidence', 1.0):.2f} -> {data.get('new_confidence', 0.0):.2f}"
    elif event_type == "optimizer.pass_applied":
        return f"{indent}[optimizer] {data.get('pass_name', '?')}: {data.get('nodes_before', 0)} -> {data.get('nodes_after', 0)} nodes"
    elif event_type == "cognition.package_compiled":
        return f"{indent}[cognition] tier={data.get('tier_recommendation', '?')}, primitives={data.get('allowed_primitives', 0)}, scope={data.get('invalidation_scope', '?')}"
    elif event_type == "ollama.invoked":
        return f"{indent}[ollama] {data.get('model', '?')} ({data.get('duration_ms', 0)}ms)"
    elif event_type == "frontier.invoked":
        return f"{indent}[frontier] {data.get('model', '?')} ({data.get('duration_ms', 0)}ms)"
    elif event_type == "replay.verified":
        return f"{indent}[replay] verified: {data.get('result', '?')}"
    else:
        return f"{indent}[{event_type}] {str(data)[:120]}"


def _format_oneline(event_type: str, data: Dict[str, Any], ts_prefix: str) -> str:
    """Render a single event as a one-line summary."""
    name = data.get("name", data.get("key", ""))
    extra = ""
    if "duration_ms" in data:
        extra = f" {data['duration_ms']}ms"
    if "tier" in data:
        extra = f" tier={data['tier']}"
    if "pass_name" in data:
        extra = f" {data['pass_name']} ({data.get('nodes_before',0)}->{data.get('nodes_after',0)})"
    return f"{ts_prefix}{event_type}{(' ' + name + extra) if (name or extra) else ''}"


def _format_detailed(event_type: str, data: Dict[str, Any], ts_prefix: str) -> str:
    """Render a single event with its full data payload."""
    import textwrap
    data_str = json.dumps(data, indent=2, default=str)
    return f"{ts_prefix}{event_type}\n{textwrap.indent(data_str, '  ')}"


# ── Execution Summary ───────────────────────────────────────────

def get_execution_summary() -> Dict[str, Any]:
    """Compute a summary of all execution events in the current session.

    Returns:
        Dict with keys:
            total_events — total number of events
            total_primitives — total primitive.started events
            avg_primitive_duration_ms — mean duration of completed primitives
            ollama_usage — number of ollama invocations
            frontier_ratio — fraction of tier selections that became frontier
            cache_hit_rate — fraction of cache lookups that hit
            by_type — breakdown of event types
    """
    bus = _get_bus()
    if bus is None:
        return {"total_events": 0, "error": "Event bus not available"}

    try:
        stats = bus.get_stats()
        by_type = stats.get("by_type", {})

        # ── Primitive durations ──
        events = bus.get_events(event_type="primitive.completed", limit=5000)
        durations = [json.loads(ev["data_json"]).get("duration_ms", 0)
                     for ev in events
                     if isinstance(json.loads(ev.get("data_json", "{}")), dict)]
        durations = [d for d in durations if isinstance(d, (int, float)) and d > 0]
        avg_dur = round(sum(durations) / len(durations), 2) if durations else 0.0

        # ── Cache hit rate ──
        hits = by_type.get("cache.hit", 0)
        misses = by_type.get("cache.miss", 0)
        total_cache = hits + misses
        cache_hit_rate = round(hits / total_cache, 4) if total_cache > 0 else 0.0

        # ── Frontier ratio ──
        tier_selected = by_type.get("tier.selected", 0)
        frontier_esc = by_type.get("frontier.escalation", 0)
        frontier_ratio = round(frontier_esc / max(tier_selected, 1), 4)

        # ── Total primitives started ──
        total_primitives = by_type.get("primitive.started", 0)

        # ── Ollama usage ──
        ollama_count = by_type.get("ollama.invoked", 0)

        return {
            "total_events": stats.get("total_events", 0),
            "total_primitives": total_primitives,
            "avg_primitive_duration_ms": avg_dur,
            "ollama_usage": ollama_count,
            "frontier_ratio": frontier_ratio,
            "cache_hit_rate": cache_hit_rate,
            "by_type": by_type,
        }
    except Exception:
        return {"total_events": 0, "error": "Failed to compute summary"}


# ── Daemon: handle_runtime_trace ───────────────────────────────

def handle_runtime_trace(params: Dict[str, Any]) -> Dict[str, Any]:
    """Daemon handler: return formatted execution trace.

    Parameters (from params):
        limit: max events (default 100)
        format: "compact", "detailed", "oneline", or "json" (default "compact")
        session_id: optional session UUID (default: current session)

    Response:
        {"trace": "<formatted string>", "event_count": N, "format": "<style>"}
        or {"events": [...], "event_count": N} when format="json"
    """
    limit = int(params.get("limit", 100))
    output_format = params.get("format", "compact")
    session_id = params.get("session_id", None)

    if output_format == "json":
        events = get_session_trace(session_id)[:limit]
        return {"events": events, "event_count": len(events)}
    else:
        if session_id:
            events = get_session_trace(session_id)[:limit]
        else:
            events = get_recent_trace(limit=limit)
        trace_str = format_trace(events, style=output_format)
        return {
            "trace": trace_str,
            "event_count": len(events),
            "format": output_format,
        }


# ── Daemon: handle_runtime_inspect ─────────────────────────────

def handle_runtime_inspect(params: Dict[str, Any]) -> Dict[str, Any]:
    """Daemon handler: return live execution stats + recent trace.

    Combines get_execution_summary() with get_recent_trace() for a
    comprehensive view of the runtime state.

    Parameters (from params):
        limit: max events for recent trace (default 20)
        format: trace format (default "compact")

    Response:
        summary: execution summary from get_execution_summary()
        recent_trace: formatted trace string
        recent_events: raw event list
        session_id: current session UUID
    """
    limit = int(params.get("limit", 20))
    trace_format = params.get("format", "compact")

    summary = get_execution_summary()
    events = get_recent_trace(limit=limit)
    trace_str = format_trace(events, style=trace_format)

    return {
        "summary": summary,
        "recent_trace": trace_str,
        "recent_events": events,
        "event_count": len(events),
        "session_id": _get_session_id(),
        "format": trace_format,
    }
