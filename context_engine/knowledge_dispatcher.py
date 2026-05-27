"""
Knowledge Dispatcher — formats and writes aihelper knowledge into
each editor's native config files.

Instead of building a custom retrieval/injection protocol, this module
reuses the existing mechanisms each editor already has:

- VSCode Copilot: ~/.github/copilot-instructions.md (markdown)
- Codex: ~/.codex/config.json (developer_instructions field)
- Claude: ~/.claude/aihelper-claude-instructions.md (markdown)
- Zed/Gemini/OpenCode: aihelper MCP tools (context/symbols/memory)

On dispatch, knowledge from the SQLite memory engine is formatted
and written to all applicable editor configs, so every agent in
every editor sees the same architectural decisions, debug history,
and developer preferences — without any new protocols.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# ── Shared constants ────────────────────────────────────────────

IS_MACOS = os.sys.platform == "darwin"
IS_WINDOWS = os.sys.platform == "win32"


def _home() -> Path:
    if IS_WINDOWS:
        return Path(os.environ.get("USERPROFILE", str(Path.home())))
    return Path.home()


# ── Knowledge formatting ────────────────────────────────────────

def _format_knowledge_markdown(knowledge: Dict[str, Any]) -> str:
    """Format knowledge into a compact markdown section for editor instructions."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "",
        "<!-- ═══════════════════════════════════════════════════════════ -->",
        f"<!-- aihelper Knowledge — auto-dispatched {now} -->",
        "<!-- ═══════════════════════════════════════════════════════════ -->",
        "",
    ]

    # Developer Preferences
    prefs = knowledge.get("preferences", {})
    if prefs:
        lines.append("## Developer Preferences (aihelper)")
        lines.append("")
        by_category: Dict[str, List[str]] = {}
        all_prefs = knowledge.get("preferences_detail", [])
        for p in all_prefs:
            cat = p.get("category", "general") or "general"
            by_category.setdefault(cat, []).append(f"- **{p['key']}**: {p['value']}")

        if by_category:
            for cat, items in sorted(by_category.items()):
                lines.append(f"### {cat.title()}")
                lines.extend(items)
                lines.append("")
        else:
            for k, v in sorted(prefs.items()):
                lines.append(f"- **{k}**: {v}")
            lines.append("")

    # Architectural Decisions
    decisions = knowledge.get("decisions", [])
    if decisions:
        lines.append("## Architectural Decisions (aihelper)")
        lines.append("")
        for d in decisions[:5]:
            lines.append(f"### {d.get('id', 'unknown')}")
            lines.append(f"- **Choice**: {d.get('choice', 'N/A')}")
            if d.get("reason"):
                lines.append(f"- **Reason**: {d['reason']}")
            alts = d.get("alternatives", [])
            if alts:
                if isinstance(alts, str):
                    try:
                        alts = json.loads(alts)
                    except json.JSONDecodeError:
                        alts = [alts]
                lines.append(f"- **Alternatives considered**: {', '.join(alts)}")
            files = d.get("related_files", [])
            if files:
                if isinstance(files, str):
                    try:
                        files = json.loads(files)
                    except json.JSONDecodeError:
                        files = [files]
                lines.append(f"- **Related files**: {', '.join(files)}")
            lines.append("")

    # Debugging History
    debugs = knowledge.get("debugs", [])
    if debugs:
        lines.append("## Known Issues & Fixes (aihelper)")
        lines.append("")
        for dbg in debugs[:3]:
            lines.append(f"- **{dbg.get('symptom', 'Unknown')[:120]}**")
            if dbg.get("root_cause"):
                lines.append(f"  - Root cause: {dbg['root_cause'][:150]}")
            if dbg.get("fix_commit"):
                lines.append(f"  - Fix: {dbg['fix_commit']}")
            lines.append("")

    return "\n".join(lines)


