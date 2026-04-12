# Project Knowledge Base

## Purpose

This KB is the kickoff document for a new project. It explains how to discover the codebase, document the business functions, generate the AI indexes, and keep the docs aligned with the implementation.

## Kickoff Workflow

1. Discover the project KB from code, docs, routes, entities, services, jobs, and overrides.
2. Build the project function mindmap in Mermaid and write it to docs.
3. Expand each top-level function into detailed use cases.
4. Add technical, data, relationships, service-call, integration, and admin notes for each use case.
5. Build the function/use-case vs. system architecture matrix in Markdown.
6. Generate the AI indexes under `/ai`.
7. Update the docs nav so every page links to the next level down.

## Fast Start

### One-line launcher

```bash
~/github/aihelper/bin/aihelper "build project KB"
```

### Explicit target root

```bash
AIHELPER_TARGET_ROOT=/opt/homebrew/var/www/his ~/github/aihelper/bin/aihelper "build project KB"
```

### Prompt-only output

```bash
~/github/aihelper/bin/aihelper analyze "trace patient intake flow" --format prompt
```

## Documentation Order

```text
docs/
  README.md
  PROJECT-KNOWLEDGE-BASE.md
  architecture/
    function-mindmap.md
    use-case-system-matrix.md
    entity-crud-matrix.md
  core/
    README.md
  features/
    README.md
  use-cases/
    README.md
  workflows/
    README.md
  integrations/
    README.md
  ai-agent/
    README.md
  platform/
    platform-and-operations.md
  runtime/
    target-project-runtime.md
  development/
    entity-generation-and-custom-id-patterns.md
```

## Example Project Mapping

For a legacy PHP project like `/opt/homebrew/var/www/his`, map the code into business groups instead of folder names:

| Project Area | Likely Docs Home |
|---|---|
| `modules/outpatient_core`, `modules/inpatient_core`, `modules/bed_management` | `use-cases/` and `workflows/` |
| `modules/billing`, `modules/insurance_hack` | `features/` and `integrations/` |
| `modules/dept_*`, `modules/general_emr`, `modules/hsba` | `use-cases/` and `architecture/` |
| `local/`, `server/`, `tool/`, `installer/` | `core/`, `platform/`, `development/` |
| `docs/`, `assets/`, `tests/` | documentation, reference material, and verification notes |
| `ai/` | AI feature, flow, and integration indexes |

## Output Expectations

- Keep the mindmap readable and business-first.
- Keep the use-case docs concise but complete.
- Always include flows in Mermaid where a process spans multiple steps.
- Always link the docs together so a reader can move from overview to detail to matrix to AI index.

