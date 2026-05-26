"""
affected.py — Test-file impact analysis from git diff (v0.0.7).

Given changed files, finds test files that depend on them via the SQLite graph.
Similar to codegraph's `codegraph affected` command.

Usage:
    aihelper affected src/utils.py src/api.py
    git diff --name-only | aihelper affected --stdin
    aihelper affected src/auth.ts --filter "e2e/*"
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Dict, Any, Optional, Set


def find_affected_tests(changed_files: List[str],
                        project_root: Path,
                        max_depth: int = 5,
                        test_filter: Optional[str] = None) -> Dict[str, Any]:
    """Find test files affected by changes to source files.

    Traces import dependencies transitively to find test files.
    """
    from .graph_db import get_db
    db = get_db(project_root)

    # Normalize paths
    changed = [f.lstrip("./") for f in changed_files]
    test_files: Set[str] = set()
    trace_log: List[Dict] = []

    for changed_file in changed:
        # Get dependents (files that import the changed file)
        dependents = db.get_file_dependents(changed_file)
        for dep in dependents:
            # Check if dependent is a test file
            if _is_test_file(dep, test_filter):
                test_files.add(dep)
                trace_log.append({
                    "changed": changed_file,
                    "test": dep,
                    "depth": 1,
                    "reason": "direct_dependent",
                })

        # Transitive: find dependents of dependents
        visited: Set[str] = {changed_file}
        queue = [(changed_file, 0)]
        while queue and len(test_files) < 200:
            current, depth = queue.pop(0)
            if depth >= max_depth:
                continue
            deps = db.get_file_dependents(current)
            for dep in deps:
                if dep in visited:
                    continue
                visited.add(dep)
                if _is_test_file(dep, test_filter):
                    test_files.add(dep)
                    trace_log.append({
                        "changed": changed_file,
                        "test": dep,
                        "depth": depth + 1,
                        "via": current,
                        "reason": "transitive_dependent",
                    })
                queue.append((dep, depth + 1))

    return {
        "changed_files": changed,
        "affected_tests": sorted(test_files),
        "affected_count": len(test_files),
        "trace": trace_log[:50],
        "recommendation": _recommend(test_files, changed),
    }


def _is_test_file(file_path: str, custom_filter: Optional[str] = None) -> bool:
    """Heuristic: check if a file is a test file."""
    lower = file_path.lower()

    # Custom glob filter
    if custom_filter:
        import fnmatch
        if fnmatch.fnmatch(file_path, custom_filter):
            return True

    # Standard test file patterns
    test_patterns = [
        "/test/", "/tests/", "/__tests__/",
        "test_", "_test.", ".test.", ".spec.",
        "tests/", "__tests__/",
        "/spec/", ".spec.",
        "Test.java", "Tests.java", "TestCase",
        "test.go", "_test.go",
        "test.py", "_test.py",
    ]
    return any(p in lower for p in test_patterns)


def _recommend(tests: Set[str], changed: List[str]) -> str:
    if not tests:
        return (
            f"No test files found importing the {len(changed)} changed file(s). "
            "Consider adding tests for the affected code."
        )
    if len(tests) <= 3:
        return f"Run the {len(tests)} affected test file(s)."
    if len(tests) <= 15:
        return f"Run {len(tests)} affected test files. Consider running the full suite if cascading."
    return f"Critical: {len(tests)} test files affected across {len(changed)} changed files. Run full test suite."


# ── CLI Handler ───────────────────────────────────────────────────

def handle_affected(argv: List[str], project_root: Path) -> Dict[str, Any]:
    """Handle 'aihelper affected' CLI command."""
    import sys

    files: List[str] = []
    use_stdin = "--stdin" in argv
    test_filter = None
    max_depth = 5

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--stdin":
            use_stdin = True
        elif arg == "-f" or arg == "--filter":
            if i + 1 < len(argv):
                test_filter = argv[i + 1]
                i += 1
        elif arg == "-d" or arg == "--depth":
            if i + 1 < len(argv):
                max_depth = int(argv[i + 1])
                i += 1
        elif not arg.startswith("-"):
            files.append(arg)
        i += 1

    if use_stdin:
        stdin_files = sys.stdin.read().strip().splitlines()
        files.extend(f for f in stdin_files if f.strip())

    if not files:
        return {"error": "No files provided. Use: aihelper affected file1.py file2.py"}

    return find_affected_tests(files, project_root, max_depth=max_depth, test_filter=test_filter)
