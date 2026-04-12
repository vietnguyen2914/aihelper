# Target Project Runtime Guide

## Fast path

From the repo you want to inspect:

```bash
~/github/aihelper/bin/aihelper "trace upload flow"
```

That command automatically points the helper at the current directory.

## Example Targets

### HIS PHP project

```bash
cd /opt/homebrew/var/www/his
~/github/aihelper/bin/aihelper "trace outpatient intake flow"
```

The launcher uses the current directory as the target project, so the helper reads `/opt/homebrew/var/www/his/ai/...` when you run it from that project root.

## When to use direct `main.py`

```bash
python3 ~/github/aihelper/context_engine/main.py analyze "trace outpatient intake flow" --project-root "$PWD"
```

Use this when you want explicit flags like:

- `--format prompt`
- `--max-context-chars 8000`
- `--auto-update-kb`
