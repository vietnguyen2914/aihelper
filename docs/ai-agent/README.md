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

Use aihelper to produce a compact, feature-aware prompt before asking Codex to inspect broad code:

```bash
/Users/vietnguyen/github/aihelper/bin/aihelper analyze "<task>" --format prompt --max-context-chars 6000
```

Keep local LLM calls on the discovery path only. Deterministic index routing is the default because it is much faster and avoids spending local model time on repeated keyword normalization.

## MCP Tool

Editors and agents can expose aihelper as an MCP server:

```bash
python3 /Users/vietnguyen/github/aihelper/context_engine/mcp_server.py
```

The MCP tool is `aihelper_context`. It returns the same compact prompt as:

```bash
/Users/vietnguyen/github/aihelper/bin/aihelper analyze "<task>" --format prompt --max-context-chars 6000
```
