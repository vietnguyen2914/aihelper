"""
aihelperd — Persistent Unix-socket daemon for zero-latency AI context.

Eliminates Python startup latency (~0.44s) by running as a persistent
background process. Keeps caches warm in memory. CLI becomes a thin client.

Protocol: JSON-line over Unix socket at ~/.aihelper/aihelper.sock

Start:   aihelper daemon start
Stop:    aihelper daemon stop
Status:  aihelper daemon status
"""
from __future__ import annotations

import json
import os
import signal
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

SOCKET_PATH = Path.home() / ".aihelper" / "aihelper.sock"
PID_FILE = Path.home() / ".aihelper" / "aihelperd.pid"
LOG_FILE = Path.home() / ".aihelper" / "daemon.log"

# In-memory caches
_memory_cache: Dict[str, Dict[str, Any]] = {}  # project_root -> cached context


def _log(msg: str) -> None:
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"[{timestamp}] {msg}\n")
    except OSError:
        pass


def _resolve_project(params: Dict[str, Any]) -> Path:
    """Resolve project_root from params, defaulting to CWD."""
    root = params.get("project_root") or os.getcwd()
    return Path(root).resolve()


def _warm_cache(project_root: Path) -> Dict[str, Any]:
    """Load or return cached context for a project."""
    key = str(project_root)
    if key in _memory_cache:
        return _memory_cache[key]

    try:
        from .cache import cache_status, load_cached_context
    except ImportError:
        from cache import cache_status, load_cached_context

    status = cache_status(project_root)
    if not status.get("fresh"):
        try:
            from .cache import build_cache
        except ImportError:
            from cache import build_cache
        build_cache(project_root)

    ctx = load_cached_context(project_root)
    _memory_cache[key] = ctx
    return ctx


# ── Command Handlers ──────────────────────────────────────────────

def handle_health(params: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "status": "ok",
        "pid": os.getpid(),
        "uptime_seconds": time.time() - handle_health._start_time if hasattr(handle_health, '_start_time') else 0,
        "cached_projects": len(_memory_cache),
    }


def handle_route(params: Dict[str, Any]) -> Dict[str, Any]:
    task = params.get("task", "")
    project_root = _resolve_project(params)
    _warm_cache(project_root)
    try:
        from .router import route_task
    except ImportError:
        from router import route_task
    return route_task(task, project_root=project_root)


def handle_symbol_find(params: Dict[str, Any]) -> Dict[str, Any]:
    query = params.get("query", "")
    project_root = _resolve_project(params)
    limit = params.get("limit", 20)
    _warm_cache(project_root)
    try:
        from .symbols import find_symbols
    except ImportError:
        from symbols import find_symbols
    return find_symbols(query, project_root, limit=limit)


def handle_symbol_context(params: Dict[str, Any]) -> Dict[str, Any]:
    query = params.get("query", "")
    project_root = _resolve_project(params)
    limit = params.get("limit", 20)
    _warm_cache(project_root)
    try:
        from .symbols import symbol_context
    except ImportError:
        from symbols import symbol_context
    return symbol_context(query, project_root, limit=limit)


def handle_cache_status(params: Dict[str, Any]) -> Dict[str, Any]:
    project_root = _resolve_project(params)
    include_diff = params.get("include_diff", False)
    try:
        from .cache import cache_status
    except ImportError:
        from cache import cache_status
    return cache_status(project_root, include_diff=include_diff)


def handle_cache_build(params: Dict[str, Any]) -> Dict[str, Any]:
    project_root = _resolve_project(params)
    # Invalidate memory cache for this project
    _memory_cache.pop(str(project_root), None)
    try:
        from .cache import build_cache
    except ImportError:
        from cache import build_cache
    return build_cache(project_root)


def handle_prompt_blocks(params: Dict[str, Any]) -> Dict[str, Any]:
    project_root = _resolve_project(params)
    try:
        from .prompt_blocks import load_prompt_blocks
    except ImportError:
        from prompt_blocks import load_prompt_blocks
    return load_prompt_blocks(project_root)


def handle_diff_summary(params: Dict[str, Any]) -> Dict[str, Any]:
    project_root = _resolve_project(params)
    try:
        from .semantic_diff import semantic_diff_summary
    except ImportError:
        from semantic_diff import semantic_diff_summary
    return semantic_diff_summary(project_root)


