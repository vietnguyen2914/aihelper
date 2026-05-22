"""
Semantic Scheduler — AI-native orchestration layer.

The daemon's "brain" that tracks:
- Recently edited files (by recency & frequency)
- Active git branch
- Recent build errors
- Hot symbols (frequently queried)
- Unstable modules (frequently changed)
- Recent conversation context

Uses this to:
- Prewarm relevant caches
- Reprioritize cache freshness
- Rerank symbol importance
- Predict next queries
- Feed editor-awareness signals

This is what turns aihelper from a "tool" into an "operating system for AI coding".
"""
from __future__ import annotations

import json
import os
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


# ── Data Structures ──────────────────────────────────────────────

class SemanticScheduler:
    """Tracks semantic signals and schedules preemptive actions."""

    def __init__(self, state_dir: Optional[Path] = None):
        self.state_dir = state_dir or Path.home() / ".aihelper" / "scheduler"
        self.state_dir.mkdir(parents=True, exist_ok=True)

        # ── Hot signals ──────────────────────────────────────────
        self.recent_edits: Dict[str, List[float]] = defaultdict(list)     # file -> [timestamps]
        self.symbol_queries: Dict[str, int] = defaultdict(int)            # symbol -> count
        self.active_branches: Dict[str, str] = {}                         # project -> branch
        self.build_errors: Dict[str, List[Dict]] = defaultdict(list)      # project -> [{file, error, time}]
        self.conversation_context: List[str] = []                          # recent task descriptions
        self.hot_modules: Dict[str, float] = defaultdict(float)           # module -> heat score

        # ── Derived rankings ─────────────────────────────────────
        self.module_rankings: Dict[str, float] = {}                       # module -> importance
        self.symbol_heat: Dict[str, float] = {}                           # symbol -> query frequency score

        # ── Metadata ─────────────────────────────────────────────
        self._last_save = 0.0
        self._save_interval = 60.0  # Save state every 60 seconds
        self._decay_window = 3600.0  # 1 hour decay window

        self._load_state()

    # ── Signal Ingestion ──────────────────────────────────────────

    def record_edit(self, file_path: str, project_root: Optional[str] = None) -> None:
        """Record that a file was edited."""
        now = time.time()
        self.recent_edits[file_path].append(now)
        # Keep only recent edits
        cutoff = now - self._decay_window
        self.recent_edits[file_path] = [t for t in self.recent_edits[file_path] if t > cutoff]
        if not self.recent_edits[file_path]:
            del self.recent_edits[file_path]

        # Boost module ranking
        module = self._file_to_module(file_path)
        self.hot_modules[module] = self.hot_modules.get(module, 0) + 1.0

        self._maybe_save()

    def record_symbol_query(self, symbol: str) -> None:
        """Record that a symbol was queried."""
        self.symbol_queries[symbol] += 1
        # Decay old queries
        total = sum(self.symbol_queries.values())
        if total > 0:
            self.symbol_heat = {
                sym: count / total
                for sym, count in self.symbol_queries.items()
            }
        self._maybe_save()

    def record_branch(self, project_root: str, branch: str) -> None:
        """Record active git branch for a project."""
        self.active_branches[project_root] = branch

    def record_build_error(self, project_root: str, file_path: str, error: str) -> None:
        """Record a build error."""
        self.build_errors[project_root].append({
            "file": file_path,
            "error": error[:200],
            "time": datetime.now(timezone.utc).isoformat(),
        })
        # Keep only last 50 errors per project
        if len(self.build_errors[project_root]) > 50:
            self.build_errors[project_root] = self.build_errors[project_root][-50:]

        # Mark module as unstable
        module = self._file_to_module(file_path)
        self.hot_modules[module] = self.hot_modules.get(module, 0) + 5.0  # Errors are important

        self._maybe_save()

    def record_conversation(self, task_description: str) -> None:
        """Record a conversation context for predictive prefetching."""
        self.conversation_context.append(task_description[:200])
        if len(self.conversation_context) > 20:
            self.conversation_context = self.conversation_context[-20:]

    def record_route(self, task: str, project_root: str) -> None:
        """Record a routed task for context tracking."""
        self.record_conversation(task)

    # ── Intelligence Queries ──────────────────────────────────────

    def get_hot_files(self, top_n: int = 10) -> List[Dict[str, Any]]:
        """Get most recently/frequently edited files."""
        now = time.time()
        scored = []
        for file_path, timestamps in self.recent_edits.items():
            recency = max(timestamps) if timestamps else 0
            frequency = len(timestamps)
            score = frequency * 10 + (recency - (now - self._decay_window)) / 100
            scored.append({"file": file_path, "score": round(score, 1), "edits": frequency})
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_n]

    def get_hot_symbols(self, top_n: int = 10) -> List[Dict[str, Any]]:
        """Get most frequently queried symbols."""
        ranked = sorted(self.symbol_heat.items(), key=lambda x: x[1], reverse=True)
        return [{"symbol": sym, "heat": round(heat, 3)} for sym, heat in ranked[:top_n]]

    def get_unstable_modules(self, top_n: int = 5) -> List[Dict[str, Any]]:
        """Get modules with recent errors or frequent changes."""
        ranked = sorted(self.hot_modules.items(), key=lambda x: x[1], reverse=True)
        return [{"module": mod, "heat": round(heat, 1)} for mod, heat in ranked[:top_n]]

    def get_recent_errors(self, project_root: Optional[str] = None) -> List[Dict]:
        """Get recent build errors."""
        if project_root:
            return self.build_errors.get(project_root, [])[-10:]
        all_errors = []
        for errors in self.build_errors.values():
            all_errors.extend(errors)
        all_errors.sort(key=lambda e: e.get("time", ""), reverse=True)
        return all_errors[:20]

    def get_active_branch(self, project_root: str) -> Optional[str]:
        """Get active git branch for a project."""
        return self.active_branches.get(project_root)

    def get_context_snapshot(self) -> Dict[str, Any]:
        """Get a full snapshot of the scheduler state for AI context."""
        return {
            "hot_files": self.get_hot_files(10),
            "hot_symbols": self.get_hot_symbols(10),
            "unstable_modules": self.get_unstable_modules(5),
            "recent_errors": self.get_recent_errors(),
            "active_branches": self.active_branches,
            "recent_tasks": self.conversation_context[-5:],
            "total_tracked_edits": sum(len(v) for v in self.recent_edits.values()),
            "total_symbol_queries": sum(self.symbol_queries.values()),
        }

    def predict_next_actions(self) -> List[Dict[str, Any]]:
        """Predict what the user might need next based on context."""
        predictions = []

        # 1. If there are hot files being edited, suggest related symbols
        hot_files = self.get_hot_files(5)
        if hot_files:
            predictions.append({
                "action": "prefetch_symbols_for_files",
                "files": [f["file"] for f in hot_files[:3]],
                "confidence": 0.8,
            })

        # 2. If there are build errors, suggest diagnostics
        recent_errors = self.get_recent_errors()
        if recent_errors:
            predictions.append({
                "action": "run_diagnostics",
                "files": list({e["file"] for e in recent_errors[:5]}),
                "confidence": 0.9,
            })

        # 3. If there are hot symbols, suggest pre-warming their context
        hot_symbols = self.get_hot_symbols(5)
        if hot_symbols:
            predictions.append({
                "action": "prewarm_symbol_context",
                "symbols": [s["symbol"] for s in hot_symbols],
                "confidence": 0.7,
            })

        # 4. If unstable modules found, suggest deeper analysis
        unstable = self.get_unstable_modules(3)
        if unstable:
            predictions.append({
                "action": "analyze_unstable_modules",
                "modules": [m["module"] for m in unstable],
                "confidence": 0.6,
            })

        return predictions

    # ── Persistence ──────────────────────────────────────────────

    def _maybe_save(self) -> None:
        """Save state periodically."""
        now = time.time()
        if now - self._last_save < self._save_interval:
            return
        self._save_state()

    def _save_state(self) -> None:
        """Persist scheduler state to disk."""
        state = {
            "recent_edits": {k: v for k, v in self.recent_edits.items()},
            "symbol_queries": dict(self.symbol_queries),
            "active_branches": self.active_branches,
            "build_errors": dict(self.build_errors),
            "conversation_context": self.conversation_context,
            "hot_modules": dict(self.hot_modules),
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        state_file = self.state_dir / "scheduler_state.json"
        try:
            with open(state_file, "w") as f:
                json.dump(state, f, indent=2, default=str)
        except OSError:
            pass
        self._last_save = time.time()

    def _load_state(self) -> None:
        """Restore scheduler state from disk."""
        state_file = self.state_dir / "scheduler_state.json"
        if not state_file.exists():
            return
        try:
            with open(state_file) as f:
                state = json.load(f)
            self.recent_edits = defaultdict(list, state.get("recent_edits", {}))
            self.symbol_queries = defaultdict(int, state.get("symbol_queries", {}))
            self.active_branches = state.get("active_branches", {})
            self.build_errors = defaultdict(list, state.get("build_errors", {}))
            self.conversation_context = state.get("conversation_context", [])
            self.hot_modules = defaultdict(float, state.get("hot_modules", {}))
        except (json.JSONDecodeError, OSError):
            pass

    # ── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _file_to_module(file_path: str) -> str:
        """Extract module name from file path."""
        parts = Path(file_path).parts
        # Find the first meaningful directory after src/app/lib
        key_dirs = {"src", "app", "lib", "modules", "components", "services", "controllers"}
        for i, part in enumerate(parts):
            if part.lower() in key_dirs and i + 1 < len(parts):
                return parts[i + 1]
        # Fallback: parent directory
        if len(parts) >= 2:
            return parts[-2]
        return "root"


# ── Global singleton ─────────────────────────────────────────────

_scheduler: Optional[SemanticScheduler] = None


def get_scheduler() -> SemanticScheduler:
    """Get or create the global semantic scheduler."""
    global _scheduler
    if _scheduler is None:
        _scheduler = SemanticScheduler()
    return _scheduler


# ── Daemon handlers ──────────────────────────────────────────────

def handle_scheduler_snapshot(params: Dict[str, Any]) -> Dict[str, Any]:
    """Return full scheduler context snapshot."""
    return get_scheduler().get_context_snapshot()


def handle_scheduler_predict(params: Dict[str, Any]) -> Dict[str, Any]:
    """Return predicted next actions."""
    return {"predictions": get_scheduler().predict_next_actions()}


def handle_scheduler_record(params: Dict[str, Any]) -> Dict[str, Any]:
    """Record a signal into the scheduler."""
    s = get_scheduler()
    signal_type = params.get("type", "")
    if signal_type == "edit":
        s.record_edit(params.get("file_path", ""), params.get("project_root"))
    elif signal_type == "symbol_query":
        s.record_symbol_query(params.get("symbol", ""))
    elif signal_type == "branch":
        s.record_branch(params.get("project_root", ""), params.get("branch", ""))
    elif signal_type == "build_error":
        s.record_build_error(params.get("project_root", ""), params.get("file_path", ""), params.get("error", ""))
    elif signal_type == "route":
        s.record_route(params.get("task", ""), params.get("project_root", ""))
    return {"recorded": True, "type": signal_type}
