# Target Project Runtime Guide

## Fast path

From the repo you want to inspect:

```bash
/Users/vietnguyen/github/aihelper/bin/aihelper "trace upload flow"
```

That command automatically points the helper at the current directory.

## Example Targets

### HIS PHP project

```bash
cd /opt/homebrew/var/www/his
/Users/vietnguyen/github/aihelper/bin/aihelper "trace outpatient intake flow"
```

The launcher uses the current directory as the target project, so the helper reads `/opt/homebrew/var/www/his/ai/...` when you run it from that project root.

## When to use direct `main.py`

```bash
python3 /Users/vietnguyen/github/aihelper/context_engine/main.py analyze "trace outpatient intake flow" --project-root "$PWD"
```

Use this when you want explicit flags like:

- `--json`
- `--format prompt`
- `--max-context-chars 8000`
- `--auto-update-kb`

By default, the helper prints structured Markdown instead of JSON.

## Ollama fallback

If Ollama is not available locally, the helper prints a ready-to-paste discovery prompt instead of failing. You can paste that prompt into GPT or Claude and use their output to continue the discovery step manually.

## Local Cost / Speed Defaults

For normal Codex usage, keep aihelper as a fast context router:

```bash
/Users/vietnguyen/github/aihelper/bin/aihelper analyze "trace upload flow" --format prompt --max-context-chars 6000
```

Default local model roles:

| Role | Model | Use |
|---|---|---|
| `tiny` | `deepseek-coder:1.3b` | very small code-oriented checks and warmup |
| `medium` | `qwen3.5:4b` | default unknown-feature discovery |
| `large` | `qwen3.5:4b` | heavier local reasoning when still practical |

Avoid `qwen3.5:9b` and `sorc/qwen3.5-claude-4.6-opus:latest` for interactive loops on this Mac unless quality matters more than latency.

Check and prewarm:

```bash
/Users/vietnguyen/github/aihelper/bin/aihelper ollama health
/Users/vietnguyen/github/aihelper/bin/aihelper ollama prewarm --model-type medium
```

The fast path does not call Ollama for every keyword normalization. Set these only for experiments:

```bash
AIHELPER_LLM_NORMALIZE=1
AIHELPER_LLM_INTENT=1
```

Recommended Ollama LaunchAgent runtime on Apple Silicon:

```text
OLLAMA_HOST=127.0.0.1:11434
OLLAMA_FLASH_ATTENTION=1
OLLAMA_KV_CACHE_TYPE=q8_0
OLLAMA_MAX_LOADED_MODELS=1
OLLAMA_NUM_PARALLEL=1
OLLAMA_KEEP_ALIVE=30m
```
