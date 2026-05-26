# Comparisons

## aihelper vs codegraph (v0.0.7 vs v0.9.4)

| Feature | aihelper v0.0.7 | codegraph v0.9.4 |
|---|---|---|
| **Symbol extraction** | Regex + Tree-sitter (optional) | Tree-sitter WASM |
| **Storage engine** | SQLite WAL + FTS5 + JSON backup | SQLite WAL + FTS5 |
| **Languages** | 20+ (AST) + 6 (regex) | 20+ |
| **Callers/Callees** | ✅ Multi-depth BFS via SQLite | ✅ Via SQLite BFS |
| **Path tracing** | ✅ `aihelper_trace` BFS shortest path | ✅ `codegraph_trace` |
| **Impact analysis** | ✅ Transitive BFS | ✅ BFS traversal |
| **Type hierarchy** | ✅ (extends/implements) | ✅ |
| **Framework routes** | ✅ 14 frameworks (regex) | ✅ 14 frameworks (tree-sitter) |
| **MCP tools** | 15 (context, callers, callees, trace, impact, explore, route, patch, ...) | 10 (search, context, callers, callees, trace, impact, explore, node, files, status) |
| **File watching** | ✅ watchdog + Watchman fallback | ✅ chokidar (native OS events) |
| **Incremental sync** | ✅ semantic fingerprints + watchman | ✅ content hash + chokidar |
| **Daemon IPC** | ✅ **0.3ms** persistent daemon | ❌ Cold Node.js MCP call (~200ms) |
| **Intent routing** | ✅ Task → tool + model routing | ❌ No routing layer |
| **Patch planning** | ✅ 5-factor confidence engine | ❌ No patch engine |
| **Model routing** | ✅ Tiered: hot + medium + cloud | ❌ Single-model dependency |
| **LSP bridge** | ✅ (intelephense, tsserver, pylsp) | ❌ AST-only |
| **Working memory** | ✅ (remember/recall per project) | ❌ No persistent memory |
| **Cross-editor MCP** | ✅ Zed, Claude, Gemini, Codex, VSCode, OpenCode | Limited (Claude Code, Cursor, Codex, OpenCode, Hermes) |
| **Capability router** | ✅ vision, OCR, doc pipeline | ❌ |
| **Telemetry** | ✅ latency, cache, health | ❌ |
| **Offline capable** | ✅ Full local stack | ✅ Full local stack |
| **Bundled binary** | ❌ Requires Python 3.9+ | ✅ Ships own Node.js runtime |
| **Community** | Growing | 26K stars |

---

## aihelper vs Traditional AI IDEs

| Aspect | Traditional AI IDEs | aihelper |
|--------|-------------------|----------|
| Context strategy | Full repo scan → giant prompt | Semantic routing → compact context |
| Latency | Cold Python startup (163ms+) | Persistent daemon (0.3ms IPC) |
| Token use | 50K+ tokens per task | 750 tokens average |
| Editing approach | Raw file rewrites | Patch planning + validation |
| Confidence | No scoring | 5-factor confidence engine |
| Model dependency | Cloud-only or giant local | Tiered: hot + medium + cloud |
| Editor support | Single IDE | 6 editors (Zed, Claude, Gemini, Codex, VSCode, OpenCode) |
| Multimodal | Proprietary | Open: minicpm-v, PaddleOCR, whisper |
| Telemetry | None | Built-in: latency, cache, health |
| Offline capable | Rarely | Yes — full local stack |

## aihelper vs Cursor

| Aspect | Cursor | aihelper |
|--------|--------|----------|
| Runtime | IDE-integrated | Runtime-agnostic daemon |
| Context | Tab-based | Semantic router + scheduler |
| Models | Cloud-first | Local-first, tiered |
| Extensibility | Plugin-limited | MCP-native, 6 editors |
| Token optimization | Limited | 95%+ reduction via routing |

## aihelper vs MCP Standalone

| Aspect | Raw MCP tools | aihelper MCP |
|--------|--------------|-------------|
| Profile | 10+ heavy servers | 4 minimal (git, fetch, context7, aihelper) |
| Routing | Manual selection | Intent-aware auto-routing |
| Latency | Per-tool startup | Daemonized (0.3ms) |
| Context | Tool-level | Project-level semantic graph |

## aihelper vs codegraph — Detailed Feature Matrix

```
┌─────────────────────────────────────────────────────────────────────┐
│                    AIHELPER v0.0.7                    CODEGRAPH     │
│                                                                     │
│  AI ORCHESTRATION LAYER                          GRAPH ENGINE       │
│  ┌──────────────────────────┐          ┌─────────────────────────┐ │
│  │ Intent Router            │          │ Tree-sitter AST (20+)   │ │
│  │ Model Router             │          │ SQLite + FTS5 ✓         │ │
│  │ Token Budgeting          │          │ Callers/Callees ✓       │ │
│  │ Patch Planning (5f)      │          │ Path Tracing ✓          │ │
│  │ Confidence Engine        │          │ Impact Radius ✓         │ │
│  │ Semantic Scheduler       │    vs    │ Type Hierarchy ✓        │ │
│  │ Working Memory           │          │ Framework Routes (14)   │ │
│  │ Editor Awareness         │          │ File Watcher(chokidar)  │ │
│  │ Capability Router        │          │ Cross-Project Query     │ │
│  │ Document Pipeline        │          │ Incremental Sync        │ │
│  │ Telemetry + Health       │          │ Bundled Binary          │ │
│  │ LSP Bridge               │          └─────────────────────────┘ │
│  │ Daemon IPC (0.3ms)       │                                      │
│  │ Watchman + Watchdog      │         KHÔNG CÓ:                    │
│  │ RAM Disk + Persistence   │         • Routing / Planning         │
│  │ 6 Editors MCP ✓         │         • Patch Engine               │
│  └──────────────────────────┘         • Model Selection            │
│                                       • Intent Detection           │
│  NEW IN v0.0.7:                       • Working Memory             │
│  • SQLite + FTS5 ✓                    • Telemetry                  │
│  • Callers/Callees ✓                  • LSP Bridge                 │
│  • Path Tracing ✓                     • Capability Router          │
│  • Impact Radius ✓                    • Daemon Architecture        │
│  • Framework Routes ✓                 • Document Pipeline          │
│  • File Watcher (watchdog) ✓                                      │
│  • 15 MCP Tools (was 9)                                           │
└─────────────────────────────────────────────────────────────────────┘
```

**Key insight:** aihelper and codegraph are **complementary**, not competitive. codegraph is a semantic graph engine (lower layer), aihelper is becoming an AI orchestration operating layer (upper layer). The strongest architecture combines aihelper's orchestration with a codegraph-style graph engine underneath — and v0.0.7 brings them closer together with shared SQLite + FTS5 + call graph capabilities.

---

## aihelper Unique Differentiators (codegraph doesn't have)

| Differentiator | Impact |
|---|---|
| **Daemon (0.3ms)** | Every `aihelper_*` tool call is 500x faster than cold Python |
| **Intent routing** | Tasks auto-routed to optimal tools before agent spins up |
| **Patch sequencing** | AI generates patch → confidence score → safe auto-apply |
| **Model tiering** | Tiny local model for autocomplete, larger for reasoning, cloud for architecture |
| **Multimodal pipeline** | Screenshot → OCR → structured data, fully local |
| **Editor sync** | aihelper knows which editor/file you're in across 6 editors |
| **Working memory** | Persistent project memory across sessions (agents forget; aihelper remembers) |
