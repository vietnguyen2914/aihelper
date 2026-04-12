# Architecture Overview

## Primary goal

Build one portable helper that keeps the strongest behavior from the three source projects:

- `mindforme`: richer prompt rewriting, flow-aware planning, cross-project thinking
- `signserver`: documentation discipline, deterministic operating model, adaptive keyword ideas
- `lms`: root-aware service discovery, structured JSON output, cleaner orchestration

## Core flow

1. Resolve the target project root from the current shell directory or `--project-root`.
2. Discover every service inside that root that contains `ai/index/features.json`.
3. Detect intent and rank the most relevant features using feature metadata plus learned keywords.
4. Load related feature payloads, flows, integrations, and likely override paths.
5. Produce:
   - `selected_context`
   - `rewritten_prompt`
   - `final_prompt`
   - `execution_steps`
6. Fall back to lightweight codebase discovery when indexed features do not match.

## Why this design is better than any single source helper

- It is portable like `lms`, but not tied to one repo layout.
- It keeps richer planning than `signserver`.
- It handles more index shapes than `mindforme`.
- It gives both machine-friendly JSON and prompt-ready output without maintaining multiple entrypoints.

