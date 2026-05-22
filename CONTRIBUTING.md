# Contributing to aihelper

Thanks for helping improve aihelper. The project is focused on one practical goal:
make AI coding workflows faster and smaller by routing to the right context instead
of sending giant prompts.

## Good First Contributions

- Improve demo workflows, screenshots, and benchmark visuals.
- Add focused examples for real coding tasks.
- Tighten install and troubleshooting docs.
- Report editor integration issues with reproducible steps.
- Add tests or fixtures for routing, diagnostics, and patch planning.

## Before You Open a PR

1. Run diagnostics:

```bash
./bin/aihelper doctor
```

2. Verify the command or workflow you changed:

```bash
./bin/aihelper cache status --project-root .
./bin/aihelper route "fix bug" --project-root .
```

3. Keep changes focused. Avoid mixing docs, runtime behavior, and generated assets
   unless the change genuinely needs all three.

## PR Guidelines

- Explain the user workflow the change improves.
- Include before/after output for CLI behavior changes.
- Include screenshots or GIFs for README/demo changes.
- Update docs when commands, flags, or setup steps change.
- Do not include secrets, private paths, or local machine credentials.

## Issue Guidelines

For bugs, include:

- OS and Python version.
- `./bin/aihelper doctor` output.
- Daemon status and relevant logs from `~/.aihelper/daemon.log`.
- Minimal command that reproduces the issue.

For feature requests, describe the workflow pain first. The most useful requests
are framed as "I want aihelper to help me do X with less context, latency, or
manual routing."

## Development Notes

aihelper is designed to be local-first, editor-portable, and model-optional.
Prefer deterministic routing, cache, and patch validation paths before adding
new model dependencies.
