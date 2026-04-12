# Use Case Map

## Primary use cases

- Analyze a prompt against the current repo's indexed AI knowledge.
- Generate a prompt-ready context block for Codex or another assistant.
- Trace the owning business feature and flow before touching code.
- Reuse one helper across `mindforme`, `signserver`, `lms`, or another repo that follows the same `ai/` layout.
- Optionally record feedback or persist newly discovered features.

## Common entrypoints

- One-line launcher: `/Users/vietnguyen/github/aihelper/bin/aihelper "your prompt"`
- Direct engine call: `python3 /Users/vietnguyen/github/aihelper/context_engine/main.py analyze "your prompt" --project-root "$PWD"`
- Prompt-only mode: `... --format prompt`

