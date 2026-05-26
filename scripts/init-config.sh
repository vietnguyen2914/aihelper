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
#   - VS Code copilot settings reference
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

# ── 4b: ~/.codex/config.json ──────────────────────────────────────────
CODEX_CONFIG_DIR="$HOME/.codex"
CODEX_CONFIG_FILE="$CODEX_CONFIG_DIR/config.json"
CODEX_CONFIG_CONTENT=$(cat <<- CODEXEOF
{
  "developer_instructions": "CRITICAL: Before every response, run aihelper_route and aihelper_context tools first to compress project context. Never scan full repos. Use symbol lookups instead of grep. Respect the token budget from aihelper_route. Default to 2000 max_context_chars for context tool calls. Only escalate to full file reads when aihelper context is insufficient. This applies regardless of which model is being used.",
  "model_auto_compact_token_limit": 4000,
  "model_context_window": 32000,
  "model_verbosity": "concise"
}
CODEXEOF
)
write_if_changed "$CODEX_CONFIG_FILE" "$CODEX_CONFIG_CONTENT"

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

# ── 4d: VS Code settings ──────────────────────────────────────────────
VSCODE_SETTINGS="$HOME/Library/Application Support/Code/User/settings.json"
if [ -f "$VSCODE_SETTINGS" ]; then
    # Use python3 to safely merge JSON
    python3 -c "
import json, sys, os

home = os.path.expanduser('~')
settings_path = '$VSCODE_SETTINGS'

try:
    with open(settings_path) as f:
        settings = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    settings = {}

instructions_key = 'github.copilot.chat.codeGeneration.instructions'
instructions_value = [{'file': '~/.github/copilot-instructions.md'}]

if instructions_key not in settings:
    settings[instructions_key] = instructions_value
    with open(settings_path, 'w') as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
    print('[OK]   Written: VS Code copilot instructions reference')
else:
    print('[SKIP] No change: VS Code already has copilot instructions')
" 2>&1 || log "WARN" "Could not update VS Code settings (non-VS Code machine?)"
fi

# ── 4e: Zed settings (update MCP server paths if needed) ──────────────
ZED_SETTINGS="$HOME/.config/zed/settings.json"
if [ -f "$ZED_SETTINGS" ]; then
    python3 -c "
import json, os, sys

settings_path = '$ZED_SETTINGS'
aihelper_root = '$AIHELPER_ROOT'

try:
    with open(settings_path) as f:
        settings = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    settings = {}

mcp_key = 'mcp_servers'
if mcp_key not in settings:
    # No MCP section, nothing to update
    print('[SKIP] No change: Zed has no MCP servers section')
    sys.exit(0)

aihelper_mcp = settings.get(mcp_key, {}).get('mcp-server-aihelper', {})
if aihelper_mcp:
    # Fix the command path if it points to a hardcoded location
    cmd = aihelper_mcp.get('command', '')
    if 'aihelper' in cmd and not cmd.startswith('python3 ') and not cmd.endswith('mcp_server.py'):
        # Try to resolve
        possible_path = os.path.join(aihelper_root, 'context_engine', 'mcp_server.py')
        if os.path.exists(possible_path):
            new_cmd = 'python3 ' + possible_path
            if cmd != new_cmd:
                aihelper_mcp['command'] = 'python3'
                aihelper_mcp.setdefault('args', [])
                # Filter out old path args
                aihelper_mcp['args'] = [a for a in aihelper_mcp.get('args', []) if not a.endswith('mcp_server.py')]
                aihelper_mcp['args'].append(possible_path)
                settings[mcp_key]['mcp-server-aihelper'] = aihelper_mcp
                with open(settings_path, 'w') as f:
                    json.dump(settings, f, indent=2, ensure_ascii=False)
                print('[OK]   Updated: Zed aihelper MCP server path')
                sys.exit(0)
    print('[SKIP] No change: Zed MCP path looks correct')
else:
    print('[SKIP] No aihelper MCP server found in Zed config')
" 2>&1 || log "WARN" "Could not update Zed settings (non-Zed machine?)"
fi

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
