# aihelper — AI-native development runtime


> **📖 See [INSTALLATION.md](docs/INSTALLATION.md) for complete setup guide.**
**Portable AI context engine** that turns any repository into an AI-aware development environment.  
Built for editors, agents, and local-first coding workflows.

> **Context-centric, NOT model-centric.** Retrieval quality + semantic routing + editor awareness > more params.

---

## Why aihelper?

Most AI coding tools do **full repo scans + giant prompts** → slow, token-heavy, inaccurate.

aihelper does **semantic slicing + intent routing + patch planning** → sub-millisecond, 95%+ token reduction.

### Benchmarks (M1 Pro 32GB)

| Operation | Raw Python | Via Daemon | Reduction |
|-----------|-----------|------------|-----------|
| `route` | 163ms | **0.7ms** | 99.6% |
| `symbol_find` | 163ms | **3.1ms** | 98.1% |
| `cache_status` | 163ms | **0.3ms** | 99.8% |
| `context` | 163ms | **0.5ms** | 99.7% |
| Prompt assembly | 500ms+ | **<100ms** | 80%+ |

### Token Efficiency

| Without aihelper | With aihelper |
|-----------------|---------------|
| 50K+ tokens (full repo scan) | 750 tokens (compact context) |
| 163ms Python startup per call | 0.3ms daemon IPC |
| 10-20 tool calls per task | 2-3 targeted calls |

---

## Features

### 🔥 Daemon (Zero Latency)
- Persistent Unix socket (`~/.aihelper/aihelper.sock`)
- 47 method handlers in-memory
- Auto-fallback to direct Python if daemon unavailable

```bash
aihelper daemon start    # Start persistent daemon
aihelper daemon status   # 0.3ms health check
aihelper daemon stop
```

### 🧠 Semantic Indexing
- Symbol graph (47K+ symbols indexed)
- Dependency graph (import-based)
- SQL schema summaries
- Semantic fingerprints (formatting-only changes ignored)
- Incremental refresh via Watchman

### 🎯 Intent-Aware Routing
Routes by **coding intent**, not file path:

| Intent | Model/Pipeline |
|--------|---------------|
| `bugfix` | `error_traces + recent_changes + tests` |
| `refactor` | `dependency_graph + callers + interfaces` |
| `schema_migration` | `db_schema + migrations + orm_models` |
| `optimization` | `hot_paths + profiling + algorithm_context` |

### ✏️ Patch-Based Editing
- Unified diff generation + git apply dry-run
- 5-factor confidence scoring (syntax, ambiguity, API, tests, files)
- Auto-apply gated at 0.85 confidence
- Structural diff: detects renamed methods, changed signatures, SQL changes

### 📊 Structured Telemetry
```bash
aihelper telemetry   # Cache hit rate, latency histogram, error tracking
aihelper health      # Subsystem health (watchman, ramdisk, ollama)
aihelper degradation # Graceful degradation status
```

### 🧩 Cross-Editor Integration

| Editor | Integration | Details |
|--------|-------------|---------|
| **Zed** | ✅ MCP native | `git`, `fetch`, `context7`, `aihelper` via `settings.json` |
| **Claude Desktop** | ✅ MCP native | Same 4 MCP servers via `claude_desktop_config.json` |
| **Gemini/Antigravity** | ✅ MCP native | Via `~/.gemini/config/mcp_config.json` |
| **Codex** | ✅ Plugin config | Via `~/.codex/config.toml` |
| **OpenCode** | ✅ MCP config | Via `~/.config/opencode/opencode.json` |
| **VSCode** | ✅ Extension | Via `rooveterinaryinc.roo-cline` or `Continue.continue` |

### 👁️ Capability Router
- Vision: `minicpm-v` for screenshots, UI parsing
- OCR: `PaddleOCR` for text extraction
- Embeddings: `bge-m3` + `nomic-embed-text`
- Reranker: `CrossEncoder` for retrieval scoring

