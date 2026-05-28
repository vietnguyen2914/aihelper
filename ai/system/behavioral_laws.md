# Behavioral Laws — MANDATORY Execution Protocol

> **Canonical source document.** This file is the single source of truth for AI agent behavioral laws.
> Init-config copies this to all editor configs. Do not edit individual editor configs directly;
> edit this file and re-run init-config.

These are NOT suggestions. These are execution laws for all AI agents processing this repository.

---

## 1. REQUIRED WORKFLOW

Before ANY file reads or terminal commands, execute these three steps in order:

### Step 1: Route
```
aihelper_route "<task>"
```
Classify the task and get tool recommendations. This determines whether the task is deterministic,
local-model-routable, or requires a frontier model.

### Step 2: Context
```
aihelper_context --max-context-chars 3000
```
Get a compact project overview from the knowledge graph cache. Avoids scanning the filesystem
and reduces token usage by 60-80%.

### Step 3: Symbol Lookup
```
aihelper_symbol_lookup <target>
```
Find relevant symbols semantically using the SQLite knowledge graph. Do NOT use grep for this.

---

## 2. FORBIDDEN OPERATIONS

| ❌ Forbidden | ✅ Use Instead |
|---|---|
| `grep -r` / `find .` / `rg -r` for code exploration | `aihelper_symbol_lookup` |
| Recursive `read_file` on multiple files | `aihelper_explore` |
| Manual dependency tracing | `aihelper_callers` / `aihelper_callees` |
| Reading full files to understand imports | `aihelper_symbol_lookup` (includes import context) |
| Sending raw file dumps to cloud models | `aihelper_context` (compressed cognition package) |

---

## 3. TIER ENFORCEMENT

Tasks are automatically classified by `aihelper_tier_route` into three tiers:

### Tier 1 — Deterministic (local, no AI needed)
- Simple string/regex operations
- File moves, renames, copies
- Config file formatting
- Trivial git operations

### Tier 2 — Local Model (Ollama, MUST use)
- DTO generation
- CRUD boilerplate
- Repository interfaces
- Simple mapper/converter code
- Test stubs and fixtures
- Documentation generation from code

### Tier 3 — Frontier Model (cloud, permission-gated)
- Architecture decisions and refactoring
- Security-sensitive changes
- Complex business logic
- Multi-file orchestration
- Debugging non-trivial failures

**Rule:** If `aihelper_tier_route` returns Tier 2, you MUST use a local Ollama model.
Only Tier 3 may use frontier (cloud) models.

---

## 4. SUBAGENT EXECUTION

When spawning subagents:

1. Subagents receive **bounded cognition packages** (`aihelper_compress_context`), not raw prompts.
2. Subagents MUST stay within their assigned **graph boundary** (defined by `aihelper_impact`).
3. Subagents MUST NOT scan repos freely — no recursive file reads.
4. Subagents report back structured results, not raw output.

---

## 5. VERIFICATION

Before declaring a task complete:

### After structural changes (architecture, refactoring, renames):
```
aihelper_verify architecture
```

### After code changes (any file modification):
```
aihelper_verify regression-risk --target <symbol>
```

### After dependency changes:
```
aihelper_verify dependency-health
```

### After auth/permission changes:
```
aihelper_verify auth-safety
```

---

## 6. TOKEN BUDGET

| Operation | Max Context Chars | Max Tokens |
|---|---|---|
| Quick lookup / autocomplete | 500 | ~125 |
| Single-file change | 2,000 | ~500 |
| Multi-file change | 4,000 | ~1,000 |
| Architecture / design | 8,000 | ~2,000 |
| Debugging | 5,000 | ~1,250 |

---

## 7. ENFORCEMENT

- These laws are injected into every AI agent prompt via editor-specific config files.
- Violations (e.g., grep instead of symbol_lookup) should be flagged immediately.
- The `aihelper` runtime hard-enforces token budgets and tool restrictions.
- To update these laws: edit this file, then run `aihelper init-config` to propagate.
