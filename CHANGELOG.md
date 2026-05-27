# Changelog

All notable changes to aihelper will be documented here.

This project follows a lightweight release-note style. Dates use `YYYY-MM-DD`.

## Unreleased

## v0.1 - 2026-05-28

### Kernel Hardening — Typed Execution & Semantic Invalidation

**Zero new features. Pure integration.** Wires together the compiler-inspired modules
that v0.0.9 introduced in isolation.

- **Typed Execution Capabilities** (`primitives.py`): `PrimitiveContract` gains 4 immutable
  capability fields — `purity` (pure/mutative), `determinism`, `invalidation_scope` (symbol/file/module/global),
  `parallel_safe`. Smart defaults infer purity from `side_effects` and parallel_safe from purity.
  Distribution: 14/17 pure, 14/17 parallel-safe.

- **Optimizer Wired** (`optimizer.py` → `workflow_engine.py`): `optimize_dag()` now runs before
  DAG staging in `_execute_primitives()`. Returns `OptimizationResult` with full profiling
  (`applied_passes`, `folded_nodes`, `cache_hits`, `eliminated_nodes`, `estimated_speedup`).
  Optimizer remains PURE — no filesystem, graph, or cache mutation.

- **Semantic Invalidation Wired** (`invalidation.py` → `cache.py`): Every cache update
  classifies file changes via `classify_change()` with `ChangeClassification` dataclass
  carrying `semantic_confidence`. `should_propagate_invalidation()` makes call-graph-aware
  decisions. High-risk modules (auth/security/payment) always propagate.

- **Compression Confidence Decay** (`compressor.py` + `invalidation.py`): Weighted decay
  replaces fixed thresholds. 7 decay rates (body_only=0.01 → branch_switch=0.40).
  Recompression threshold at 0.60. Conservative 1.5× boost for high-risk modules.

### Changed
- `optimizer.py`: `optimize_dag()` returns `OptimizationResult` (was `List[str]`).
  `constant_folding_pass()` now checks `is_pure` before caching. Fixed dedup eliminated_nodes tracking.
- `workflow_engine.py`: `_execute_primitives()` calls optimizer before DAG staging.
  Cache-hit skipping integrated. Optimizer stats in `_profiling`.
- `cache.py`: `update_cache()` runs `_apply_semantic_invalidation()`. Returns `invalidation_report`.
- `daemon.py`: +1 handler (`invalidation_classify`), 55 total (was 54).
- `primitives.py`: `PrimitiveContract.to_dict()` includes typed capability fields.
- `invalidation.py`: +230 lines — `ChangeClassification`, weighted decay table, high-risk detection,
  `should_propagate_invalidation()`, `compute_semantic_confidence()`, `handle_invalidation_classify`.
- `compressor.py`: +65 lines — `compression_confidence` tracking, `apply_compression_decay()`,
  `force_recompress()`, `reset_compression_confidence()`.

### Design Principles
- **Harden the kernel** — No new features, pure integration
- **Immutable capabilities** — Set at registration, never mutated at runtime
- **Pure optimizer** — No filesystem, graph, or cache mutation
- **Conservative invalidation** — High-risk modules always propagate
- **Weighted decay** — Proportional to change severity
- **Zero new dependencies** — All Python stdlib

## v0.0.9 - 2026-05-28

### Added — Incremental Engineering Cognition Runtime