def _format_knowledge_codex(knowledge: Dict[str, Any]) -> str:
    """Format knowledge for Codex developer_instructions (compact text, no markdown)."""
    parts = []

    prefs = knowledge.get("preferences", {})
    if prefs:
        pref_list = "; ".join(f"{k}={v}" for k, v in sorted(prefs.items()))
        parts.append(f"Developer preferences: {pref_list}.")

    decisions = knowledge.get("decisions", [])
    if decisions:
        dec_parts = []
        for d in decisions[:3]:
            dec_parts.append(f"{d.get('id')}: {d.get('choice')}" +
                           (f" (reason: {d.get('reason')[:80]})" if d.get('reason') else ""))
        parts.append("Architectural decisions: " + "; ".join(dec_parts) + ".")

    debugs = knowledge.get("debugs", [])
    if debugs:
        dbg_parts = []
        for d in debugs[:3]:
            dbg_parts.append(f"{d.get('symptom', '')[:80]} -> {d.get('root_cause', '')[:80]}")
        parts.append("Known issues: " + "; ".join(dbg_parts) + ".")

    return "\n".join(parts)


# ── File I/O (reuses integration_common patterns) ──────────────

def _write_if_changed(path: Path, content: str, label: str = "") -> bool:
    """Write content to file only if changed. Returns True if written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            current = path.read_text(encoding="utf-8")
            if current == content:
                return False
        except (OSError, UnicodeDecodeError):
            pass
    path.write_text(content, encoding="utf-8")
    return True


def _merge_markdown_section(file_path: Path, section: str, marker: str = "aihelper Knowledge") -> bool:
    """Merge a markdown section into a file. Replaces existing section or appends."""
    file_path.parent.mkdir(parents=True, exist_ok=True)

    existing = ""
    if file_path.exists():
        try:
            existing = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            pass

    # Remove existing aihelper knowledge section
    import re
    pattern = re.compile(
        r'<!-- ═+ -->\s*\n<!-- aihelper Knowledge.*?-->\s*\n<!-- ═+ -->.*?(?=\n#|\Z)',
        re.DOTALL,
    )
    cleaned = pattern.sub("", existing).rstrip() + "\n"

    new_content = cleaned + section
    if new_content == existing:
        return False

    file_path.write_text(new_content, encoding="utf-8")
    return True


def _load_json(path: Path, default: Any = None) -> Any:
    """Safely load JSON, returning default on failure."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default if default is not None else {}


# ── Editor-specific dispatchers ─────────────────────────────────

def _dispatch_copilot(knowledge: Dict[str, Any]) -> Dict[str, str]:
    """Write knowledge to GitHub Copilot instructions."""
    results = {}
    md = _format_knowledge_markdown(knowledge)

    # Global instructions
    global_path = _home() / ".github" / "copilot-instructions.md"
    if _merge_markdown_section(global_path, md):
        results["copilot_global"] = str(global_path)

    return results


def _dispatch_codex(knowledge: Dict[str, Any]) -> Dict[str, str]:
    """Write knowledge to Codex config.json developer_instructions."""
    results = {}
    codex_path = _home() / ".codex" / "config.json"
    existing = _load_json(codex_path, default={})

    knowledge_text = _format_knowledge_codex(knowledge)
    current_instructions = existing.get("developer_instructions", "")

    # Check if our knowledge is already in there
    if knowledge_text and knowledge_text not in current_instructions:
        # Append or prepend
        existing["developer_instructions"] = knowledge_text + "\n\n" + current_instructions
        codex_path.parent.mkdir(parents=True, exist_ok=True)
        codex_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        results["codex"] = str(codex_path)

    return results


def _dispatch_claude(knowledge: Dict[str, Any]) -> Dict[str, str]:
    """Write knowledge to Claude instructions."""
    results = {}
    md = _format_knowledge_markdown(knowledge)

    claude_path = _home() / ".claude" / "aihelper-claude-instructions.md"
    if _merge_markdown_section(claude_path, md):
        results["claude"] = str(claude_path)

    return results


# ── Main dispatch function ──────────────────────────────────────