### 📄 Document Pipeline
```
Markdown content → Mermaid/DBML/Vega specs → Marp renders deck → PPTX/PDF
```
- Mermaid diagrams, DBML ERDs, Vega-Lite charts
- Marp markdown-to-PPTX conversion
- Pandoc/LibreOffice for format conversion
- Docling for document structure parsing

---

## Quick Start

See [docs/INSTALLATION.md](docs/INSTALLATION.md) for prerequisites, editor integration, daemon setup, and troubleshooting.


```bash
# Install
git clone https://github.com/vietnguyen2914/aihelper.git
cd aihelper

# Build cache
./bin/aihelper cache build --project-root /path/to/your/project

# Route a task
./bin/aihelper route "fix payment bug"

# MCP server (for editors)
python3 context_engine/mcp_server.py
```

---

## Commands

### Cache
```bash
aihelper cache build             # Full index build
aihelper cache status            # Freshness + diff
aihelper cache watch             # Watchman-backed refresh
aihelper cache persist --all     # RAM cache → SSD (8h auto)
aihelper cache restore           # SSD → RAM on reboot
```

### Context
```bash
aihelper route "bug fix"         # Intent-aware routing
aihelper symbol find "UserService"
aihelper symbol context "method"
aihelper prompt-blocks show      # Compact summaries
aihelper diff-summary            # Semantic git diff
```

### Editor / LSP
```bash
aihelper editor-context          # Detect active editor/file
aihelper lsp definition <file>
aihelper lsp references <file>
```

### Patch
```bash
aihelper patch-plan "fix" --file src/Main.java
aihelper structural-diff --patch-file patch.diff
aihelper impact-graph "UserService"  # Rename impact analysis
aihelper confidence --patch-file fix.patch
```

### Document
```bash
aihelper generate_mermaid        # Mermaid DSL generation
aihelper generate_presentation   # Markdown → Marp → PPTX
aihelper convert_document        # Pandoc/LibreOffice
aihelper parse_document          # Docling parsing
```

### Diagnostics
```bash
aihelper diagnostics --file-path src/Main.java
aihelper intent-route "fix null pointer"
aihelper scheduler snapshot      # Semantic scheduler state
```

### Health
```bash
aihelper telemetry               # Daemon metrics
aihelper health                  # Subsystem health
aihelper degradation              # Graceful degradation
```

---

## Model Stack

| Tier | Model | RAM | Role |
|------|-------|-----|------|
| 🔥 Hot | `deepseek-coder:1.3b` | 2.9GB | Autocomplete, inline |
| 🔥 Hot | `phi4-mini:latest` | 5.7GB | Assistant, automation |
| 🔥 Hot | `qwen3.5:4b-16k` | 6.1GB | Semantic edits, patch |
| 🟡 Medium | `deepseek-coder-v2:16b` | ~10GB | Coding fallback (MoE) |
| 🟡 Medium | `qwen3.5:9b` | ~13GB | Vietnamese, general |
| ☁️ Cloud | DeepSeek V4 Pro / GPT-5.5 / Gemini | ∞ | Architecture, complex |

---

## Architecture

```
Editor (Zed/Codex/VSCode/Gemini/Claude)
    ↓
Unified MCP Profile (git, fetch, context7, aihelper)
    ↓
aihelper Daemon (Unix socket, 47 handlers)
    ├── Semantic Scheduler
    ├── Symbol/Dependency Graph
    ├── Patch Planner + Confidence Engine
    ├── Intent Router
    ├── Editor Awareness
    ├── LSP Bridge
    ├── Capability Router (vision, OCR, embeddings, reranker)
    ├── Document Pipeline (Marp, Mermaid, Pandoc, Vega-Lite)
    ├── Telemetry + Subsystem Health
    └── Cache Persistence (RAM→SSD, 8h auto)
```

---

## Requirements

- Python 3.9+
- Unix-like OS (macOS/Linux)
- Optional: Watchman (for cache watching)
- Optional: Ollama (for local models)

---

## License

MIT
