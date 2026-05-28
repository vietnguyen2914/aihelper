# Documentation

## Getting Started

- [user/setup-guide.md](./user/setup-guide.md) — **Quick 5-step setup** (install, initialize, build cache, verify)
- [INSTALLATION.md](./INSTALLATION.md) — Full installation, prerequisites, editor integration (macOS, Linux, Windows)
- [README.md](../README.md) — Overview, features, benchmarks, commands
- [CONTRIBUTING.md](../CONTRIBUTING.md) — How to report issues and contribute workflow-focused improvements
- [CHANGELOG.md](../CHANGELOG.md) — Release history and upcoming changes

## Behavioral Laws

- [ai/system/behavioral_laws.md](../ai/system/behavioral_laws.md) — AI agent behavioral code (routing, token budget, graph boundaries)

## Core

- [core/models.md](./core/models.md) — Model strategy, tier architecture, intent→model mapping, selection guide
- [core/local-setup.md](./core/local-setup.md) — Local setup, cache architecture, optimization, memory budget

## Architecture

- [architecture/](./architecture/) — System design, use cases, entity CRUD

## Integrations

- [integrations/](./integrations/) — Editor MCP configs (Zed, Claude Desktop, VSCode, Gemini, OpenCode)
- [integrations/editor-integration.md](./integrations/editor-integration.md) — On-demand VS Code/Copilot, Codex, Claude integration scripts

## Multimodal

- Vision: `minicpm-v` for screenshots, UI parsing
- OCR: PaddleOCR for text extraction
- Embeddings: `bge-m3` + `nomic-embed-text`
- Reranker: CrossEncoder for retrieval scoring
- STT: `faster-whisper` for speech-to-text

## Runtime

- [runtime/target-project-runtime.md](./runtime/target-project-runtime.md) — Runtime configuration

## Examples

- [examples/fix-php-bug.md](./examples/fix-php-bug.md) — Fix PHP bug with semantic routing + patch planning
- [examples/diagnostics-to-patch.md](./examples/diagnostics-to-patch.md) — Generate patch plans from compiler/linter diagnostics
- [examples/parse-screenshot.md](./examples/parse-screenshot.md) — Vision + OCR screenshot analysis
- [examples/generate-presentation.md](./examples/generate-presentation.md) — Mermaid → Marp → PPTX pipeline

## Community

- [../CONTRIBUTING.md](../CONTRIBUTING.md) — Contribution guide
- [../CHANGELOG.md](../CHANGELOG.md) — Release history
- [releases/v0.0.6.md](./releases/v0.0.6.md) — Release notes for v0.0.6

## Troubleshooting

- [INSTALLATION.md#troubleshooting](./INSTALLATION.md#troubleshooting) — Common issues and solutions
- `aihelper doctor` — Full diagnostic command
- `cat ~/.aihelper/daemon.log` — Daemon runtime logs

## Features

- [features/](./features/) — Feature documentation

## Use Cases

- [use-cases/](./use-cases/) — Business use cases

## Development

- [development/](./development/) — Development notes
- [workflows/README.md](./workflows/README.md) — Common workflow patterns
