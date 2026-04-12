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
```

The default output format is structured Markdown. Use `--json` or `-json` when you need machine-readable output.

Docs: [docs/README.md](~/github/aihelper/docs/README.md)
