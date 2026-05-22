"""
Graceful Degradation — subsystem fallback modes.

When a subsystem fails, the daemon degrades gracefully instead of crashing:
- LSP dead → symbol graph only
- Ollama unavailable → cloud routing only
- RAM disk offline → SSD cache
- Watchman dead → polling fallback

Each subsystem has: primary, degraded, fallback modes.
"""
from __future__ import annotations

import shutil
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class DegradationLevel(Enum):
    FULL = "full"           # All subsystems healthy
    DEGRADED = "degraded"   # Some subsystems in fallback mode
    MINIMAL = "minimal"     # Core only (daemon + symbol graph)
    OFFLINE = "offline"     # No external services


class DegradationManager:
    """Manages graceful degradation across all subsystems."""

    def __init__(self):
        self.subsystem_states: Dict[str, str] = {}  # subsystem -> "ok"|"degraded"|"failed"
        self._fallback_handlers: Dict[str, Dict[str, Callable]] = {}

    def register_subsystem(
        self,
        name: str,
        primary_fn: Callable,
        fallback_fn: Optional[Callable] = None,
        is_critical: bool = False,
    ) -> None:
        """Register a subsystem with optional fallback."""
        self.subsystem_states[name] = "ok"
        self._fallback_handlers[name] = {
            "primary": primary_fn,
            "fallback": fallback_fn,
            "critical": is_critical,
        }

    def mark_degraded(self, name: str) -> None:
        """Mark a subsystem as degraded."""
        self.subsystem_states[name] = "degraded"

    def mark_failed(self, name: str) -> None:
        """Mark a subsystem as failed."""
        self.subsystem_states[name] = "failed"

    def mark_ok(self, name: str) -> None:
        """Mark a subsystem as healthy."""
        self.subsystem_states[name] = "ok"

    def get_level(self) -> DegradationLevel:
        """Get current degradation level."""
        critical_failures = sum(
            1 for name, state in self.subsystem_states.items()
            if state == "failed" and self._fallback_handlers.get(name, {}).get("critical", False)
        )
        degraded_count = sum(
            1 for s in self.subsystem_states.values() if s in ("degraded", "failed")
        )
        total = max(len(self.subsystem_states), 1)

        if critical_failures >= 2:
            return DegradationLevel.MINIMAL
        if degraded_count / total > 0.5:
            return DegradationLevel.MINIMAL
        if degraded_count > 0:
            return DegradationLevel.DEGRADED
        return DegradationLevel.FULL

    def call(self, name: str, *args, **kwargs) -> Any:
        """Call a subsystem with automatic fallback."""
        handler = self._fallback_handlers.get(name, {})
        primary = handler.get("primary")

        if not primary:
            return None

        # Try primary
        try:
            result = primary(*args, **kwargs)
            self.mark_ok(name)
            return result
        except Exception:
            pass

        # Try fallback
        fallback = handler.get("fallback")
        if fallback:
            try:
                self.mark_degraded(name)
                return fallback(*args, **kwargs)
            except Exception:
                pass

        self.mark_failed(name)
        return None

    def status_report(self) -> Dict[str, Any]:
        """Get degradation status report."""
        return {
            "level": self.get_level().value,
            "subsystems": dict(self.subsystem_states),
            "degraded_count": sum(1 for s in self.subsystem_states.values() if s == "degraded"),
            "failed_count": sum(1 for s in self.subsystem_states.values() if s == "failed"),
            "critical_failures": sum(
                1 for name, state in self.subsystem_states.items()
                if state == "failed" and self._fallback_handlers.get(name, {}).get("critical", False)
            ),
        }


# ── Built-in fallback functions ──────────────────────────────────

def lsp_primary(file_path: str, project_root: str) -> Dict:
    """Primary: use LSP bridge."""
    try:
        from .lsp_bridge import find_definition
    except ImportError:
        from lsp_bridge import find_definition
    return find_definition("", file_path, 1, 1, __import__('pathlib').Path(project_root))


def lsp_fallback(file_path: str, project_root: str) -> Dict:
    """Fallback: use symbol graph only."""
    try:
        from .symbols import find_symbols
    except ImportError:
        from symbols import find_symbols
    from pathlib import Path
    # Extract symbol name from file path
    file_stem = Path(file_path).stem
    return find_symbols(file_stem, Path(project_root), limit=20)


def ollama_primary(prompt: str, model: str = "qwen2.5:3b") -> Optional[str]:
    """Primary: use local Ollama."""
    import subprocess, json
    result = subprocess.run(
        ["ollama", "run", model, prompt],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        timeout=30,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def ollama_fallback_fn(prompt: str, model: str = "qwen2.5:3b") -> Optional[str]:
    """Fallback: return None, caller routes to cloud."""
    return None  # Signal to use cloud routing


def ramdisk_primary() -> bool:
    """Primary: check RAM disk available."""
    import subprocess
    result = subprocess.run(["mount"], stdout=subprocess.PIPE, text=True)
    return "/Volumes/ramdisk" in result.stdout


def ramdisk_fallback() -> bool:
    """Fallback: RAM disk unavailable, notify but continue with SSD."""
    return True  # SSD is always available


# ── Global instance ──────────────────────────────────────────────

_degradation: Optional[DegradationManager] = None


def get_degradation_manager() -> DegradationManager:
    global _degradation
    if _degradation is None:
        _degradation = DegradationManager()
        # Register subsystems
        _degradation.register_subsystem("lsp", lsp_primary, lsp_fallback, is_critical=False)
        _degradation.register_subsystem("ollama", ollama_primary, ollama_fallback_fn, is_critical=False)
        _degradation.register_subsystem("ramdisk", ramdisk_primary, ramdisk_fallback, is_critical=False)
    return _degradation


# ── Daemon handler ───────────────────────────────────────────────

def handle_degradation_status(params: Dict[str, Any]) -> Dict[str, Any]:
    """Return degradation status report."""
    return get_degradation_manager().status_report()
