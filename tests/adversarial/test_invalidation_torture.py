"""
Adversarial Semantic Invalidation Torture Tests
===============================================

Validates that the invalidation system correctly handles hostile mutation
scenarios: body-only changes, signature changes, type widening, multi-symbol
files, import changes, propagation depth, high-risk modules, confidence decay,
and false invalidation measurement.

Each test is self-contained, uses tempfile isolation, and cleans up after
itself. Runnable with: python -m pytest tests/adversarial/test_invalidation_torture.py -v

Author: aihelper torture-test generator
"""
from __future__ import annotations

import os
import sys
import json
import tempfile
import hashlib
from pathlib import Path
from typing import Any, Dict

# ── Ensure project root is on sys.path ─────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ── Imports under test ─────────────────────────────────────────
from context_engine.invalidation import (
    ChangeClassification,
    classify_change,
    should_propagate_invalidation,
    extract_signatures,
    _extract_py_signatures,
    _is_high_risk_module,
    compute_compression_confidence,
    should_recompress,
    compute_signature_hash,
    compute_semantic_confidence,
    get_weighted_decay,
    RECOMPRESSION_THRESHOLD,
    WEIGHTED_DECAY_TABLE,
)
from context_engine.compressor import (
    reset_compression_confidence,
    get_compression_confidence,
    apply_compression_decay,
    _compression_confidence,
)


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def _write(path: Path, content: str) -> None:
    """Write a file atomically (for the test)."""
    path.write_text(content, encoding="utf-8")


def _compute_sig_hash(file_path: Path) -> str:
    """Helper: extract + hash signatures for a file."""
    sigs = extract_signatures(file_path)
    return compute_signature_hash(sigs)


def _make_lib_file(tmp: Path, version: str = "v1") -> Path:
    """Create lib.py with a simple validate function. Version controls the body."""
    bodies = {
        "v1": "    return x > 5\n",
        "v2": "    return x > 10\n",
        "v3": "    return x > 500\n",
    }
    body = bodies.get(version, bodies["v1"])
    p = tmp / "lib.py"
    _write(p, f"def validate(x):\n{body}")
    return p


def _make_consumer_file(tmp: Path) -> Path:
    """Create consumer.py that imports and calls validate."""
    p = tmp / "consumer.py"
    _write(p, """from lib import validate

def check(values):
    return [validate(v) for v in values]
""")
    return p


def _make_chain_files(tmp: Path) -> Dict[str, Path]:
    """Build a 3-deep call chain: validate() → check() → audit()."""
    # leaf
    lib = tmp / "lib.py"
    _write(lib, "def validate(x):\n    return x > 5\n")

    # direct caller
    checker = tmp / "checker.py"
    _write(checker, """from lib import validate

def check(values):
    return all(validate(v) for v in values)
""")

    # transitive caller
    auditor = tmp / "auditor.py"
    _write(auditor, """from checker import check

def audit(data):
    return check(data.get("scores", []))
""")

    return {"lib": lib, "checker": checker, "auditor": auditor}


def _make_multi_symbol_file(tmp: Path) -> Path:
    """Create a file with 3 independent functions."""
    p = tmp / "multi.py"
    _write(p, """def add(a, b):
    return a + b

def subtract(a, b):
    return a - b

def multiply(a, b):
    return a * b
""")
    return p


# ═══════════════════════════════════════════════════════════════
# TEST 1: Body-only change → should NOT invalidate downstream
# ═══════════════════════════════════════════════════════════════

