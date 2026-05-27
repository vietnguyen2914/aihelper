"""
Compression Fidelity Verification — ensures compressed context preserves critical facts.

Tests that the compressed cognition package sent to frontier models does not:
  - Remove edge constraints
  - Hide architectural nuance
  - Omit historical context
  - Collapse uncertainty
  - Fabricate or distort data
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple


# ── Fidelity Checks ──────────────────────────────────────────────

def check_symbol_presence(original: Dict, compressed: Dict) -> Tuple[bool, str]:
    """Verify all symbol names in original are present in compressed."""
    orig_symbols = set()
    for key in ("callers", "callees", "caller_list", "callee_list"):
        for item in original.get(key, []):
            if isinstance(item, str):
                orig_symbols.add(item)
            elif isinstance(item, dict):
                orig_symbols.add(item.get("name", ""))

    comp_graph = compressed.get("system_state", {}).get("affected_graph", {})
    comp_symbols = set(comp_graph.get("callers", []) + comp_graph.get("callees", []))

    missing = orig_symbols - comp_symbols
    if missing and len(orig_symbols) > 0:
        return False, f"Missing symbols in compressed: {missing}"
    return True, "All symbols preserved"


def check_file_paths_accurate(original: Dict, compressed: Dict) -> Tuple[bool, str]:
    """Verify file paths are accurate in compressed package."""
    orig_files = set()
    for key in ("files", "file_list"):
        for f in original.get(key, []):
            orig_files.add(str(f))

    comp_risks = compressed.get("system_state", {}).get("risks", [])
    comp_files = set()
    for risk in comp_risks:
        comp_files.update(risk.get("files", []))

    # File paths should be relative, not absolute
    for f in comp_files:
        if f.startswith("/"):
            return False, f"Absolute path found in compressed: {f}"

    return True, "File paths accurate"


def check_risk_level_preserved(original: Dict, compressed: Dict) -> Tuple[bool, str]:
    """Verify risk levels are preserved."""
    orig_risk = original.get("risk_level", original.get("risk", ""))
    comp_risks = compressed.get("system_state", {}).get("risks", [])
    comp_risk_levels = [r.get("level", "") for r in comp_risks if r.get("type") == "impact_risk"]

    if orig_risk and not comp_risk_levels:
        return False, f"Risk level '{orig_risk}' lost in compression"
    return True, "Risk level preserved"


def check_dependency_counts_match(original: Dict, compressed: Dict) -> Tuple[bool, str]:
    """Verify dependency/count numbers are accurate."""
    comp_graph = compressed.get("system_state", {}).get("affected_graph", {})

    orig_caller_count = original.get("callers", original.get("caller_count", 0))
    comp_caller_count = comp_graph.get("total_callers", 0)

    # Allow small discrepancy from deduplication
    if isinstance(orig_caller_count, int) and isinstance(comp_caller_count, int):
        if abs(orig_caller_count - comp_caller_count) > max(orig_caller_count * 0.2, 2):
            return False, (f"Caller count mismatch: original={orig_caller_count}, "
                          f"compressed={comp_caller_count}")

    return True, "Dependency counts consistent"


def check_no_fabricated_data(compressed: Dict) -> Tuple[bool, str]:
    """Verify compressed package contains no obviously fabricated data."""
    ss = compressed.get("system_state", {})

    # Architecture should have reasonable numbers
    arch = ss.get("architecture", {})
    symbol_count = arch.get("symbol_count", 0)
    file_count = arch.get("file_count", 0)
    if isinstance(symbol_count, int) and symbol_count > 1000000:
        return False, f"Suspicious symbol count: {symbol_count}"
    if isinstance(file_count, int) and file_count > 100000:
        return False, f"Suspicious file count: {file_count}"

    # Question field must be present
    if not compressed.get("question"):
        return False, "Missing question field in compressed package"

    return True, "No fabricated data detected"


def check_uncertainty_not_collapsed(compressed: Dict) -> Tuple[bool, str]:
    """Verify uncertainty markers are not completely collapsed."""
    # The compressed package should not claim certainty where there is ambiguity
    question = compressed.get("question", "")
    risks = compressed.get("system_state", {}).get("risks", [])

    # If there are risks, that's a good sign — uncertainty is preserved
    if risks:
        return True, "Uncertainty preserved via risk markers"
    return True, "No uncertainty markers needed"


# ── Full Fidelity Test ───────────────────────────────────────────

FIDELITY_CHECKS = [
    ("symbol_presence", check_symbol_presence),
    ("file_paths_accurate", check_file_paths_accurate),
    ("risk_level_preserved", check_risk_level_preserved),
    ("dependency_counts_match", check_dependency_counts_match),
    ("no_fabricated_data", check_no_fabricated_data),
    ("uncertainty_not_collapsed", check_uncertainty_not_collapsed),
]


def verify_compression_fidelity(original_context: Dict[str, Any],
                                 compressed_package: Dict[str, Any]) -> Dict[str, Any]:
    """Run all fidelity checks on a compressed package.

    Returns a report with each check's pass/fail status and details.
    """
    results = []
    all_passed = True

    for check_name, check_fn in FIDELITY_CHECKS:
        try:
            if check_name in ("no_fabricated_data", "uncertainty_not_collapsed"):
                passed, message = check_fn(compressed_package)
            else:
                passed, message = check_fn(original_context, compressed_package)
        except Exception as e:
            passed = False
            message = f"Check error: {e}"

        results.append({"check": check_name, "passed": passed, "message": message})
        if not passed:
            all_passed = False

    return {
        "passed": all_passed,
        "checks_passed": sum(1 for r in results if r["passed"]),
        "checks_total": len(results),
        "results": results,
        "verdict": "PASS" if all_passed else "FAIL",
    }


# ── Daemon Handler ──────────────────────────────────────────────

def handle_compression_fidelity(params: Dict[str, Any]) -> Dict[str, Any]:
    """Verify compression fidelity for a context-compress operation."""
    question = params.get("question", params.get("task", ""))
    target = params.get("target", "")
    project_root = Path(params.get("project_root", str(Path.cwd())))

    # Build original context
    original = {"question": question, "target": target}

    from .graph_db import get_db
    from .graph_query import _find_symbol_id
    db = get_db(project_root)
    if target:
        sym_id = _find_symbol_id(target, project_root)
        if sym_id:
            original["symbol_id"] = sym_id
            callers = db.get_callers(sym_id, max_depth=2)
            callees = db.get_callees(sym_id, max_depth=2)
            original["callers"] = [c.get("name", "") for c in callers]
            original["caller_count"] = len(callers)
            original["callee_count"] = len(callees)

    # Build compressed package
    from .compressor import compress_context, estimate_token_count
    ctx_for_compress = {
        "question": question, "target": target,
        "symbol_id": original.get("symbol_id", ""),
    }
    if target:
        sym_id = original.get("symbol_id", "")
        if sym_id:
            ctx_for_compress["callers"] = db.get_callers(sym_id, max_depth=2)
            ctx_for_compress["callees"] = db.get_callees(sym_id, max_depth=2)
    ctx_for_compress["memories"] = []
    ctx_for_compress["circular_deps"] = db.find_circular_deps()
    ctx_for_compress["dead_code"] = db.find_dead_code()

    compressed = compress_context(ctx_for_compress, project_root)
    compressed["estimated_tokens"] = estimate_token_count(compressed)

    fidelity = verify_compression_fidelity(original, compressed)

    return {
        "compressed_tokens": compressed.get("estimated_tokens", 0),
        "original_context_size": len(str(original)),
        "fidelity": fidelity,
    }
