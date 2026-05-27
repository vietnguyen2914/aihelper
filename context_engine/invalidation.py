"""
Signature-based Invalidation — compiler-grade cache invalidation.

Distinguishes between body-only changes (don't invalidate downstream) and
signature changes (propagate invalidation along call graph). Logs every
invalidation for debugging and cognition drift analysis.

v0.1: Semantic confidence scoring + weighted decay + conservative fallback.
  - ChangeClassification now includes `semantic_confidence` (0.0–1.0)
  - Weighted decay rates per change type for compression confidence
  - Conservative invalidation fallback for high-risk modules
  - `should_propagate_invalidation()` for call-graph-aware decisions

Principles:
  - Signature change = invalidation propagates to callers
  - Body change = only the changed file is invalidated
  - Branch switch = full rebuild baseline
  - Churn > threshold = full rebuild baseline
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


# ── v0.1: Change Classification ────────────────────────────────

@dataclass
class ChangeClassification:
    """Classifies a file change with semantic confidence.

    v0.1: Added semantic_confidence — how sure are we about the classification?
    Low confidence means we should widen invalidation scope (conservative fallback).
    """
    change_type: str                # "signature_change" | "body_only_change" | "unchanged"
    old_hash: str = ""
    new_hash: str = ""
    changed_symbols: List[str] = field(default_factory=list)
    total_symbols: int = 0
    semantic_confidence: float = 1.0  # 0.0–1.0, how confident in the classification

    @property
    def should_propagate(self) -> bool:
        """Should invalidation propagate to callers?"""
        if self.change_type == "signature_change":
            return True
        if self.change_type == "unchanged":
            return False
        # body_only_change with low confidence → propagate (conservative)
        return self.semantic_confidence < 0.75

    @property
    def invalidation_scope(self) -> str:
        """How far to invalidate: symbol, file, module, or global."""
        if self.change_type == "signature_change" and self.semantic_confidence > 0.8:
            return "symbol"  # targeted: only affected callers
        if self.change_type == "signature_change":
            return "file"    # widen: whole file
        if self.should_propagate:
            return "module"
        return "file"


# ── v0.1: Weighted Decay Table ─────────────────────────────────

# Decay rates for compression confidence — per change type.
# Lower = more stable. Higher = faster drift toward recompression threshold.
WEIGHTED_DECAY_TABLE: Dict[str, float] = {
    "body_only_change":         0.01,   # negligible impact
    "signature_change":         0.08,   # moderate impact
    "architectural_hotspot":    0.15,   # high impact — structural change
    "branch_switch":            0.40,   # full context shift
    "large_churn":              0.25,   # many files changed
    "dependency_change":        0.10,   # import/dependency changed
    "security_module":          0.12,   # auth/security — conservative
}

# Modules with elevated risk — always use conservative invalidation
HIGH_RISK_MODULE_PATTERNS: List[str] = [
    r"""(?ix)
    (?:auth|authenticate|authorize|
       security|crypto|encrypt|decrypt|
       payment|billing|invoice|charge|
       session|token|jwt|oauth|
       permission|role|access.control|
       database.migration|schema.migration)
    """
]

# Threshold at which compression confidence triggers full recompression
RECOMPRESSION_THRESHOLD = 0.60

# Initial compression confidence for fresh contexts
INITIAL_COMPRESSION_CONFIDENCE = 1.0


def get_weighted_decay(change_type: str, file_path: str = "") -> float:
    """Get the weighted decay rate for a change type, accounting for risk.

    High-risk modules get elevated decay to trigger faster recompression.
    """
    base = WEIGHTED_DECAY_TABLE.get(change_type, 0.05)

    # Check if file is a high-risk module
    if file_path and _is_high_risk_module(file_path):
        # Boost decay for security-critical files
        return min(base * 1.5, 0.30)

    return base


def _is_high_risk_module(file_path: str) -> bool:
    """Check if a file path matches high-risk module patterns (auth, security, payment)."""
    for pattern in HIGH_RISK_MODULE_PATTERNS:
        if re.search(pattern, file_path, re.IGNORECASE | re.VERBOSE):
            return True
    return False


def compute_compression_confidence(current_confidence: float,
                                    change_type: str,
                                    file_path: str = "",
                                    change_count: int = 1) -> float:
    """Apply weighted decay to compression confidence.

    Returns new confidence value clamped to [0.0, 1.0].
    """
    decay = get_weighted_decay(change_type, file_path) * change_count
    new_confidence = max(0.0, current_confidence - decay)
    return round(new_confidence, 4)


def should_recompress(confidence: float) -> bool:
    """Check if confidence is below threshold — trigger full recompression."""
    return confidence < RECOMPRESSION_THRESHOLD


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
            m = re.match(r'(?:async\s+)?def\s+(\w+)', sig_line)
            if m:
                sigs[m.group(1)] = sig_line[:240]
        # Match `class Name:`
        elif line.startswith("class ") and line.rstrip().endswith(":"):
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


# ── v0.1: Semantic Confidence Scoring ─────────────────────────

def compute_semantic_confidence(signature_count: int,
                                 changed_count: int,
                                 file_path: str = "") -> float:
    """Compute how confident we are in change classification.

    Factors:
      - Proportion of changed signatures (more changes = higher confidence)
      - File complexity (very large files have lower confidence)
      - High-risk module status (lower confidence for security-critical code)

    Returns 0.0–1.0 confidence score.
    """
    if signature_count == 0:
        return 1.0  # No signatures to analyze — full confidence (or full caution?)

    # Base confidence from change proportion
    proportion = changed_count / max(signature_count, 1)
    confidence = 0.70 + (proportion * 0.25)  # 0.70–0.95 range

    # Small files with few signatures: raise confidence slightly
    if signature_count <= 3:
        confidence = min(confidence + 0.05, 1.0)

    # Large files: lower confidence — more room for hidden semantic changes
    if signature_count > 20:
        confidence = max(confidence - 0.10, 0.5)

    # High-risk modules: conservative — lower confidence
    if file_path and _is_high_risk_module(file_path):
        confidence = max(confidence - 0.10, 0.5)

    return round(confidence, 2)


# ── Signature-aware Diff ──────────────────────────────────────

def classify_change(file_path: Path, cached_sig_hash: str = "") -> ChangeClassification:
    """Classify a file change: signature_change or body_only_change.

    v0.1: Returns ChangeClassification with semantic_confidence.

    Returns:
      - change_type: "signature_change" | "body_only_change" | "unchanged"
      - old_hash, new_hash: signature hashes
      - changed_symbols: list of symbol names whose signatures changed
      - semantic_confidence: 0.0–1.0 confidence in the classification
    """
    new_sigs = extract_signatures(file_path)
    new_hash = compute_signature_hash(new_sigs)

    if not cached_sig_hash:
        confidence = compute_semantic_confidence(
            len(new_sigs), len(new_sigs), str(file_path)
        )
        return ChangeClassification(
            change_type="signature_change", old_hash="", new_hash=new_hash,
            changed_symbols=list(new_sigs.keys()),
            total_symbols=len(new_sigs),
            semantic_confidence=confidence,
        )

    if new_hash == cached_sig_hash:
        return ChangeClassification(
            change_type="unchanged", old_hash=cached_sig_hash, new_hash=new_hash,
            changed_symbols=[], total_symbols=len(new_sigs),
            semantic_confidence=1.0,
        )

    # Hash differs — at minimum, body changed. Check if signatures differ.
    # Conservative: without old signatures cached per-symbol, assume all changed
    changed_symbols = list(new_sigs.keys())
    change_type = "signature_change" if changed_symbols else "body_only_change"
    confidence = compute_semantic_confidence(
        len(new_sigs), len(changed_symbols), str(file_path)
    )

    return ChangeClassification(
        change_type=change_type, old_hash=cached_sig_hash, new_hash=new_hash,
        changed_symbols=changed_symbols, total_symbols=len(new_sigs),
        semantic_confidence=confidence,
    )


# ── v0.1: Call-graph-aware Invalidation Propagation ───────────

def should_propagate_invalidation(classification: ChangeClassification,
                                   file_path: str = "") -> Tuple[bool, str]:
    """Determine whether invalidation should propagate to callers.

    Returns (should_propagate, reason).

    Decision logic:
      - signature_change + high confidence → propagate (targeted)
      - signature_change + low confidence → propagate (conservative)
      - body_only_change + high confidence → skip
      - body_only_change + low confidence → propagate (conservative)
      - high-risk module → always propagate (conservative)
    """
    if classification.change_type == "unchanged":
        return False, "no change detected"

    if classification.change_type == "signature_change":
        if classification.semantic_confidence > 0.8:
            return True, "signature changed, high confidence — targeted propagation"
        return True, "signature changed, low confidence — conservative propagation"

    # body_only_change
    if _is_high_risk_module(file_path):
        return True, "body-only change in high-risk module — conservative propagation"

    if classification.semantic_confidence < 0.65:
        return True, "body-only change but low semantic confidence — conservative propagation"

    return False, "body-only change, high confidence — skip propagation"


# ── Daemon Handler ────────────────────────────────────────────

def handle_invalidation_log(params: Dict[str, Any]) -> Dict[str, Any]:
    """Query invalidation log."""
    limit = int(params.get("limit", 50))
    reason_filter = str(params.get("reason", ""))
    entries = read_invalidation_log(limit=limit, reason_filter=reason_filter)
    stats = get_invalidation_stats()
    return {"entries": entries, "stats": stats}


def handle_invalidation_classify(params: Dict[str, Any]) -> Dict[str, Any]:
    """Classify a file change and return invalidation guidance.

    v0.1: New daemon handler — exposes semantic invalidation to MCP/CLI.
    """
    file_path = Path(params.get("file_path", ""))
    cached_hash = str(params.get("cached_sig_hash", ""))

    if not file_path.exists():
        return {"error": f"File not found: {file_path}"}

    classification = classify_change(file_path, cached_hash)
    should_prop, reason = should_propagate_invalidation(
        classification, str(file_path)
    )

    return {
        "classification": {
            "change_type": classification.change_type,
            "semantic_confidence": classification.semantic_confidence,
            "changed_symbols": classification.changed_symbols[:20],
            "total_symbols": classification.total_symbols,
            "invalidation_scope": classification.invalidation_scope,
        },
        "should_propagate": should_prop,
        "propagation_reason": reason,
        "is_high_risk": _is_high_risk_module(str(file_path)),
        "weighted_decay": get_weighted_decay(classification.change_type, str(file_path)),
    }