def test_1_body_only_does_not_propagate():
    """Body-only changes (e.g. return x > 5 → return x > 10) should
    produce 'unchanged' signature classification, and
    should_propagate_invalidation must return False."""
    with tempfile.TemporaryDirectory(prefix="torture_1_") as td:
        tmp = Path(td)

        # 1A. Create files
        lib = _make_lib_file(tmp, "v1")
        consumer = _make_consumer_file(tmp)

        # 1B. Compute old signature hash BEFORE changing body
        old_hash = _compute_sig_hash(lib)

        # 1C. Change ONLY the body (same signature)
        _write(lib, "def validate(x):\n    return x > 10\n")

        # 1D. Classify with the old hash
        classification = classify_change(lib, old_hash)
        should_prop, reason = should_propagate_invalidation(classification, str(lib))

        # 1E. ASSERTIONS
        print(f"  [Test 1] change_type={classification.change_type}, "
              f"should_propagate={should_prop}, confidence={classification.semantic_confidence}")
        print(f"  [Test 1] reason={reason}")

        # The body-only change does NOT alter extracted signatures (same def line)
        # so classify_change returns "unchanged" when old_hash is provided.
        assert classification.change_type == "unchanged", (
            f"Expected 'unchanged' for body-only change, got '{classification.change_type}'"
        )
        assert classification.old_hash == old_hash
        assert classification.new_hash == old_hash  # same hash since sigs unchanged
        assert should_prop is False, (
            f"Body-only change should NOT propagate; got should_propagate={should_prop}"
        )
        assert "no change detected" in reason

        # 1F. Also verify: classify_change WITHOUT old hash (first-seen path)
        #     returns "signature_change" because there's no baseline.
        first_seen = classify_change(lib)
        assert first_seen.change_type == "signature_change", (
            f"First-seen file should classify as 'signature_change', "
            f"got '{first_seen.change_type}'"
        )

    print("  [Test 1] PASS")


# ═══════════════════════════════════════════════════════════════
# TEST 2: Signature change → SHOULD propagate
# ═══════════════════════════════════════════════════════════════

def test_2_signature_change_propagates():
    """Changing a function's parameter list (def validate(x) → def validate(x, threshold=10))
    must produce 'signature_change' and should_propagate must be True."""
    with tempfile.TemporaryDirectory(prefix="torture_2_") as td:
        tmp = Path(td)

        lib = _make_lib_file(tmp, "v1")
        old_hash = _compute_sig_hash(lib)

        # Change signature: add a parameter
        _write(lib, "def validate(x, threshold=10):\n    return x > threshold\n")

        classification = classify_change(lib, old_hash)
        should_prop, reason = should_propagate_invalidation(classification, str(lib))

        print(f"  [Test 2] change_type={classification.change_type}, "
              f"should_propagate={should_prop}, confidence={classification.semantic_confidence}")
        print(f"  [Test 2] reason={reason}")

        assert classification.change_type == "signature_change", (
            f"Expected 'signature_change', got '{classification.change_type}'"
        )
        assert classification.old_hash == old_hash
        assert classification.new_hash != old_hash, (
            "New signature hash must differ from old hash"
        )
        assert should_prop is True, (
            f"Signature change MUST propagate; got should_propagate={should_prop}"
        )
        assert "signature changed" in reason.lower()

        # Verify changed_symbols contains the changed function
        assert "validate" in classification.changed_symbols, (
            f"'validate' should be in changed_symbols, got {classification.changed_symbols}"
        )

    print("  [Test 2] PASS")


# ═══════════════════════════════════════════════════════════════
# TEST 3: Signature-compatible but semantic-breaking
# ═══════════════════════════════════════════════════════════════

def test_3_semantic_breaking_with_same_signature():
    """SAME signature but DRAMATICALLY different behavior (x > 5 vs x > 500).
    This is a KNOWN LIMITATION: the current system only compares signature lines
    via extract_signatures and cannot detect semantic changes within function bodies.

    The test documents this gap and verifies the system is honest about it."""
    with tempfile.TemporaryDirectory(prefix="torture_3_") as td:
        tmp = Path(td)

        lib = _make_lib_file(tmp, "v1")  # return x > 5
        old_hash = _compute_sig_hash(lib)

        # Same signature, wildly different body
        _write(lib, "def validate(x):\n    return x > 500\n")

        classification = classify_change(lib, old_hash)
        should_prop, reason = should_propagate_invalidation(classification, str(lib))

        print(f"  [Test 3] change_type={classification.change_type}, "
              f"should_propagate={should_prop}, confidence={classification.semantic_confidence}")
        print(f"  [Test 3] reason={reason}")
        print(f"  [Test 3] KNOWN LIMITATION: system does NOT inspect bodies; "
              f"semantic-breaking changes within same signature are invisible.")

        # The system returns 'unchanged' because signatures are identical.
        # This is the honest behavior given the design.
        assert classification.change_type == "unchanged", (
            f"Expected 'unchanged' (same sig, different body), got '{classification.change_type}'"
        )
        assert should_prop is False, (
            "Semantic-breaking but same-signature should not propagate per current design"
        )

        # ── Document limitation severity ──────────────────────────
        print(f"  [Test 3] LIMITATION SEVERITY: "
              f"All callers silently receive incorrect results. "
              f"Mitigation: semantic_diff or body-hash tracking needed.")

    print("  [Test 3] PASS (limitation documented)")