def dispatch_knowledge(
    project_root: Optional[Path] = None,
    editors: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Read knowledge from the memory engine and dispatch to all editor configs.

    Args:
        project_root: Target project (affects which knowledge DB to query)
        editors: Specific editors to dispatch to. None = all available.
    """
    try:
        from .memory_engine import get_all_knowledge, all_preferences_detail
    except ImportError:
        from memory_engine import get_all_knowledge, all_preferences_detail

    knowledge = get_all_knowledge(project_root=project_root)
    knowledge["preferences_detail"] = all_preferences_detail(project_root=project_root)

    target_editors = editors or ["copilot", "codex", "claude"]

    results: Dict[str, Any] = {
        "dispatched_at": datetime.now(timezone.utc).isoformat(),
        "knowledge_summary": {
            "decisions": len(knowledge.get("decisions", [])),
            "debugs": len(knowledge.get("debugs", [])),
            "preferences": len(knowledge.get("preferences", {})),
        },
        "editors": {},
    }

    for editor in target_editors:
        try:
            if editor == "copilot":
                results["editors"]["copilot"] = _dispatch_copilot(knowledge)
            elif editor == "codex":
                results["editors"]["codex"] = _dispatch_codex(knowledge)
            elif editor == "claude":
                results["editors"]["claude"] = _dispatch_claude(knowledge)
        except Exception as e:
            results["editors"][editor] = {"error": str(e)}

    return results


# ── Auto-detect preferences from project configs ────────────────

def auto_detect_preferences(project_root: Path) -> Dict[str, Any]:
    """
    Auto-detect developer preferences from project config files.
    Called by init-config to seed the preference store.
    """
    detected: Dict[str, Dict[str, str]] = {}

    root = project_root.resolve()

    # Package manager
    if (root / "pnpm-lock.yaml").exists() or (root / "pnpm-workspace.yaml").exists():
        detected["package_manager"] = {"value": "pnpm", "category": "frontend"}
    elif (root / "yarn.lock").exists():
        detected["package_manager"] = {"value": "yarn", "category": "frontend"}
    elif (root / "package-lock.json").exists():
        detected["package_manager"] = {"value": "npm", "category": "frontend"}

    # Build tool
    if (root / "pom.xml").exists():
        detected["build_tool"] = {"value": "maven", "category": "backend"}
    elif list(root.glob("build.gradle*")):
        detected["build_tool"] = {"value": "gradle", "category": "backend"}
    elif (root / "Cargo.toml").exists():
        detected["build_tool"] = {"value": "cargo", "category": "backend"}

    # Language
    if list(root.glob("*.py")) or (root / "setup.py").exists() or (root / "pyproject.toml").exists():
        detected["language"] = {"value": "python", "category": "backend"}
    elif list(root.glob("*.php")):
        detected["language"] = {"value": "php", "category": "backend"}
    elif list(root.glob("*.java")):
        detected["language"] = {"value": "java", "category": "backend"}
    elif list(root.glob("*.rs")):
        detected["language"] = {"value": "rust", "category": "backend"}
    elif (root / "package.json").exists():
        pkg = _load_json(root / "package.json", default={})
        if "react" in str(pkg).lower():
            detected["language"] = {"value": "javascript/react", "category": "frontend"}
        elif "next" in str(pkg).lower():
            detected["language"] = {"value": "javascript/nextjs", "category": "frontend"}
        elif "vue" in str(pkg).lower():
            detected["language"] = {"value": "javascript/vue", "category": "frontend"}
        else:
            detected["language"] = {"value": "javascript/node", "category": "frontend"}

    # Framework hints
    if (root / "composer.json").exists():
        detected["framework"] = {"value": "laravel/symfony", "category": "backend"}
    if list(root.glob("spring*.xml")) or list(root.glob("*Application.java")):
        detected["framework"] = {"value": "spring", "category": "backend"}

    # Store detected preferences
    try:
        from .memory_engine import set_preference
    except ImportError:
        from memory_engine import set_preference

    stored = []
    for key, info in detected.items():
        result = set_preference(
            key=key,
            value=info["value"],
            category=info.get("category", ""),
            confidence=0.8,
            source="auto-detected",
            project_root=project_root,
        )
        stored.append(result)

    return {
        "detected": detected,
        "stored": len(stored),
    }
