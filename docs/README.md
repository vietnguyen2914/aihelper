# Documentation

## Getting Started

- [INSTALLATION.md](./INSTALLATION.md) — Setup, prerequisites, editor integration (Apple Silicon, Linux, minimal/full)
- [README.md](../README.md) — Overview, features, benchmarks, commands
- [CONTRIBUTING.md](../CONTRIBUTING.md) — How to report issues and contribute workflow-focused improvements
- [CHANGELOG.md](../CHANGELOG.md) — Release history and upcoming changes

## Core

- [core/models.md](./core/models.md) — Model strategy, tier architecture, intent→model mapping, selection guide
- [core/local-setup.md](./core/local-setup.md) — Local setup, cache architecture, optimization, memory budget

## Architecture

- [architecture/](./architecture/) — System design, use cases, entity CRUD

## Integrations

- [integrations/](./integrations/) — Editor MCP configs (Zed, Claude Desktop, VSCode, Gemini, OpenCode)

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

- [community/discussions.md](./community/discussions.md) — Suggested GitHub Discussions setup and first pinned topic
- [community/launch-playbook.md](./community/launch-playbook.md) — Public launch messaging and content cadence
- [community/hacker-news-post.md](./community/hacker-news-post.md) — Hacker News launch draft
- [community/reddit-posts.md](./community/reddit-posts.md) — Reddit launch drafts
- [community/testimonials.md](./community/testimonials.md) — Testimonial collection guide
- [releases/v0.6.0.md](./releases/v0.6.0.md) — Release notes for v0.6.0
- [blog/semantic-routing-vs-giant-prompts.md](./blog/semantic-routing-vs-giant-prompts.md) — Blog draft for the core positioning narrative

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
