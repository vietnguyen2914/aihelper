# aihelper Setup Guide

## 1. Install

```bash
cd ~/github/aihelper
pip install -r requirements.txt
ollama pull qwen3.5:4b-16k phi4-mini:latest deepseek-coder:1.3b
```

## 2. Initialize for your projects

```bash
# For each project:
bash scripts/init-config.sh --project-root ~/github/your-project
```

This installs behavioral laws into:
- `<project>/.github/copilot-instructions.md`
- `<project>/AGENTS.md`
- `~/.github/copilot-instructions.md` (global)
- Editor MCP configs (Zed, Claude, Codex, Gemini, VSCode, OpenCode)

## 3. Build cache

```bash
aihelper cache build --project-root ~/github/your-project
```

## 4. Verify

```bash
aihelper cache status --project-root ~/github/your-project
aihelper route "add feature X"
```

## 5. Behavioral Laws (automatic)

Once initialized, ALL AI agents will automatically:

- **Use `aihelper_route` and `aihelper_context` FIRST** — before scanning repos or reading files
- **Prefer semantic tools** (`symbol_lookup`, `explore`, `diff_summary`) over `grep`/`read_file`
- **Route DTO/CRUD tasks to local Ollama** — saving cloud costs for simple structural work
- **Stay within graph boundaries** — sub-agents operate on one module at a time
- **Obey token budget** — max 2,000 chars for single-file changes, 4,000 for multi-file

See [`ai/system/behavioral_laws.md`](../../ai/system/behavioral_laws.md) for the full behavioral code.

---

## What's Next

| Guide | Description |
|-------|-------------|
| [INSTALLATION.md](../INSTALLATION.md) | Full installation with all options |
| [editor-integration.md](../integrations/editor-integration.md) | Editor MCP setup details |
| [core/models.md](../core/models.md) | Model tier strategy |
| [workflows/README.md](../workflows/README.md) | Common workflow patterns |
