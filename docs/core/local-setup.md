# Local Setup & Optimization

## Overview

aihelper is designed to run **100% locally**. No cloud dependency for core features. This guide covers optimal local configuration.

## Architecture at a Glance

```
Your Editor (Zed/Claude/VSCode/Codex)
    │ MCP protocol
    ▼
aihelper Daemon (Unix socket, ~0.3ms IPC)
    │ in-memory cache
    ▼
Context Engine (routing, symbols, patches)
    │ intent-triggered
    ▼
Local Models (Ollama) or Cloud APIs
```

## Directory Layout

```
~/.aihelper/
├── aihelper.sock       # Unix socket (daemon IPC)
├── aihelperd.pid       # Daemon PID file
├── daemon.log          # Daemon runtime log
├── logs/               # LaunchAgent logs
│   ├── launchd.stdout.log
│   └── launchd.stderr.log
├── persist/            # SSD cache persistence
├── models/             # Model metadata
└── telemetry.db        # Performance telemetry
```

## Cache Architecture

### Two-tier cache

| Tier | Storage | Speed | Persistence |
|------|---------|-------|-------------|
| L1 | RAM (process memory) | ~0.3ms | Ephemeral |
| L2 | SSD (~/.aihelper/persist) | ~5ms | 8h auto-sync |

### How cache works

1. **Build:** `aihelper cache build` scans project, indexes symbols, dependencies, schema
2. **Hot:** Daemon keeps L1 in RAM — zero-latency access
3. **Refresh:** `aihelper cache watch` uses Watchman for incremental updates
4. **Persist:** Every 8h, L1 → L2 syncs to SSD
5. **Restore:** After reboot, L2 → L1 reloads on first access

### Cache contents

- Symbol graph (class/function/variable definitions)
- Dependency graph (import/require relationships)
- SQL schema summaries
- Semantic fingerprints (line-hash based)
- Feature indexes

## Optimization Techniques

### 1. Ramdisk (faster than SSD)

```bash
# macOS: Create 2GB RAM disk
diskutil erasevolume HFS+ "ramdisk" \
  $(hdiutil attach -nomount ram://4096000)

# Symlink persist to RAM
mv ~/.aihelper/persist ~/.aihelper/persist.ssd
ln -s /Volumes/ramdisk ~/.aihelper/persist
```

### 2. Watchman (incremental cache)

Without Watchman, `cache build` re-scans all files. With Watchman:

```bash
brew install watchman
aihelper cache watch --project-root /my/project

# Only changed files are re-indexed
# → 10x faster for large projects
```

### 3. Prewarm models

```bash
# Pre-load hot models into memory
aihelper ollama prewarm --model-type tiny

# Or for full stack
aihelper ollama prewarm --model-type large
```

### 4. Intent-triggered loading

Medium-tier models (16b) are **not preloaded**. They load on first use when the intent router detects a complex task. This saves ~10GB RAM.

### 5. Telemetry-driven tuning

```bash
# View latency histogram
aihelper telemetry

# Check subsystem health
aihelper health

# View degradation status
aihelper degradation
```

Use telemetry to identify slow paths:
- High cache miss rate → increase persist frequency
- High daemon latency → check RAM pressure
- Frequent fallback to direct Python → check daemon health

## Memory Budget

| Component | RAM | Notes |
|-----------|-----|-------|
| Daemon (idle) | ~50MB | No projects cached |
| Daemon (1 project) | ~100-200MB | Depends on project size |
| Daemon (10 projects) | ~500MB-1GB | Proportional |
| Ollama (3 hot models) | ~14GB | Combined RSS |
| Ramdisk (optional) | 2GB+ | Configurable size |

## Network-Local Tradeoffs

| Aspect | Local | Cloud |
|--------|-------|-------|
| Latency | 0.3ms–30ms | 500ms–5s |
| Privacy | Full | Dependent on provider |
| Cost | Electricity only | Per-token pricing |
| Capability | Limited to model size | Unlimited (SOTA models) |
| Offline | Yes | No |

aihelper is **local-first**: core runtime works offline. Cloud is only for complex reasoning tasks.
