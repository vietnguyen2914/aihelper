from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List


def semantic_diff_summary(project_root: Path, max_files: int = 80) -> Dict[str, Any]:
    root = project_root.resolve()
    name_status = subprocess.run(
        ["git", "diff", "--name-status"],
        cwd=str(root),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    stat = subprocess.run(
        ["git", "diff", "--stat", "--compact-summary"],
        cwd=str(root),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    files: List[Dict[str, str]] = []
    for line in name_status.stdout.splitlines()[:max_files]:
        parts = line.split("\t")
        if len(parts) >= 2:
            files.append({"status": parts[0], "path": parts[-1], "kind": _kind(parts[-1])})
    return {
        "project_root": str(root),
        "changed_file_count": len(files),
        "files": files,
        "stat": stat.stdout.strip(),
        "summary": _summarize(files),
    }


def _kind(path: str) -> str:
    lower = path.lower()
    if lower.endswith((".md", ".rst", ".txt")):
        return "docs"
    if lower.endswith((".sql", ".xml")) or "migration" in lower:
        return "schema"
    if lower.endswith((".ts", ".tsx", ".js", ".jsx", ".css", ".scss")):
        return "frontend"
    if lower.endswith((".java", ".kt", ".py", ".php", ".go", ".rb")):
        return "backend"
    if lower.endswith((".json", ".yml", ".yaml", ".toml")):
        return "config"
    return "other"


def _summarize(files: List[Dict[str, str]]) -> List[str]:
    counts: Dict[str, int] = {}
    for item in files:
        counts[item["kind"]] = counts.get(item["kind"], 0) + 1
    return [f"{count} {kind} file(s) changed" for kind, count in sorted(counts.items())]
