#!/usr/bin/env bash
# ============================================================================
# init-config.sh — Generate local AI agent configs per machine
# ============================================================================
# Part of aihelper. Run from within ANY Git repo to add aihelper agent config:
#
# Usage:
#   cd /path/to/any-git-project    # GitHub, GitLab, internal, any Git
#   aihelper init-config           # configures THIS project
#
#   aihelper init-config --all                  # scan all projects in ~/github
#   aihelper init-config --all /custom/root     # scan custom root
#   aihelper init-config --path /some/project   # configure specific project
#   REGISTRY_FILE=~/registry.md aihelper init-config   # + project registry
#
# On first run (no --all), also generates:
#   - ~/.github/copilot-instructions.md (global)
#   - ~/.codex/config.json (Codex settings)
#   - ~/.config/zed/settings.json (Zed MCP)
#   - ~/.gemini/config/mcp_config.json (Gemini/Antigravity MCP)
#   - ~/.config/opencode/opencode.json (OpenCode MCP)
#   - VS Code copilot settings reference
#   - On-demand integration scripts for:
#       VS Code/Copilot, Zed, Gemini, OpenCode, Codex, and Claude
# ============================================================================

set -euo pipefail

# ── Parse flags (two-pass: dry-run/verbose first, then action flags) ──────
DRY_RUN=false
VERBOSE=false
MODE="cwd"   # cwd, all, path
SCAN_ROOT="" # for --all mode
TARGET_DIRS=()

i=0
while [ $i -lt $# ]; do
    arg="${@:$i+1:1}"
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        --verbose) VERBOSE=true ;;
    esac
    i=$((i + 1))
done

i=0
while [ $i -lt $# ]; do
    arg="${@:$i+1:1}"
    case "$arg" in
        --dry-run|--verbose) ;;
        --all) MODE="all" ;;
        --path=*) MODE="path"; TARGET_DIRS+=("${arg#--path=}") ;;
        --path) MODE="path"; i=$((i + 1)); TARGET_DIRS+=("${@:$i+1:1}") ;;
        *)
            if [ "$MODE" = "all" ] && [ "${arg:0:1}" != "-" ] && [ -z "$SCAN_ROOT" ]; then
                SCAN_ROOT="$arg"
            fi
            ;;
    esac
    i=$((i + 1))
done

log() {
    if $VERBOSE || [ "$1" = "ERROR" ] || [ "$1" = "OK" ] || [ "$1" = "SKIP" ]; then
        echo "[$1] $2"
    fi
}

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║   aihelper — Local Config Initializer                       ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ── Step 0: Determine script location & AIHELPER_ROOT ──────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AIHELPER_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
log "INFO" "aihelper root: $AIHELPER_ROOT"

# Verify it's valid
if [ ! -f "$AIHELPER_ROOT/context_engine/router.py" ]; then
    echo "[ERROR] Could not locate aihelper installation from script location."
    echo "        Expected to find context_engine/router.py at: $AIHELPER_ROOT/context_engine/router.py"
    exit 1
fi
log "OK" "AIHELPER_ROOT = $AIHELPER_ROOT"

# ── is_valid_project(): Git repo with source files, not self ───────────────
is_valid_project() {
    local dir="$1"
    # Must be a directory
    [ ! -d "$dir" ] && return 1
    # Must have .git
    [ ! -d "$dir/.git" ] && return 1
    # Must have at least one source file (not counting .git itself)
    local file_count
    file_count=$(find "$dir" -maxdepth 1 -type f | wc -l | tr -d ' ')
    [ "$file_count" -lt 1 ] && return 1
    # Must NOT be aihelper repo itself
    local abs_dir
    abs_dir="$(cd "$dir" && pwd)"
    [ "$abs_dir" = "$AIHELPER_ROOT" ] && return 1
    return 0
}

# ── Step 2: Determine target projects ──────────────────────────────────
if [ "$MODE" = "cwd" ]; then
    TARGET_DIRS=("$PWD")
