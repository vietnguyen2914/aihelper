# CLI Reference

## Cache
```bash
aihelper cache build             # Full index (symbols, deps, schemas)
aihelper cache status            # Freshness + diff report
aihelper cache watch             # Watchman-backed incremental refresh
aihelper cache persist --all     # RAM cache → SSD (8h auto-sync)
aihelper cache restore           # SSD → RAM on reboot
aihelper cache persist-status    # Check persistence state
```

## Context & Routing
```bash
aihelper route "fix bug"         # Intent-aware routing
aihelper symbol find "UserService"
aihelper symbol context "method"
aihelper context                 # Compact project context
aihelper prompt-blocks show      # Precomputed summaries
aihelper diff-summary            # Semantic git diff
```

## Daemon
```bash
aihelper daemon start            # Persistent background runtime
aihelper daemon status           # Health + local IPC endpoint check
aihelper daemon stop
```

## Editor / LSP
```bash
aihelper editor-context          # Detect active editor + file
aihelper lsp definition <file>   # Go-to-definition
aihelper lsp references <file>   # Find references
aihelper lsp symbols <file>      # Document symbols
```

## Patch & Confidence
```bash
aihelper patch-plan "fix" --file src/Main.java
aihelper structural-diff --patch-file patch.diff
aihelper impact-graph "UserService"  # Rename impact analysis
aihelper confidence --patch-file fix.patch
aihelper classify-op --patch-file patch.diff
```

## Diagnostics & Health
```bash
aihelper diagnostics --file-path src/Main.java
aihelper doctor                  # Installation diagnostics
aihelper health                  # Subsystem health (watchman, ollama, ramdisk)
aihelper degradation             # Graceful degradation status
aihelper telemetry               # Daemon metrics (latency, cache, errors)
```

## Scheduler & Memory
```bash
aihelper scheduler snapshot      # Semantic scheduler state
aihelper scheduler predict       # Predicted next actions
aihelper scheduler record        # Record signal (edit, query, error)
aihelper memory add "topic" "note"
aihelper memory recall "query"
```

## Intent Routing
```bash
aihelper intent-route "fix null pointer"  # Route by intent type
```

## Document Pipeline
```bash
aihelper generate_mermaid        # Mermaid diagram DSL
aihelper generate_presentation   # Markdown → Marp → PPTX/PDF
aihelper convert_document        # Pandoc/LibreOffice conversion
aihelper parse_document          # Docling parsing
```

## Capabilities
```bash
aihelper capability-route        # Classify + select pipeline
aihelper capability-vision       # Screenshot parsing (minicpm-v)
aihelper capability-ocr          # Text extraction (PaddleOCR)
aihelper capability-rerank       # Document reranking
aihelper capability-embed        # Text embeddings
```

## Setup & Config
```bash
aihelper init-config          # Generate per-project agent configs (.github/copilot-instructions.md)
```

## Bootstrap
```bash
bash scripts/bootstrap.sh        # Prerequisites + env setup
aihelper doctor                  # Verify installation
```
