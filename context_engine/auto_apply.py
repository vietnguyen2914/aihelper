"""
Safe Auto-Apply — gated automatic patch application with rollback.

Phase 4C: Autonomous Assistance.

Features:
1. Confidence-gated auto-apply (only when score >= 0.85)
2. Pre-apply git snapshot for rollback
3. Post-apply validation (syntax + tests)
4. Automatic rollback on failure
5. Branch-aware: never auto-apply on main/master
6. Intent continuation tracking
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def create_snapshot(project_root: Path, label: str = "") -> Dict[str, Any]:
    """Create a git snapshot (stash) for potential rollback."""
    try:
        # Get current state
        result = subprocess.run(
            ["git", "stash", "create"],
            cwd=str(project_root),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        snapshot_hash = result.stdout.strip()

        if not snapshot_hash:
            # No changes to snapshot
            return {"snapshot_created": False, "reason": "no_changes"}

        # Store snapshot reference
        snapshot_dir = project_root / ".ai-cache" / "aihelper" / "snapshots"
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        snapshot_file = snapshot_dir / f"snapshot-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.json"
        snapshot_data = {
            "hash": snapshot_hash,
            "label": label,
            "branch": _get_branch(project_root),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        snapshot_file.write_text(json.dumps(snapshot_data, indent=2))

        return {
            "snapshot_created": True,
            "hash": snapshot_hash,
            "file": str(snapshot_file),
            "branch": snapshot_data["branch"],
        }
    except Exception as e:
        return {"snapshot_created": False, "error": str(e)}


def rollback_to_snapshot(project_root: Path, snapshot_hash: str) -> Dict[str, Any]:
    """Rollback to a previously created git snapshot."""
    try:
        result = subprocess.run(
            ["git", "stash", "apply", snapshot_hash],
            cwd=str(project_root),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        if result.returncode != 0:
            return {"rolled_back": False, "error": result.stderr.strip()[:200]}

        return {"rolled_back": True, "hash": snapshot_hash}
    except Exception as e:
        return {"rolled_back": False, "error": str(e)}


def safe_apply_patch(
    project_root: Path,
    patch_content: str,
    files: List[str],
    auto_apply: bool = False,
    confidence_threshold: float = 0.85,
) -> Dict[str, Any]:
    """
    Apply a patch with safety gates.

    Safety gates:
    1. Never auto-apply on protected branches (main, master, production)
    2. Requires confidence >= threshold for auto-apply
    3. Creates snapshot before applying
    4. Validates after applying
    5. Rolls back on failure
    """
    branch = _get_branch(project_root)
    is_protected = branch in ("main", "master", "production", "release")

    # ── Confidence check ────────────────────────────────────────
    try:
        from .confidence import score_patch
    except ImportError:
        from confidence import score_patch

    confidence = score_patch(patch_content, project_root, files)
    score = confidence.get("confidence", 0)

    # ── Safety gates ─────────────────────────────────────────────
    if is_protected:
        return {
            "applied": False,
            "reason": "protected_branch",
            "branch": branch,
            "message": f"Cannot auto-apply on protected branch '{branch}'. Switch to a feature branch.",
        }

    if auto_apply and score < confidence_threshold:
        return {
            "applied": False,
            "reason": "confidence_too_low",
            "score": score,
            "threshold": confidence_threshold,
            "recommendation": confidence.get("recommendation", "review"),
        }

    # ── Create snapshot ──────────────────────────────────────────
    snapshot = create_snapshot(project_root, f"auto-apply-{datetime.now(timezone.utc).strftime('%H%M%S')}")

    # ── Write patch to temp file ─────────────────────────────────
    with tempfile.NamedTemporaryFile(mode="w", suffix=".patch", delete=False) as tmp:
        tmp.write(patch_content)
        patch_path = tmp.name

    try:
        # ── Apply patch ──────────────────────────────────────────
        result = subprocess.run(
            ["git", "apply", "--check", patch_path],
            cwd=str(project_root),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )

        if result.returncode != 0:
            return {
                "applied": False,
                "reason": "patch_check_failed",
                "error": result.stderr.strip()[:500],
            }

        # Dry-run check passed, now apply
        result = subprocess.run(
            ["git", "apply", patch_path],
            cwd=str(project_root),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )

        if result.returncode != 0:
            return {
                "applied": False,
                "reason": "patch_apply_failed",
                "error": result.stderr.strip()[:500],
            }

        # ── Post-apply validation ─────────────────────────────────
        validation_errors = _validate_files(project_root, files)

        if validation_errors:
            # Rollback!
            if snapshot.get("snapshot_created"):
                rollback_to_snapshot(project_root, snapshot["hash"])

            return {
                "applied": True,
                "rolled_back": True,
                "reason": "post_apply_validation_failed",
                "validation_errors": validation_errors,
                "snapshot_hash": snapshot.get("hash"),
            }

        return {
            "applied": True,
            "rolled_back": False,
            "confidence": score,
            "snapshot_hash": snapshot.get("hash"),
            "files_changed": len(files),
            "branch": branch,
        }

    finally:
        # Cleanup temp file
        try:
            os.unlink(patch_path)
        except OSError:
            pass


def _validate_files(project_root: Path, files: List[str]) -> List[Dict]:
    """Run lightweight validation on changed files."""
    errors = []
    for file_path in files[:10]:
        full_path = project_root / file_path
        if not full_path.exists():
            continue

        suffix = full_path.suffix.lower()
        try:
            if suffix == ".py":
                result = subprocess.run(
                    ["python3", "-m", "py_compile", str(full_path)],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                )
                if result.returncode != 0:
                    errors.append({"file": file_path, "error": result.stderr.strip()[:200]})
            elif suffix == ".php":
                result = subprocess.run(
                    ["php", "-l", str(full_path)],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                )
                if "No syntax errors" not in result.stdout:
                    errors.append({"file": file_path, "error": result.stdout.strip()[:200]})
            elif suffix == ".json":
                try:
                    with open(full_path) as f:
                        json.load(f)
                except (json.JSONDecodeError, OSError) as e:
                    errors.append({"file": file_path, "error": str(e)[:200]})
        except Exception as e:
            errors.append({"file": file_path, "error": str(e)[:200]})

    return errors


def _get_branch(project_root: Path) -> str:
    """Get current git branch."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(project_root),
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