- **Workflow Runtime Engine** (`workflow_engine.py`): State machine with DAG-based execution, primitive caching, observability. ~480 lines.
- **Primitives Registry** (`primitives.py`): 17 named primitives with execution contracts. DAG builder + parallel staging. ~430 lines.
- **Tier Router** (`tier_router.py`): Three-tier task classification (deterministic/ollama/frontier) with ambiguity scoring. 95% classification accuracy. ~160 lines.
- **Verification Runtime** (`verify.py`): 4 verification commands (architecture, auth-safety, regression-risk, dependency-health). 100% deterministic. ~175 lines.
- **Context Compressor** (`compressor.py`): Cognition packages with incremental `_compression_cache`. ~160 lines.
- **Compression Fidelity** (`compressor_fidelity.py`): 6 automated checks for context preservation. ~210 lines.
- **Signature Invalidation** (`invalidation.py`): AST-based signature extraction for 5 languages. Distinguishes body-only from signature changes. JSON-line invalidation logging. ~255 lines.
- **Optimizer** (`optimizer.py`): 3 compiler-inspired passes — deduplication, constant folding, dead branch pruning. ~125 lines.
- **Mermaid Export** (`mermaid_export.py`): Visualizes primitive dependency graph, execution DAG stages, and category overview. ~125 lines.
- **Workflow DSL**: 5 YAML workflow definitions in `context_engine/workflows/` (v1.1, uses: composition).
- **4 new MCP tools**: `aihelper_workflow_run`, `aihelper_tier_route`, `aihelper_verify`, `aihelper_compress_context`. Total: 24 (was 20).
- **4 new CLI commands**: `aihelper workflow`, `aihelper verify`, `aihelper compress`, `aihelper tier-route`.

### Changed

- `daemon.py`: +5 handlers in `_external_handlers` (54 total).
- `mcp_server.py`: 24 MCP tools (was 20). 4 new schema functions, 4 new call handlers.
- `main.py`: +4 CLI parsers, +4 dispatch blocks.
- New docs: `runtime-vision.md`, `v0.0.9.md`, `benchmarks/v0.0.9-comparison.md`.
- `workflow_engine.py`: +`_primitive_cache`, +DAG-based `_execute_primitives`.
- `compressor.py`: +`_compression_cache` for incremental compression.

### Design Principles

- **Incremental-first**: Cache and reuse — don't recompute. From v0.0.7 cache layer through primitive cache to compression cache.
- **Compiler architecture**: Primitive contracts = execution IR, DAG = optimization pass.
- **Deterministic-first** (92% of steps): Execute locally whenever possible.
- **AI-at-decision-points**: Only call LLMs when ambiguity threshold exceeded.
- **Zero new dependencies**: All Python stdlib.

### Benchmarks

| Metric | v0.0.8 | v0.0.9 | Improvement |
|---|---|---|---|
| Deterministic steps | ~65% | ~92% | +27pp |
| Monthly token usage | ~888K | ~54K | 93.9% reduction |
| Monthly cost (GPT-4 @ $10/M) | $8.88 | $0.54 | $8.34 saved |
| Release check time | ~6 min | 1.2 sec | 300x |
| Primitive cache hit rate | N/A | ~60% (est.) | New capability |
| Compression cache hit rate | N/A | ~80% (est.) | New capability |

### Incremental Architecture (v0.0.7 substrate + v0.0.9 contracts)

| Compiler Concept | aihelper | Version |
|---|---|---|
| File invalidation | `cache_diff()` | v0.0.7 |
| Semantic fingerprinting | `semantic_changed` | v0.0.7 |
| Partial rebuild | `build_*_incremental()` | v0.0.7 |
| Watch mode | `watch_cache()` | v0.0.7 |
| Incremental DB sync | `sync_sqlite_incremental()` | v0.0.7 |
| Execution IR | `PrimitiveContract` | v0.0.9 |
| Execution DAG | `build_execution_dag()` | v0.0.9 |
| Primitive caching | `_primitive_cache` | v0.0.9 |
| Compression caching | `_compression_cache` | v0.0.9 |
| Fidelity checks | `compressor_fidelity.py` | v0.0.9 |

## v0.0.8 - 2026-05-27

### Added — Persistent Engineering Intelligence

