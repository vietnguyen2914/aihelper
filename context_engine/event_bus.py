"""
Runtime Event Instrumentation Layer — the nervous system of the cognition runtime.

Every execution event (primitive start/complete, cache hit/miss, invalidation,
tier selection, frontier escalation, workflow lifecycle) is emitted via the
EventBus singleton and persisted to SQLite for observability, debugging, and
post-hoc analysis.

Design:
  - Singleton EventBus with pub/sub + SQLite persistence
  - Lazy initialization — no cost if unused
  - All imports from event_bus in other modules are lazy (try/except)
  - Thread-safe via threading.Lock
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


# ── Session identity (one per process) ──────────────────────────
_SESSION_ID: str = str(uuid.uuid4())


# ── Event Type Constants ────────────────────────────────────────
# Primitive execution
PRIMITIVE_STARTED = "primitive.started"
PRIMITIVE_COMPLETED = "primitive.completed"

# Cache operations
CACHE_HIT = "cache.hit"
CACHE_MISS = "cache.miss"

# Semantic invalidation
INVALIDATION_TRIGGERED = "invalidation.triggered"
INVALIDATION_PROPAGATED = "invalidation.propagated"

# Partitioning
PARTITION_CREATED = "partition.created"

# Tier routing
TIER_SELECTED = "tier.selected"
FRONTIER_ESCALATION = "frontier.escalation"

# Model invocation
OLLAMA_INVOKED = "ollama.invoked"
FRONTIER_INVOKED = "frontier.invoked"

# Compression / optimizer
COMPRESSION_REUSED = "compression.reused"
COMPRESSION_DECAYED = "compression.decayed"
OPTIMIZER_PASS_APPLIED = "optimizer.pass_applied"
COGNITION_PACKAGE_COMPILED = "cognition.package_compiled"
CACHE_REBUILT = "cache.rebuilt"
CACHE_UPDATED = "cache.updated"
CACHE_AUTO_MAINTAINED = "cache.auto_maintained"

# Replay verification
REPLAY_VERIFIED = "replay.verified"

# Workflow lifecycle
WORKFLOW_STARTED = "workflow.started"
WORKFLOW_COMPLETED = "workflow.completed"

# ── All known event types ───────────────────────────────────────
ALL_EVENT_TYPES = frozenset({
    PRIMITIVE_STARTED,
    PRIMITIVE_COMPLETED,
    CACHE_HIT,
    CACHE_MISS,
    INVALIDATION_TRIGGERED,
    INVALIDATION_PROPAGATED,
    PARTITION_CREATED,
    TIER_SELECTED,
    FRONTIER_ESCALATION,
    OLLAMA_INVOKED,
    FRONTIER_INVOKED,
    COMPRESSION_REUSED,
    COMPRESSION_DECAYED,
    OPTIMIZER_PASS_APPLIED,
    COGNITION_PACKAGE_COMPILED,
    CACHE_REBUILT,
    CACHE_UPDATED,
    CACHE_AUTO_MAINTAINED,
    REPLAY_VERIFIED,
    WORKFLOW_STARTED,
    WORKFLOW_COMPLETED,
})


# ── SQLite Schema ───────────────────────────────────────────────

_EVENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS runtime_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,
    data_json TEXT NOT NULL,
    session_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_type ON runtime_events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_session ON runtime_events(session_id);
"""


# ── EventBus ────────────────────────────────────────────────────

