"""
Background warmup daemon — pre-computes summaries and warms caches during idle time.

Runs as a background thread in aihelperd. Tasks:
1. Pre-warm all project caches at startup
2. Regenerate prompt blocks periodically
3. Generate git summaries
4. Refresh DB schema summaries
5. Ranking refresh

Goal: "instant feel" — zero latency for common queries.
"""
from __future__ import annotations

import time
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional


def discover_all_projects(github_root: Optional[Path] = None, extra_roots: Optional[List[Path]] = None) -> List[Path]:
    """Discover all git projects for warming."""
    if github_root is None:
        github_root = Path.home() / "github"
    
    roots: List[Path] = []
    if github_root.exists():
        for git_dir in sorted(github_root.glob("*/.git")):
            roots.append(git_dir.parent.resolve())
    for extra in (extra_roots or []):
        if extra.exists():
            roots.append(extra.resolve())
    
    # Deduplicate
    seen = set()
    unique = []
    for r in roots:
        key = str(r)
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


def warm_single_project(project_root: Path) -> Dict:
    """Warm all caches for a single project."""
    result = {"project": str(project_root), "steps": []}
    
    try:
        from .cache import cache_status, build_cache, warm_project
    except ImportError:
        from cache import cache_status, build_cache, warm_project
    
    # Step 1: Build/refresh cache
    status = cache_status(project_root)
    if not status.get("fresh"):
        try:
            build_cache(project_root)
            result["steps"].append("cache_built")
        except Exception as e:
            result["steps"].append(f"cache_build_failed:{e}")
    else:
        result["steps"].append("cache_fresh")
    
    # Step 2: Build prompt blocks
    try:
        from .prompt_blocks import build_prompt_blocks
    except ImportError:
        from prompt_blocks import build_prompt_blocks
    
    try:
        blocks = build_prompt_blocks(project_root)
        block_count = len(blocks.get("blocks", {}))
        result["steps"].append(f"prompt_blocks:{block_count}")
    except Exception as e:
        result["steps"].append(f"prompt_blocks_failed:{e}")
    
    # Step 3: Pre-load symbols into memory
    try:
        from .symbols import find_symbols
    except ImportError:
        from symbols import find_symbols
    # Touch a common symbol to warm the index
    try:
        find_symbols("main", project_root, limit=5)
        result["steps"].append("symbols_warmed")
    except Exception:
        pass
    
    # Step 4: Restore from persist if needed
    try:
        from .cache_persistence import auto_restore_if_needed
    except ImportError:
        from cache_persistence import auto_restore_if_needed
    
    try:
        restore = auto_restore_if_needed(project_root)
        if restore.get("restored"):
            result["steps"].append("cache_restored_from_ssd")
    except Exception:
        pass
    
    return result


def warm_all_projects(github_root: Optional[Path] = None, extra_roots: Optional[List[Path]] = None) -> Dict:
    """Warm all discovered projects. Called at daemon startup."""
    projects = discover_all_projects(github_root, extra_roots)
    results = []
    
    for project in projects:
        try:
            result = warm_single_project(project)
            results.append(result)
        except Exception as e:
            results.append({"project": str(project), "error": str(e)})
    
    return {
        "total_projects": len(projects),
        "warmed": sum(1 for r in results if "error" not in r),
        "failed": sum(1 for r in results if "error" in r),
        "results": results,
    }


class BackgroundWarmer:
    """Manages background warmup tasks with configurable intervals."""
    
    def __init__(self, github_root: Optional[Path] = None, extra_roots: Optional[List[Path]] = None):
        self.github_root = github_root or Path.home() / "github"
        self.extra_roots = extra_roots or []
        self._stop = threading.Event()
        self._tasks: Dict[str, Dict] = {
            "prompt_blocks_refresh": {"interval": 3600, "last_run": 0},     # Every hour
            "cache_health_check": {"interval": 300, "last_run": 0},          # Every 5 min
            "persist_check": {"interval": 28800, "last_run": 0},             # Every 8 hours
            "ranking_refresh": {"interval": 7200, "last_run": 0},            # Every 2 hours
        }
    
    def start(self) -> None:
        """Start background warmup thread."""
        thread = threading.Thread(target=self._run_loop, daemon=True)
        thread.start()
    
    def stop(self) -> None:
        """Stop background warmup."""
        self._stop.set()
    
    def _should_run(self, task_name: str) -> bool:
        task = self._tasks[task_name]
        elapsed = time.time() - task["last_run"]
        return elapsed >= task["interval"]
    
    def _run_loop(self) -> None:
        """Main warmup loop."""
        # Initial full warmup
        try:
            warm_all_projects(self.github_root, self.extra_roots)
        except Exception:
            pass
        
        while not self._stop.wait(timeout=30):  # Check every 30 seconds
            try:
                projects = discover_all_projects(self.github_root, self.extra_roots)
                
                for task_name, task in self._tasks.items():
                    if not self._should_run(task_name):
                        continue
                    
                    task["last_run"] = time.time()
                    
                    if task_name == "prompt_blocks_refresh":
                        self._refresh_prompt_blocks(projects)
                    elif task_name == "cache_health_check":
                        self._check_cache_health(projects)
                    elif task_name == "persist_check":
                        self._run_persist(projects)
                    elif task_name == "ranking_refresh":
                        self._refresh_rankings(projects)
                        
            except Exception:
                pass
    
    def _refresh_prompt_blocks(self, projects: List[Path]) -> None:
        for project in projects:
            try:
                from .prompt_blocks import build_prompt_blocks
            except ImportError:
                from prompt_blocks import build_prompt_blocks
            try:
                build_prompt_blocks(project)
            except Exception:
                pass
    
    def _check_cache_health(self, projects: List[Path]) -> None:
        for project in projects:
            try:
                from .cache import cache_status, build_cache
            except ImportError:
                from cache import cache_status, build_cache
            try:
                status = cache_status(project)
                if not status.get("fresh"):
                    build_cache(project)
            except Exception:
                pass
    
    def _run_persist(self, projects: List[Path]) -> None:
        try:
            from .cache_persistence import persist_all_projects
        except ImportError:
            from cache_persistence import persist_all_projects
        try:
            persist_all_projects(github_root=self.github_root)
        except Exception:
            pass
    
    def _refresh_rankings(self, projects: List[Path]) -> None:
        """Refresh file importance rankings based on recent git activity."""
        for project in projects:
            try:
                from .prompt_blocks import build_prompt_blocks
            except ImportError:
                from prompt_blocks import build_prompt_blocks
            try:
                # Rebuilding prompt blocks includes ranking refresh
                build_prompt_blocks(project)
            except Exception:
                pass
