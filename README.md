# aihelper

Portable hybrid AI helper for repositories that keep project knowledge in `ai/`.

Quick start from a target repo:

```bash
/Users/vietnguyen/github/aihelper/bin/aihelper "trace upload flow"
```

Available commands:

```bash
/Users/vietnguyen/github/aihelper/bin/aihelper
/Users/vietnguyen/github/aihelper/bin/aihelper "trace upload flow"
/Users/vietnguyen/github/aihelper/bin/aihelper analyze "trace upload flow"
/Users/vietnguyen/github/aihelper/bin/aihelper analyze "trace upload flow" --json
/Users/vietnguyen/github/aihelper/bin/aihelper feedback "trace upload flow" --intent upload_flow
/Users/vietnguyen/github/aihelper/bin/aihelper feedback-summary
/Users/vietnguyen/github/aihelper/bin/aihelper rebuild-index
/Users/vietnguyen/github/aihelper/bin/aihelper ollama health
/Users/vietnguyen/github/aihelper/bin/aihelper ollama prewarm --model-type medium
```

The default output format is structured Markdown. Use `--json` or `-json` when you need machine-readable output.

For Codex, use compact prompt mode from the target repository:

```bash
/Users/vietnguyen/github/aihelper/bin/aihelper analyze "trace upload flow" --format prompt --max-context-chars 6000
```

Local Ollama is used only for unknown-feature discovery and explicit `ollama prewarm` by default. Fast keyword routing is deterministic unless `AIHELPER_LLM_NORMALIZE=1` or `AIHELPER_LLM_INTENT=1` is set.

For agent tools that support MCP, expose aihelper through:

```bash
python3 /Users/vietnguyen/github/aihelper/context_engine/mcp_server.py
```

Docs: [docs/README.md](./docs/README.md)

In case of functional analysis template for multi-languages project (English mixed with Vietnamese), reference to HIS project with below example prompt:

`Phân tích và cập nhật luồng thu ngân ngoại trú theo mẫu đang có, bám 'docs/ai-agent/mau-phan-tich-luong.md', cập nhật 'docs/use-cases/', và giữ file chính là 'overview.md'.`