- **Cognitive Memory Engine** (`memory_engine.py`): SQLite + FTS5 persistent knowledge store with three knowledge types: architectural decisions, debugging history (auto-recurrence detection), developer preferences. ~490 lines, zero new dependencies.
- **Knowledge Dispatcher** (`knowledge_dispatcher.py`): Formats and writes knowledge into each editor's native config files (markdown for Copilot/Claude, compact text for Codex). Auto-detect preferences from project lock files. ~300 lines.
- **Auto-capture observer**: `_auto_capture_knowledge()` runs silently after every daemon request. Detects preferences from route keywords, captures decisions from config patches, captures debug entries from diagnostics. Auto-dispatches on bootstrap.
- **5 new MCP tools**: `aihelper_knowledge_add_decision`, `aihelper_knowledge_add_debug`, `aihelper_knowledge_set_preference`, `aihelper_knowledge_recall`, `aihelper_knowledge_dispatch`. Total: 20 (was 15).
- **`aihelper knowledge` CLI**: 6 subcommands — `add-decision`, `add-debug`, `set-preference`, `recall`, `dispatch`, `list`.
- **init-config auto-detect**: Auto-detects project preferences from lock files and dispatches knowledge to all editor configs on every `aihelper init-config` run.

### Added — Modular Intelligence Package

- **`context_engine/intelligence/` package**: 11 modules, avg 50 lines each. Single responsibility per module.
  - `schema.py` — DB schema + v1→v2 migration
  - `storage.py` — Connection pool (WAL mode)
  - `evidence.py` — Confidence escalation, scoring gate, contradiction logging
  - `decisions.py` — Architectural decisions CRUD
  - `debugging.py` — Debug history + recurrence detection
  - `preferences.py` — Developer preferences key-value store
  - `search.py` — FTS5 hybrid search
  - `graph.py` — Graph-memory cross-reference links
  - `capture.py` — Auto-capture observer (36 preference patterns)
  - `handlers.py` — Daemon/MCP handler functions
- **Evidence tracking**: confidence, frequency, source, recency on all entries.
- **Lifecycle management**: active/deprecated/superseded status filtering.
- **Contradiction detection**: knowledge_conflicts table for conflicting entries.
- **Graph-memory fusion**: memory_graph_links table linking decisions to symbols.
- **Scoring gate**: auto-capture discards entries below 0.35 confidence threshold.
- **Frequency escalation**: repeated evidence boosts confidence over time.
- **V1→V2 safe migration**: automatic upgrade preserving all existing data.
- **Extended preference auto-detection**: 36 patterns across languages, databases, infra, architecture.
- **Dynamic retrieval**: dispatch_knowledge(task_context=...) for targeted context filtering.
- **Negative memory**: alternatives store rejection reasons as dicts with name and reason_rejected.
- **Codex MCP registration fix**: `scripts/codex-integration.py` now calls `codex mcp add aihelper` to register the aihelper MCP server. Codex v0.133.0 manages MCP via CLI subcommand, not JSON files. Without this, Codex had aihelper instructions but no way to call the tools.

### Changed

- `daemon.py`: 5 new knowledge handlers (60 total). Auto-capture observer.
- `session_bootstrap.py`: Knowledge recall — merges project-specific + global knowledge.
- `mcp_server.py`: 20 MCP tools (was 15).
- `scripts/init-config.sh` and `init-config.ps1`: Auto-detect + dispatch section.
- `scripts/codex-integration.py`: Added `_register_mcp_server()` — uses `codex mcp add aihelper` to register aihelper MCP server for Codex v0.133.0+
- `docs/integrations/editor-integration.md`: Documented Codex MCP integration details (registration, verification, removal)

### Fixed

- Session bootstrap now correctly merges project-specific and global knowledge.

### Design Principles

- **Not chat memory** — Structured types: decisions, debug history, preferences
- **Zero new dependencies** — SQLite + FTS5 built into Python stdlib
- **No new protocols** — Writes to editor native config files
- **Auto-capture** — Daemon learns passively, no explicit user calls needed
- **Idempotent** — All writes merge; safe to run repeatedly
- **Failsafe** — Auto-capture never blocks; graceful degradation

## v0.0.7 - 2026-05-26

### Added — Semantic Knowledge Graph

