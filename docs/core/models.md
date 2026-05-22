# Model Stack

## Principle

> **Context-centric, NOT model-centric.** Retrieval quality + semantic routing + editor awareness > more params.

## Local Models (Ollama)

| Tier | Model | RAM | Context | Wall Time | Role |
|------|-------|-----|---------|-----------|------|
| 🔥 Hot | `deepseek-coder:1.3b` | 2.9GB | 16K | 1.69s | Autocomplete, inline, speculative |
| 🔥 Hot | `phi4-mini:latest` | 5.7GB | 32K | 1.45s | Assistant, automation, shell |
| 🔥 Hot | `qwen3.5:4b-16k` | 6.1GB | 16K | 2.77s | Semantic edits, patch, refactor |
| 🟡 Medium | `deepseek-coder-v2:16b` | ~10GB | 128K | — | Coding fallback (MoE, 2B active) |
| 🟡 Medium | `qwen3.5:9b` | ~13GB | 32K | — | Vietnamese docs, general |

## Cloud Models

| Model | Provider | Use |
|-------|----------|-----|
| DeepSeek V4 Pro | Zed | Complex reasoning, multi-file patches |
| GPT-5.5 | Codex | Architecture, debugging, security |
| Gemini 3.5 Pro | Antigravity | Large-context analysis |

## Context Strategy

| Workflow | Context | Model |
|----------|---------|-------|
| autocomplete | 4K | deepseek-coder:1.3b |
| patch drafting | 8K | qwen3.5:4b-16k |
| semantic edits | 16K | qwen3.5:4b-16k |
| refactor | 24-32K | deepseek-coder-v2:16b |
| giant operations | 64K+ | cloud |

## Benchmarks (M1 Pro 32GB)

| Model | Wall Time | Memory | Thinking |
|-------|-----------|--------|----------|
| deepseek-coder:1.3b | 1.69s | 2.9GB | No |
| phi4-mini | 1.45s | 5.7GB | Yes |
| qwen3.5:4b-16k | 2.77s | 6.1GB | Yes |
| gemma4:e4b (removed) | 2.63s | 10GB | Yes — too heavy |
| MLX Qwen3-8B | 11 tok/s | 16.4GB | — too heavy |

> **Winner**: qwen3.5:4b-16k remains optimal for hot tier (best memory/quality ratio).
> deepseek-coder:1.3b is 2x faster for autocomplete/inline tasks.