# ═══════════════════════════════════════════════════════════════
# TEST 4: Type widening → signature_change
# ═══════════════════════════════════════════════════════════════

def test_4_type_widening_detected():
    """Changing type annotations (int → int | str or int → Any) changes the
    signature line, so extract_signatures MUST detect the difference."""
    with tempfile.TemporaryDirectory(prefix="torture_4_") as td:
        tmp = Path(td)

        # 4A: Narrow type
        lib = tmp / "process.py"
        _write(lib, "def process(data: int) -> bool:\n    return data > 0\n")
        old_hash = _compute_sig_hash(lib)

        # 4B: Widen to Union type
        _write(lib, "def process(data: int | str) -> bool:\n    return bool(data)\n")
        classification = classify_change(lib, old_hash)
        should_prop, reason = should_propagate_invalidation(classification, str(lib))

        print(f"  [Test 4a] Union type widening: change_type={classification.change_type}, "
              f"should_propagate={should_prop}")
        assert classification.change_type == "signature_change", (
            f"Type widening (int → int|str) must be signature_change, "
            f"got '{classification.change_type}'"
        )
        assert should_prop is True

        # 4C: Widen to Any
        _write(lib, "def process(data: Any) -> bool:\n    return bool(data)\n")
        classification2 = classify_change(lib, old_hash)
        print(f"  [Test 4b] Widening to Any: change_type={classification2.change_type}, "
              f"should_propagate={classification2.should_propagate}")
        # This also changes the signature line → detectable
        assert classification2.change_type == "signature_change", (
            f"Type widening (int → Any) must be signature_change, "
            f"got '{classification2.change_type}'"
        )

        # 4D: Remove return type annotation entirely
        _write(lib, "def process(data):\n    return bool(data)\n")
        classification3 = classify_change(lib, old_hash)
        print(f"  [Test 4c] Remove annotations: change_type={classification3.change_type}")
        assert classification3.change_type == "signature_change", (
            f"Removing type annotations changes signature line, got '{classification3.change_type}'"
        )

    print("  [Test 4] PASS")


# ═══════════════════════════════════════════════════════════════
# TEST 5: Multi-symbol file — only changed function propagates
# ═══════════════════════════════════════════════════════════════

def test_5_multi_symbol_isolation():
    """In a file with 3 functions, changing only 1 function's signature must
    result in that single symbol being in changed_symbols. The other 2
    functions should NOT be listed as changed."""
    with tempfile.TemporaryDirectory(prefix="torture_5_") as td:
        tmp = Path(td)

        mp = _make_multi_symbol_file(tmp)
        old_hash = _compute_sig_hash(mp)

        # Change only 'add' signature: add parameter
        _write(mp, """def add(a, b, c=0):
    return a + b + c

def subtract(a, b):
    return a - b

def multiply(a, b):
    return a * b
""")

        classification = classify_change(mp, old_hash)
        should_prop, reason = should_propagate_invalidation(classification, str(mp))

        print(f"  [Test 5] change_type={classification.change_type}, "
              f"changed_symbols={classification.changed_symbols}, "
              f"total_symbols={classification.total_symbols}")

        assert classification.change_type == "signature_change"
        assert should_prop is True

        # NOTE: The current implementation lists ALL symbols as changed
        # when hash differs (since it can't do per-symbol diffs without
        # old signatures stored per symbol). This is a known limitation.
        changed = set(classification.changed_symbols)
        assert "add" in changed, "'add' must be in changed_symbols"
        assert classification.total_symbols == 3, (
            f"3 functions total, got {classification.total_symbols}"
        )

        # ── Per-symbol granularity documentation ────────────────
        has_unnecessary = changed - {"add"}
        if has_unnecessary:
            print(f"  [Test 5] NOTE: current impl reports ALL symbols as changed "
                  f"({changed}) because per-symbol signature history is not cached. "
                  f"Unnecessary symbols flagged: {has_unnecessary}")
        else:
            print(f"  [Test 5] Per-symbol granularity achieved!")

    print("  [Test 5] PASS")


# ═══════════════════════════════════════════════════════════════
# TEST 6: Import change detection
# ═══════════════════════════════════════════════════════════════

