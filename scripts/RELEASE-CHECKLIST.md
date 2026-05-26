# Release Checklist

> Use this checklist before tagging any release to ensure cross-platform compatibility.

## Cross-Platform (macOS, Linux, Windows)

- [ ] `scripts/init-config.sh` — bash (macOS/Linux) — tested
- [ ] `scripts/init-config.ps1` — PowerShell (Windows) — syntax-checked
- [ ] `bin/aihelper` — bash CLI — `init-config` subcommand
- [ ] `bin/aihelper.ps1` — PowerShell CLI — `init-config` subcommand
- [ ] `bin/aihelper.cmd` — cmd.exe CLI — `init-config` subcommand
- [ ] `scripts/bootstrap.sh` — bash — calls `init-config` after bootstrap
- [ ] `scripts/bootstrap.ps1` — PowerShell — calls `init-config` after bootstrap
- [ ] `scripts/init-config.sh` runs cleanly in CWD mode, `--all`, `--path`
- [ ] `scripts/init-config.sh` rejects non-Git directories with clear error
- [ ] `scripts/init-config.ps1` runs cleanly in CWD mode, `-All`, `-Path`
- [ ] `scripts/init-config.ps1` rejects non-Git directories with clear error

## Documentation

- [ ] `README.md` — Quick Start includes `init-config` step
- [ ] `docs/INSTALLATION.md` — Windows + macOS/Linux sections mention `init-config`
- [ ] `docs/commands.md` — `init-config` documented
- [ ] `docs/core/local-setup.md` — includes `init-config` in Next Steps
- [ ] `AGENTS.md` — no hardcoded paths, references `init-config`
- [ ] `docs/ai-agent/README.md` — no hardcoded paths, references `init-config`

## Core Engine

- [ ] Daemon running: `aihelper daemon status`
- [ ] Router returns token budget: `aihelper route "fix bug"`
- [ ] Context compression: `aihelper context --max-context-chars 2000`
- [ ] Symbol lookup: `aihelper symbol_lookup "UserService"`
- [ ] Diff summary: `aihelper diff_summary`

## Token Budget Enforcement

- [ ] `load_context.py` default max_chars = 6000
- [ ] `main.py` `analyze_request()` default = 6000
- [ ] `router.py` `token_budget()` values: realtime=1000, arch=8000, debug=5000, patch=4000, default=4000
- [ ] `build_prompt.py` truncates context when exceeding `max_total_chars`

## Per-Project Config Files

- [ ] `~/.github/copilot-instructions.md` — exists with English content
- [ ] `~/.codex/config.json` — exists
- [ ] `<project>/.github/copilot-instructions.md` — exists for each Git repo

## Platform Specific

### macOS
- [ ] `launchctl` LaunchAgents install correctly
- [ ] RAM disk mount script works
- [ ] Unix socket IPC works

### Linux
- [ ] systemd service file works
- [ ] Unix socket IPC works

### Windows
- [ ] PowerShell 7+ ExecutionPolicy bypass works
- [ ] `init-config.ps1` generates correct Windows paths
- [ ] VS Code settings update works on Windows
- [ ] cmd.exe CLI dispatches correctly
