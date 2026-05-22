# Roadmap

## Phase 1 — Semantic Runtime (v0.1) ✅
- [x] Symbol graph + dependency graph indexing
- [x] Semantic fingerprints (formatting-only ignores)
- [x] Intent-aware task routing
- [x] Compact context assembly (95%+ token reduction)
- [x] SQL schema summaries

## Phase 2 — Daemonization (v0.2) ✅
- [x] Persistent Unix socket daemon (0.3ms IPC)
- [x] In-memory hot cache (47 method handlers)
- [x] Auto-fallback to direct Python
- [x] Structured telemetry (latency, cache hits, errors)
- [x] Subsystem health monitoring + graceful degradation

## Phase 3 — Editor Awareness (v0.3) ✅
- [x] Cross-editor MCP integration (Zed, Claude, Gemini, Codex, VSCode, OpenCode)
- [x] Active editor detecton (open file, git branch)
- [x] LSP bridge (go-to-definition, references, document symbols)
- [x] Working memory + branch-specific context

## Phase 4 — Patch-First Editing (v0.3) ✅
- [x] Unified diff generation + git apply validation
- [x] 5-factor confidence scoring (syntax, ambiguity, API, tests, files)
- [x] Structural diff (AST-aware: renamed methods, changed signatures, SQL)
- [x] Safe auto-apply with rollback snapshots
- [x] Rename impact graph + transitive analysis

## Phase 5 — Multimodal (v0.4) ✅
- [x] Vision: minicpm-v (screenshots, UI parsing)
- [x] OCR: PaddleOCR (text extraction)
- [x] Embeddings: nomic-embed-text (hot) + bge-m3 (high-quality)
- [x] Reranker: CrossEncoder (retrieval scoring)
- [x] STT: faster-whisper (speech-to-text)

## Phase 6 — Capability Orchestration (v0.5) ✅
- [x] Capability router (classify input → select pipeline)
- [x] Document pipeline (Mermaid, DBML, Vega-Lite, Marp, Pandoc, LibreOffice)
- [x] Intent-triggered activation (no preload)
- [x] Bootstrap script + doctor diagnostics

## Future

| Area | Goal |
|------|------|
| **Collaborative** | Multi-agent shared semantic runtime |
| **Predictive** | Scheduler-driven prefetching |
| **Metadata** | Cross-session working memory sync |
| **LLM-agnostic** | MLX + llama.cpp runtime support |
| **Mobile** | Edge inference companion |
| **Cloud bridge** | Hybrid local/cloud orchestration |
