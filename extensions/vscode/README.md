# aihelper for VSCode

**Zero-config MCP integration.** Install the extension, and aihelper's context engine is available to VSCode's native MCP system, Roo-Cline, and Continue.dev — no manual config files.

## Features

- ⚡ **Auto-discovery** — finds your aihelper installation automatically (no path config needed)
- 🔌 **One-click MCP enable** — registers all 9 aihelper MCP tools in VSCode
- 🟢 **Status bar** — see daemon health at a glance (⚡ running · ⏸ stopped · ❌ unconfigured)
- 🚀 **Auto-start** — daemon starts automatically when VSCode opens
- 🛠 **Commands** — start/stop daemon, view logs, check status, reconfigure
- 🪟 **Windows-native** — detects `python` vs `python3`, uses `.ps1`/`.cmd` launchers

## Quick Start

1. Install this extension in VSCode
2. Run **"aihelper: Enable MCP Integration"** from the command palette (`Ctrl+Shift+P`)
3. That's it. The extension finds aihelper, starts the daemon, and registers the MCP server.

## What You Get

Once enabled, these MCP tools are available to any VSCode AI assistant (Copilot, Cline, Continue, etc.):

| Tool | What it does |
|------|-------------|
| `aihelper_route` | Route a task to the optimal tools and symbols |
| `aihelper_context` | Build compact, feature-aware context prompts |
| `aihelper_symbol_lookup` | Find symbol definitions and dependencies |
| `aihelper_cache_status` | Check if the project cache is fresh |
| `aihelper_diff_summary` | Semantic summary of current changes |
| `aihelper_patch_plan` | Generate AST-aware patch plans |
| `aihelper_memory_recall` | Recall working memory |
| `aihelper_prompt_blocks` | Build/load precompiled prompt blocks |
| `aihelper_capability_route` | Classify and route to capability pipeline |

## Commands

| Command | Description |
|---------|-------------|
| `aihelper: Enable MCP Integration` | Auto-detect, start daemon, register MCP server |
| `aihelper: Disable MCP Integration` | Remove MCP server from settings |
| `aihelper: Start Daemon` | Start the background aihelper daemon |
| `aihelper: Stop Daemon` | Stop the daemon |
| `aihelper: Check Daemon Status` | Show status and action menu |
| `aihelper: Open Daemon Logs` | Open daemon.log in the editor |
| `aihelper: Re-run Bootstrap & Reinstall` | Reinstall dependencies and restart |

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `aihelper.path` | `auto` | Path to aihelper installation |
| `aihelper.pythonCommand` | `auto` | Python command (`python`, `python3`, `py`) |
| `aihelper.enableOnStartup` | `true` | Auto-configure MCP on VSCode start |
| `aihelper.statusBar` | `true` | Show status bar indicator |

## Requirements

- **VSCode 1.98+** (native MCP support)
- **aihelper** installed on your machine
- **Python 3.9+** (detected automatically)

## Manual Installation

If you cloned the aihelper repo, you can install this extension locally:

```bash
# From the aihelper repo root
code --install-extension extensions/vscode/
```

Or package it:

```bash
npx -p @vscode/vsce vsce package -o aihelper-vscode.vsix
code --install-extension aihelper-vscode.vsix
```
