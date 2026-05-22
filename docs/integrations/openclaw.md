# OpenClaw Integration

[OpenClaw](https://github.com/openclaw/openclaw) is a collaborative AI coding platform. aihelper integrates as a **semantic context provider** — bringing symbol graphs, dependency maps, and intent routing into OpenClaw's multi-agent workflows.

## How It Works

```
OpenClaw Agent
    │
    ├── requests context via MCP
    ▼
aihelper Daemon
    ├── symbol graph → OpenClaw's code understanding
    ├── intent routing → OpenClaw's task planning
    ├── patch planning → OpenClaw's editing workflow
    └── context assembly → OpenClaw's token budget
```

## Setup

### 1. Ensure aihelper daemon is running

```bash
aihelper daemon status
# If not running:
aihelper daemon start
```

### 2. Add aihelper MCP server to OpenClaw config

In your OpenClaw configuration (or via the OpenClaw UI → MCP settings):

```json
{
  "mcpServers": {
    "aihelper": {
      "command": "python3",
      "args": ["/path/to/aihelper/context_engine/mcp_server.py"],
      "env": {
        "AIHELPER_TARGET_ROOT": "/path/to/your/project"
      }
    }
  }
}
```

### 3. Available tools

Once connected, OpenClaw agents can call these aihelper tools directly:

| Tool | Description | OpenClaw Use Case |
|------|-------------|-------------------|
| `route` | Intent-aware task routing | Route user requests to correct agent |
| `symbol_find` | Find symbols in codebase | Code understanding, navigate |
| `context` | Compact context assembly | Token-efficient prompt building |
| `patch_plan` | Generate unified diff | Automated code changes |
| `diff_summary` | Semantic git diff | Review changes between agents |
| `capability_route` | Route to multimodal pipeline | Vision, OCR, embeddings |

### 4. Example workflow

```
User: "Fix the null pointer in UserService"

OpenClaw orchestrator:
  1. Call aihelper.route("fix null pointer in UserService")
     → Returns: intent=bugfix, files=[UserService.php]

  2. Call aihelper.symbol_find("getUser")
     → Returns: location, callers, dependencies

  3. Assign coding agent with context
     → Agent edits UserService.php

  4. Call aihelper.patch_plan("add null check", file=UserService.php)
     → Returns: unified diff + confidence score

  5. Apply patch via aihelper.safe_apply()
```

## Benefits

- **Shared semantics**: All agents work from the same symbol/dependency graph
- **No token waste**: Compact context (750 tokens) vs raw repo scan (50K+ tokens)
- **Sub-millisecond routing**: Daemon IPC replaces Python startup per call
- **Consistent intent detection**: Same router for all agents
