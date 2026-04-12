# AI Helper Project Knowledge Base

## Purpose

This repository provides a portable AI context engine that you can run from one place while targeting another repository. The engine reads the target repo's `ai/index/*.json` files, loads related feature and flow documents, inspects override paths, and emits a structured prompt and execution plan for the task you want to run.

## Quick Start

### One-line usage from another project

```bash
~/github/aihelper/bin/aihelper "fix signing timeout"
```

Run that command from the target repo root. The launcher automatically uses the current directory as `AIHELPER_TARGET_ROOT`.

### Explicit project root

```bash
AIHELPER_TARGET_ROOT=~/github/mindforme ~/github/aihelper/bin/aihelper "trace S3 upload flow"
```

### Prompt-only output

```bash
~/github/aihelper/bin/aihelper analyze "trace S3 upload flow" --format prompt
```

## Documentation Map

### Function-First Entry Points

- [Architecture Overview](./architecture/README.md)
- [Use Case Map](./use-cases/README.md)
- [Platform And Operations](./platform/platform-and-operations.md)
- [Target Project Runtime Guide](./runtime/target-project-runtime.md)
- [Development Workflow](./development/entity-generation-and-custom-id-patterns.md)

### Analysis Notes

- [Hybrid Design Findings](./analysis/hybrid-design.md)

## Repository Map

```text
context_engine/
  main.py              CLI entrypoint for cross-project analysis
  common.py            Root detection, index compatibility, JSON helpers
  detect_feature.py    Feature matching across target services
  load_context.py      Feature, flow, integration, and ext override loading
  intent_detector.py   Intent classification with project fallback support
  build_prompt.py      Final prompt and rewritten prompt builders
  planner.py           Deterministic execution plan builder
  discovery.py         Codebase inspection fallback when indexes do not match
  learning.py          Learned keywords and feedback persistence
  kb_updater.py        Optional write-back for newly discovered features

bin/
  aihelper             One-line launcher that targets the current directory

ai/system/
  intents.json         Default portable intent configuration
  shared_keywords.json Shared seed keyword structure

docs/
  ...                  Function-first documentation tree
```

## How To Navigate By Task

| If you are working on... | Start here |
|---|---|
| What this helper does and how the pieces fit | [Architecture Overview](./architecture/README.md) |
| How to run it against `mindforme`, `signserver`, or `lms` | [Target Project Runtime Guide](./runtime/target-project-runtime.md) |
| What changed relative to the source helpers | [Hybrid Design Findings](./analysis/hybrid-design.md) |
| How to extend intents, planning, or KB write-back | [Development Workflow](./development/entity-generation-and-custom-id-patterns.md) |

## Core Conventions

### Target-root-first execution

- The helper repo stays stable and portable.
- The current shell directory is treated as the target project unless `AIHELPER_TARGET_ROOT` or `--project-root` says otherwise.
- The helper reads from the target repo's `ai/` folder and writes learning data back there when that folder exists.

### Index compatibility

- `features.json`, `flows.json`, and `integrations.json` can be either keyed objects like `{"features": [...]}` or raw arrays.
- Feature payloads can come from either feature files in `ai/features/*.json` or directly from the feature index when no separate file exists.
- Override discovery uses both explicit metadata like `related_ext_files` and filesystem heuristics like `ext` paths or `*Ext*` classes.

### Documentation policy

- Docs are organized by function first, then runtime and development usage.
- Behavior-changing tasks should update both code and the relevant documentation page in this tree.

