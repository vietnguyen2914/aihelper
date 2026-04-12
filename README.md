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

Docs: [docs/README.md](./docs/README.md)

In case of functional analysis template for multi-languages project (English mixed with Vietnamese), reference to HIS project with below example prompt:

`Phân tích và cập nhật luồng thu ngân ngoại trú theo mẫu đang có, bám 'docs/ai-agent/mau-phan-tich-luong.md', cập nhật 'docs/use-cases/', và giữ file chính là 'overview.md'.`
