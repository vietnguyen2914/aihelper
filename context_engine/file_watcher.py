"""
file_watcher.py — Native OS file watcher với debounce.

Sử dụng watchdog (Python wrapper cho FSEvents/inotify/ReadDirectoryChangesW)
để watch file changes. Fallback polling timer nếu watchdog không có.

Kế thừa và nâng cấp từ Watchman integration hiện tại.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable, Dict, Optional, Set

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileSystemEvent
    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False


class DebouncedWatcher:
    """Watch file changes với debounce — chỉ trigger sync sau khi file ngừng thay đổi.

    Codegraph uses chokidar (Node.js) with 2-second debounce.
    We use watchdog (Python) with the same debounce strategy.
    """

    def __init__(self, project_root: Path,
                 on_change: Callable[[Set[str]], None],
                 debounce_ms: int = 2000):
        self.project_root = project_root.resolve()
        self.on_change = on_change
        self.debounce_ms = debounce_ms
        self._pending: Dict[str, float] = {}
        self._timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()
        self._observer: Optional[Observer] = None
        self._running = False

    def start(self) -> bool:
        if not HAS_WATCHDOG:
            return False
        try:
            handler = _ChangeHandler(self._on_file_event)
            self._observer = Observer()
            self._observer.schedule(handler, str(self.project_root), recursive=True)
            self._observer.start()
            self._running = True
            return True
        except Exception:
            return False

    def stop(self):
        self._running = False
        with self._lock:
            if self._timer:
                self._timer.cancel()
                self._timer = None
            self._pending.clear()
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=2)
            self._observer = None

    def is_running(self) -> bool:
        return self._running

    def _on_file_event(self, path: str):
        with self._lock:
            self._pending[path] = time.time()
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(
                self.debounce_ms / 1000.0, self._flush
            )
            self._timer.start()

    def _flush(self):
        with self._lock:
            if not self._pending:
                return
            changed = set(self._pending.keys())
            self._pending.clear()
            self._timer = None
        if changed:
            self.on_change(changed)

    def get_pending(self) -> Set[str]:
        with self._lock:
            return set(self._pending.keys())


class _ChangeHandler(FileSystemEventHandler):
    def __init__(self, callback: Callable[[str], None]):
        super().__init__()
        self._callback = callback
        self._ignored_patterns = {".git", ".ai-cache", "__pycache__", ".idea"}

    def _should_ignore(self, path: str) -> bool:
        return any(p in path for p in self._ignored_patterns)

    def on_modified(self, event: FileSystemEvent):
        if not event.is_directory and not self._should_ignore(event.src_path):
            self._callback(event.src_path)

    def on_created(self, event: FileSystemEvent):
        if not event.is_directory and not self._should_ignore(event.src_path):
            self._callback(event.src_path)

    def on_deleted(self, event: FileSystemEvent):
        if not event.is_directory and not self._should_ignore(event.src_path):
            self._callback(event.src_path)

    def on_moved(self, event: FileSystemEvent):
        if not event.is_directory and not self._should_ignore(event.dest_path):
            self._callback(event.dest_path)


# ── Polling Fallback ──────────────────────────────────────────────

class PollingWatcher:
    """Polling-based file watcher — fallback khi watchdog không available."""

    def __init__(self, project_root: Path,
                 on_change: Callable[[Set[str]], None],
                 interval: float = 2.0):
        self.project_root = project_root.resolve()
        self.on_change = on_change
        self.interval = interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._mtimes: Dict[str, float] = {}

    def start(self):
        self._build_snapshot()
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=self.interval + 1)

    def _build_snapshot(self):
        self._mtimes = {}
        for p in self.project_root.rglob("*"):
            if p.is_file() and not self._is_ignored(p):
                try:
                    self._mtimes[str(p)] = p.stat().st_mtime
                except OSError:
                    pass

    def _is_ignored(self, path: Path) -> bool:
        ignored = {".git", ".ai-cache", "__pycache__", ".idea", "node_modules"}
        return any(p in ignored for p in path.parts)

    def _loop(self):
        while self._running:
            time.sleep(self.interval)
            changed = set()
            for p in self.project_root.rglob("*"):
                if not p.is_file() or self._is_ignored(p):
                    continue
                key = str(p)
                try:
                    mtime = p.stat().st_mtime
                except OSError:
                    if key in self._mtimes:
                        changed.add(key)
                    continue
                if key not in self._mtimes or self._mtimes[key] != mtime:
                    changed.add(key)
                    self._mtimes[key] = mtime
            if changed:
                self.on_change(changed)


# ── Unified Watcher ───────────────────────────────────────────────

class FileWatcher:
    """Unified file watcher — chọn best strategy có sẵn."""

    def __init__(self, project_root: Path,
                 on_change: Callable[[Set[str]], None],
                 debounce_ms: int = 2000,
                 poll_interval: float = 2.0):
        self.watcher = DebouncedWatcher(project_root, on_change, debounce_ms)
        self.fallback = PollingWatcher(project_root, on_change, poll_interval)
        self._active = False

    def start(self) -> bool:
        if self.watcher.start():
            self._active = True
            return True
        self.fallback.start()
        self._active = True
        return False  # Returns False if using fallback

    def stop(self):
        self._active = False
        self.watcher.stop()
        self.fallback.stop()

    @property
    def is_active(self) -> bool:
        return self._active
