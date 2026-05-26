# aihelper Agent Instructions

## Local AI / aihelper First

- This repository is the local `aihelper` runtime installed at a local path (default: `~/github/aihelper`). Run `aihelper init-config` to configure agents.
- Use local `aihelper` as much as possible before broad manual scans or cloud-heavy prompts, including when working on `aihelper` itself.
- Start non-trivial tasks with `aihelper route "<task brief>"` and `aihelper cache status --project-root <repo>`.
- Prefer `aihelper` context, symbol lookup, prompt blocks, route suggestions, and diff summaries before recursive filesystem reads.
- Treat local Ollama as available on this machine with installed coding/assistant models such as `qwen3.5:4b-16k`, `phi4-mini:latest`, `deepseek-coder:1.3b`, plus larger lazy-load models like `deepseek-coder-v2:16b` and `qwen3.5:9b` when needed.
- Use local `aihelper`/Ollama for discovery, routing, prewarm, and compact context first; escalate to cloud models only after local context is gathered or when task complexity requires it.
- To set up per-project agent configs after first install:
  - **macOS/Linux**: `bash scripts/init-config.sh`
  - **Windows**: `powershell -ExecutionPolicy Bypass -File scripts\init-config.ps1`

## Working Rules

- Keep README/docs workflow-first and grounded in real command output, demo assets, or measured benchmarks.
- Do not commit or push without explicit user permission.
- Preserve unrelated local changes.
