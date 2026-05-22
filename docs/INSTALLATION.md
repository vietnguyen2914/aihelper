# Installation Guide

## Quick Install

```bash
# Prerequisites
git clone https://github.com/vietnguyen2914/aihelper.git
cd aihelper

# No dependencies beyond Python 3.9+
python3 bin/aihelper cache build --project-root /path/to/your/project

# Route a task
python3 bin/aihelper route "fix bug"
```

## Requirements

| Requirement | Minimum | Notes |
|-------------|---------|-------|
| Python | 3.9+ | 3.11+ recommended |
| OS | macOS or Linux | Windows via WSL |
| RAM | 8GB | 16GB+ for local models |
| Disk | 500MB | Without Ollama models |

## Optional Dependencies

### For cache watching (recommended)
```bash
brew install watchman
# or: apt install watchman / pacman -S watchman
```

### For local AI models (Ollama)
```bash
brew install ollama
ollama pull deepseek-coder:1.3b    # Ultra-fast, 776MB
ollama pull phi4-mini:latest       # Assistant, 2.5GB
ollama pull qwen3.5:4b-16k         # Primary coding, 3.4GB
```

See [docs/core/models.md](./core/models.md) for full model stack.

### For MCP editor integration
```bash
# The MCP server runs directly — no install needed
python3 context_engine/mcp_server.py
```

### For editor MCP configs
Each editor needs its own config file. See [docs/integrations/](./integrations/).

## Editor Integration

### Zed
Add to `~/.config/zed/settings.json`:
```json
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

### Claude Desktop
Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "aihelper": {
      "command": "python3",
      "args": ["/path/to/aihelper/context_engine/mcp_server.py"]
    }
  }
}
```

### VSCode (with Roo-Cline extension)
Add to the extension's MCP settings:
```json
{
  "mcpServers": {
    "aihelper": {
      "command": "python3",
      "args": ["/path/to/aihelper/context_engine/mcp_server.py"]
    }
  }
}
```

### Gemini/Antigravity
Add to `~/.gemini/config/mcp_config.json`.

### OpenCode
Add to `~/.config/opencode/opencode.json`.

## Daemon Mode (Zero Latency)

```bash
# Start daemon
python3 bin/aihelper daemon start

# Check status
python3 bin/aihelper daemon status

# Use normally — commands auto-proxy through daemon
python3 bin/aihelper route "find bug"

# Stop daemon
python3 bin/aihelper daemon stop
```

## First Use

```bash
# 1. Build cache for your project
cd /path/to/your/project
python3 /path/to/aihelper/bin/aihelper cache build

# 2. Start daemon
python3 /path/to/aihelper/bin/aihelper daemon start

# 3. Route a task
python3 /path/to/aihelper/bin/aihelper route "fix checkout bug"

# 4. Find symbols
python3 /path/to/aihelper/bin/aihelper symbol find "UserService"

# 5. Check cache status
python3 /path/to/aihelper/bin/aihelper cache status
```

## Verification

```bash
python3 bin/aihelper cache status --project-root .
# Should show: fresh=true

python3 bin/aihelper daemon status
# Should show: running=true

python3 bin/aihelper telemetry
# Should show request metrics
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `daemon: not found` | Run from aihelper root: `python3 bin/aihelper` |
| `cache: command not found` | Use `cache build` not just `cache` |
| MCP server fails | Ensure Python 3.9+ is in PATH |
| Symbol graph empty | Project must have code files (not just markdown) |
| Watchman not found | Cache still works with fallback polling |
| Daemon won't start | Check `~/.aihelper/logs/daemon.err.log` |

## Uninstall

```bash
# aihelper is portable — just delete the directory
rm -rf /path/to/aihelper

# Remove cache directories
rm -rf ~/.aihelper

# Remove LaunchAgent (if installed)
launchctl unload ~/Library/LaunchAgents/com.vietnguyen.aihelper.daemon.plist
rm ~/Library/LaunchAgents/com.vietnguyen.aihelper.daemon.plist
```

## License

MIT
