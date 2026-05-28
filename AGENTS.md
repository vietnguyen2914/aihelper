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

## Behavioral Laws — MANDATORY Execution Protocol

These are NOT suggestions. These are execution laws for all AI agents.

### REQUIRED WORKFLOW (before ANY file reads or terminal commands)
1. `aihelper_route "<task>"` — classify task and get tool recommendations
2. `aihelper_context --max-context-chars 3000` — compact project overview
3. `aihelper_symbol_lookup <target>` — find symbols semantically (NOT grep)

### FORBIDDEN (use semantic tools instead)
- ❌ `grep -r` / `find .` for code exploration → use `aihelper_symbol_lookup`
- ❌ Recursive `read_file` on multiple files → use `aihelper_explore`
- ❌ Manual dependency tracing → use `aihelper_callers` / `aihelper_callees`

### TIER ENFORCEMENT (automatic delegation)
- DTOs, CRUD, repositories, boilerplate → MUST use local Ollama model
- Only refactoring, architecture, security, complex logic → may use frontier
- `aihelper_tier_route` determines tier automatically

### SUBAGENT EXECUTION
- Subagents receive bounded cognition packages, not raw prompts
- Subagents MUST stay within assigned graph boundary
- Subagents MUST NOT scan repos freely

### VERIFICATION (before declaring done)
- `aihelper_verify architecture` after structural changes
- `aihelper_verify regression-risk --target <symbol>` after code changes

## Working Rules

- **File Writing: Always use Python.** Use `write_file` or `edit_file` tools for all file creation/modification. Never use terminal heredocs, `cat` redirects, or MCP file writes — Python is dramatically faster and avoids shell-escaping bugs. Terminal is for reading/listing only.
- Keep README/docs workflow-first and grounded in real command output, demo assets, or measured benchmarks.
- Do not commit or push without explicit user permission.
- Preserve unrelated local changes.
