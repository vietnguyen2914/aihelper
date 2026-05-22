# aihelper

Portable hybrid AI helper for repositories that keep project knowledge in `ai/`.

Quick start from a target repo:

```bash
~/github/aihelper/bin/aihelper "trace upload flow"
```

Available commands:

```bash
~/github/aihelper/bin/aihelper
~/github/aihelper/bin/aihelper "trace upload flow"
~/github/aihelper/bin/aihelper analyze "trace upload flow"
~/github/aihelper/bin/aihelper analyze "trace upload flow" --json
~/github/aihelper/bin/aihelper feedback "trace upload flow" --intent upload_flow
~/github/aihelper/bin/aihelper feedback-summary
~/github/aihelper/bin/aihelper rebuild-index
~/github/aihelper/bin/aihelper cache build --project-root "$PWD"
~/github/aihelper/bin/aihelper cache status --project-root "$PWD"
~/github/aihelper/bin/aihelper cache watch --project-root "$PWD"
~/github/aihelper/bin/aihelper cache watch-all --extra-project /opt/homebrew/var/www/his
~/github/aihelper/bin/aihelper cache warm --project-root "$PWD"
~/github/aihelper/bin/aihelper prompt-blocks build --project-root "$PWD"
~/github/aihelper/bin/aihelper diff-summary --project-root "$PWD"
~/github/aihelper/bin/aihelper memory recall --project-root "$PWD"
~/github/aihelper/bin/aihelper symbol find UserService --project-root "$PWD"
~/github/aihelper/bin/aihelper symbol context UserService --project-root "$PWD"
~/github/aihelper/bin/aihelper deps UserService --project-root "$PWD"
~/github/aihelper/bin/aihelper route "fix checkout service" --project-root "$PWD"
~/github/aihelper/bin/aihelper patch-plan "fix checkout service" --file src/path/File.java
~/github/aihelper/bin/aihelper patch-apply --patch-file /tmp/change.diff --project-root "$PWD"
~/github/aihelper/bin/aihelper validate-files src/path/File.java --project-root "$PWD"
~/github/aihelper/bin/aihelper ollama health
~/github/aihelper/bin/aihelper ollama prewarm --model-type medium
```

The default output format is structured Markdown. Use `--json` or `-json` when you need machine-readable output.

For Codex, use compact prompt mode from the target repository:

```bash
~/github/aihelper/bin/aihelper analyze "trace upload flow" --format prompt --max-context-chars 6000
```

Local Ollama is used only for unknown-feature discovery and explicit `ollama prewarm` by default. Fast keyword routing is deterministic unless `AIHELPER_LLM_NORMALIZE=1` or `AIHELPER_LLM_INTENT=1` is set.

## Local Cache And Routing

`aihelper cache build` writes local-only cache files under `.ai-cache/aihelper/` in the target repository. The cache contains a file index, compact repo summary, symbol graph, import/dependency graph, SQL schema summary when local schema files are present, and semantic fingerprints so formatting-only edits do not look like meaningful code drift.

`aihelper cache watch` uses Watchman when available and refreshes the cache only when the current file index differs from the cached index. Use `--once` for CI/smoke checks, or run it as a local background process when working in a repo for a while.

`aihelper cache watch-all` discovers each Git repository under `~/github` as a separate project root and can add external projects such as `/opt/homebrew/var/www/his`. `cache warm` builds cache plus precompiled prompt blocks.

Use `aihelper route "<task>"` before broad reads. The router keeps `aihelper_context` as the primary coding path, recommends `context7` for upstream docs, DB schema summaries for SQL tasks, browser/profile tools only when UI verification is needed, and a model route for local vs cloud work. Generic filesystem access should be exact-path fallback rather than recursive discovery.

`patch-plan` emits proposal templates. `patch-apply` accepts standard git unified diffs, runs `git apply --check` by default, and only mutates files when `--apply` is passed. `validate-files` runs lightweight native validation for known stacks such as PHP, TypeScript, and Java.

For agent tools that support MCP, expose aihelper through:

```bash
python3 ~/github/aihelper/context_engine/mcp_server.py
```

The MCP server exposes `aihelper_context`, `aihelper_symbol_lookup`, `aihelper_cache_status`, `aihelper_route`, `aihelper_patch_plan`, `aihelper_prompt_blocks`, `aihelper_diff_summary`, and `aihelper_memory_recall`.

Docs: [docs/README.md](./docs/README.md)

In case of functional analysis template for multi-languages project (English mixed with Vietnamese), reference to HIS project with below example prompt:

`Phân tích và cập nhật luồng thu ngân ngoại trú theo mẫu đang có, bám 'docs/ai-agent/mau-phan-tich-luong.md', cập nhật 'docs/use-cases/', và giữ file chính là 'overview.md'.`
