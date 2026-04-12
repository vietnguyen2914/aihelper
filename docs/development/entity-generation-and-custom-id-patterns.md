# Development Workflow

## Extending the helper

### Add or tune intents

- Edit [ai/system/intents.json](~/github/aihelper/ai/system/intents.json).
- A target project can override this with its own `ai/system/intents.json`.

### Improve feature detection

- Update [context_engine/detect_feature.py](~/github/aihelper/context_engine/detect_feature.py).
- Prefer adding deterministic token or metadata handling before adding new heuristics.

### Improve context loading

- Update [context_engine/load_context.py](~/github/aihelper/context_engine/load_context.py).
- Preserve compatibility with both keyed JSON indexes and raw list indexes.

### Add knowledge-base write-back

- Update [context_engine/kb_updater.py](~/github/aihelper/context_engine/kb_updater.py).
- Keep writes opt-in through `--auto-update-kb`.

## Guardrails

- Keep the helper portable across projects.
- Avoid assumptions about one backend or frontend framework.
- Prefer project-root metadata over hardcoded repository-specific rules.
- When documenting a new project, map business features first, then fill in code, data, and integration details.