class EventBus:
    """Singleton pub/sub event bus with SQLite persistence.

    Every method is thread-safe. The bus lazily opens its SQLite database
    on first emit. Subscribers are called synchronously (in-process).
    """

    def __init__(self, db_path: Optional[Path] = None):
        self._lock = threading.Lock()
        self._db_path: Optional[Path] = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._subscribers: Dict[str, List[Callable[[str, Dict[str, Any]], None]]] = {}
        self._initialized = False

    # ── Initialization ──────────────────────────────────────────

    def _ensure_db(self) -> None:
        """Open SQLite connection and create schema if needed."""
        if self._initialized and self._conn is not None:
            return
        with self._lock:
            if self._initialized:
                return
            if self._db_path is None:
                self._db_path = Path.cwd() / ".aihelper" / "events.db"
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(
                str(self._db_path), check_same_thread=False
            )
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(_EVENTS_SCHEMA)
            self._conn.commit()
            self._initialized = True

    def _exec(self, sql: str, params: Tuple[Any, ...] = ()) -> sqlite3.Cursor:
        """Thread-safe SQLite execute."""
        with self._lock:
            if self._conn is None:
                raise RuntimeError("Database not initialized")
            return self._conn.execute(sql, params)

    def _commit(self) -> None:
        """Thread-safe SQLite commit."""
        with self._lock:
            if self._conn is not None:
                self._conn.commit()

    def _rollback(self) -> None:
        """Thread-safe SQLite rollback."""
        with self._lock:
            if self._conn is not None:
                self._conn.rollback()

    # ── Emit ────────────────────────────────────────────────────

    def emit(self, event_type: str, data: Dict[str, Any]) -> None:
        """Emit an event: persist to SQLite and notify subscribers.

        Never raises. Errors during persistence or subscriber notification
        are silently swallowed so the runtime is never blocked by
        observability.
        """
        try:
            self._ensure_db()
            self._persist(event_type, data)
            self._notify(event_type, data)
        except Exception:
            pass  # Event emission is best-effort — never blocks runtime

    def _persist(self, event_type: str, data: Dict[str, Any]) -> None:
        """Write an event row to SQLite."""
        if self._conn is None:
            return
        try:
            ts = datetime.now(timezone.utc).isoformat()
            data_json = json.dumps(data, default=str)
            self._exec(
                "INSERT INTO runtime_events (timestamp, event_type, data_json, session_id) "
                "VALUES (?, ?, ?, ?)",
                (ts, event_type, data_json, _SESSION_ID),
            )
            self._commit()
        except Exception:
            self._rollback()

    def _notify(self, event_type: str, data: Dict[str, Any]) -> None:
        """Call all subscribers for this event type."""
        handlers = list(self._subscribers.get(event_type, []))
        wildcard = list(self._subscribers.get("*", []))
        for handler in handlers + wildcard:
            try:
                handler(event_type, data)
            except Exception:
                pass

    # ── Subscribe ───────────────────────────────────────────────

    def subscribe(
        self, event_type: str, handler: Callable[[str, Dict[str, Any]], None]
    ) -> None:
        """Register a handler for a specific event type (or '*' for all)."""
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(handler)

    def unsubscribe(
        self, event_type: str, handler: Callable[[str, Dict[str, Any]], None]
    ) -> None:
        """Remove a previously registered handler."""
        with self._lock:
            handlers = self._subscribers.get(event_type, [])
            if handler in handlers:
                handlers.remove(handler)

    # ── Query ───────────────────────────────────────────────────

    def get_events(
        self,
        event_type: Optional[str] = None,
        limit: int = 100,
        session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Query events, optionally filtered by type and/or session.

        Defaults to filtering by the current process session. Pass
        session_id=None to query across all sessions.
        """
        try:
            self._ensure_db()
            if self._conn is None:
                return []

            parts: List[str] = ["SELECT id, timestamp, event_type, data_json, session_id FROM runtime_events"]
            params: List[Any] = []
            clauses: List[str] = []

            if event_type:
                clauses.append("event_type = ?")
                params.append(event_type)

            if session_id is None:
                # Default: current session only
                clauses.append("session_id = ?")
                params.append(_SESSION_ID)
            elif session_id:
                clauses.append("session_id = ?")
                params.append(session_id)

            if clauses:
                parts.append("WHERE " + " AND ".join(clauses))

            parts.append("ORDER BY id DESC")
            parts.append("LIMIT ?")
            params.append(limit)

            cursor = self._exec(" ".join(parts), tuple(params))
            rows = cursor.fetchall()

            results = []
            for row in rows:
                results.append({
                    "id": row[0],
                    "timestamp": row[1],
                    "event_type": row[2],
                    "data_json": row[3],
                    "session_id": row[4],
                })
            return results
        except Exception:
            return []

    def get_stats(self) -> Dict[str, Any]:
        """Aggregate statistics across all events in the current session."""
        try:
            self._ensure_db()
            if self._conn is None:
                return {"total_events": 0, "by_type": {}}

            # Total events
            cursor = self._exec(
                "SELECT COUNT(*) FROM runtime_events WHERE session_id = ?",
                (_SESSION_ID,),
            )
            total = cursor.fetchone()[0]

            # Breakdown by type
            cursor = self._exec(
                "SELECT event_type, COUNT(*) as cnt FROM runtime_events "
                "WHERE session_id = ? GROUP BY event_type ORDER BY cnt DESC",
                (_SESSION_ID,),
            )
            by_type: Dict[str, int] = {}
            for row in cursor.fetchall():
                by_type[row[0]] = row[1]

            # Cache hit rate
            hits = by_type.get(CACHE_HIT, 0)
            misses = by_type.get(CACHE_MISS, 0)
            total_cache = hits + misses
            cache_hit_rate = round(hits / total_cache, 4) if total_cache > 0 else 0.0

            # Frontier ratio
            tier_selected = by_type.get(TIER_SELECTED, 0)
            frontier_escalations = by_type.get(FRONTIER_ESCALATION, 0)
            frontier_ratio = round(
                frontier_escalations / max(tier_selected, 1), 4
            )

            # Ollama usage
            ollama_count = by_type.get(OLLAMA_INVOKED, 0)

            return {
                "total_events": total,
                "by_type": by_type,
                "cache_hit_rate": cache_hit_rate,
                "frontier_ratio": frontier_ratio,
                "ollama_invocations": ollama_count,
            }
        except Exception:
            return {"total_events": 0, "by_type": {}}

    # ── Format trace ───────────────────────────────────────────

    def format_trace(self, limit: int = 100, human_readable: bool = True) -> str | List[Dict[str, Any]]:
        """Format recent events as a readable execution trace.

        Args:
            limit: Maximum number of events to include.
            human_readable: If True, return a formatted string. If False, return
                            the raw event dicts (same as get_events).
        """
        events = self.get_events(limit=limit)
        if not human_readable:
            return events
        lines = []
        for e in events:
            try:
                data = json.loads(e["data_json"])
            except Exception:
                data = {}
            ts = e["timestamp"][:19]
            et = e["event_type"]
            if et == WORKFLOW_STARTED:
                lines.append(f"[{ts}] \u2550\u2550\u2550 WORKFLOW START: {data.get('name','?')} \u2550\u2550\u2550")
            elif et == WORKFLOW_COMPLETED:
                lines.append(f"[{ts}] \u2550\u2550\u2550 WORKFLOW DONE: {data.get('name','?')} ({data.get('duration_ms',0)}ms) \u2550\u2550\u2550")
            elif et == PRIMITIVE_STARTED:
                lines.append(f"[{ts}]   \u251c\u2500 START {data.get('name','?')}")
            elif et == PRIMITIVE_COMPLETED:
                cache = " (cache hit)" if data.get("cache_hit") else ""
                error_suffix = f" ERROR: {data.get('error','')}" if data.get("error") else ""
                lines.append(f"[{ts}]   \u251c\u2500 DONE  {data.get('name','?')} ({data.get('duration_ms',0)}ms){cache}{error_suffix}")
            elif et == CACHE_HIT:
                lines.append(f"[{ts}]   \u2502  CACHE HIT: {data.get('key','?')}")
            elif et == CACHE_MISS:
                lines.append(f"[{ts}]   \u2502  CACHE MISS: {data.get('key','?')}")
            elif et == TIER_SELECTED:
                lines.append(f"[{ts}]   \u251c\u2500 TIER: {data.get('tier','?')} ({data.get('model','?')})")
            elif et == FRONTIER_ESCALATION:
                lines.append(f"[{ts}]   \u251c\u2500 [ESCALATE] FRONTIER: {data.get('reason','?')}")
            elif et == OLLAMA_INVOKED:
                lines.append(f"[{ts}]   \u251c\u2500 [OLLAMA] {data.get('model','?')} ({data.get('duration_ms',0)}ms)")
            elif et == FRONTIER_INVOKED:
                lines.append(f"[{ts}]   \u251c\u2500 [FRONTIER] {data.get('model','?')} ({data.get('duration_ms',0)}ms)")
            elif et == OPTIMIZER_PASS_APPLIED:
                lines.append(f"[{ts}]   \u251c\u2500 [OPTIMIZER] {data.get('pass_name','?')}: {data.get('nodes_before',0)}\u2192{data.get('nodes_after',0)}")
            elif et == COGNITION_PACKAGE_COMPILED:
                lines.append(f"[{ts}]   \u251c\u2500 [COGNITION] tier={data.get('tier_recommendation','?')} primitives={data.get('allowed_primitives',0)}")
            elif et == CACHE_REBUILT:
                lines.append(f"[{ts}]   \u251c\u2500 [CACHE] rebuilt: {data.get('file_count',0)} files, {data.get('symbol_count',0)} symbols ({data.get('duration_ms',0)}ms)")
            elif et == CACHE_UPDATED:
                lines.append(f"[{ts}]   \u251c\u2500 [CACHE] updated: {data.get('change_count',0)} changes")
            elif et == INVALIDATION_TRIGGERED:
                lines.append(f"[{ts}]   \u251c\u2500 [INVALIDATE] {data.get('file','?')} ({data.get('change_type','?')})")
            else:
                lines.append(f"[{ts}]   \u251c\u2500 {et}: {str(data)[:100]}")
        return '\n'.join(lines)

    # ── Clear (testing) ─────────────────────────────────────────

    def clear(self) -> None:
        """Delete ALL events from the bus. Intended for testing only."""
        try:
            self._exec("DELETE FROM runtime_events")
            self._commit()
            with self._lock:
                self._subscribers.clear()
        except Exception:
            pass

    def close(self) -> None:
        """Close the SQLite connection."""
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None
                self._initialized = False

    def __del__(self) -> None:
        self.close()


# ── Singleton accessor ──────────────────────────────────────────

_BUS: Optional[EventBus] = None
_BUS_LOCK = threading.Lock()


def get_event_bus(db_path: Optional[Path] = None) -> EventBus:
    """Return the singleton EventBus instance.

    Args:
        db_path: Optional custom path for the SQLite database.
                 Only used on first call (subsequent calls ignore it).
    """
    global _BUS
    if _BUS is None:
        with _BUS_LOCK:
            if _BUS is None:
                _BUS = EventBus(db_path=db_path)
    return _BUS


def reset_event_bus() -> None:
    """Reset the singleton (for testing). Clears all persisted events."""
    global _BUS
    with _BUS_LOCK:
        if _BUS is not None:
            try:
                _BUS.clear()
            except Exception:
                pass
            _BUS.close()
            _BUS = None


# ── Daemon: handle_runtime_stats ────────────────────────────────

def handle_runtime_stats(params: Dict[str, Any]) -> Dict[str, Any]:
    """Return live runtime statistics aggregated from the event bus.

    Designed to be registered as a daemon handler so the user can query
    runtime stats via 'aihelper runtime stats' or similar.

    Response:
        total_events: total events in current session
        by_type: dict of event_type -> count
        recent_events: last 20 events (with data preview)
        ollama_usage: number of ollama invocations
        frontier_ratio: fraction of tasks that escalated to frontier
        cache_hit_rate: fraction of cache lookups that hit
    """
    try:
        bus = get_event_bus()
        stats = bus.get_stats()

        recent = bus.get_events(limit=20)
        # Truncate data_json to 200 chars for readability
        for ev in recent:
            try:
                parsed = json.loads(ev["data_json"])
                # Keep only keys summary
                summary = {}
                for k, v in parsed.items():
                    if isinstance(v, str) and len(v) > 100:
                        summary[k] = v[:100] + "..."
                    elif isinstance(v, (dict, list)):
                        summary[k] = type(v).__name__
                    else:
                        summary[k] = v
                ev["data"] = summary
            except Exception:
                ev["data"] = {}
            del ev["data_json"]

        return {
            "total_events": stats.get("total_events", 0),
            "by_type": stats.get("by_type", {}),
            "recent_events": recent,
            "ollama_usage": stats.get("ollama_invocations", 0),
            "frontier_ratio": stats.get("frontier_ratio", 0.0),
            "cache_hit_rate": stats.get("cache_hit_rate", 0.0),
        }
    except Exception:
        return {
            "total_events": 0,
            "by_type": {},
            "recent_events": [],
            "ollama_usage": 0,
            "frontier_ratio": 0.0,
            "cache_hit_rate": 0.0,
            "error": "Event bus not available",
        }


# ── Daemon: handle_runtime_trace ───────────────────────────────

def handle_runtime_trace(params: Dict[str, Any]) -> Dict[str, Any]:
    """Return a formatted execution trace from the event bus.

    Designed to be registered as a daemon handler so the user can query
    runtime traces via 'aihelper runtime trace' or similar.

    Parameters (from params):
        limit: max events (default 100)
        format: "json" for raw events, "text" for human-readable trace (default "text")

    Response:
        format="text": { "trace": "<multi-line string>", "event_count": N }
        format="json": { "events": [...], "event_count": N }
    """
    try:
        bus = get_event_bus()
        limit = int(params.get("limit", 100))
        output_format = params.get("format", "text")

        if output_format == "json":
            events = bus.format_trace(limit=limit, human_readable=False)
            # Strip full data_json to keep response compact
            for ev in events:
                try:
                    ev["data"] = json.loads(ev.pop("data_json", "{}"))
                except Exception:
                    ev["data"] = {}
            return {
                "events": events,
                "event_count": len(events),
            }
        else:
            trace_str = bus.format_trace(limit=limit, human_readable=True)
            return {
                "trace": trace_str,
                "event_count": len(trace_str.split("\n")) if trace_str else 0,
            }
    except Exception:
        return {
            "trace": "",
            "event_count": 0,
            "error": "Event bus not available",
        }


# ── Daemon: handle_runtime_summary ─────────────────────────────

def handle_runtime_summary(params: Dict[str, Any]) -> Dict[str, Any]:
    """Return a concise runtime summary from the event bus.

    Designed to be registered as a daemon handler so the user can query
    runtime summary via 'aihelper runtime summary' or similar.

    Response:
        total_events: total events in current session
        by_type: dict of event_type -> count
        cache_hit_rate: fraction of cache lookups that hit
        cache_miss_rate: fraction of cache lookups that missed
        tier_ratio: { "frontier": N, "ollama": N, "deterministic": N, "ratio_str": "..." }
        average_primitive_duration_ms: mean duration of completed primitives
        most_used_primitives: top-10 most executed primitives with counts and avg durations
        recent_frontier_escalations: last 10 frontier escalations
        session_uptime_seconds: seconds elapsed since earliest event
    """
    try:
        bus = get_event_bus()
        limit = int(params.get("limit", 100))
        stats = bus.get_stats()
        by_type = stats.get("by_type", {})

        # ── Tier ratio ──
        frontier_count = by_type.get(FRONTIER_INVOKED, 0) + by_type.get(FRONTIER_ESCALATION, 0)
        ollama_count = by_type.get(OLLAMA_INVOKED, 0)
        # Deterministic = primitive.started minus cache.hit and primitives from local/frontier
        primitive_started = by_type.get(PRIMITIVE_STARTED, 0)
        det_count = max(0, primitive_started - ollama_count - frontier_count)
        total_tier = frontier_count + ollama_count + det_count or 1
        tier_ratio = {
            "frontier": frontier_count,
            "ollama": ollama_count,
            "deterministic": det_count,
            "ratio_str": f"F:{frontier_count} O:{ollama_count} D:{det_count} ({round(frontier_count/total_tier*100)}%/{round(ollama_count/total_tier*100)}%/{round(det_count/total_tier*100)}%)",
        }

        # ── Cache hit rate ──
        hits = by_type.get(CACHE_HIT, 0)
        misses = by_type.get(CACHE_MISS, 0)
        total_cache = hits + misses
        cache_hit_rate = round(hits / total_cache, 4) if total_cache > 0 else 0.0

        # ── Average primitive duration ──
        events = bus.get_events(event_type=PRIMITIVE_COMPLETED, limit=1000)
        durations = []
        prim_counts: Dict[str, Dict[str, Any]] = {}
        for ev in events:
            try:
                data = json.loads(ev["data_json"])
            except Exception:
                continue
            name = data.get("name", "?")
            dur = data.get("duration_ms", 0)
            if isinstance(dur, (int, float)):
                durations.append(dur)
            if name not in prim_counts:
                prim_counts[name] = {"count": 0, "total_duration": 0.0}
            prim_counts[name]["count"] += 1
            prim_counts[name]["total_duration"] += dur

        avg_prim_duration = round(sum(durations) / len(durations), 2) if durations else 0.0

        # Most used primitives (top 10 by count)
        sorted_prims = sorted(prim_counts.items(), key=lambda x: x[1]["count"], reverse=True)
        most_used = [
            {
                "name": name,
                "count": info["count"],
                "avg_duration_ms": round(info["total_duration"] / info["count"], 2),
            }
            for name, info in sorted_prims[:10]
        ]

        # ── Recent frontier escalations ──
        escalation_events = bus.get_events(event_type=FRONTIER_ESCALATION, limit=10)
        recent_escalations = []
        for ev in escalation_events:
            try:
                data = json.loads(ev["data_json"])
            except Exception:
                data = {}
            recent_escalations.append({
                "timestamp": ev["timestamp"],
                "reason": data.get("reason", "?"),
                "task": data.get("task", "?"),
                "data": data,
            })

        # ── Session uptime ──
        earliest = bus.get_events(limit=1)
        session_uptime_seconds = 0
        if earliest:
            try:
                from datetime import datetime
                t_earliest = datetime.fromisoformat(earliest[-1]["timestamp"])
                t_now = datetime.now(timezone.utc)
                session_uptime_seconds = int((t_now - t_earliest).total_seconds())
            except Exception:
                pass

        return {
            "total_events": stats.get("total_events", 0),
            "by_type": by_type,
            "cache_hit_rate": cache_hit_rate,
            "cache_miss_rate": round(misses / total_cache, 4) if total_cache > 0 else 0.0,
            "tier_ratio": tier_ratio,
            "average_primitive_duration_ms": avg_prim_duration,
            "most_used_primitives": most_used,
            "recent_frontier_escalations": recent_escalations,
            "session_uptime_seconds": session_uptime_seconds,
        }
    except Exception:
        return {
            "total_events": 0,
            "by_type": {},
            "cache_hit_rate": 0.0,
            "tier_ratio": {"frontier": 0, "ollama": 0, "deterministic": 0, "ratio_str": "F:0 O:0 D:0"},
            "error": "Event bus not available",
        }
