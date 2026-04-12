You are a senior software engineer.

Your task is to build a lightweight "AI Context Engine" for a codebase that already contains structured JSON files under `/ai`.

The system must dynamically select and inject relevant context for AI agents (Codex, Claude, Copilot, Qwen) based on user prompts.

---

# GOAL

Create a minimal but production-ready context selection system.

It must:

* Detect relevant feature(s) from a user prompt
* Load corresponding JSON context files
* Inject them into a final prompt template
* Output the final prompt ready to send to any AI

---

# INPUT STRUCTURE

The project already contains:

/ai/index/features.json
/ai/index/flows.json
/ai/index/integrations.json

/ai/features/*.json
/ai/flows/*.json

---

# OUTPUT FILES TO CREATE

/context_engine/
detect_feature.py
load_context.py
build_prompt.py
main.py

---

# REQUIREMENTS

## 1. detect_feature.py

* Input: user_prompt (string)
* Output: list of feature names

Implement TWO methods:

A. simple keyword-based matching (fast, fallback)
B. optional AI-based detection (function stub, not implemented)

---

## 2. load_context.py

* Input: list of features

* Load:

  * /ai/features/<feature>.json
  * related flows from flows.json

* Return combined JSON context as string

---

## 3. build_prompt.py

Create a function:

build_prompt(user_prompt, context)

Output format:

You are working on a JHipster-based system.

Context: <JSON CONTEXT>

Rules:

* Follow existing flows
* Respect ext overrides
* Do not break integrations

Task: <USER PROMPT>

---

## 4. main.py

* CLI tool

Usage:
python main.py "fix login timeout bug"

Steps:

1. detect features
2. load context
3. build final prompt
4. print output

---

# RULES

* Keep code simple and readable
* No external dependencies except standard Python
* Handle missing files safely
* Do NOT over-engineer
* Add comments explaining logic
* Ensure it works for multiple projects

---

# OPTIONAL (nice to have)

* limit context size (truncate if too large)
* log detected features

---

# OUTPUT FORMAT

Provide FULL working code for all files.

Do NOT explain anything.