def handle_memory_add(params: Dict[str, Any]) -> Dict[str, Any]:
    project_root = _resolve_project(params)
    topic = params.get("topic", "")
    note = params.get("note", "")
    tags = params.get("tags", [])
    try:
        from .working_memory import remember
    except ImportError:
        from working_memory import remember
    return remember(project_root, topic, note, tags=tags)


def handle_memory_recall(params: Dict[str, Any]) -> Dict[str, Any]:
    project_root = _resolve_project(params)
    query = params.get("query", "")
    limit = params.get("limit", 10)
    try:
        from .working_memory import recall
    except ImportError:
        from working_memory import recall
    return recall(project_root, query, limit=limit)


def handle_persist(params: Dict[str, Any]) -> Dict[str, Any]:
    all_projects = params.get("all", False)
    if all_projects:
        try:
            from .cache_persistence import persist_all_projects
        except ImportError:
            from cache_persistence import persist_all_projects
        github_root = Path(params.get("github_root", str(Path.home() / "github")))
        return persist_all_projects(github_root=github_root)
    else:
        project_root = _resolve_project(params)
        try:
            from .cache_persistence import persist_cache
        except ImportError:
            from cache_persistence import persist_cache
        return persist_cache(project_root)


def handle_restore(params: Dict[str, Any]) -> Dict[str, Any]:
    project_root = _resolve_project(params)
    _memory_cache.pop(str(project_root), None)
    try:
        from .cache_persistence import restore_cache
    except ImportError:
        from cache_persistence import restore_cache
    return restore_cache(project_root)


def handle_persist_status(params: Dict[str, Any]) -> Dict[str, Any]:
    project_root = _resolve_project(params)
    try:
        from .cache_persistence import cache_persist_status
    except ImportError:
        from cache_persistence import cache_persist_status
    return cache_persist_status(project_root)


def handle_patch_plan(params: Dict[str, Any]) -> Dict[str, Any]:
    task = params.get("task", "")
    files = params.get("files", [])
    project_root = _resolve_project(params)
    style = params.get("style", "unified")
    try:
        from .patch_engine import build_patch_plan
    except ImportError:
        from patch_engine import build_patch_plan
    return build_patch_plan(task, files=files, project_root=project_root, style=style)


def handle_context(params: Dict[str, Any]) -> Dict[str, Any]:
    """Return compact context for a project (the primary token-reduction path)."""
    project_root = _resolve_project(params)
    max_chars = params.get("max_context_chars", 6000)
    ctx = _warm_cache(project_root)

    try:
        from .router import route_task
    except ImportError:
        from router import route_task

    task = params.get("task", "")
    route = route_task(task, project_root=project_root) if task else {}

    return {
        "cache": ctx.get("cache", {}),
        "repo_summary": ctx.get("repo_summary", {}),
        "symbols": ctx.get("symbols", [])[:30],
        "db_schema_summary": ctx.get("db_schema_summary", {}),
        "route": route.get("recommended_next_tools", []),
        "token_budget": route.get("token_budget", {}),
    }


# ── Method Router ─────────────────────────────────────────────────

# External handlers loaded lazily
_external_handlers: Dict[str, Callable] = {}