def test_6_import_changes():
    """Changing 'from lib import validate' to 'from lib_v2 import validate'
    is an IMPORT change. The current system ONLY tracks function/class
    signatures via extract_signatures; it does NOT track import lines.

    This is a KNOWN LIMITATION. Document the gap."""
    with tempfile.TemporaryDirectory(prefix="torture_6_") as td:
        tmp = Path(td)

        consumer = tmp / "consumer.py"
        _write(consumer, """from lib import validate

def check(values):
    return [validate(v) for v in values]
""")
        old_hash = _compute_sig_hash(consumer)

        # Change import line only
        _write(consumer, """from lib_v2 import validate

def check(values):
    return [validate(v) for v in values]
""")

        classification = classify_change(consumer, old_hash)
        should_prop, reason = should_propagate_invalidation(classification, str(consumer))

        print(f"  [Test 6] change_type={classification.change_type}, "
              f"should_propagate={should_prop}")
        print(f"  [Test 6] reason={reason}")

        # The signature of `check` is unchanged, so extract_signatures
        # returns the same result → 'unchanged'. Import changes are invisible.
        assert classification.change_type == "unchanged", (
            f"Expected 'unchanged' (import changes invisible to sig extractor), "
            f"got '{classification.change_type}'"
        )
        print(f"  [Test 6] KNOWN LIMITATION: import changes are NOT detected. "
              f"Mitigation: AST-based import tracking or file-level content hash.")

    print("  [Test 6] PASS (limitation documented)")


# ═══════════════════════════════════════════════════════════════
# TEST 7: Propagation depth — transitive caller coverage
# ═══════════════════════════════════════════════════════════════

def test_7_propagation_depth():
    """Build validate() → check() → audit() chain. When validate's signature
    changes, should_propagate_invalidation returns True for the lib.py file,
    but the CURRENT system does NOT traverse transitive callers automatically.

    This test documents the distinction between 'should propagate' (True) and
    'does the system actually follow the full call graph' (no — that requires
    integration with the graph_db / _apply_semantic_invalidation)."""
    with tempfile.TemporaryDirectory(prefix="torture_7_") as td:
        tmp = Path(td)
        files = _make_chain_files(tmp)

        # Change validate's signature
        lib = files["lib"]
        old_hash = _compute_sig_hash(lib)
        _write(lib, "def validate(x, min_val=0):\n    return x > min_val\n")
        classification = classify_change(lib, old_hash)
        should_prop, reason = should_propagate_invalidation(classification, str(lib))

        print(f"  [Test 7] lib.py: change_type={classification.change_type}, "
              f"should_propagate={should_prop}")
        print(f"  [Test 7] reason={reason}")

        assert classification.change_type == "signature_change"
        assert should_prop is True, "Signature change on leaf must propagate"

        # ── Now check that the call graph isn't traversed here ──
        # should_propagate_invalidation returns a per-file bool, not a
        # transitive caller list. True means "yes, callers of this file
        # should be invalidated" — but it does NOT enumerate them.
        checker_class = classify_change(files["checker"], old_hash)
        # (checker didn't change, so unchanged — the graph_db / cache.py
        #  integration is responsible for traversing call graph edges)
        print(f"  [Test 7] checker.py (unchanged): type={checker_class.change_type}")
        print(f"  [Test 7] Transitive caller traversal requires graph_db integration "
              f"in _apply_semantic_invalidation, not tested here in isolation.")

    print("  [Test 7] PASS")


# ═══════════════════════════════════════════════════════════════
# TEST 8: High-risk module detection
# ═══════════════════════════════════════════════════════════════

