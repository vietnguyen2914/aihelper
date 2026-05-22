"""
Subsystem Health & Failure Isolation.

Each subsystem runs isolated:
- LSP crash → doesn't kill daemon
- Watchman crash → doesn't kill daemon  
- Cache corruption → auto-repair, doesn't kill daemon
- Memory pressure → graceful degradation

Health checks track subsystem states: ok, degraded, failed, restarting.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class SubsystemState(Enum):
    OK = "ok"
    DEGRADED = "degraded"
    FAILED = "failed"
    RESTARTING = "restarting"
    DISABLED = "disabled"


class Subsystem:
    """A monitored subsystem with health checks and auto-recovery."""

    def __init__(self, name: str, check_fn: Callable[[], bool], restart_fn: Optional[Callable[[], bool]] = None):
        self.name = name
        self.state = SubsystemState.OK
        self.last_check = 0.0
        self.last_error = ""
        self.failure_count = 0
        self.max_failures = 3
        self._check_fn = check_fn
        self._restart_fn = restart_fn
        self._lock = threading.Lock()

    def check(self) -> SubsystemState:
        """Run health check. Auto-restart on failure."""
        with self._lock:
            self.last_check = time.time()
            try:
                if self._check_fn():
                    self.state = SubsystemState.OK
                    self.failure_count = 0
                    return self.state
            except Exception as e:
                self.last_error = str(e)[:200]

            self.failure_count += 1

            if self.failure_count >= self.max_failures:
                self.state = SubsystemState.FAILED
                return self.state

            # Try restart
            if self._restart_fn:
                self.state = SubsystemState.RESTARTING
                try:
                    if self._restart_fn():
                        self.state = SubsystemState.OK
                        self.failure_count = 0
                        return self.state
                except Exception:
                    pass

            self.state = SubsystemState.DEGRADED
            return self.state

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "last_error": self.last_error,
            "last_check_ago": round(time.time() - self.last_check, 1) if self.last_check else None,
        }


class SubsystemManager:
    """Manages all subsystems with periodic health checks."""

    def __init__(self):
        self.subsystems: Dict[str, Subsystem] = {}
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def register(self, name: str, check_fn: Callable[[], bool], restart_fn: Optional[Callable[[], bool]] = None) -> None:
        self.subsystems[name] = Subsystem(name, check_fn, restart_fn)

    def start_monitoring(self, interval: float = 30.0) -> None:
        """Start periodic health checks."""
        def _loop():
            while not self._stop.wait(timeout=interval):
                for sub in self.subsystems.values():
                    sub.check()
        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def health_report(self) -> Dict[str, Any]:
        return {
            "subsystems": {name: sub.to_dict() for name, sub in self.subsystems.items()},
            "overall": "ok" if all(
                s.state == SubsystemState.OK for s in self.subsystems.values()
            ) else "degraded",
        }

    def is_healthy(self) -> bool:
        return all(s.state == SubsystemState.OK for s in self.subsystems.values())


# ── Health check functions ───────────────────────────────────────

def check_watchman() -> bool:
    """Check if Watchman is running."""
    result = subprocess.run(
        ["watchman", "version"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        timeout=5,
    )
    return result.returncode == 0


def check_ramdisk() -> bool:
    """Check if RAM disk is mounted."""
    result = subprocess.run(
        ["mount"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        timeout=2,
    )
    return "/Volumes/ramdisk" in result.stdout


def check_ollama() -> bool:
    """Check if Ollama is available."""
    try:
        import urllib.request
        req = urllib.request.Request("http://localhost:11434/api/tags")
        urllib.request.urlopen(req, timeout=3)
        return True
    except Exception:
        return False


def check_cache_integrity(project_root: Path) -> bool:
    """Check if aihelper cache is not corrupted."""
    manifest = project_root / ".ai-cache" / "aihelper" / "manifest.json"
    if not manifest.exists():
        return True  # No cache is not an error
    try:
        with open(manifest) as f:
            data = json.load(f)
        return bool(data.get("version"))
    except (json.JSONDecodeError, OSError):
        return False


def repair_cache(project_root: Path) -> bool:
    """Repair corrupted cache by rebuilding."""
    try:
        from .cache import build_cache
    except ImportError:
        from cache import build_cache
    try:
        build_cache(project_root)
        return True
    except Exception:
        return False


# ── Global instance ──────────────────────────────────────────────

_manager: Optional[SubsystemManager] = None


def get_subsystem_manager() -> SubsystemManager:
    global _manager
    if _manager is None:
        _manager = SubsystemManager()
        _manager.register("watchman", check_watchman)
        _manager.register("ramdisk", check_ramdisk)
        _manager.register("ollama", check_ollama)
    return _manager


# ── Daemon handler ───────────────────────────────────────────────

def handle_subsystem_health(params: Dict[str, Any]) -> Dict[str, Any]:
    """Return subsystem health report."""
    mgr = get_subsystem_manager()
    # Run checks now
    for sub in mgr.subsystems.values():
        sub.check()
    return mgr.health_report()
