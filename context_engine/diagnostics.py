"""
Diagnostics Aggregation — collect and normalize compiler/linter errors.

Aggregates diagnostics from multiple sources:
- LSP (via lsp_bridge)
- PHP lint (php -l)
- Python compile (py_compile)
- JSON parse
- ESLint (if available)
- Shell scripts (bash -n)

Provides unified diagnostic view for AI consumption.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional


def collect_diagnostics(file_path: str, project_root: Path) -> Dict[str, Any]:
    """Collect all diagnostics for a file from available tools."""
    full_path = project_root / file_path
    if not full_path.exists():
        return {"file": file_path, "error": "file_not_found"}

    suffix = full_path.suffix.lower()
    diagnostics: List[Dict[str, Any]] = []
    sources: List[str] = []

    # ── PHP: php -l ──────────────────────────────────────────
    if suffix == ".php":
        sources.append("php_lint")
        result = subprocess.run(
            ["php", "-l", str(full_path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        if "No syntax errors" not in result.stdout:
            for line in result.stdout.splitlines():
                if "error" in line.lower() or "parse" in line.lower():
                    diagnostics.append({
                        "source": "php_lint",
                        "severity": "error",
                        "message": line.strip(),
                        "file": file_path,
                    })

    # ── Python: py_compile ───────────────────────────────────
    elif suffix == ".py":
        sources.append("py_compile")
        result = subprocess.run(
            ["python3", "-m", "py_compile", str(full_path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        if result.returncode != 0:
            diagnostics.append({
                "source": "py_compile",
                "severity": "error",
                "message": result.stderr.strip()[:500],
                "file": file_path,
            })

    # ── JSON: json.tool ──────────────────────────────────────
    elif suffix == ".json":
        sources.append("json_parse")
        try:
            with open(full_path) as f:
                json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            diagnostics.append({
                "source": "json_parse",
                "severity": "error",
                "message": str(e),
                "file": file_path,
            })

    # ── JavaScript/TypeScript: ESLint (if available) ─────────
    elif suffix in (".js", ".jsx", ".ts", ".tsx"):
        eslint = subprocess.run(
            ["which", "eslint"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        )
        if eslint.returncode == 0:
            sources.append("eslint")
            result = subprocess.run(
                ["eslint", "--format", "json", str(full_path)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            try:
                eslint_results = json.loads(result.stdout)
                for entry in eslint_results:
                    for msg in entry.get("messages", []):
                        diagnostics.append({
                            "source": "eslint",
                            "severity": "error" if msg.get("severity") == 2 else "warning",
                            "message": msg.get("message", ""),
                            "line": msg.get("line"),
                            "column": msg.get("column"),
                            "rule": msg.get("ruleId"),
                            "file": file_path,
                        })
            except json.JSONDecodeError:
                pass

    # ── Shell: bash -n ───────────────────────────────────────
    elif suffix == ".sh":
        sources.append("bash_syntax")
        result = subprocess.run(
            ["bash", "-n", str(full_path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        if result.returncode != 0:
            diagnostics.append({
                "source": "bash_syntax",
                "severity": "error",
                "message": result.stderr.strip()[:500],
                "file": file_path,
            })

    # ── Java: javac (if available) ───────────────────────────
    elif suffix == ".java":
        javac = subprocess.run(
            ["which", "javac"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        )
        if javac.returncode == 0:
            sources.append("javac")
            result = subprocess.run(
                ["javac", "-d", "/tmp", str(full_path)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            if result.returncode != 0:
                for line in result.stdout.splitlines():
                    if "error" in line.lower():
                        diagnostics.append({
                            "source": "javac",
                            "severity": "error",
                            "message": line.strip()[:300],
                            "file": file_path,
                        })

    return {
        "file": file_path,
        "error_count": len([d for d in diagnostics if d.get("severity") == "error"]),
        "warning_count": len([d for d in diagnostics if d.get("severity") == "warning"]),
        "sources_checked": sources,
        "diagnostics": diagnostics[:50],  # Cap at 50
    }


def collect_project_diagnostics(project_root: Path, files: List[str]) -> Dict[str, Any]:
    """Collect diagnostics for multiple files."""
    results = []
    error_total = 0
    warning_total = 0

    for file_path in files[:20]:  # Cap at 20 files
        diag = collect_diagnostics(file_path, project_root)
        results.append(diag)
        error_total += diag.get("error_count", 0)
        warning_total += diag.get("warning_count", 0)

    return {
        "files_checked": len(results),
        "total_errors": error_total,
        "total_warnings": warning_total,
        "results": results,
    }


# ── Daemon handler ───────────────────────────────────────────────

def handle_diagnostics(params: Dict[str, Any]) -> Dict[str, Any]:
    """Collect diagnostics for a file or project."""
    file_path = params.get("file_path", "")
    files = params.get("files", [])
    project_root = Path(params.get("project_root", "."))

    if files:
        return collect_project_diagnostics(project_root, files)
    if file_path:
        return collect_diagnostics(file_path, project_root)

    return {"error": "no file_path or files provided"}
