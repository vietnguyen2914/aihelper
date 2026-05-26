# AI Agent Guide

## Purpose

This repository is designed so AI agents can discover a project, build a knowledge base, and generate structured indexes from it.

## Agent Workflow

1. Read the docs first.
2. Inspect the codebase.
3. Build or refresh `ai/index/*.json`.
4. Build or refresh `ai/features/*.json` and `ai/flows/*.json`.
5. Keep docs and indexes aligned.

## Output Contract

- Valid JSON only for indexes.
- Mermaid for mindmaps and flows.
- Markdown for human-readable maps, matrices, and kickoff docs.

## Codex Fast Path

> **Before first use:** Run `aihelper init-config` to generate `.github/copilot-instructions.md` for every Git repository — this ensures all agents apply aihelper token budget rules.


Use aihelper to produce a compact, feature-aware prompt before asking Codex to inspect broad code:

```bash
aihelper analyze "<task>" --format prompt --max-context-chars 6000
```

Keep local LLM calls on the discovery path only. Deterministic index routing is the default because it is much faster and avoids spending local model time on repeated keyword normalization.

Build and reuse the local cache when a repo will be inspected repeatedly:

```bash
aihelper cache build --project-root <repo>
aihelper cache watch --project-root <repo>
aihelper cache warm --project-root <repo>
aihelper prompt-blocks build --project-root <repo>
aihelper diff-summary --project-root <repo>
aihelper symbol find "<symbol>" --project-root <repo>
aihelper route "<task>" --project-root <repo>
```

Use the router result to choose targeted reads and the right model tier. Treat filesystem MCP as exact-path fallback; use `rg`, `fd`, symbol lookup, and compact prompts for normal coding discovery.

For edits, prefer this order:

```bash
aihelper patch-plan "<task>" --file <path>
aihelper patch-apply --patch-file <diff> --project-root <repo>
aihelper validate-files <path> --project-root <repo>
```

`patch-apply` is dry-run by default. Use Codex `apply_patch` for live edits in Codex sessions, or pass `--apply` only from trusted local automation.

## MCP Tool

Editors and agents can expose aihelper as an MCP server:

```bash
# Replace with your actual aihelper path, e.g.:
python3 /path/to/aihelper/context_engine/mcp_server.py
```

The primary MCP tool is `aihelper_context`. It returns the same compact prompt as:

```bash
aihelper analyze "<task>" --format prompt --max-context-chars 6000
```

Additional MCP tools are available for token-efficient routing:

- `aihelper_symbol_lookup`
- `aihelper_cache_status`
- `aihelper_route`
- `aihelper_patch_plan`
- `aihelper_prompt_blocks`
- `aihelper_diff_summary`
- `aihelper_memory_recall`