elif [ "$MODE" = "all" ]; then
    # Auto-detect or use provided scan root
    if [ -z "$SCAN_ROOT" ]; then
        for candidate in "$HOME/github" "$HOME/code" "$HOME/dev" "$HOME/src" "$HOME/projects"; do
            if [ -d "$candidate" ] && [ "$(ls -A "$candidate" 2>/dev/null | wc -l)" -gt 0 ]; then
                SCAN_ROOT="$candidate"
                break
            fi
        done
        if [ -z "$SCAN_ROOT" ]; then
            echo "╔─ INPUT ─────────────────────────────────────────────────╗"
            echo "║  --all mode needs a root directory to scan.            ║"
            echo "╚─────────────────────────────────────────────────────────╝"
            read -r -p "Projects root (e.g. ~/github): " INPUT_ROOT
            SCAN_ROOT="${INPUT_ROOT/#\~/$HOME}"
        fi
    fi
    log "INFO" "Scanning: $SCAN_ROOT"
    while IFS= read -r -d '' dir; do
        TARGET_DIRS+=("$dir")
    done < <(find "$SCAN_ROOT" -maxdepth 2 -mindepth 1 -type d -print0 2>/dev/null | sort -z)
fi

# ── Step 3: Validate projects ──────────────────────────────────
PROJECTS=()
for dir in "${TARGET_DIRS[@]}"; do
    if is_valid_project "$dir"; then
        PROJECTS+=("$dir")
    fi
done

if [ "${#PROJECTS[@]}" -eq 0 ]; then
    if [ "$MODE" = "cwd" ]; then
        echo "[ERROR] Current directory is not a Git project or has no source files."
        echo "        Run aihelper init-config from inside a Git repository, or use:"
        echo "          aihelper init-config --path /path/to/project"
        echo "          aihelper init-config --all           # scan all projects"
    else
        echo "[ERROR] No valid Git projects found in $SCAN_ROOT"
    fi
    exit 1
fi

log "OK" "Valid projects: ${#PROJECTS[@]}"

# ── Step 4: Generate files ──────────────────────────────────────────────────

# Helper: write_if_changed
write_if_changed() {
    local file="$1"
    local content="$2"
    if $DRY_RUN; then
        echo "  [DRY-RUN] Would write: $file"
        return
    fi

    mkdir -p "$(dirname "$file")"

    # Compare with existing content
    if [ -f "$file" ]; then
        local current
        current="$(cat "$file" 2>/dev/null || echo "")"
        if [ "$current" = "$content" ]; then
            log "SKIP" "  No change: $file"
            return
        fi
    fi

    echo "$content" > "$file"
    log "OK" "  Written: $file"
}

run_integration_script() {
    local script="$1"
    shift
    if $DRY_RUN; then
        echo "  [DRY-RUN] Would run: python3 $script $*"
        return
    fi
    if ! command -v python3 >/dev/null 2>&1; then
        log "SKIP" "  Python3 unavailable; skipping integration script $script"
        return
    fi
    if ! python3 "$script" "$@"; then
        log "WARN" "  Integration script failed: $script $*"
    fi
}

# Helper: build dry-run flag for integration scripts
DRY_FLAG=""
if $DRY_RUN; then
    DRY_FLAG="--dry-run"
fi

echo ""
echo "── Generating config files ──────────────────────────────"
echo ""

# ── 4a: Global ~/.github/copilot-instructions.md ──────────────────────
CO_GLOBAL_FILE="$HOME/.github/copilot-instructions.md"
CO_GLOBAL_CONTENT=$(cat <<- 'GLOBALEOF'
# Global Agent Instructions: Token Budget Protocol

Applies to ALL agents: Claude, Gemini, DeepSeek, Codex, Copilot, Ollama.

## Mandatory: Use aihelper context compression FIRST

Before scanning repos, running grep, or reading multiple files:

1. `aihelper route "<task>"` — identify tools + token budget
2. `aihelper context --max-context-chars 2000` — compact project overview
3. `aihelper symbol_lookup <symbol>` — instead of grep
4. `aihelper diff_summary` — instead of full git diffs

## Token Budget

| Operation | Max Context Chars | Max Tokens |
|-----------|------------------:|-----------:|
| Quick lookup / autocomplete | 500 | ~125 |
| Single-file change | 2,000 | ~500 |
| Multi-file change | 4,000 | ~1,000 |
| Architecture / design | 8,000 | ~2,000 |
| Debugging | 5,000 | ~1,250 |

## NEVER
- Run `find .`, `grep -r`, `rg -r` on a full project without aihelper first
- Read >3 raw files without `aihelper_context` first
- Send raw file dumps to cloud models without aihelper compression
- Exceed token budget — aihelper engine hard-enforces it
GLOBALEOF
)
write_if_changed "$CO_GLOBAL_FILE" "$CO_GLOBAL_CONTENT"

