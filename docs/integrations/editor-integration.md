# Editor and Agent Integration

aihelper provides on-demand integration scripts for all supported editors and agents.
These scripts are designed to be **failsafe**, **re-runnable**, and **auto-integrated**
into `aihelper init-config`.

## What `aihelper init-config` does

`aihelper init-config` automatically invokes ALL integration scripts as part of the setup flow:

### Per-project scripts (run once per detected Git repo)
- `scripts/vscode-copilot-integration.py --path <project>`
- `scripts/claude-integration.py --path <project>`

### Global editor/agent scripts (run once, globally)
- `scripts/zed-integration.py`
- `scripts/gemini-integration.py`
- `scripts/opencode-integration.py`
- `scripts/codex-integration.py`

That means a first-time user can run:

```bash
cd /path/to/your/project
aihelper init-config
```

and `aihelper` will:

- generate global agent instructions at `~/.github/copilot-instructions.md`
- generate project-level instructions at `<project>/.github/copilot-instructions.md`
- generate VS Code workspace settings under `<project>/.vscode`
- generate Zed MCP config at `~/.config/zed/settings.json`
- generate Gemini/Antigravity MCP config at `~/.gemini/config/mcp_config.json`
- generate OpenCode MCP config at `~/.config/opencode/opencode.json`
- generate global Codex config at `~/.codex/config.json` and register the aihelper MCP server via `codex mcp add`
- generate Claude instructions at `~/.claude/aihelper-claude-instructions.md`
- generate project-level Claude instructions at `<project>/.github/claude-instructions.md`

## On-demand scripts

If you only want to apply one integration, run the corresponding script directly:

```bash
python3 scripts/vscode-copilot-integration.py --path /path/to/project
python3 scripts/zed-integration.py
python3 scripts/gemini-integration.py
python3 scripts/opencode-integration.py
python3 scripts/codex-integration.py
python3 scripts/claude-integration.py --path /path/to/project
```

All scripts accept `--dry-run` to preview changes without writing files.

## Available integration scripts

| Script | Target | Generates |
|--------|--------|----------|
| `vscode-copilot-integration.py` | VS Code + GitHub Copilot Chat | `<project>/.vscode/settings.json`, `<project>/.vscode/extensions.json`, `~/.github/copilot-instructions.md`, user VS Code settings |
| `zed-integration.py` | Zed Editor | `~/.config/zed/settings.json` (MCP server config) |
| `gemini-integration.py` | Gemini / Antigravity | `~/.gemini/config/mcp_config.json` (MCP server config) |
| `opencode-integration.py` | OpenCode | `~/.config/opencode/opencode.json` (MCP server config) |
| `codex-integration.py` | Codex CLI (v0.133.0+) | `~/.codex/config.json` + registers MCP server via `codex mcp add` |
| `claude-integration.py` | Claude Desktop / CLI | `~/.claude/aihelper-claude-instructions.md`, `<project>/.github/claude-instructions.md` |

## Shared core: `scripts/integration_common.py`

All integration scripts import from `scripts/integration_common.py`, which provides:

| Module | Exports | Purpose |
|--------|---------|---------|
| **OS detection** | `IS_WINDOWS`, `IS_MACOS`, `IS_LINUX`, `IS_POSIX` | Single source of truth for platform branches |
| **Path resolution** | `aihelper_root()`, `mcp_server_path()`, `home()`, `get_appdata_config_path()` | Locate aihelper files and OS-appropriate config directories |
| **JSON I/O** | `load_json()`, `write_json()`, `merge_settings()` | Idempotent JSON file operations with deep-merge |
| **Text I/O** | `write_text()` | Idempotent plain-text file writes |
| **Extension mgmt** | `ensure_extension_recommendation()` | VS Code extension recommendation (idempotent) |
| **Subprocess** | `safe_run()` | Failsafe command execution (returns None on failure) |
| **Binary detection** | `detect_binary()` | Cross-platform binary lookup (tries `.exe` on Windows) |
| **CLI helpers** | `add_dry_run_arg()`, `add_path_arg()`, `resolve_project_root()` | Consistent argument parsing |

## OS boundaries

Every integration script explicitly marks OS-specific code. Below is the complete audit:

| Script | Windows path | macOS path | Linux path | Unsupported |
|--------|-------------|------------|------------|-------------|
| `vscode-copilot-integration.py` | `%APPDATA%\Code\User\settings.json`, `%USERPROFILE%\.vscode\extensions`, `%ProgramFiles%\Microsoft VS Code\resources\app\extensions` | `~/Library/Application Support/Code/User/settings.json`, `/Applications/Visual Studio Code.app/...` | `~/.config/Code/User/settings.json`, `/usr/share/code/resources/app/extensions`, Flatpak `~/.var/...` | — |
| `codex-integration.py` | `~/.codex/config.json` (via `Path.home()`) + `codex mcp add` | same | same | — |
| `claude-integration.py` | `~/.claude/` (via `Path.home()`) | same | same | — |
| `zed-integration.py` | **N/A** (Zed not on Windows) | `~/Library/Application Support/Zed/settings.json`, `/Applications/Zed.app` | `~/.config/zed/settings.json` | Windows |
| `gemini-integration.py` | `%APPDATA%\Gemini\config\mcp_config.json` | `~/.gemini/config/mcp_config.json` | same as macOS | — |
| `opencode-integration.py` | `%APPDATA%\opencode\opencode.json` | `~/.config/opencode/opencode.json`, `~/Library/Application Support/opencode/opencode.json` | `~/.config/opencode/opencode.json` | — |

## Init-config platform callers

| File | Platform | Language | Invocation |
|------|----------|----------|------------|
| `scripts/init-config.sh` | macOS / Linux | Bash | Called by `aihelper init-config` via `bin/aihelper` |
| `scripts/init-config.ps1` | Windows | PowerShell | Called by `aihelper init-config` via `bin/aihelper.ps1` |

Both callers invoke **all 6 integration Python scripts**; the only platform-specific logic in each caller is:
- Shell command syntax (bash vs PowerShell)
- Path conventions (`$HOME` vs `$env:USERPROFILE`)
- File existence checks (`test -f` vs `Test-Path`)

All config content and editor-specific logic lives in the Python scripts — **not** in the shell/PowerShell callers.

## Design principles

### Failsafe

All integration scripts:
- do not error if the target editor/tool is missing
- create config files for later use instead of blocking setup
- print informational messages when the tool is not installed

### Re-runnable (idempotent)

All integration scripts:
- merge settings rather than overwriting (preserve existing config keys)
- skip writing if file content has not changed
- can be run multiple times safely

### Auto-integrated

All scripts are called from `aihelper init-config` — one command sets up everything.

### Cross-platform

Platform-conditional code is isolated to single-source-of-truth constants (`IS_WINDOWS`, `IS_MACOS`, `IS_LINUX`) from `integration_common`. Each script's OS-specific config paths are resolved in a single helper function at the top of the file.

## Codex MCP integration details

Codex CLI v0.133.0+ uses a dedicated `codex mcp` subcommand to manage external
MCP servers. Configuration is stored in a SQLite database (`~/.codex/state_5.sqlite`)
rather than a plain JSON config file.

The `codex-integration.py` script:

1. Writes `~/.codex/config.json` with `developer_instructions` (always, failsafe)
2. Registers the aihelper MCP server via `codex mcp add` — equivalent to:
   ```bash
   codex mcp add aihelper -- python3 /path/to/aihelper/context_engine/mcp_server.py
   ```

**MCP transport**: stdio (the `mcp_server.py` speaks stdio-based MCP).
**Idempotent**: `codex mcp add` overwrites any existing config for the same name.
**Failsafe**: if the `codex` binary is not found, MCP registration is skipped.

To inspect the registered servers:

```bash
codex mcp list                 # tabular view
codex mcp list --json          # JSON view
codex mcp get aihelper --json  # detail for one server
```

To remove the server:

```bash
codex mcp remove aihelper
```

## Architecture

```
scripts/
├── integration_common.py         ← shared utilities (274 lines)
├── vscode-copilot-integration.py ← VS Code + Copilot Chat
├── codex-integration.py          ← Codex CLI config
├── zed-integration.py            ← Zed MCP config (macOS/Linux)
├── gemini-integration.py         ← Gemini/Antigravity MCP config
├── opencode-integration.py       ← OpenCode MCP config
├── claude-integration.py         ← Claude Desktop/CLI instructions
├── init-config.sh                ← caller: macOS / Linux (bash)
└── init-config.ps1               ← caller: Windows (PowerShell)
```

Each Python script is 60-80 lines (except `vscode-copilot-integration.py` at ~340 lines due to Copilot detection + VS Code path discovery). The shared module eliminated ~430 lines of duplicated code.

## Recommended workflow

1. Run `aihelper init-config` once per machine (or on each new project).
2. Use `aihelper cache build` to index the project.
3. Use `aihelper route "<task>"` before any large repo scan.
4. Use `aihelper context --max-context-chars 2000` for most tasks.