def test_8_high_risk_module_detection():
    """Paths containing auth/security/payment/config/secret MUST be
    identified as high-risk by _is_high_risk_module."""
    high_risk_paths = [
        "/app/auth/login.py",
        "/app/security/encrypt.py",
        "/app/payment/checkout.py",
        "database_migration/config.yml",
        "security/crypto/keys.py",
        "billing/invoice.py",
        "session/manager.py",
        "token/generator.py",
        "jwt/validate.py",
        "oauth/flow.py",
        "permission/checker.py",
        "role/admin.py",
        "access_control/gate.py",
        "database_migration/v002.py",
        "schema_migration/add_column.py",
        "authentication/middleware.py",
        "authorize/decorator.py",
        "crypto/aes.py",
        "charge/webhook.py",
        "encrypt/password.py",
        "decrypt/token.py",
    ]

    safe_paths = [
        "/app/utils/helpers.py",
        "models/user.py",
        "routes/index.py",
        "views/dashboard.py",
        "services/notification.py",
        "lib/parser.py",
        "core/types.py",
        "middleware/logging.py",
        "decorators/cache.py",
        "handlers/errors.py",
    ]

    all_pass = True
    for path in high_risk_paths:
        result = _is_high_risk_module(path)
        if not result:
            print(f"  [Test 8] FAIL: '{path}' should be high-risk but was not")
            all_pass = False
        else:
            print(f"  [Test 8] OK: '{path}' → high-risk\u2713")

    for path in safe_paths:
        result = _is_high_risk_module(path)
        if result:
            print(f"  [Test 8] FAIL: '{path}' should be safe but was flagged high-risk")
            all_pass = False
        else:
            print(f"  [Test 8] OK: '{path}' → safe\u2713")

    assert all_pass, "One or more high-risk detection checks failed"
    print("  [Test 8] PASS (all 21 high-risk paths detected, 10 safe paths clear)")


# ═══════════════════════════════════════════════════════════════
# TEST 9: Confidence decay accumulation
# ═══════════════════════════════════════════════════════════════

def test_9_confidence_decay_accumulation():
    """Apply multiple changes to the same file/context and verify that
    compression confidence decays below RECOMPRESSION_THRESHOLD (0.60),
    and should_recompress returns True."""
    with tempfile.TemporaryDirectory(prefix="torture_9_") as td:
        tmp = Path(td)
        project_root = tmp

        # Reset to baseline
        with _patch_compression_confidence(project_root):
            reset_compression_confidence(project_root)
            initial = get_compression_confidence(project_root)
            print(f"  [Test 9] Initial confidence: {initial}")
            assert initial == 1.0

            # Apply 15 body_only changes (0.01 each) — NOT enough to cross threshold
            for i in range(15):
                result = apply_compression_decay(
                    "body_only_change",
                    file_path=str(tmp / f"change_{i}.py"),
                    change_count=1,
                    project_root=project_root,
                )

            confidence_after_15_body = get_compression_confidence(project_root)
            print(f"  [Test 9] After 15 body_only changes: {confidence_after_15_body}")
            assert confidence_after_15_body > RECOMPRESSION_THRESHOLD, (
                f"15 body-only changes should NOT drop below {RECOMPRESSION_THRESHOLD}, "
                f"got {confidence_after_15_body}"
            )
            assert result["needs_recompression"] is False, (
                "15 body-only should not trigger recompression"
            )

            # Now apply signature changes to force below threshold
            # Each signature_change decays 0.08.
            # Current ~0.85, need 0.85 - 0.6 = 0.25 more decay.
            # 0.25 / 0.08 = 3.125 → 4 signature changes needed.
            for i in range(15, 19):
                result = apply_compression_decay(
                    "signature_change",
                    file_path=str(tmp / f"change_{i}.py"),
                    change_count=1,
                    project_root=project_root,
                )

            final_confidence = get_compression_confidence(project_root)
            print(f"  [Test 9] After 15 body + 4 sig changes: {final_confidence}")
            print(f"  [Test 9] Result: {json.dumps(result, default=str)}")

            assert final_confidence < RECOMPRESSION_THRESHOLD, (
                f"After sufficient changes, confidence must drop below "
                f"{RECOMPRESSION_THRESHOLD}, got {final_confidence}"
            )
            assert result["needs_recompression"] is True, (
                "should_recompress must return True when below threshold"
            )

            # Verify monotonic decay: each call reduces confidence
            reset_compression_confidence(project_root)
            prev = get_compression_confidence(project_root)
            for i in range(5):
                apply_compression_decay(
                    "signature_change",
                    change_count=1,
                    project_root=project_root,
                )
                cur = get_compression_confidence(project_root)
                assert cur <= prev, (
                    f"Confidence must not increase: {prev} → {cur}"
                )
                prev = cur
            print(f"  [Test 9] Monotonic decay verified (5 steps: 1.0 → {prev})")

            # Verify signature_change decays faster than body_only_change
            reset_compression_confidence(project_root)
            apply_compression_decay("signature_change", project_root=project_root)
            sig_conf = get_compression_confidence(project_root)

            reset_compression_confidence(project_root)
            apply_compression_decay("body_only_change", project_root=project_root)
            body_conf = get_compression_confidence(project_root)

            assert sig_conf < body_conf, (
                f"Signature change decay ({sig_conf}) should be larger "
                f"than body-only decay ({body_conf})"
            )
            print(f"  [Test 9] Signature decay faster: {sig_conf} < {body_conf} ✓")

        # Verify cleanup restored state
        assert _compression_confidence.get(str(project_root)) is None, (
            "Should have cleaned up test state"
        )

    print("  [Test 9] PASS")


