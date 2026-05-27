"""Auto-capture observer — runs silently after every daemon request."""
import time
from pathlib import Path
from typing import Any, Dict
from .evidence import score_candidate
from .decisions import add_decision
from .debugging import add_debug_entry
from .preferences import set_preference
from .search import search_knowledge

PREFERENCE_PATTERNS = {
    "pnpm": ("package_manager", "pnpm", "frontend"),
    "npm": ("package_manager", "npm", "frontend"),
    "yarn": ("package_manager", "yarn", "frontend"),
    "mariadb": ("database", "mariadb", "backend"),
    "postgres": ("database", "postgresql", "backend"),
    "mysql": ("database", "mysql", "backend"),
    "sqlite": ("database", "sqlite", "backend"),
    "redis": ("database", "redis", "backend"),
    "mongodb": ("database", "mongodb", "backend"), "mongo": ("database", "mongodb", "backend"),
    "docker": ("infra", "docker", "infra"),
    "kubernetes": ("infra", "kubernetes", "infra"), "k8s": ("infra", "kubernetes", "infra"),
    "nginx": ("infra", "nginx", "infra"), "apache": ("infra", "apache", "infra"),
    "serverless": ("infra", "serverless", "infra"), "lambda": ("infra", "serverless", "infra"),
    "typescript": ("language", "typescript", "language"), "ts": ("language", "typescript", "language"),
    "python": ("language", "python", "language"), "python3": ("language", "python", "language"),
    "rust": ("language", "rust", "language"), "cargo": ("language", "rust", "language"),
    "golang": ("language", "go", "language"), "go mod": ("language", "go", "language"),
    "java": ("language", "java", "language"), "maven": ("language", "java", "language"),
    "gradle": ("language", "java", "language"),
    "supabase": ("backend", "supabase", "backend"), "firebase": ("backend", "firebase", "backend"),
    "monolith": ("infra_style", "monolithic", "infra"),
    "microservices": ("infra_style", "microservices", "infra"),
    "api": ("architecture", "api-first", "architecture"),
    "graphql": ("architecture", "graphql", "architecture"),
}

def auto_capture(method: str, params: Dict[str, Any],
                 result: Dict[str, Any]) -> None:
    """Called after every daemon request. Silent, non-blocking."""
    if score_candidate(method, params, result) < 0.35: return
    pr = Path(params["project_root"]) if isinstance(params.get("project_root"), str) else None

    if method == "patch_plan" and isinstance(result, dict):
        files = params.get("files", []) or result.get("files", [])
        task = params.get("task", "")
        if any(p in str(f).lower() for f in files for p in
               ("config", "middleware", "auth", "migration", "schema", "docker", "ci")):
            try:
                add_decision(f"auto-{method}-{int(time.time())}", task[:100],
                             f"Auto-captured: {', '.join(files[:3])}",
                             related_files=list(files)[:5],
                             confidence=0.3, source="auto-detected",
                             tags=["auto-captured"], project_root=pr)
            except Exception: pass

    if method == "diagnostics" and isinstance(result, dict):
        errors = result.get("errors", [])
        if errors:
            sig = str(errors[0])[:200]
            if sig:
                try:
                    if not search_knowledge(sig[:50], pr, 1).get("debugs"):
                        add_debug_entry(symptom=sig[:200], error_signature=sig[:100],
                                        source="auto-detected", project_root=pr)
                except Exception: pass

    if method == "route" and isinstance(params.get("task"), str):
        task = params["task"].lower()
        for kw, (k, v, cat) in PREFERENCE_PATTERNS.items():
            if kw in task:
                try: set_preference(k, v, cat, confidence=0.3, source="auto-detected", project_root=pr)
                except Exception: pass
