"""
Signature-based Invalidation — compiler-grade cache invalidation.

Distinguishes between body-only changes (don't invalidate downstream) and
signature changes (propagate invalidation along call graph). Logs every
invalidation for debugging and cognition drift analysis.

Principles:
  - Signature change = invalidation propagates to callers
  - Body change = only the changed file is invalidated
  - Branch switch = full rebuild baseline
  - Churn > threshold = full rebuild baseline
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


# ── Invalidation Log ──────────────────────────────────────────

INVALIDATION_LOG = Path.home() / ".aihelper" / "invalidation.log"


def log_invalidation(reason: str, entity: str, detail: str = "",
                    level: str = "info") -> None:
    """Log an invalidation event for debugging and drift analysis."""
    try:
        INVALIDATION_LOG.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
            "entity": entity,
            "detail": detail,
            "level": level,
        }
        with open(INVALIDATION_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def read_invalidation_log(limit: int = 50, reason_filter: str = "") -> List[Dict]:
    """Read recent invalidation events."""
    if not INVALIDATION_LOG.exists():
        return []
    entries = []
    try:
        with open(INVALIDATION_LOG) as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    if reason_filter and reason_filter not in entry.get("reason", ""):
                        continue
                    entries.append(entry)
                except json.JSONDecodeError:
                    pass
    except OSError:
        pass
    return entries[-limit:]


def get_invalidation_stats() -> Dict[str, Any]:
    """Get summary statistics from invalidation log."""
    entries = read_invalidation_log(limit=1000)
    if not entries:
        return {"total": 0, "by_reason": {}, "by_level": {}}

    by_reason: Dict[str, int] = {}
    by_level: Dict[str, int] = {}
    for e in entries:
        reason = e.get("reason", "unknown")
        level = e.get("level", "info")
        by_reason[reason] = by_reason.get(reason, 0) + 1
        by_level[level] = by_level.get(level, 0) + 1

    return {
        "total": len(entries),
        "by_reason": by_reason,
        "by_level": by_level,
        "oldest": entries[0].get("timestamp", "") if entries else "",
        "newest": entries[-1].get("timestamp", "") if entries else "",
    }


# ── Signature Extraction ──────────────────────────────────────

def extract_signatures(file_path: Path) -> Dict[str, str]:
    """Extract function/method signatures from a source file.

    Returns mapping: symbol_name → signature_string.
    Only captures the declaration line, not the body.
    """
    signatures: Dict[str, str] = {}
    suffix = file_path.suffix.lower()

    if suffix == ".py":
        signatures = _extract_py_signatures(file_path)
    elif suffix in (".js", ".ts", ".tsx", ".jsx"):
        signatures = _extract_js_signatures(file_path)
    elif suffix == ".java":
        signatures = _extract_java_signatures(file_path)
    elif suffix in (".rs", ".go"):
        signatures = _extract_brace_signatures(file_path)
    elif suffix == ".php":
        signatures = _extract_brace_signatures(file_path)

    return signatures


def _extract_py_signatures(file_path: Path) -> Dict[str, str]:
    """Extract Python def/class signatures."""
    sigs: Dict[str, str] = {}
    try:
        lines = file_path.read_text(errors="ignore").split("\n")
    except OSError:
        return sigs

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # Match `def name(...)` or `async def name(...)`
        if line.startswith("def ") or line.startswith("async def "):
            sig_line = line
            # Handle multi-line signatures
            while not sig_line.rstrip().endswith(":") and i + 1 < len(lines):
                i += 1
                next_line = lines[i].strip()
                if next_line and not next_line.startswith("#"):
                    sig_line += " " + next_line
            # Extract name
            import re
            m = re.match(r'(?:async\s+)?def\s+(\w+)', sig_line)
            if m:
                sigs[m.group(1)] = sig_line[:240]
        # Match `class Name:`
        elif line.startswith("class ") and line.rstrip().endswith(":"):
            import re
            m = re.match(r'class\s+(\w+)', line)
            if m:
                sigs[m.group(1)] = line[:240]
        i += 1

    return sigs


def _extract_js_signatures(file_path: Path) -> Dict[str, str]:
    """Extract JS/TS function signatures."""
    sigs: Dict[str, str] = {}
    try:
        text = file_path.read_text(errors="ignore")
    except OSError:
        return sigs
    import re
    # function name(...)
    for m in re.finditer(r'(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\([^)]*\)', text):
        sigs[m.group(1)] = m.group(0)[:240]
    # const/let name = (...) => ...
    for m in re.finditer(r'(?:const|let)\s+(\w+)\s*=\s*\([^)]*\)\s*=>', text):
        sigs[m.group(1)] = m.group(0)[:240]
    # class Name { ... method() ...
    for m in re.finditer(r'(?:static\s+)?(?:async\s+)?(\w+)\s*\([^)]*\)\s*{', text):
        name = m.group(1)
        if name not in ("if", "while", "for", "switch", "catch"):
            sigs[name] = m.group(0)[:240]
    return sigs


def _extract_java_signatures(file_path: Path) -> Dict[str, str]:
    """Extract Java method signatures."""
    sigs: Dict[str, str] = {}
    try:
        text = file_path.read_text(errors="ignore")
    except OSError:
        return sigs
    import re
    for m in re.finditer(r'(?:public|private|protected|static|\s)+[\w<>[\],\s]+\s+(\w+)\s*\([^)]*\)', text):
        sigs[m.group(1)] = m.group(0)[:240]
    return sigs


def _extract_brace_signatures(file_path: Path) -> Dict[str, str]:
    """Generic signature extraction for brace-based languages (Go, Rust, PHP, C)."""
    sigs: Dict[str, str] = {}
    try:
        lines = file_path.read_text(errors="ignore").split("\n")
    except OSError:
        return sigs
    import re
    for line in lines:
        line = line.strip()
        # fn name(...) {  or func name(...) {
        m = re.match(r'(?:fn|func|function)\s+(\w+)\s*\([^)]*\)', line)
        if m:
            sigs[m.group(1)] = line[:240]
    return sigs


def compute_signature_hash(signatures: Dict[str, str]) -> str:
    """Compute a stable hash of all signatures in a file."""
    if not signatures:
        return ""
    canonical = json.dumps(
        {k: v for k, v in sorted(signatures.items())},
        sort_keys=True,
    )
    return hashlib.sha1(canonical.encode()).hexdigest()


# ── Signature-aware Diff ──────────────────────────────────────

def classify_change(file_path: Path, cached_sig_hash: str = "") -> Dict[str, Any]:
    """Classify a file change: signature_change or body_only_change.

    Returns:
      - change_type: "signature_change" | "body_only_change" | "unchanged"
      - old_hash, new_hash: signature hashes
      - changed_symbols: list of symbol names whose signatures changed
    """
    new_sigs = extract_signatures(file_path)
    new_hash = compute_signature_hash(new_sigs)

    if not cached_sig_hash:
        return {"change_type": "signature_change", "old_hash": "",
                "new_hash": new_hash, "changed_symbols": list(new_sigs.keys()),
                "total_symbols": len(new_sigs)}

    if new_hash == cached_sig_hash:
        return {"change_type": "unchanged", "old_hash": cached_sig_hash,
                "new_hash": new_hash, "changed_symbols": [],
                "total_symbols": len(new_sigs)}

    # Compute which symbols changed
    old_sigs = {}  # We'd need to load from cache; simplified for now
    changed_symbols = list(new_sigs.keys())  # Conservative: assume all changed

    return {"change_type": "signature_change" if changed_symbols else "body_only_change",
            "old_hash": cached_sig_hash, "new_hash": new_hash,
            "changed_symbols": changed_symbols,
            "total_symbols": len(new_sigs)}


# ── Daemon Handler ────────────────────────────────────────────

def handle_invalidation_log(params: Dict[str, Any]) -> Dict[str, Any]:
    """Query invalidation log."""
    limit = int(params.get("limit", 50))
    reason_filter = str(params.get("reason", ""))
    entries = read_invalidation_log(limit=limit, reason_filter=reason_filter)
    stats = get_invalidation_stats()
    return {"entries": entries, "stats": stats}
