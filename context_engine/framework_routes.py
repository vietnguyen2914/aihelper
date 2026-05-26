"""
framework_routes.py — Phát hiện web framework routes và link đến handlers.

Hỗ trợ: Django, Flask, FastAPI, Express, NestJS, Laravel, Spring,
        Gin, chi, gorilla/mux, Axum, actix, Rocket, ASP.NET, React Router.

Mỗi route được lưu dưới dạng symbol 'route' với edges → handler symbols.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional


# ── Framework Detectors ───────────────────────────────────────────

def detect_framework_routes(file_path: str, content: str,
                            language: str) -> List[Dict[str, Any]]:
    """Detect all routes in a file."""
    routes = []
    suffix = Path(file_path).suffix.lower()

    if language == "python":
        if file_path.endswith("urls.py"):
            routes = _detect_django_routes(file_path, content)
        if not routes:
            routes = _detect_flask_routes(file_path, content)
        if not routes:
            routes = _detect_fastapi_routes(file_path, content)

    elif language in ("javascript", "typescript", "tsx"):
        routes = _detect_express_routes(file_path, content)
        if not routes:
            routes = _detect_nestjs_routes(file_path, content)
        if not routes:
            routes = _detect_react_router_routes(file_path, content)

    elif language == "java":
        routes = _detect_spring_routes(file_path, content)

    elif language == "php":
        if file_path.endswith("web.php") or "routes" in file_path:
            routes = _detect_laravel_routes(file_path, content)

    elif language == "go":
        routes = _detect_gin_routes(file_path, content)

    elif language == "rust":
        routes = _detect_axum_routes(file_path, content)

    elif language == "csharp":
        routes = _detect_aspnet_routes(file_path, content)

    return routes


# ── Django ────────────────────────────────────────────────────────

def _detect_django_routes(file_path: str, content: str) -> List[Dict]:
    routes = []
    # path('url/', view_handler, name='...')
    # re_path(r'^regex$', view_handler)
    # url(r'^regex$', view_handler)
    for m in re.finditer(
        r"""(?:path|re_path|url)\s*\(\s*["']([^"']+)["']\s*,\s*(\w[\w.]*)""",
        content
    ):
        routes.append({
            "method": "ALL", "path": m.group(1),
            "handler": m.group(2),
            "file": file_path,
            "line": content[:m.start()].count("\n") + 1,
            "framework": "django",
        })

    # include() patterns
    for m in re.finditer(r'include\s*\(\s*["\']([^"\']+)["\']', content):
        routes.append({
            "method": "INCLUDE", "path": m.group(1),
            "handler": "include",
            "file": file_path,
            "line": content[:m.start()].count("\n") + 1,
            "framework": "django",
        })
    return routes


# ── Flask ─────────────────────────────────────────────────────────

def _detect_flask_routes(file_path: str, content: str) -> List[Dict]:
    routes = []
    # @app.route('/path', methods=['GET', 'POST'])
    pattern = r'@\w+\.route\s*\(\s*["\']([^"\']+)["\'](?:\s*,\s*methods\s*=\s*\[([^\]]+)\])?'
    for m in re.finditer(pattern, content):
        path = m.group(1)
        methods_str = m.group(2)
        if methods_str:
            methods = [x.strip().strip("'\"") for x in methods_str.split(",")]
        else:
            methods = ["GET"]
        for method in methods:
            routes.append({
                "method": method.upper(), "path": path,
                "handler": "",  # Will be resolved to the decorated function
                "file": file_path,
                "line": content[:m.start()].count("\n") + 1,
                "framework": "flask",
            })
    return routes


# ── FastAPI ───────────────────────────────────────────────────────

def _detect_fastapi_routes(file_path: str, content: str) -> List[Dict]:
    routes = []
    # @app.get('/path'), @router.post('/path'), etc.
    for m in re.finditer(
        r'@(?:\w+\.)?(get|post|put|delete|patch|head|options)\s*\(\s*["\']([^"\']+)["\']',
        content
    ):
        routes.append({
            "method": m.group(1).upper(), "path": m.group(2),
            "handler": "",
            "file": file_path,
            "line": content[:m.start()].count("\n") + 1,
            "framework": "fastapi",
        })
    return routes


# ── Express ───────────────────────────────────────────────────────

def _detect_express_routes(file_path: str, content: str) -> List[Dict]:
    routes = []
    # app.get('/path', handler)
    # router.post('/path', middleware, handler)
    for m in re.finditer(
        r'(?:app|router|this)\.(get|post|put|delete|patch|all|use)\s*\(\s*["\']([^"\']+)["\'](?:\s*,\s*(\w[\w.]*))?',
        content
    ):
        routes.append({
            "method": m.group(1).upper(), "path": m.group(2),
            "handler": m.group(3) or "",
            "file": file_path,
            "line": content[:m.start()].count("\n") + 1,
            "framework": "express",
        })
    return routes


# ── NestJS ────────────────────────────────────────────────────────

def _detect_nestjs_routes(file_path: str, content: str) -> List[Dict]:
    routes = []
    if "@Controller" not in content:
        return routes

    # Extract controller base path
    controller_match = re.search(r'@Controller\s*\(\s*["\']([^"\']*)["\']', content)
    base_path = controller_match.group(1) if controller_match else ""

    # @Get('/path'), @Post('/path'), etc.
    for m in re.finditer(
        r'@(Get|Post|Put|Delete|Patch|All)\s*\(\s*["\']([^"\']*)["\']',
        content
    ):
        sub_path = m.group(2)
        full_path = base_path.rstrip("/") + ("" if not sub_path else "/" + sub_path.lstrip("/"))
        routes.append({
            "method": m.group(1).upper(), "path": full_path,
            "handler": "",
            "file": file_path,
            "line": content[:m.start()].count("\n") + 1,
            "framework": "nestjs",
        })
    return routes


# ── Spring ────────────────────────────────────────────────────────

def _detect_spring_routes(file_path: str, content: str) -> List[Dict]:
    routes = []
    base = ""
    rm = re.search(r'@RequestMapping\s*\(\s*["\']([^"\']*)["\']', content)
    if rm:
        base = rm.group(1)

    for m in re.finditer(
        r'@(Get|Post|Put|Delete|Patch)Mapping\s*\(\s*(?:value\s*=\s*)?["\']([^"\']+)["\']',
        content
    ):
        path = base.rstrip("/") + m.group(2)
        routes.append({
            "method": m.group(1).upper(), "path": path,
            "handler": "",
            "file": file_path,
            "line": content[:m.start()].count("\n") + 1,
            "framework": "spring",
        })
    return routes


# ── Laravel ───────────────────────────────────────────────────────

def _detect_laravel_routes(file_path: str, content: str) -> List[Dict]:
    routes = []
    for m in re.finditer(
        r"""Route::(get|post|put|delete|patch|options|any|match)\s*\(\s*["']([^"']+)["']\s*,\s*\[?['"]?([A-Za-z_][A-Za-z0-9_\\]+)""",
        content
    ):
        routes.append({
            "method": m.group(1).upper(), "path": m.group(2),
            "handler": m.group(3),
            "file": file_path,
            "line": content[:m.start()].count("\n") + 1,
            "framework": "laravel",
        })
    return routes


# ── Gin / chi / gorilla ──────────────────────────────────────────

def _detect_gin_routes(file_path: str, content: str) -> List[Dict]:
    routes = []
    for m in re.finditer(
        r'\.(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS|Handle)\s*\(\s*["\']([^"\']+)["\']',
        content
    ):
        routes.append({
            "method": m.group(1).upper(), "path": m.group(2),
            "handler": "",
            "file": file_path,
            "line": content[:m.start()].count("\n") + 1,
            "framework": "gin",
        })
    return routes


# ── Axum / actix / Rocket (Rust) ─────────────────────────────────

def _detect_axum_routes(file_path: str, content: str) -> List[Dict]:
    routes = []
    # .route("/path", get(handler))
    for m in re.finditer(
        r'\.route\s*\(\s*["\']([^"\']+)["\']\s*,\s*(get|post|put|delete|patch)\s*\(\s*(\w+)',
        content
    ):
        routes.append({
            "method": m.group(2).upper(), "path": m.group(1),
            "handler": m.group(3),
            "file": file_path,
            "line": content[:m.start()].count("\n") + 1,
            "framework": "axum",
        })
    # #[get("/path")], #[post("/path")]
    for m in re.finditer(
        r'#\[(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']',
        content
    ):
        routes.append({
            "method": m.group(1).upper(), "path": m.group(2),
            "handler": "",
            "file": file_path,
            "line": content[:m.start()].count("\n") + 1,
            "framework": "actix",
        })
    return routes


# ── ASP.NET ──────────────────────────────────────────────────────

def _detect_aspnet_routes(file_path: str, content: str) -> List[Dict]:
    routes = []
    # [HttpGet("/path")], [HttpPost("/path")]
    for m in re.finditer(
        r'\[Http(Get|Post|Put|Delete|Patch)\s*\(\s*["\']([^"\']+)["\']',
        content
    ):
        routes.append({
            "method": m.group(1).upper(), "path": m.group(2),
            "handler": "",
            "file": file_path,
            "line": content[:m.start()].count("\n") + 1,
            "framework": "aspnet",
        })
    return routes


# ── React Router ──────────────────────────────────────────────────

def _detect_react_router_routes(file_path: str, content: str) -> List[Dict]:
    routes = []
    # <Route path="/users" element={<Users />} />
    for m in re.finditer(
        r'<Route\s+path\s*=\s*["\']([^"\']+)["\']\s+component\s*=\s*\{(\w+)}',
        content
    ):
        routes.append({
            "method": "COMPONENT", "path": m.group(1),
            "handler": m.group(2),
            "file": file_path,
            "line": content[:m.start()].count("\n") + 1,
            "framework": "react-router",
        })
    return routes