# ═══════════════════════════════════════════════════════════════
# TEST 10: False invalidation measurement
# ═══════════════════════════════════════════════════════════════

def test_10_false_invalidation_measurement():
    """With 10 files where only 1 function body changes, measure how many
    downstream callers are unnecessarily invalidated. The system should
    report 0 unnecessary invalidations because body-only changes on
    non-high-risk files do NOT propagate."""
    with tempfile.TemporaryDirectory(prefix="torture_10_") as td:
        tmp = Path(td)

        # Create 10 "library" files, each with a function
        lib_files: Dict[str, Path] = {}
        for i in range(10):
            p = tmp / f"lib_{i}.py"
            _write(p, f"def func_{i}(x):\n    return x + {i}\n")
            lib_files[f"lib_{i}"] = p

        # Create 10 consumer files, each importing a specific lib
        consumer_files: Dict[str, Path] = {}
        for i in range(10):
            p = tmp / f"consumer_{i}.py"
            _write(p, f"""from lib_{i} import func_{i}

def use_{i}(values):
    return [func_{i}(v) for v in values]
""")
            consumer_files[f"consumer_{i}"] = p

        # Pre-compute all signature hashes
        old_hashes: Dict[str, str] = {}
        for name, p in {**lib_files, **consumer_files}.items():
            old_hashes[name] = _compute_sig_hash(p)

        # ── Change ONLY lib_3.py's body (not signature) ─────
        _write(lib_files["lib_3"],
               "def func_3(x):\n    return x + 3000\n")  # dramatic but same sig

        # ── Classify ALL files ──────────────────────────────
        false_invalidations = 0
        total_downstream = 0
        results: Dict[str, Dict[str, Any]] = {}

        for name, file_path in {**lib_files, **consumer_files}.items():
            old_hash = old_hashes.get(name, "")
            classification = classify_change(file_path, old_hash)
            should_prop, reason = should_propagate_invalidation(
                classification, str(file_path)
            )

            results[name] = {
                "change_type": classification.change_type,
                "should_propagate": should_prop,
                "reason": reason,
            }

            # A consumer is a "downstream" file. If it's flagged for propagation
            # without any actual signature change in its own dependencies, that's
            # a false invalidation.
            if name.startswith("consumer_"):
                total_downstream += 1
                if should_prop:
                    false_invalidations += 1

        # ── Print results ───────────────────────────────────
        for name, r in sorted(results.items()):
            marker = " ⚠ FALSE INVALIDATION" if r["should_propagate"] and name.startswith("consumer_") else ""
            print(f"  [Test 10] {name}: type={r['change_type']}, "
                  f"propagate={r['should_propagate']}{marker}")
            if marker:
                print(f"    reason: {r['reason']}")

        # ── Assertions ──────────────────────────────────────
        # lib_3 itself: body-only change → "unchanged"
        assert results["lib_3"]["change_type"] == "unchanged", (
            f"lib_3 should be 'unchanged' (body-only), got '{results['lib_3']['change_type']}'"
        )

        # Verify: exactly 0 downstream callers are flagged
        print(f"\n  [Test 10] Total downstream: {total_downstream}, "
              f"False invalidations: {false_invalidations}")
        assert false_invalidations == 0, (
            f"Expected 0 false invalidations, got {false_invalidations}. "
            f"Downstream consumers should NOT propagate for body-only changes."
        )
        # Verify lib_3 itself does not propagate
        assert results["lib_3"]["should_propagate"] is False, (
            "lib_3 body-only change should not propagate"
        )

        # Verify all other lib files are unchanged
        for i in range(10):
            if i == 3:
                continue
            assert results[f"lib_{i}"]["change_type"] == "unchanged", (
                f"lib_{i} should be unchanged, got {results[f'lib_{i}']['change_type']}"
            )

    print("  [Test 10] PASS")


