"""
Confidence scoring for AI-generated patches.

Scores patches on multiple signals:
1. Syntax validity (does the code parse?)
2. File count (fewer files = safer)
3. Symbol ambiguity (are changed symbols unique?)
4. Public API changes (did signatures change?)
5. Test coverage hint (are test files in the patch?)

Output: 0.0–1.0 confidence score with auto-apply threshold.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List


AUTO_APPLY_THRESHOLD = 0.85
WARN_THRESHOLD = 0.5


def score_patch(patch_content: str, project_root: Path, files: List[str]) -> Dict[str, Any]:
    """Score a patch and return confidence assessment."""
    scores = {}
    details = {}

    # 1. Syntax check
    syntax_score, syntax_details = _check_syntax(patch_content, project_root, files)
    scores["syntax"] = syntax_score
    details["syntax"] = syntax_details

    # 2. File count signal
    file_count_score, file_count_details = _score_file_count(files)
    scores["file_count"] = file_count_score
    details["file_count"] = file_count_details

    # 3. Symbol ambiguity
    symbol_score, symbol_details = _score_symbol_ambiguity(patch_content, project_root)
    scores["symbol_ambiguity"] = symbol_score
    details["symbol_ambiguity"] = symbol_details

    # 4. Public API changes
    api_score, api_details = _score_api_changes(patch_content)
    scores["api_changes"] = api_score
    details["api_changes"] = api_details

    # 5. Test coverage
    test_score, test_details = _score_test_coverage(files)
    scores["test_coverage"] = test_score
    details["test_coverage"] = test_details

    # Weighted aggregate
    weights = {
        "syntax": 0.35,
        "file_count": 0.20,
        "symbol_ambiguity": 0.20,
        "api_changes": 0.15,
        "test_coverage": 0.10,
    }

    overall = sum(scores[k] * weights[k] for k in weights)

    recommendation = "review"
    if overall >= AUTO_APPLY_THRESHOLD:
        recommendation = "auto_apply"
    elif overall >= WARN_THRESHOLD:
        recommendation = "review"
    else:
        recommendation = "manual"

    return {
        "confidence": round(overall, 3),
        "recommendation": recommendation,
        "auto_apply_threshold": AUTO_APPLY_THRESHOLD,
        "scores": {k: round(v, 3) for k, v in scores.items()},
        "details": details,
    }


def _check_syntax(patch_content: str, project_root: Path, files: List[str]) -> tuple:
    """Check syntax validity of changed files."""
    valid = 0
    total = 0
    errors = []

    for file_path in files:
        full_path = project_root / file_path
        if not full_path.exists():
            continue
        total += 1
        suffix = full_path.suffix.lower()

        try:
            if suffix == ".py":
                result = subprocess.run(
                    ["python3", "-m", "py_compile", str(full_path)],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                )
                if result.returncode == 0:
                    valid += 1
                else:
                    errors.append({"file": file_path, "error": result.stderr.strip()[:200]})
            elif suffix == ".php":
                result = subprocess.run(
                    ["php", "-l", str(full_path)],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                )
                if "No syntax errors" in result.stdout:
                    valid += 1
                else:
                    errors.append({"file": file_path, "error": result.stdout.strip()[:200]})
            elif suffix in (".json",):
                try:
                    with open(full_path) as f:
                        json.load(f)
                    valid += 1
                except (json.JSONDecodeError, OSError) as e:
                    errors.append({"file": file_path, "error": str(e)[:200]})
            else:
                # Unknown format — assume valid but flag
                valid += 0.8
                errors.append({"file": file_path, "warning": "unvalidated_format"})
        except Exception as e:
            errors.append({"file": file_path, "error": str(e)[:200]})

    score = valid / max(total, 1)
    return score, {"valid": valid, "total": total, "errors": errors}


def _score_file_count(files: List[str]) -> tuple:
    """Fewer files = higher confidence."""
    count = len(files)
    if count == 0:
        return 1.0, {"count": 0, "risk": "none"}
    if count <= 2:
        return 1.0, {"count": count, "risk": "low"}
    if count <= 5:
        return 0.85, {"count": count, "risk": "medium"}
    if count <= 10:
        return 0.6, {"count": count, "risk": "high"}
    return 0.3, {"count": count, "risk": "very_high"}


def _score_symbol_ambiguity(patch_content: str, project_root: Path) -> tuple:
    """Check if changed symbols are unique (unambiguous) in the codebase."""
    # Extract changed function/class names from the patch
    changed_symbols = set()
    for line in patch_content.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            # Look for function/class definitions
            match = re.search(
                r'(?:def|class|function|public function|private function|protected function)\s+([A-Za-z_][A-Za-z0-9_]*)',
                line
            )
            if match:
                changed_symbols.add(match.group(1))

    if not changed_symbols:
        return 1.0, {"symbols": [], "ambiguity": "none"}

    # Check if these symbols exist elsewhere in the codebase
    ambiguous = []
    try:
        from .symbols import find_symbols
    except ImportError:
        from symbols import find_symbols

    for symbol in changed_symbols:
        try:
            matches = find_symbols(symbol, project_root, limit=50)
            match_list = matches.get("matches", []) if isinstance(matches, dict) else []
            # Count unique files where this symbol appears
            files_with_symbol = {m.get("file") for m in match_list if m.get("file")}
            if len(files_with_symbol) > 3:
                ambiguous.append({"symbol": symbol, "occurrences": len(files_with_symbol)})
        except Exception:
            pass

    if not ambiguous:
        return 1.0, {"ambiguous": [], "risk": "none"}
    if len(ambiguous) <= 1:
        return 0.8, {"ambiguous": ambiguous, "risk": "low"}
    return 0.5, {"ambiguous": ambiguous, "risk": "high"}


def _score_api_changes(patch_content: str) -> tuple:
    """Detect if public API signatures changed."""
    api_changes = []
    for line in patch_content.splitlines():
        if not (line.startswith("+") and not line.startswith("+++")):
            continue
        # Public method signatures
        if re.search(r'public\s+(?:static\s+)?function\s+\w+\s*\(', line):
            api_changes.append({"line": line.strip()[:120], "type": "public_method"})
        # Exported functions
        if re.search(r'export\s+(?:async\s+)?function\s+\w+', line):
            api_changes.append({"line": line.strip()[:120], "type": "exported_function"})
        # Interface changes
        if re.search(r'interface\s+\w+', line):
            api_changes.append({"line": line.strip()[:120], "type": "interface"})

    if not api_changes:
        return 1.0, {"changes": [], "risk": "none"}
    if len(api_changes) <= 2:
        return 0.7, {"changes": api_changes, "risk": "medium"}
    return 0.4, {"changes": api_changes, "risk": "high"}


def _score_test_coverage(files: List[str]) -> tuple:
    """Check if test files are included in the patch."""
    test_files = [f for f in files if "test" in Path(f).name.lower() or "spec" in Path(f).name.lower()]
    test_dirs = [f for f in files if "/test" in f.lower() or "/tests" in f.lower() or "/__tests__" in f.lower()]

    if test_files or test_dirs:
        return 1.0, {"test_files": len(test_files) + len(test_dirs), "covered": True}

    # Check if any file is near a test directory
    has_nearby_tests = any(
        (Path(f).parent / "__tests__").exists() or
        any(p.name.lower().endswith(".test" + Path(f).suffix) for p in Path(f).parent.iterdir() if p.is_file())
        for f in files
    )

    if has_nearby_tests:
        return 0.7, {"test_files": 0, "covered": False, "nearby_tests": True}

    return 0.3, {"test_files": 0, "covered": False, "nearby_tests": False}


# ── Daemon handler ───────────────────────────────────────────────

def handle_confidence(params: Dict[str, Any]) -> Dict[str, Any]:
    """Daemon handler: score a patch for confidence."""
    patch_content = params.get("patch_content", "")
    project_root = Path(params.get("project_root", "."))
    files = params.get("files", [])
    return score_patch(patch_content, project_root, files)