def _load_external_handlers() -> None:
    """Lazy-load handlers from external modules to avoid circular imports."""
    global _external_handlers
    if _external_handlers:
        return
    try:
        from .confidence import handle_confidence as _hc
        from .editor_context import handle_editor_context as _hec
        from .lsp_bridge import handle_lsp_definition as _hld, handle_lsp_references as _hlr, handle_lsp_symbols as _hls
        from .warmup import warm_all_projects as _wap
        from .scheduler import handle_scheduler_snapshot as _hss, handle_scheduler_predict as _hsp, handle_scheduler_record as _hsr
        from .structural_diff import handle_structural_diff as _hsd, handle_hierarchical_context as _hhic
        from .telemetry import handle_telemetry as _ht
        from .intent_router import handle_intent_route as _hir
        from .subsystem_health import handle_subsystem_health as _hsh
        from .degradation import handle_degradation_status as _hds
        from .diagnostics import handle_diagnostics as _hdi
        from .impact_graph import handle_impact_graph as _hig, handle_classify_operation as _hco
        from .auto_apply import handle_safe_apply as _hsa, handle_intent_continuation as _hic2, handle_branch_memory as _hbm
        from .session_bootstrap import handle_bootstrap as _hboot
        from .capability_router import handle_capability_route as _hcr, handle_capability_vision as _hcv, handle_capability_ocr as _hco2, handle_capability_rerank as _hcr2, handle_capability_embed as _hce
        from .document_pipeline import handle_generate_mermaid as _hgm, handle_render_diagram as _hrd, handle_generate_presentation as _hgp, handle_convert_document as _hcd, handle_parse_document as _hpd
        _external_handlers = {
            "editor_context": _hec,
            "lsp_definition": _hld,
            "lsp_references": _hlr,
            "lsp_symbols": _hls,
            "confidence": _hc,
            "warmup_status": lambda p: _wap(),
            "scheduler_snapshot": _hss,
            "scheduler_predict": _hsp,
            "scheduler_record": _hsr,
            "structural_diff": _hsd,
            "hierarchical_context": _hhic,
            "telemetry": _ht,
            "intent_route": _hir,
            "subsystem_health": _hsh,
            "degradation_status": _hds,
            "diagnostics": _hdi,
            "impact_graph": _hig,
            "classify_operation": _hco,
            "safe_apply": _hsa,
            "intent_continuation": _hic2,
            "branch_memory": _hbm,
            "capability_route": _hcr,
            "capability_vision": _hcv,
            "capability_ocr": _hco2,
            "capability_rerank": _hcr2,
            "capability_embed": _hce,
            "generate_mermaid": _hgm,
            "render_diagram": _hrd,
            "generate_presentation": _hgp,
            "convert_document": _hcd,
            "parse_document": _hpd,
            "bootstrap": _hboot,
        }
    except ImportError:
        from confidence import handle_confidence as _hc
        from editor_context import handle_editor_context as _hec
        from lsp_bridge import handle_lsp_definition as _hld, handle_lsp_references as _hlr, handle_lsp_symbols as _hls
        from warmup import warm_all_projects as _wap
        from scheduler import handle_scheduler_snapshot as _hss, handle_scheduler_predict as _hsp, handle_scheduler_record as _hsr
        from structural_diff import handle_structural_diff as _hsd, handle_hierarchical_context as _hhic
        from telemetry import handle_telemetry as _ht
        from intent_router import handle_intent_route as _hir
        from subsystem_health import handle_subsystem_health as _hsh
        from degradation import handle_degradation_status as _hds
        from diagnostics import handle_diagnostics as _hdi
        from impact_graph import handle_impact_graph as _hig, handle_classify_operation as _hco
        from auto_apply import handle_safe_apply as _hsa, handle_intent_continuation as _hic2, handle_branch_memory as _hbm
        from session_bootstrap import handle_bootstrap as _hboot
        from capability_router import handle_capability_route as _hcr, handle_capability_vision as _hcv, handle_capability_ocr as _hco2, handle_capability_rerank as _hcr2, handle_capability_embed as _hce
        from document_pipeline import handle_generate_mermaid as _hgm, handle_render_diagram as _hrd, handle_generate_presentation as _hgp, handle_convert_document as _hcd, handle_parse_document as _hpd
        _external_handlers = {
            "editor_context": _hec,
            "lsp_definition": _hld,
            "lsp_references": _hlr,
            "lsp_symbols": _hls,
            "confidence": _hc,
            "warmup_status": lambda p: _wap(),
            "scheduler_snapshot": _hss,
            "scheduler_predict": _hsp,
            "scheduler_record": _hsr,
            "structural_diff": _hsd,
            "hierarchical_context": _hhic,
            "telemetry": _ht,
            "intent_route": _hir,
            "subsystem_health": _hsh,
            "degradation_status": _hds,
            "diagnostics": _hdi,
            "impact_graph": _hig,
            "classify_operation": _hco,
            "safe_apply": _hsa,
            "intent_continuation": _hic2,
            "branch_memory": _hbm,
            "capability_route": _hcr,
            "capability_vision": _hcv,
            "capability_ocr": _hco2,
            "capability_rerank": _hcr2,
            "capability_embed": _hce,
            "generate_mermaid": _hgm,
            "render_diagram": _hrd,
            "generate_presentation": _hgp,
            "convert_document": _hcd,
            "parse_document": _hpd,
            "bootstrap": _hboot,
        }

