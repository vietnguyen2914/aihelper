# Comparisons

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
