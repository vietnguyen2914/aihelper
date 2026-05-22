"""
Structured Telemetry — track daemon performance and behavior.

Metrics tracked:
- Cache hit/miss rate
- Symbol lookup latency
- Route latency
- Prompt assembly time
- Token estimate
- Patch success/failure rate
- Warmup effectiveness
- Daemon uptime
- Connection count

Stored in ~/.aihelper/telemetry/ as daily JSON files.
Provides /metrics endpoint for monitoring.
"""
from __future__ import annotations

import json
import time
import threading
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class Telemetry:
    """Collects and reports daemon telemetry."""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or Path.home() / ".aihelper" / "telemetry"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._start_time = time.time()

        # ── Counters ─────────────────────────────────────────────
        self.counters: Dict[str, int] = defaultdict(int)
        # ── Latency histograms ───────────────────────────────────
        self.latencies: Dict[str, List[float]] = defaultdict(list)
        # ── Cache metrics ────────────────────────────────────────
        self.cache_hits = 0
        self.cache_misses = 0
        self.cache_builds = 0
        # ── Errors ────────────────────────────────────────────────
        self.errors: Dict[str, int] = defaultdict(int)

    def record_request(self, method: str, latency_ms: float) -> None:
        """Record a daemon request."""
        with self._lock:
            self.counters[f"request:{method}"] += 1
            self.counters["request:total"] += 1
            self.latencies[f"latency:{method}"].append(latency_ms)
            # Keep last 1000 samples per method
            if len(self.latencies[f"latency:{method}"]) > 1000:
                self.latencies[f"latency:{method}"] = self.latencies[f"latency:{method}"][-1000:]

    def record_cache_hit(self) -> None:
        with self._lock:
            self.cache_hits += 1

    def record_cache_miss(self) -> None:
        with self._lock:
            self.cache_misses += 1

    def record_cache_build(self) -> None:
        with self._lock:
            self.cache_builds += 1

    def record_error(self, subsystem: str, error_type: str) -> None:
        """Record a subsystem error."""
        with self._lock:
            self.errors[f"{subsystem}:{error_type}"] += 1

    def record_warmup(self, project_count: int, duration_ms: float) -> None:
        with self._lock:
            self.counters["warmup:runs"] += 1
            self.counters["warmup:projects"] += project_count
            self.latencies["latency:warmup"].append(duration_ms)

    def record_connection(self) -> None:
        with self._lock:
            self.counters["connections:total"] += 1

    def get_snapshot(self) -> Dict[str, Any]:
        """Get current telemetry snapshot."""
        with self._lock:
            uptime = time.time() - self._start_time
            total_requests = self.counters.get("request:total", 0)

            # Calculate cache hit rate
            total_cache = self.cache_hits + self.cache_misses
            hit_rate = self.cache_hits / max(total_cache, 1)

            # Calculate average latencies
            avg_latencies = {}
            for key, samples in self.latencies.items():
                if samples:
                    avg_latencies[key.replace("latency:", "")] = round(
                        sum(samples) / len(samples), 2
                    )

            # Request breakdown
            request_breakdown = {
                k.replace("request:", ""): v
                for k, v in self.counters.items()
                if k.startswith("request:") and k != "request:total"
            }

            return {
                "uptime_seconds": round(uptime, 1),
                "uptime_human": _format_duration(uptime),
                "requests": {
                    "total": total_requests,
                    "rate_per_second": round(total_requests / max(uptime, 1), 2),
                    "breakdown": request_breakdown,
                },
                "cache": {
                    "hits": self.cache_hits,
                    "misses": self.cache_misses,
                    "hit_rate": round(hit_rate, 3),
                    "builds": self.cache_builds,
                },
                "latency_ms": avg_latencies,
                "errors": dict(self.errors),
                "warmup_runs": self.counters.get("warmup:runs", 0),
                "connections": self.counters.get("connections:total", 0),
            }

    def persist(self) -> None:
        """Persist telemetry to disk."""
        snapshot = self.get_snapshot()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        file_path = self.data_dir / f"telemetry-{today}.json"

        # Merge with existing data if file exists
        existing = {}
        if file_path.exists():
            try:
                with open(file_path) as f:
                    existing = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass

        existing["latest"] = snapshot
        existing["persisted_at"] = datetime.now(timezone.utc).isoformat()

        try:
            with open(file_path, "w") as f:
                json.dump(existing, f, indent=2, default=str)
        except OSError:
            pass


def _format_duration(seconds: float) -> str:
    """Format seconds into human-readable duration."""
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60)}s"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    return f"{hours}h {minutes}m"


# ── Global singleton ─────────────────────────────────────────────

_telemetry: Optional[Telemetry] = None


def get_telemetry() -> Telemetry:
    global _telemetry
    if _telemetry is None:
        _telemetry = Telemetry()
    return _telemetry


# ── Daemon handler ───────────────────────────────────────────────

def handle_telemetry(params: Dict[str, Any]) -> Dict[str, Any]:
    """Return current telemetry snapshot."""
    return get_telemetry().get_snapshot()