def _get_methods() -> Dict[str, Callable]:
    _load_external_handlers()
    return {
        "health": handle_health,
        "route": handle_route,
        "symbol_find": handle_symbol_find,
        "symbol_context": handle_symbol_context,
        "cache_status": handle_cache_status,
        "cache_build": handle_cache_build,
        "prompt_blocks": handle_prompt_blocks,
        "diff_summary": handle_diff_summary,
        "memory_add": handle_memory_add,
        "memory_recall": handle_memory_recall,
        "persist": handle_persist,
        "restore": handle_restore,
        "persist_status": handle_persist_status,
        "patch_plan": handle_patch_plan,
        "context": handle_context,
        **_external_handlers,
    }


def handle_request(raw: str) -> str:
    """Process a single JSON-line request, return JSON-line response."""
    try:
        req = json.loads(raw)
    except json.JSONDecodeError:
        return json.dumps({"error": "invalid_json", "id": None})

    method = req.get("method", "")
    params = req.get("params", {})
    req_id = req.get("id")

    methods = _get_methods()
    handler = methods.get(method)
    if not handler:
        return json.dumps({"error": f"unknown_method: {method}", "id": req_id})

    start = time.perf_counter()
    try:
        result = handler(params)
        elapsed = (time.perf_counter() - start) * 1000
        # Record telemetry (robust import for both relative and absolute contexts)
        try:
            from .telemetry import get_telemetry as _gt
        except ImportError:
            try:
                from telemetry import get_telemetry as _gt
            except ImportError:
                _gt = None
        if _gt:
            try:
                _gt().record_request(method, elapsed)
            except Exception:
                pass
        # Auto-feed scheduler for behavioral learning
        if method in ("route", "symbol_find", "symbol_context", "context", "lsp_definition", "lsp_references"):
            try:
                from .scheduler import get_scheduler as _gts
                s = _gts()
                if method == "route":
                    s.record_route(params.get("task", ""), params.get("project_root", ""))
                elif method in ("symbol_find", "symbol_context"):
                    s.record_symbol_query(params.get("query", ""))
            except Exception:
                pass

        return json.dumps({"result": result, "id": req_id, "_elapsed_ms": round(elapsed, 2)}, default=str)
    except Exception as exc:
        elapsed = (time.perf_counter() - start) * 1000
        try:
            from .telemetry import get_telemetry as _gte
        except ImportError:
            try:
                from telemetry import get_telemetry as _gte
            except ImportError:
                _gte = None
        if _gte:
            try:
                _gte().record_error("handler", type(exc).__name__)
            except Exception:
                pass
        return json.dumps({"error": str(exc), "id": req_id, "_elapsed_ms": round(elapsed, 2)})


def _periodic_persist(stop_event: threading.Event) -> None:
    """Background thread: persist all caches every 8 hours."""
    interval = 8 * 3600  # 8 hours
    while not stop_event.wait(timeout=interval):
        try:
            from .cache_persistence import persist_all_projects
        except ImportError:
            from cache_persistence import persist_all_projects
        try:
            persist_all_projects()
            _log("periodic persist completed")
        except Exception as exc:
            _log(f"periodic persist failed: {exc}")