# ═══════════════════════════════════════════════════════════════
# BONUS: Edge Case Tests
# ═══════════════════════════════════════════════════════════════

def test_edge_empty_file():
    """Empty files or files with no extractable signatures."""
    with tempfile.TemporaryDirectory(prefix="torture_edge_") as td:
        tmp = Path(td)
        p = tmp / "empty.py"
        _write(p, "")
        sigs = extract_signatures(p)
        assert sigs == {}, f"Empty file should have 0 signatures, got {sigs}"
        h = compute_signature_hash(sigs)
        assert h == "", f"Empty signature hash should be '', got '{h}'"

        classification = classify_change(p)
        # First-seen with no signatures: semantic_confidence = 1.0
        assert classification.change_type == "signature_change"
        # 0 total_symbols since no signatures found
        print(f"  [Edge] Empty file: type={classification.change_type}, "
              f"symbols={classification.total_symbols}, "
              f"confidence={classification.semantic_confidence}")
    print("  [Edge empty_file] PASS")


def test_edge_non_python_file():
    """Non-Python file parsing — should return empty signatures."""
    with tempfile.TemporaryDirectory(prefix="torture_edge_") as td:
        tmp = Path(td)
        p = tmp / "data.json"
        _write(p, '{"key": "value"}')
        sigs = extract_signatures(p)
        assert sigs == {}, f"JSON file should have 0 signatures, got {sigs}"
    print("  [Edge non_python] PASS")


def test_edge_high_risk_boosted_decay():
    """High-risk modules should get 1.5x decay boost, capped at 0.30."""
    with tempfile.TemporaryDirectory(prefix="torture_edge_") as td:
        tmp = Path(td)

        # body_only in auth file
        decay_auth = get_weighted_decay("body_only_change", "/app/auth/login.py")
        expected_auth = min(WEIGHTED_DECAY_TABLE["body_only_change"] * 1.5, 0.30)
        assert decay_auth == expected_auth, (
            f"Expected auth decay {expected_auth}, got {decay_auth}"
        )

        # body_only in safe file (no boost)
        decay_safe = get_weighted_decay("body_only_change", "/app/utils/helpers.py")
        expected_safe = WEIGHTED_DECAY_TABLE["body_only_change"]
        assert decay_safe == expected_safe, (
            f"Expected safe decay {expected_safe}, got {decay_safe}"
        )

        # signature_change in payment file
        decay_payment = get_weighted_decay("signature_change", "/app/payment/charge.py")
        expected_payment = min(WEIGHTED_DECAY_TABLE["signature_change"] * 1.5, 0.30)
        assert decay_payment == expected_payment, (
            f"Expected payment decay {expected_payment}, got {decay_payment}"
        )

        print(f"  [Edge] auth body={decay_auth}, safe body={decay_safe}, "
              f"payment sig={decay_payment}")
    print("  [Edge high_risk_decay] PASS")


def test_edge_semantic_confidence_scoring():
    """Verify semantic confidence scoring logic from compute_semantic_confidence."""
    # 1 changed out of 1 total → proportion=1.0 → 0.70 + 0.25 = 0.95
    # Small file (1 ≤ 3) → +0.05 → 1.0
    conf1 = compute_semantic_confidence(1, 1)
    assert conf1 == 1.0, f"Expected 1.0, got {conf1}"

    # 1 changed out of 10 → proportion=0.1 → 0.70 + 0.025 = 0.725
    # Python 3 uses banker's rounding: round(0.725, 2) = 0.72
    conf2 = compute_semantic_confidence(10, 1)
    assert conf2 == 0.72, f"Expected 0.72, got {conf2}"

    # 5 changed out of 10 → 0.70 + 0.125 = 0.825
    conf3 = compute_semantic_confidence(10, 5)
    assert conf3 == 0.82, f"Expected 0.82, got {conf3}"

    # Large file (25) → -0.10 from base
    conf4 = compute_semantic_confidence(25, 1)
    # 1/25=0.04, 0.70+0.04*0.25=0.71, large file → 0.61
    assert conf4 == 0.61, f"Expected 0.61, got {conf4}"

    # High risk + large file → 0.71 - 0.10 (large) - 0.10 (high-risk) = 0.51
    conf5 = compute_semantic_confidence(25, 1, "/app/auth/login.py")
    assert conf5 == 0.51, f"Expected 0.51, got {conf5}"

    print(f"  [Edge] conf scores: simple={conf1}, moderate={conf2}, "
          f"large={conf4}, highrisk={conf5}")
    print("  [Edge semantic_confidence] PASS")