- **SQLite + FTS5** knowledge graph (`graph_db.py`): zero-dependency, WAL mode, sub-ms symbol lookup. Auto-syncs on every `cache build`.
- **Graph query MCP tools** (6 new): `aihelper_callers`, `aihelper_callees`, `aihelper_trace`, `aihelper_impact`, `aihelper_explore`, `aihelper_graph_status`. Total MCP tools: 15 (was 9).
- **`aihelper graph` CLI**: callers, callees, trace, impact, explore, status subcommands.
- **`aihelper upgrade`**: auto-migrate all projects under `~/github` to SQLite.
- **`aihelper affected`**: find test files impacted by changed source files (git diff integration).
- **Tree-sitter AST extraction** (`ast_extractor.py`): now default via `requirements.txt`. 9 languages (Python, JS, TS, Java, Go, Rust, PHP, C, C++). Falls back to regex.
- **Framework route detection** (`framework_routes.py`): 14 frameworks (Django → React Router).
- **Native file watcher** (`file_watcher.py`): watchdog + polling fallback with 2s debounce.
- **Benchmark suite** (`scripts/benchmark.py`): 4 runs per metric, median reported.

### Changed

- `cache.py`: auto-syncs to SQLite on every `build_cache` with `_sync_cache_to_sqlite()`.
- `symbols.py`: SQLite FTS5 used as primary lookup, JSON fallback.
- `mcp_server.py`: 15 MCP tools (up from 9), daemon-proxied graph queries.
- `daemon.py`: 6 new handler methods.
- `main.py`: `upgrade`, `graph`, `affected` subcommands.
- `requirements.txt`: tree-sitter + watchdog now default dependencies.

### Fixed

- JSON file storage O(n) bottleneck → SQLite FTS5 O(log n).
- No call graph capabilities → multi-depth BFS callers/callees/trace/impact.
- No framework routes → 14 web frameworks detected with edges from routes → handlers.
- **`clean_cache` not resetting SQLite singleton** → now calls `close_all()` to prevent stale connections.
- **`watch_cache` always doing full rebuild** → replaced by `update_cache()` incremental path. `cache_diff()` detects changes → `build_file_index_incremental()` + `build_symbol_graph_incremental()` + `sync_sqlite_incremental()` process only changed files. Initial test: 3x speedup on 120-file project; scales better on larger codebases.
- Symbol lookup iteration → sub-millisecond FTS5.

### Benchmarks (aihelper self-host, M1 Pro)

| Metric | Value |
|---|---|
| Cache build | 12ms (102 files, 650 symbols) |
| FTS5 search | **0.032ms/query** |
| JSON lookup | 0.5ms/query (baseline) |
| SQLite DB size | 0.64MB (102 files) |
| Journal mode | WAL |

### Added (v0.0.7 extras)

- Windows support foundation: PowerShell/CMD launchers, PowerShell bootstrap, Windows CI smoke job, and Windows install docs.
- Portable daemon IPC: Unix sockets remain on macOS/Linux; Windows uses an auto-detected TCP loopback endpoint.
- Contributor guide for focused workflow-driven pull requests.
- Release notes for v0.0.6.
- Blog draft explaining semantic routing versus giant prompts.

### Changed (v0.0.7 extras)

- README positioning now leads with the "Stop sending giant prompts" narrative.
- Demo workflow previews use a wider table layout for better GitHub readability.
- OCR and diagnostics GIF demos were regenerated at a shorter, more readable size.
- Diagnostics and document-pipeline temp paths are more portable across platforms.

## v0.0.6 - 2026-05-23

### Added

- OSS onboarding assets: README visuals, demo GIFs, benchmark charts, issue templates,
  PR template, funding metadata, installation docs, and workflow examples.
- Architecture SVG plus runtime map.
- Benchmark visuals for daemon latency, token reduction, and local model memory tiers.
- Contributor guide and changelog.

### Highlights

- Semantic routing replaces broad repo scans with compact context.
- Daemonized runtime removes repeated Python startup overhead.
- Patch-first workflows connect diagnostics, context, confidence scoring, and safe apply.