def run_daemon() -> None:
    """Main daemon loop — listen on Unix socket."""
    handle_health._start_time = time.time()  # type: ignore[attr-defined]

    # Ensure socket directory exists
    SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Remove stale socket
    if SOCKET_PATH.exists():
        SOCKET_PATH.unlink()

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(SOCKET_PATH))
    server.listen(5)
    os.chmod(str(SOCKET_PATH), 0o600)

    # Write PID
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))

    # Start periodic persist thread
    stop_event = threading.Event()
    persist_thread = threading.Thread(target=_periodic_persist, args=(stop_event,), daemon=True)
    persist_thread.start()

    # Start background warmup
    try:
        from .warmup import BackgroundWarmer
    except ImportError:
        from warmup import BackgroundWarmer
    warmer = BackgroundWarmer()
    warmer.start()

    # Start subsystem health monitoring
    try:
        from .subsystem_health import get_subsystem_manager
        sm = get_subsystem_manager()
        sm.start_monitoring(interval=60)
        _log("subsystem health monitoring started")
    except Exception:
        pass

    # Start telemetry persistence thread
    def _persist_telemetry_loop():
        while True:
            time.sleep(300)  # Every 5 minutes
            try:
                from .telemetry import get_telemetry
                get_telemetry().persist()
            except Exception:
                pass
    threading.Thread(target=_persist_telemetry_loop, daemon=True).start()

    _log(f"aihelperd started on {SOCKET_PATH} (pid={os.getpid()}) (warmup=on health=on telemetry=on)")

    # Handle graceful shutdown
    def shutdown(signum=None, frame=None):
        _log("shutting down...")
        stop_event.set()
        try:
            from .cache_persistence import persist_all_projects
        except ImportError:
            from cache_persistence import persist_all_projects
        try:
            persist_all_projects()
            _log("final persist completed")
        except Exception:
            pass
        server.close()
        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink()
        if PID_FILE.exists():
            PID_FILE.unlink()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    # Accept loop
    buffer_size = 65536
    while True:
        try:
            conn, _ = server.accept()
        except (OSError, KeyboardInterrupt):
            break

        try:
            data = b""
            while True:
                chunk = conn.recv(buffer_size)
                if not chunk:
                    break
                data += chunk
                if b"\n" in data:
                    break

            raw = data.decode("utf-8", errors="replace").strip()
            if raw:
                response = handle_request(raw)
                conn.sendall((response + "\n").encode("utf-8"))
        except Exception as exc:
            _log(f"connection error: {exc}")
        finally:
            conn.close()

    shutdown()


# ── Client (thin CLI) ─────────────────────────────────────────────

def is_daemon_running() -> bool:
    """Check if daemon is running and socket is responsive."""
    if not SOCKET_PATH.exists():
        return False
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(1.0)
        sock.connect(str(SOCKET_PATH))
        sock.sendall(json.dumps({"method": "health", "params": {}, "id": 1}).encode() + b"\n")
        response = sock.recv(4096)
        sock.close()
        try:
            data = json.loads(response.decode())
            return data.get("result", {}).get("status") == "ok"
        except (json.JSONDecodeError, KeyError):
            return False
    except (OSError, socket.timeout):
        return False


def daemon_call(method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 5.0) -> Dict[str, Any]:
    """Send a request to the daemon and return the result."""
    if not is_daemon_running():
        return {"error": "daemon_not_running", "hint": "Start with: aihelper daemon start"}

    request = json.dumps({
        "method": method,
        "params": params or {},
        "id": 1,
    })

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    sock.connect(str(SOCKET_PATH))
    sock.sendall(request.encode() + b"\n")

    data = b""
    while True:
        chunk = sock.recv(65536)
        if not chunk:
            break
        data += chunk
        if b"\n" in data:
            break

    sock.close()
    response = json.loads(data.decode("utf-8", errors="replace").strip())
    if "error" in response:
        return {"error": response["error"]}
    return response.get("result", response)


def start_daemon() -> Dict[str, Any]:
    """Start the daemon as a background process."""
    if is_daemon_running():
        return {"status": "already_running", "pid": _read_pid()}

    import subprocess
    main_py = Path(__file__).resolve().parent / "main.py"

    proc = subprocess.Popen(
        [sys.executable, str(main_py), "daemon", "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    # Wait for socket to appear
    for _ in range(30):
        if is_daemon_running():
            return {"status": "started", "pid": proc.pid}
        time.sleep(0.1)

    return {"status": "start_pending", "pid": proc.pid, "note": "Daemon may still be starting"}


def stop_daemon() -> Dict[str, Any]:
    """Stop the daemon gracefully."""
    pid = _read_pid()
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            time.sleep(0.5)
        except ProcessLookupError:
            pass

    # Clean up socket
    if SOCKET_PATH.exists():
        SOCKET_PATH.unlink()

    if PID_FILE.exists():
        PID_FILE.unlink()

    return {"status": "stopped"}


def daemon_status() -> Dict[str, Any]:
    """Get daemon status."""
    running = is_daemon_running()
    pid = _read_pid() if running else None
    return {
        "running": running,
        "pid": pid,
        "socket": str(SOCKET_PATH),
        "socket_exists": SOCKET_PATH.exists(),
    }


def _read_pid() -> Optional[int]:
    if PID_FILE.exists():
        try:
            return int(PID_FILE.read_text().strip())
        except (ValueError, OSError):
            pass
    return None
