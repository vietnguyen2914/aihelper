# aihelper — Local Project Instructions

## File Writing — ALWAYS USE PYTHON
- **Always use Python** (via `run-code` or `write_file` tools) for creating or modifying files — never use terminal heredocs, `cat` redirects, or MCP file writes
- Python is orders of magnitude faster and avoids encoding/shell-escaping bugs
- Prefer `write_file` tool for new files, `edit_file` tool for targeted patches
- Only use terminal for reading/listing files, not writing them

## Context Budget
- Use `aihelper context --max-context-chars 2000` for most tasks
- Extend to `--max-context-chars 4000` only for multi-file changes
- Never exceed 5000 chars without explicit user permission

## Integration Scripts — DO NOT FORGET BOTH PLATFORMS

When adding or modifying integration scripts in `scripts/`, you MUST update ALL of the following files:

### Python scripts (in `scripts/`)
- `scripts/claude-integration.py`
- `scripts/codex-integration.py`
- `scripts/gemini-integration.py`
- `scripts/opencode-integration.py`
- `scripts/vscode-copilot-integration.py`
- `scripts/zed-integration.py`

### Init-config callers (BOTH platforms)
- `scripts/init-config.sh` — **macOS / Linux** (bash)
- `scripts/init-config.ps1` — **Windows** (PowerShell)

When a new integration script is added, call it from **both** `init-config.sh` AND `init-config.ps1`.

### Documentation
- `docs/integrations/editor-integration.md`
- `docs/integrations/README.md`

## Key principles
### Failsafe
Integration scripts must never error if the target editor is missing. Write config files for later use.
### Idempotent
Use `merge_settings()` deep-merge. Skip writing when content is unchanged.
### Cross-platform
Each script must handle macOS, Linux, AND Windows paths and Python commands.

## Behavioral Laws — MANDATORY Execution Protocol

These are NOT suggestions. These are execution laws for all AI agents.

### REQUIRED WORKFLOW (before ANY file reads or terminal commands)
1. `aihelper_route "<task>"` — classify task and get tool recommendations
2. `aihelper_context --max-context-chars 3000` — compact project overview
3. `aihelper_symbol_lookup <target>` — find symbols semantically (NOT grep)

### FORBIDDEN (use semantic tools instead)
- ❌ `grep -r` / `find .` for code exploration → use `aihelper_symbol_lookup`
- ❌ Recursive `read_file` on multiple files → use `aihelper_explore`
- ❌ Manual dependency tracing → use `aihelper_callers` / `aihelper_callees`

### TIER ENFORCEMENT (automatic delegation)
- DTOs, CRUD, repositories, boilerplate → MUST use local Ollama model
- Only refactoring, architecture, security, complex logic → may use frontier
- `aihelper_tier_route` determines tier automatically

### SUBAGENT EXECUTION
- Subagents receive bounded cognition packages, not raw prompts
- Subagents MUST stay within assigned graph boundary
- Subagents MUST NOT scan repos freely

### VERIFICATION (before declaring done)
- `aihelper_verify architecture` after structural changes
- `aihelper_verify regression-risk --target <symbol>` after code changes