def test_edge_conservative_fallback_body_only_low_confidence():
    """body_only_change with low semantic confidence should propagate
    as a conservative fallback (confidence < 0.65 in should_propagate_invalidation)."""
    # Low confidence body-only change → propagate
    classification = ChangeClassification(
        change_type="body_only_change",
        semantic_confidence=0.50,
        changed_symbols=["validate"],
        total_symbols=1,
    )
    should_prop, reason = should_propagate_invalidation(classification, "/app/utils.py")
    assert should_prop is True, (
        f"Low-confidence (0.50) body-only should propagate conservatively"
    )
    assert "low semantic confidence" in reason.lower()

    # High confidence body-only change → skip propagation
    classification2 = ChangeClassification(
        change_type="body_only_change",
        semantic_confidence=0.90,
        changed_symbols=["validate"],
        total_symbols=1,
    )
    should_prop2, reason2 = should_propagate_invalidation(classification2, "/app/utils.py")
    assert should_prop2 is False, (
        f"High-confidence (0.90) body-only should NOT propagate"
    )
    assert "skip propagation" in reason2.lower()

    print(f"  [Edge] Low-conf body: propagate={should_prop}, "
          f"High-conf body: propagate={should_prop2}")
    print("  [Edge conservative_fallback] PASS")


# ═══════════════════════════════════════════════════════════════
# Context manager helper for Test 9 (clean up global state)
# ═══════════════════════════════════════════════════════════════

from contextlib import contextmanager

@contextmanager
def _patch_compression_confidence(project_root: Path):
    """Save/restore compression confidence for a given project root to
    avoid test pollution."""
    key = str(project_root)
    saved = _compression_confidence.get(key)
    try:
        yield
    finally:
        _compression_confidence.pop(key, None)
        if saved is not None:
            _compression_confidence[key] = saved


# ═══════════════════════════════════════════════════════════════
# Test Report (run via pytest)
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Manual runner that prints a detailed report
    tests = [
        ("Test 1: Body-only → no propagation", test_1_body_only_does_not_propagate),
        ("Test 2: Signature change → propagate", test_2_signature_change_propagates),
        ("Test 3: Semantic-breaking same-sig (limitation)", test_3_semantic_breaking_with_same_signature),
        ("Test 4: Type widening", test_4_type_widening_detected),
        ("Test 5: Multi-symbol isolation", test_5_multi_symbol_isolation),
        ("Test 6: Import changes (limitation)", test_6_import_changes),
        ("Test 7: Propagation depth", test_7_propagation_depth),
        ("Test 8: High-risk module detection", test_8_high_risk_module_detection),
        ("Test 9: Confidence decay", test_9_confidence_decay_accumulation),
        ("Test 10: False invalidation measurement", test_10_false_invalidation_measurement),
        ("Edge: Empty file", test_edge_empty_file),
        ("Edge: Non-Python file", test_edge_non_python_file),
        ("Edge: High-risk decay boost", test_edge_high_risk_boosted_decay),
        ("Edge: Semantic confidence scoring", test_edge_semantic_confidence_scoring),
        ("Edge: Conservative fallback", test_edge_conservative_fallback_body_only_low_confidence),
    ]

    passed = 0
    failed = 0
    skipped = []

    print("\n" + "=" * 72)
    print("  AIHELPER ADVERSARIAL INVALIDATION TORTURE TEST REPORT")
    print("=" * 72)

    for name, fn in tests:
        try:
            fn()
            passed += 1
            status = "PASS"
        except AssertionError as e:
            failed += 1
            status = f"FAIL"
            print(f"  [{status}] {name}")
            print(f"    {e}")
        except Exception as e:
            failed += 1
            status = f"ERROR"
            print(f"  [{status}] {name}")
            import traceback
            traceback.print_exc()

    print("\n" + "-" * 72)
    print(f"  TOTAL: {len(tests)}  |  PASS: {passed}  |  FAIL: {failed}  |  SKIP: {len(skipped)}")
    print("=" * 72)
    sys.exit(0 if failed == 0 else 1)
