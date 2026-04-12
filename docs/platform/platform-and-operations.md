# Platform And Operations

## What the helper expects from a target project

- An `ai/` directory in the project root or in one of its direct child services.
- `ai/index/features.json`
- Optional:
  - `ai/index/flows.json`
  - `ai/index/integrations.json`
  - `ai/features/*.json`
  - `ai/system/intents.json`
  - `ai/system/learned_keywords.json`

## Output shape

The default output is JSON with:

- `detected_intent`
- `detected_features`
- `selected_context`
- `final_prompt`
- `rewritten_prompt`
- `execution_steps`
- `feedback_summary`

## Operational choices

- No external dependencies.
- Python stdlib only.
- Fast filesystem and JSON inspection.
- Best effort discovery fallback when indexed features are missing or too weak.

