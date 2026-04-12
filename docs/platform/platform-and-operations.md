# Platform And Operations

## What the helper expects from a target project

- A project root with code and/or modules that can be inspected.
- An `ai/` directory with `index`, `features`, and `flows` content.
- Optional `ai/system` files for intent hints and learned keywords.

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
- Designed to work with PHP, Java, or mixed legacy projects as long as the `ai/` folder follows the same shape.
