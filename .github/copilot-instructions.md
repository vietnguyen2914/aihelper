# aihelper — Local Project Instructions

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
