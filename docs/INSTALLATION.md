# Installation Guide

- [Quick Start (≤5 min)](#quick-start-5-min)
- [Requirements](#requirements)
- [Minimal Install](#minimal-install)
- [Full Runtime Install](#full-runtime-install)
- [Platform Guides](#platform-guides)
  - [Apple Silicon (macOS)](#apple-silicon-macos)
  - [Linux](#linux)
  - [Windows](#windows)
- [Editor Integration](#editor-integration)
- [Daemon & Local IPC](#daemon--local-ipc)
- [Performance Tuning](#performance-tuning)
- [Troubleshooting](#troubleshooting)
- [Uninstall](#uninstall)

---

## Quick Start (≤5 min)

```bash
# 1. Clone
git clone https://github.com/vietnguyen2914/aihelper.git
cd aihelper

# 2. Bootstrap (auto: deps, cache, daemon)
bash scripts/bootstrap.sh

# 3. Generate per-project agent configs (token budget rules for all editors)
./bin/aihelper init-config

# 4. Use on any project
cd /path/to/your/project
aihelper cache build
aihelper route "fix bug"
```

> **No Ollama?** aihelper works without models — core features (routing, context, symbols) are model-free. Models enhance capability.

---

## Requirements

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| Python | 3.9+ | 3.11+ |
| OS | macOS 13+ / Linux / Windows 11 | macOS 14+ / Ubuntu 22.04+ / Windows 11 |
| RAM | 8GB | 16GB+ |
| Disk | 500MB | 10GB (with models) |
| Git | 2.30+ | latest |
| Watchman | optional | 2024+ (cache watching) |
| Ollama | optional | 0.5+ (local models) |

---

## Minimal Install

Core functionality — no local LLMs required. Everything works: routing, context assembly, symbol graph, patch planning, daemon.

```bash
# 1. Clone
git clone https://github.com/vietnguyen2914/aihelper.git
cd aihelper

# 2. Install Python deps
pip install -r requirements.txt

# 3. Build cache for your project
./bin/aihelper cache build --project-root /path/to/your/project  # correct invocation

# 4. Start daemon
./bin/aihelper daemon start

# 5. Route your first task
./bin/aihelper route "find the upload service"

# 6. Verify
./bin/aihelper doctor
./bin/aihelper daemon status

# 7. Generate per-project configs
./bin/aihelper init-config
```

**Hot-tier models** (recommended, adds ~10GB):

```bash
bash scripts/bootstrap.sh                    # Pulls 3 hot models
# Equivalent to:
# ollama pull deepseek-coder:1.3b
# ollama pull phi4-mini:latest
# ollama pull qwen3.5:4b-16k
```

---

## Full Runtime Install

Includes multimodal (vision, OCR), embeddings, reranker, and presentation pipeline.

```bash
bash scripts/bootstrap.sh --full
```

This pulls all models:

| Model | Size | Role |
|-------|------|------|
| `deepseek-coder:1.3b` | 776MB | Autocomplete, inline |
| `phi4-mini:latest` | 2.5GB | Assistant, automation |
| `qwen3.5:4b-16k` | 3.4GB | Semantic edits, patch |
| `minicpm-v:latest` | 3.1GB | Vision, screenshot analysis |
| `nomic-embed-text:latest` | 274MB | Fast embeddings |
| `bge-m3:latest` | 2.2GB | High-quality embeddings |

> After bootstrap, run `aihelper init-config` to generate `.github/copilot-instructions.md` for every Git repository on your machine — this tells all agents (Claude, Gemini, DeepSeek, Codex, Copilot, Ollama) to use aihelper context compression.

Additionally installs optional tools:

```bash
# OCR (text extraction from images)
pip install paddleocr

# STT (speech-to-text)
pip install faster-whisper

# Reranker (retrieval scoring)
pip install sentence-transformers

# Document pipeline
pip install marp-cli pandoc
```

---

## Platform Guides

### Apple Silicon (macOS)

Recommended setup for M1/M2/M3/M4 Macs.

```bash
# 1. Homebrew (if not installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 2. Install deps
brew install python@3.12 watchman ollama

# 3. Start Ollama service
brew services start ollama

# 4. Clone + bootstrap
git clone https://github.com/vietnguyen2914/aihelper.git
cd aihelper
bash scripts/bootstrap.sh

# 5. Auto-start (LaunchAgent)
# bootstrap.sh already installed this.
# Verify:
launchctl list | grep aihelper
```

**Apple Silicon optimizations:**

- Ollama runs Metal-backed (GPU acceleration) automatically
- aihelper daemon uses <50MB RAM idle
- Ramdisk (optional, for even faster cache):

```bash
# Create 2GB RAM disk for cache
diskutil erasevolume HFS+ "ramdisk" $(hdiutil attach -nomount ram://4096000)

# Symlink cache to RAM disk
ln -s /Volumes/ramdisk ~/.aihelper/ramcache
```

### Linux

Tested on Ubuntu 22.04+, Fedora 39+, Arch Linux.

```bash
# 1. Install deps
# Ubuntu/Debian:
sudo apt update && sudo apt install python3 python3-pip git watchman

# Fedora:
sudo dnf install python3 python3-pip git watchman

# Arch:
sudo pacman -S python python-pip git watchman

# 2. Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 3. Clone + bootstrap
git clone https://github.com/vietnguyen2914/aihelper.git
cd aihelper
bash scripts/bootstrap.sh

# 4. Auto-start via systemd (optional)
cat > ~/.config/systemd/user/aihelper-daemon.service << 'EOF'
[Unit]
Description=aihelper daemon
After=network.target

[Service]
ExecStart=%h/aihelper/bin/aihelper daemon start
WorkingDirectory=%h/aihelper
Restart=on-failure

[Install]
WantedBy=default.target
EOF

systemctl --user enable aihelper-daemon.service
systemctl --user start aihelper-daemon.service
```

### Windows

Tested target: Windows 11 with PowerShell 7+ or Windows PowerShell 5.1.

aihelper keeps Unix sockets on macOS/Linux. On Windows, the daemon automatically
uses a local-only TCP loopback endpoint and writes connection metadata under
`%USERPROFILE%\.aihelper`.

```powershell
# 1. Install dependencies
winget install Python.Python.3.12
winget install Git.Git

# Optional: install Ollama for Windows
# https://ollama.com/download/windows

# 2. Clone + bootstrap
git clone https://github.com/vietnguyen2914/aihelper.git
cd aihelper
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1

# 3. Generate per-project agent configs (token budget rules for all editors)
./bin/aihelper init-config

# 4. Use on any project
cd C:\path\to\your\project
<path-to-aihelper>\bin\aihelper.ps1 cache build
<path-to-aihelper>\bin\aihelper.ps1 route "fix bug"
```

CMD is also supported:

```cmd
bin\aihelper.cmd doctor
bin\aihelper.cmd daemon start
bin\aihelper.cmd route "fix bug"
```

**Windows daemon notes:**

- Transport: `127.0.0.1` TCP loopback, not exposed externally.
- Endpoint metadata: `%USERPROFILE%\.aihelper\aihelper.tcp.json`.
- PID file: `%USERPROFILE%\.aihelper\aihelperd.pid`.
- Logs: `%USERPROFILE%\.aihelper\daemon.log`.
- Auto-start: manual daemon start is supported first; for auto-start in VSCode, use the [VSCode extension](#option-a-install-the-vscode-extension-recommended). Scheduled Task support is planned after native Windows smoke testing.

---

## Editor Integration

aihelper speaks **MCP** (Model Context Protocol). Configure your editor to connect.

### Zed

```json
// ~/.config/zed/settings.json
{
  "context_servers": {
    "mcp-server-aihelper": {
      "enabled": true,
      "command": "python3",
      "args": ["/path/to/aihelper/context_engine/mcp_server.py"]
    }
  }
}
```

### VSCode (native MCP, Roo-Cline, Continue)

#### Option A: Install the VSCode extension (recommended)

This extension auto-discovers aihelper, starts the daemon, and registers the MCP server - no manual config needed.

```bash
# From the extensions/vscode directory
cd extensions/vscode

# Package the extension
npx -p @vscode/vsce vsce package --out aihelper-vscode.vsix

# Install in VSCode
code --install-extension aihelper-vscode.vsix
```

Once installed, run **"aihelper: Enable MCP Integration"** from the command palette (`Ctrl+Shift+P`).

#### Option B: Manual config (native MCP, 1.98+)

Add to your user `settings.json`:

**macOS / Linux:**
```json
{
  "mcp": {
    "servers": {
      "aihelper": {
        "command": "python3",
        "args": ["/path/to/aihelper/context_engine/mcp_server.py"]
      }
    }
  }
}
```

**Windows (PowerShell / CMD):**
```json
{
  "mcp": {
    "servers": {
      "aihelper": {
        "command": "python",
        "args": ["C:\\path\\to\\aihelper\\context_engine\\mcp_server.py"]
      }
    }
  }
}
```

For **Roo-Cline**, add to `.vscode/mcp.json` or the extension's MCP config:

```json
{
  "mcpServers": {
    "aihelper": {
      "command": "python",
      "args": ["/path/to/aihelper/context_engine/mcp_server.py"]
    }
  }
}
```

> **Windows note:** Use `python` (not `python3`) and Windows-style paths with double backslashes or forward slashes.

### Gemini / Antigravity

```json
// ~/.gemini/config/mcp_config.json
{ ... same structure as above ... }
```

### OpenCode

```json
// ~/.config/opencode/opencode.json
{ ... same structure as above ... }
```

---

## Daemon & Local IPC

### Manual daemon control

```bash
aihelper daemon start    # Start persistent daemon
aihelper daemon status   # Health check
aihelper daemon stop     # Graceful shutdown
```

Transport is selected automatically:

| Platform | Transport |
|---|---|
| macOS | Unix socket at `~/.aihelper/aihelper.sock` |
| Linux | Unix socket at `~/.aihelper/aihelper.sock` |
| Windows | TCP loopback endpoint stored in `%USERPROFILE%\.aihelper\aihelper.tcp.json` |

### macOS auto-start (LaunchAgent)

The `bootstrap.sh` script installs a LaunchAgent at:

```
~/Library/LaunchAgents/com.aihelper.daemon.plist
```

This starts the daemon at login and keeps it alive if it crashes.

**Manual install:**

```bash
launchctl load ~/Library/LaunchAgents/com.aihelper.daemon.plist
```

**Check if running:**

```bash
launchctl list | grep aihelper
# → should show PID
```

### Linux auto-start (systemd)

See [Linux section](#linux) above for systemd service setup.

### Windows auto-start

**Recommended:** Install the [VSCode extension](#option-a-install-the-vscode-extension-recommended) - it auto-starts the daemon when VSCode opens.

Alternatively, use manual daemon start for the first Windows release:

```powershell
.\bin\aihelper.ps1 daemon start
.\bin\aihelper.ps1 daemon status
```

Scheduled Task installation will be added after Windows smoke testing confirms
path, Python launcher, and PowerShell execution-policy behavior across machines.

---

## Performance Tuning

### 1. Ramdisk for cache

Faster than SSD. Useful for large projects with many symbols.

```bash
# macOS
diskutil erasevolume HFS+ "ramdisk" $(hdiutil attach -nomount ram://4096000)
ln -s /Volumes/ramdisk ~/.aihelper/ramcache

# Linux
sudo mount -t tmpfs -o size=2G tmpfs ~/.aihelper/ramcache
```

### 2. Model selection

| RAM | Recommended models |
|-----|-------------------|
| 8GB | `deepseek-coder:1.3b` only |
| 16GB | 3 hot-tier models |
| 32GB | Hot + `deepseek-coder-v2:16b` |
| 64GB+ | All models + full reranker |

### 3. Cache tuning

```bash
# Warm cache proactively for frequent projects
aihelper cache warm --project-root /path/to/project

# Persist RAM cache to SSD (auto runs every 8 hours)
aihelper cache persist --all

# Restore cache after reboot
aihelper cache restore --project-root /path/to/project
```

### 4. Watchman integration

Watchman enables **incremental cache refresh** — only changed files are re-indexed.

```bash
brew install watchman
aihelper cache watch --project-root /path/to/project
```

Without Watchman, cache still works via full rebuilds (slower for large projects).

### 5. Daemon memory

- Idle: ~50MB RSS
- With hot cache: ~200MB (depending on project size)
- Logs auto-rotate; stored at `~/.aihelper/logs/`

---

## Verification

After installation:

```bash
# Full diagnostic
aihelper doctor

# Cache freshness
aihelper cache status --project-root .

# Daemon health
aihelper daemon status

# Telemetry
aihelper telemetry

# Subsystem health
aihelper health
```

---

## Troubleshooting

| Problem | Likely Cause | Solution |
|---------|-------------|----------|
| `daemon: not found` | Wrong working dir | Run from aihelper root: `./bin/aihelper` |
| `cache: command not found` | Wrong subcommand | Use `cache build` not just `cache` |
| MCP server connection refused | Daemon not running | `aihelper daemon start` |
| Symbol graph empty | No code files | Project must have .py/.rs/.js/.php etc. |
| Watchman not found | Not installed | Cache works with fallback polling |
| Daemon won't start | Port conflict or corrupt socket | `rm -f ~/.aihelper/aihelper.sock && aihelper daemon start` |
| Models not found | Ollama not running | `ollama serve` or `brew services start ollama` |
| Slow cache build | Large project, no Watchman | Install Watchman for incremental builds |
| Permission denied: socket | Wrong ownership | `chmod 600 ~/.aihelper/aihelper.sock` |
| `doctor` shows failures | Installation incomplete | Run `bash scripts/bootstrap.sh` |
| LaunchAgent not loading | Path mismatch | Edit `~/Library/LaunchAgents/com.aihelper.daemon.plist` to fix paths |
| `ollama` command not found after install | PATH issue | `export PATH=/opt/homebrew/bin:$PATH` (Apple Silicon) |
| PowerShell blocks bootstrap | Execution policy | Run `powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1` |
| Windows firewall prompt | First daemon TCP loopback bind | Allow local/private loopback access only |

### Diagnostic commands

```bash
# Full health report
aihelper doctor --json

# Daemon logs
cat ~/.aihelper/daemon.log

# LaunchAgent logs
cat ~/.aihelper/logs/launchd.stdout.log
cat ~/.aihelper/logs/launchd.stderr.log

# Windows daemon logs
Get-Content "$HOME\.aihelper\daemon.log"

# Subsystem health
aihelper health

# Graceful degradation status
aihelper degradation
```

---

## Uninstall

```bash
# 1. Stop daemon
./bin/aihelper daemon stop

# 2. Remove aihelper directory
rm -rf /path/to/aihelper

# 3. Remove cache and data
rm -rf ~/.aihelper

# 4. Remove LaunchAgent (macOS)
launchctl unload ~/Library/LaunchAgents/com.aihelper.daemon.plist 2>/dev/null
rm -f ~/Library/LaunchAgents/com.aihelper.daemon.plist

# 5. Remove systemd service (Linux)
systemctl --user stop aihelper-daemon.service 2>/dev/null
systemctl --user disable aihelper-daemon.service 2>/dev/null
rm -f ~/.config/systemd/user/aihelper-daemon.service

# 6. Windows cleanup (PowerShell)
Remove-Item -Recurse -Force "$HOME\.aihelper" -ErrorAction SilentlyContinue

# 7. Remove Ollama models (optional)
ollama rm deepseek-coder:1.3b phi4-mini:latest qwen3.5:4b-16k minicpm-v:latest nomic-embed-text:latest bge-m3:latest
```

---

## Next Steps

- [Examples](./examples/) — Fix PHP bug, parse screenshots, generate presentations
- [Architecture](./architecture/) — How aihelper works internally
- [Integrations](./integrations/) — Editor-specific configs
- [Troubleshooting](./troubleshooting/) — Deeper diagnostic guides