# ── 4b: Agent integration scripts (VS Code/Copilot, Codex, Claude)
# The helper scripts below are on-demand and are also invoked by init-config.

# ── 4c: Per-project .github/copilot-instructions.md ───────────────────
for project_dir in "${PROJECTS[@]}"; do
    project_name="$(basename "$project_dir")"
    proj_file="$project_dir/.github/copilot-instructions.md"

    # Add project-specific info if AGENTS.md exists
    extra_rules=""
    agents_file="$project_dir/AGENTS.md"
    if [ -f "$agents_file" ] && grep -qi "php\|legacy\|wordpress" "$agents_file" 2>/dev/null; then
        extra_rules="- Legacy codebase: prefer targeted edits, avoid reformatting entire files"
    fi
    if [ -f "$agents_file" ] && grep -qi "spring\|boot\|java" "$agents_file" 2>/dev/null; then
        extra_rules="${extra_rules}\n- Java project: use Maven/Gradle for builds, respect existing code style"
    fi
    if [ -f "$agents_file" ] && grep -qi "node\|react\|angular\|vue" "$agents_file" 2>/dev/null; then
        extra_rules="${extra_rules}\n- Node/frontend project: default to pnpm"
    fi

    proj_content=$(cat <<- PROJEOF
# $project_name — Local Project Instructions

## Context Budget
- Use \`aihelper context --max-context-chars 2000\` for most tasks
- Extend to \`--max-context-chars 4000\` only for multi-file changes
- Never exceed 5000 chars without explicit user permission
${extra_rules:+## Project Notes
$extra_rules}
PROJEOF
)
    write_if_changed "$proj_file" "$proj_content"
done

# ── 4d: Editor and agent integration scripts ───────────────────────
# Each script generates config for its target editor/agent.
# All scripts are failsafe: they write configs even if the editor
# is not installed, and skip if no changes are needed.

# Per-project scripts (VS Code Copilot, Claude)
for project_dir in "${PROJECTS[@]}"; do
    run_integration_script "$AIHELPER_ROOT/scripts/vscode-copilot-integration.py" --path "$project_dir" $DRY_FLAG
done

# Global/agent scripts (MCP config for editors)
run_integration_script "$AIHELPER_ROOT/scripts/codex-integration.py" $DRY_FLAG
run_integration_script "$AIHELPER_ROOT/scripts/zed-integration.py" $DRY_FLAG
run_integration_script "$AIHELPER_ROOT/scripts/gemini-integration.py" $DRY_FLAG
run_integration_script "$AIHELPER_ROOT/scripts/opencode-integration.py" $DRY_FLAG

# Per-project scripts (Claude)
for project_dir in "${PROJECTS[@]}"; do
    run_integration_script "$AIHELPER_ROOT/scripts/claude-integration.py" --path "$project_dir" $DRY_FLAG
done

# ── Auto-detect preferences & dispatch knowledge ──────────────────
echo ""
echo "── Auto-detecting preferences & dispatching knowledge ──────"
echo ""

for project_dir in "${PROJECTS[@]}"; do
    log "INFO" "Auto-detecting preferences for: $(basename "$project_dir")"
    # Run auto-detect via Python
    if command -v python3 >/dev/null 2>&1; then
        python3 -c "
import sys
sys.path.insert(0, '$AIHELPER_ROOT')
from context_engine.knowledge_dispatcher import auto_detect_preferences, dispatch_knowledge
from pathlib import Path
result = auto_detect_preferences(Path('$project_dir'))
print(f'  Detected: {result.get(\"detected\", {})}')
print(f'  Stored: {result.get(\"stored\", 0)} preferences')
dispatch_result = dispatch_knowledge(project_root=Path('$project_dir'))
print(f'  Dispatched to: {list(dispatch_result.get(\"editors\", {}).keys())}')
print(f'  Knowledge: {dispatch_result.get(\"knowledge_summary\", {})}')
" 2>/dev/null || log "SKIP" "  Knowledge dispatch skipped (Python unavailable)"
    fi
done

# ── 4f: Auto-populate project registry (optional) ──────────────────
# Optional: generate project registry for personal KB / documentation.
# Set REGISTRY_FILE env var to enable, e.g.:
#   REGISTRY_FILE=~/github/mykb/topics/local-project-registry.md aihelper init-config
REGISTRY_FILE="${REGISTRY_FILE:-}"

if [ -n "$REGISTRY_FILE" ]; then

# Build registry content line by line (macOS bash 3.2 compat)
registry_lines=()
registry_lines+=("# Local Project Registry")
registry_lines+=("")
registry_lines+=("> Auto-generated by \`scripts/init-config.sh\` (called via mykb wrapper).")
registry_lines+=("> Lists all Git projects detected on this machine.")
registry_lines+=("")
registry_lines+=("## Configuration")
registry_lines+=("")
registry_lines+=("| Variable | Value |")
registry_lines+=("|----------|-------|")
registry_lines+=("| AIHELPER_ROOT | \`$AIHELPER_ROOT\` |")
registry_lines+=("| SCAN_ROOT | \`${SCAN_ROOT:-$PWD}\` |")
registry_lines+=("")
registry_lines+=("## Detected Projects")
registry_lines+=("")
registry_lines+=("| # | Project | Path | Type |")
registry_lines+=("|---|---------|------|------|")
if [ "${#PROJECTS[@]}" -gt 0 ]; then
  p_idx=1
  for proj in "${PROJECTS[@]}"; do
    p_name="$(basename "$proj")"
    p_type=""
    if [ -f "$proj/pom.xml" ]; then p_type="Java/Maven"
    elif [ -f "$proj/build.gradle" ] || [ -f "$proj/build.gradle.kts" ]; then p_type="Java/Gradle"
    elif [ -f "$proj/package.json" ]; then
      if grep -qi '"react"' "$proj/package.json" 2>/dev/null; then p_type="React/Node"
      elif grep -qi '"next"' "$proj/package.json" 2>/dev/null; then p_type="Next.js/Node"
      elif grep -qi '"angular"' "$proj/package.json" 2>/dev/null; then p_type="Angular/Node"
      elif grep -qi '"vue"' "$proj/package.json" 2>/dev/null; then p_type="Vue/Node"
      else p_type="Node.js"
      fi
    elif ls "$proj/"*.py 1>/dev/null 2>&1; then p_type="Python"
    elif ls "$proj/"*.php 1>/dev/null 2>&1; then p_type="PHP"
    else p_type="Unknown"
    fi
    registry_lines+=("| ${p_idx} | ${p_name} | \`${proj}\` | ${p_type} |")
    p_idx=$((p_idx + 1))
  done
else
  registry_lines+=("| _(no projects detected)_ | | | |")
fi
registry_lines+=("")
registry_lines+=("---")
registry_lines+=("")
registry_lines+=("_Generated by init-config.sh on $(date +%Y-%m-%d)._")
registry_lines+=("_Re-run the script after cloning new projects to refresh._")

# Write registry
printf '%s\n' "${registry_lines[@]}" > "$REGISTRY_FILE"
log "OK" "  Written: $REGISTRY_FILE"
fi

# ── Final summary ────────────────────────────────────────────────────────────
echo ""
echo "  ──────────────────────────────────────────────────────────"
echo "   ✅ Done. Configs generated for ${#PROJECTS[@]} project(s)"
if [ "$MODE" = "cwd" ]; then
echo "      (current directory: $PWD)"
elif [ "$MODE" = "all" ]; then
echo "      (scan root: ${SCAN_ROOT:-})"
fi
echo ""
echo "   Run 'aihelper init-config' from any Git repo to add config."
echo "   Run 'aihelper init-config --all' to configure ALL repos."
echo ""
echo "   Optional: REGISTRY_FILE=~/registry.md to generate project registry."
echo "  ──────────────────────────────────────────────────────────"
echo ""
