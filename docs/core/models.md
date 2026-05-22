# Model Strategy

aihelper uses a **tiered model architecture** — not one giant LLM. Each tier is optimized for a specific latency/capability trade-off.

## Tier Architecture

```
Hot (0.3-5ms IPC)                    Medium (50-200ms)              Cloud
┌─────────────────────┐          ┌──────────────────────┐     ┌─────────────────┐
│ deepseek-coder:1.3b │   ──→   │ deepseek-coder-v2:16b│     │ DeepSeek V4     │
│ phi4-mini           │   fall-  │ qwen3.5:9b           │  →  │ GPT 5.5         │
│ qwen3.5:4b-16k      │   back   │                      │     │ Gemini 2.5      │
└─────────────────────┘          └──────────────────────┘     └─────────────────┘
     ↓ intent router                    ↓ complex tasks            ↓ architecture
```

### Hot Tier (always loaded)

| Model | Size | RAM | Latency | Role |
|-------|------|-----|---------|------|
| `deepseek-coder:1.3b` | 776MB | 2.9GB | ~5ms | Autocomplete, inline suggestions |
| `phi4-mini:latest` | 2.5GB | 5.7GB | ~20ms | Assistant chat, code review |
| `qwen3.5:4b-16k` | 3.4GB | 6.1GB | ~30ms | Semantic edits, patch generation |

All 3 hot models fit in **16GB RAM** simultaneously.

### Medium Tier (loaded on demand)

| Model | Size | RAM | Role |
|-------|------|-----|------|
| `deepseek-coder-v2:16b` | ~10GB | ~16GB | Coding fallback (MoE architecture) |
| `qwen3.5:9b` | ~6GB | ~13GB | Vietnamese-aware, general reasoning |

Loaded via intent trigger — not preloaded.

### Cloud Tier (external API)

DeepSeek V4 Pro, GPT 5.5, Gemini 2.5 Pro — for architecture-level reasoning where latency isn't critical.

## Intent → Model Mapping

The [Intent Router](../architecture/intent-router.md) selects the model based on coding intent, not file path:

| Intent | Hot Model | Fallback |
|--------|-----------|----------|
| `bugfix` | `qwen3.5:4b-16k` | `deepseek-coder-v2:16b` |
| `refactor` | `qwen3.5:4b-16k` | Cloud |
| `autocomplete` | `deepseek-coder:1.3b` | N/A |
| `chat` | `phi4-mini` | Cloud |
| `explain` | `phi4-mini` | `qwen3.5:9b` |
| `schema` | `qwen3.5:4b-16k` | Cloud |
| `optimize` | `qwen3.5:4b-16k` | `deepseek-coder-v2:16b` |

## Embeddings

| Model | Size | Use | Latency |
|-------|------|-----|---------|
| `nomic-embed-text:latest` | 274MB | Fast lookup, hot path | ~2ms |
| `bge-m3:latest` | 2.2GB | High-quality retrieval | ~50ms |

## Multimodal

| Model | Capability | Use |
|-------|-----------|-----|
| `minicpm-v:latest` | Vision | Screenshots, UI parsing |
| PaddleOCR | OCR | Text extraction from images |
| `faster-whisper` | STT | Audio transcription |

## Model Selection Guide

```
Your RAM Budget:
├── 8GB  → deepseek-coder:1.3b only
├── 16GB → all 3 hot models
├── 32GB → hot + deepseek-coder-v2:16b
└── 64GB → everything + full reranker
```

## No Model Mode

aihelper's core features work **without any LLM**:
- Semantic routing (intent detection)
- Symbol graph + dependency graph
- Compact context assembly (95%+ token reduction)
- Patch planning + confidence scoring
- Structural diff
- Daemon IPC

Models are additive — they enhance the runtime but are not required.
