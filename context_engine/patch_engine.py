from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
import subprocess
import tempfile


def build_patch_plan(task: str, files: List[str], project_root: Path, style: str = "unified") -> Dict[str, Any]:
    root = project_root.resolve()
    targets: List[Dict[str, Any]] = []
    for raw_path in files:
        path = (root / raw_path).resolve()
        try:
            relative = str(path.relative_to(root))
        except ValueError:
            targets.append({"path": raw_path, "exists": False, "error": "path_outside_project"})
            continue
        targets.append({"path": relative, "exists": path.exists(), "size": path.stat().st_size if path.exists() else 0})

    if style == "search-replace":
        template = "\n".join(
            [
                "<<<<<<< SEARCH",
                "<exact existing text>",
                "=======",
                "<replacement text>",
                ">>>>>>> REPLACE",
            ]
        )
    else:
        template = "\n".join(
            [
                "diff --git a/<path> b/<path>",
                "--- a/<path>",
                "+++ b/<path>",
                "@@ -<start>,<count> +<start>,<count> @@",
                "-<old line>",
                "+<new line>",
                " <unchanged context line>",
            ]
        )

    return {
        "task": task,
        "project_root": str(root),
        "style": style,
        "targets": targets,
        "apply_policy": "proposal_only_use_codex_apply_patch_for_execution",
        "template": template,
    }


def validation_commands(files: List[str], project_root: Path) -> List[List[str]]:
    root = project_root.resolve()
    commands: List[List[str]] = []
    suffixes = {Path(file).suffix.lower() for file in files}
    for file in files:
        suffix = Path(file).suffix.lower()
        if suffix == ".php":
            commands.append(["php", "-l", file])
        elif suffix == ".py":
            commands.append(["python3", "-m", "py_compile", file])
        elif suffix == ".json":
            commands.append(["python3", "-m", "json.tool", file])
    if suffixes & {".ts", ".tsx", ".js", ".jsx"}:
        if (root / "package.json").exists():
            commands.append(["sh", "-lc", "if command -v pnpm >/dev/null 2>&1; then pnpm exec tsc --noEmit; elif command -v npm >/dev/null 2>&1; then npm exec tsc -- --noEmit; fi"])
    if suffixes & {".java", ".kt"}:
        if (root / "mvnw").exists():
            commands.append(["./mvnw", "-q", "-DskipTests", "compile"])
        elif (root / "gradlew").exists():
            commands.append(["./gradlew", "compileJava"])
    return commands


def validate_files(files: List[str], project_root: Path) -> Dict[str, Any]:
    root = project_root.resolve()
    results: List[Dict[str, Any]] = []
    for command in validation_commands(files, root):
        result = subprocess.run(command, cwd=str(root), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        results.append({"command": command, "returncode": result.returncode, "output": result.stdout[-4000:]})
    return {"ok": all(item["returncode"] == 0 for item in results), "results": results, "commands": len(results)}


def patch_confidence(touched_files: List[str], validation: Dict[str, Any] | None = None, symbol_ambiguity: int = 0) -> Dict[str, Any]:
    score = 0.75
    reasons: List[str] = []
    if validation and validation.get("ok"):
        score += 0.15
        reasons.append("validation_passed")
    elif validation and validation.get("commands", 0) > 0:
        score -= 0.25
        reasons.append("validation_failed")
    if len(touched_files) > 5:
        score -= 0.15
        reasons.append("many_files_touched")
    if any(path.endswith((".json", ".yml", ".yaml", ".toml", ".sql")) for path in touched_files):
        score -= 0.05
        reasons.append("config_or_schema_touched")
    if symbol_ambiguity > 1:
        score -= min(0.2, symbol_ambiguity * 0.05)
        reasons.append("symbol_ambiguity")
    score = max(0.0, min(1.0, score))
    if score >= 0.85:
        level = "high"
    elif score >= 0.65:
        level = "medium"
    else:
        level = "low"
    return {"score": round(score, 3), "level": level, "reasons": reasons}


def apply_unified_patch(patch_text: str, project_root: Path, dry_run: bool = True, validate: bool = True) -> Dict[str, Any]:
    root = project_root.resolve()
    touched: List[str] = []
    for line in patch_text.splitlines():
        if line.startswith("+++ b/"):
            touched.append(line.removeprefix("+++ b/").strip())
    if patch_text.lstrip().startswith("*** Begin Patch"):
        return {
            "applied": False,
            "dry_run": dry_run,
            "error": "codex_apply_patch_format",
            "note": "This patch uses Codex apply_patch grammar. Use the Codex apply_patch tool, or provide a standard git unified diff.",
        }
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as handle:
        handle.write(patch_text)
        handle.write("\n")
        patch_path = Path(handle.name)
    try:
        check = subprocess.run(["git", "apply", "--check", str(patch_path)], cwd=str(root), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        if check.returncode != 0:
            return {
                "applied": False,
                "dry_run": dry_run,
                "returncode": check.returncode,
                "output": check.stdout[-4000:],
                "touched_files": touched,
            }
        if dry_run:
            return {
                "applied": False,
                "dry_run": True,
                "touched_files": touched,
                "validation_plan": validation_commands(touched, root),
                "confidence": patch_confidence(touched),
                "note": "Git apply check passed. Call with dry_run=false from trusted automation to apply.",
            }
        result = subprocess.run(["git", "apply", str(patch_path)], cwd=str(root), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        validation = validate_files(touched, root) if validate and result.returncode == 0 else {"ok": result.returncode == 0, "results": []}
        confidence = patch_confidence(touched, validation)
        return {
            "applied": result.returncode == 0,
            "dry_run": False,
            "returncode": result.returncode,
            "output": result.stdout[-4000:],
            "touched_files": touched,
            "validation": validation,
            "confidence": confidence,
        }
    finally:
        try:
            patch_path.unlink()
        except OSError:
            pass
