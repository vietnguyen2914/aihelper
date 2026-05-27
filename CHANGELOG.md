# Changelog

All notable changes to aihelper will be documented here.

This project follows a lightweight release-note style. Dates use `YYYY-MM-DD`.

## Unreleased

## v0.0.8 - 2026-05-27

### Added — Persistent Engineering Intelligence

- **Cognitive Memory Engine** (`memory_engine.py`): SQLite + FTS5 persistent knowledge store with three knowledge types: architectural decisions, debugging history (auto-recurrence detection), developer preferences. ~490 lines, zero new dependencies.
- **Knowledge Dispatcher** (`knowledge_dispatcher.py`): Formats and writes knowledge into each editor's native config files (markdown for Copilot/Claude, compact text for Codex). Auto-detect preferences from project lock files. ~300 lines.
- **Auto-capture observer**: `_auto_capture_knowledge()` runs silently after every daemon request. Detects preferences from route keywords, captures decisions from config patches, captures debug entries from diagnostics. Auto-dispatches on bootstrap.
- **5 new MCP tools**: `aihelper_knowledge_add_decision`, `aihelper_knowledge_add_debug`, `aihelper_knowledge_set_preference`, `aihelper_knowledge_recall`, `aihelper_knowledge_dispatch`. Total: 20 (was 15).
- **`aihelper knowledge` CLI**: 6 subcommands — `add-decision`, `add-debug`, `set-preference`, `recall`, `dispatch`, `list`.
- **init-config auto-detect**: Auto-detects project preferences from lock files and dispatches knowledge to all editor configs on every `aihelper init-config` run.

### Changed

- `daemon.py`: 5 new knowledge handlers (60 total). Auto-capture observer.
- `session_bootstrap.py`: Knowledge recall — merges project-specific + global knowledge.
- `mcp_server.py`: 20 MCP tools (was 15).
- `scripts/init-config.sh` and `init-config.ps1`: Auto-detect + dispatch section.

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
