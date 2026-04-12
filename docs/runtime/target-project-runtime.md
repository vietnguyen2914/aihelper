# Target Project Runtime Guide

## Fast path

From the repo you want to inspect:

```bash
/Users/vietnguyen/github/aihelper/bin/aihelper "trace upload flow"
```

That command automatically points the helper at the current directory.

## Examples

### Mindforme

```bash
cd /Users/vietnguyen/github/mindforme
/Users/vietnguyen/github/aihelper/bin/aihelper "trace S3 upload and blur flow"
```

### SignServer

```bash
cd /Users/vietnguyen/github/signserver
/Users/vietnguyen/github/aihelper/bin/aihelper "fix signing timeout"
```

### LMS

```bash
cd /Users/vietnguyen/github/lms
/Users/vietnguyen/github/aihelper/bin/aihelper "analyze course enrollment flow"
```

## When to use direct `main.py`

```bash
python3 /Users/vietnguyen/github/aihelper/context_engine/main.py analyze "fix signing timeout" --project-root "$PWD"
```

Use this when you want explicit flags like:

- `--format prompt`
- `--max-context-chars 8000`
- `--auto-update-kb`