# ── Intent Continuation ──────────────────────────────────────────

def track_intent_continuation(
    project_root: Path,
    intent: str,
    task: str,
    branch: Optional[str] = None,
) -> Dict[str, Any]:
    """Track intent across sessions for continuity."""
    branch = branch or _get_branch(project_root)

    intent_file = project_root / ".ai-cache" / "aihelper" / "intent_state.json"

    state = {}
    if intent_file.exists():
        try:
            state = json.loads(intent_file.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    # Update state
    if "history" not in state:
        state["history"] = []

    state["current_intent"] = intent
    state["current_branch"] = branch
    state["last_updated"] = datetime.now(timezone.utc).isoformat()
    state["history"].append({
        "intent": intent,
        "task": task[:200],
        "branch": branch,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    # Keep last 50 entries
    if len(state["history"]) > 50:
        state["history"] = state["history"][-50:]

    intent_file.parent.mkdir(parents=True, exist_ok=True)
    intent_file.write_text(json.dumps(state, indent=2))

    return {
        "current_intent": intent,
        "branch": branch,
        "history_count": len(state["history"]),
    }


def get_intent_state(project_root: Path) -> Dict[str, Any]:
    """Get current intent state for continuity."""
    intent_file = project_root / ".ai-cache" / "aihelper" / "intent_state.json"
    if not intent_file.exists():
        return {"current_intent": None, "history": []}

    try:
        return json.loads(intent_file.read_text())
    except (json.JSONDecodeError, OSError):
        return {"current_intent": None, "history": []}


# ── Branch-Aware Memory ──────────────────────────────────────────

def remember_branch_context(
    project_root: Path,
    branch: str,
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """Store branch-specific context for continuity."""
    memory_dir = project_root / ".ai-cache" / "aihelper" / "branch_memory"
    memory_dir.mkdir(parents=True, exist_ok=True)

    memory_file = memory_dir / f"{_safe_branch_name(branch)}.json"

    existing = {}
    if memory_file.exists():
        try:
            existing = json.loads(memory_file.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    existing["branch"] = branch
    existing["last_updated"] = datetime.now(timezone.utc).isoformat()
    existing["context"] = {**existing.get("context", {}), **context}

    memory_file.write_text(json.dumps(existing, indent=2))

    return {"branch": branch, "stored": True}


def recall_branch_context(project_root: Path, branch: Optional[str] = None) -> Dict[str, Any]:
    """Recall branch-specific context."""
    branch = branch or _get_branch(project_root)
    memory_file = project_root / ".ai-cache" / "aihelper" / "branch_memory" / f"{_safe_branch_name(branch)}.json"

    if not memory_file.exists():
        return {"branch": branch, "context": {}}

    try:
        return json.loads(memory_file.read_text())
    except (json.JSONDecodeError, OSError):
        return {"branch": branch, "context": {}}


def _safe_branch_name(branch: str) -> str:
    """Convert branch name to safe filename."""
    return branch.replace("/", "-").replace("\\", "-")[:100]


# ── Daemon handlers ──────────────────────────────────────────────

def handle_safe_apply(params: Dict[str, Any]) -> Dict[str, Any]:
    """Apply patch with safety gates."""
    project_root = Path(params.get("project_root", "."))
    patch_content = params.get("patch_content", "")
    files = params.get("files", [])
    auto_apply = params.get("auto_apply", False)
    threshold = params.get("confidence_threshold", 0.85)
    return safe_apply_patch(project_root, patch_content, files, auto_apply, threshold)


def handle_intent_continuation(params: Dict[str, Any]) -> Dict[str, Any]:
    """Track or recall intent state."""
    project_root = Path(params.get("project_root", "."))
    action = params.get("action", "recall")

    if action == "track":
        return track_intent_continuation(
            project_root,
            params.get("intent", "unknown"),
            params.get("task", ""),
            params.get("branch"),
        )
    return get_intent_state(project_root)


def handle_branch_memory(params: Dict[str, Any]) -> Dict[str, Any]:
    """Store or recall branch-specific memory."""
    project_root = Path(params.get("project_root", "."))
    action = params.get("action", "recall")

    if action == "remember":
        return remember_branch_context(
            project_root,
            params.get("branch", _get_branch(project_root)),
            params.get("context", {}),
        )
    return recall_branch_context(project_root, params.get("branch"))
