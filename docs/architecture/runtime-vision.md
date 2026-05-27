# Runtime Vision: From AI Wrapper to Engineering Cognition Runtime

> **Strategic thesis:** Most "AI skills" are actually deterministic engineering workflows.
> The optimal architecture is not stuffing deterministic work into giant prompts —
> it is a three-tier system where deterministic execution handles certainty,
> local models handle lightweight reasoning, and frontier models are reserved
> exclusively for strategic cognition under ambiguity.

---

## 1. The Core Realization

Most "AI skills" fall into one of two categories:

| Type | Needs LLM? |
|---|---|
| Deterministic workflow | ❌ No |
| Static validation | ❌ No |
| Graph traversal | ❌ No |
| Architecture rule checking | ❌ No |
| Repetitive formatting | ❌ No |
| Dependency analysis | ❌ No |
| Retrieval / ranking | ❌ No |
| Shell orchestration | ❌ No |
| Git inspection | ❌ No |
| Code indexing | ❌ No |
| Reasoning under ambiguity | ✅ Yes |
| Creative architecture tradeoffs | ✅ Yes |
| Novel synthesis | ✅ Yes |
| Uncertain debugging hypotheses | ✅ Yes |

**Current ecosystem problem:** Most AI systems do:

```
huge prompt → giant model → perform deterministic workflow → burn tokens → repeat forever
```

This is absurdly wasteful. Workflows are stable, rules are deterministic,
the graph exists locally, and Python/SQLite/shell already exist.

**The correct split:**

> **AI should orchestrate uncertainty. Software should execute certainty.**

---

## 2. The Three-Tier Architecture

```
                  ┌─────────────────────────────┐
                  │  LAYER 1 — Deterministic     │
                  │  Python Runtime              │
                  │  ───────────────────────     │
                  │  • Workflow execution        │
                  │  • Graph traversal           │
                  │  • AST parsing               │
                  │  • Validation                │
                  │  • Retrieval (SQLite FTS5)   │
                  │  • Git analysis              │
                  │  • Dependency analysis       │
                  │  • Architecture checks       │
                  │  • Memory retrieval          │
                  │  • Orchestration             │
                  │                              │
                  │  NO AI — pure execution      │
                  └──────────────┬──────────────┘
                                 │
                                 ▼
                  ┌─────────────────────────────┐
                  │  LAYER 2 — Local Cognition   │
                  │  Ollama Small Models         │
                  │  ───────────────────────     │
                  │  • Classification            │
                  │  • Ranking                   │
                  │  • Summarization             │
                  │  • Compression               │
                  │  • Small code edits          │
                  │  • Workflow routing          │
                  │  • Low-ambiguity tasks       │
                  │                              │
                  │  Cheap + local + fast        │
                  └──────────────┬──────────────┘
                                 │
                                 ▼
                  ┌─────────────────────────────┐
                  │  LAYER 3 — Frontier Models   │
                  │  GPT / Claude / DeepSeek     │
                  │  ───────────────────────     │
                  │  • Novel architecture        │
                  │  • Complex synthesis         │
                  │  • Strategic reasoning       │
                  │  • Uncertainty resolution    │
                  │  • Tradeoff analysis         │
                  │  • Long-horizon planning     │
                  │  • Hard debugging            │
                  │                              │
                  │  ONLY when ambiguity is high │
                  └─────────────────────────────┘
```

**Routing principle:**

```python
if task_is_deterministic(task):
    run_local_python()
elif task_needs_light_reasoning(task):
    run_ollama_model()
elif task_has_high_ambiguity(task):
    escalate_to_frontier()
```

---

## 3. Why Frontier Models Still Matter

> **The goal is NOT to eliminate powerful models.**
> **It is to reposition them from workflow executors → strategic reasoning engines.**

### The Anti-Pattern (Current Ecosystem)

Most AI tooling uses GPT-5 / Claude / DeepSeek as a:
- Shell script engine
- Grep engine
- Workflow runner
- Checklist executor
- Context repeater
- Config file reader
- Dependency parser
- Log summarizer

This is a massive misuse. Frontier models burn expensive tokens on deterministic work
that Python does faster, cheaper, and more reliably.

### The Correct Pattern

Frontier models should **only** be invoked for:

- **Synthesis** — combining signals into a coherent plan
- **Architectural reasoning** — evaluating system-level tradeoffs
- **Ambiguity resolution** — deciding when multiple valid paths exist
- **Novel debugging** — hypothesizing about unknown failure modes
- **Tradeoff analysis** — weighing conflicting constraints
- **Design generation** — creating new patterns
- **Long-horizon planning** — multi-step strategy across modules

In short: **reasoning under uncertainty.**

---

## 4. The Compression Insight

> **Frontier models should consume a KNOWLEDGE GRAPH, not a raw repository.**

### ❌ Wrong way (current ecosystem)

```
GPT receives: 200 raw files
GPT does:     read → grep → understand → trace → parse → summarize → THEN think
Token cost:   massive
Quality:      degraded by noise
```

### ✅ Right way (aihelper)

```
aihelper runtime (deterministic, pre-GPT):
  ✓ Graph traversal (callers, callees, impact radius)
  ✓ Dependency analysis
  ✓ Memory retrieval (historical bugs, past decisions)
  ✓ Git inspection (recent changes, blame)
  ✓ Architecture extraction
  ✓ Risk classification
  ✓ Ambiguity scoring

THEN GPT receives:
  system_state:
    architecture:
      - modular monolith, auth service isolated
      - websocket gateway is hot path
    historical_failures:
      - websocket reconnect race (v0.6.3)
      - JWT expiry regression (v0.5.1)
    current_change:
      - auth middleware refactor
    affected_graph:
      - gateway, auth, session cache
    risks:
      - token invalidation
      - websocket auth desync
  question:
    "Best migration strategy minimizing regression risk?"

Token cost:   minimal (~2K vs 200K+)
Quality:      GPT operates as senior architect, not glorified grep
```

> **The more powerful the frontier model, the more it benefits from distilled context.**

---

## 5. Practical Example: Auth Middleware Refactor

### User asks: "Refactor auth middleware for multi-tenant support."

**Step 1 — aihelper Runtime (deterministic, no AI):**

```
✓ Trace callers/callees of auth middleware
✓ Detect auth hotspots (high-traffic paths)
✓ Retrieve historical auth bugs from memory
✓ Inspect dependency graph
✓ Analyze JWT flow end-to-end
✓ Detect websocket coupling
✓ Check regression history
✓ Classify risk level
✓ Build architecture summary
```

**Step 2 — Local Model (Ollama, lightweight):**

```
✓ Rank findings by relevance
✓ Summarize historical failure patterns
✓ Classify risk priority
```

**Step 3 — Frontier Model (strategic only):**

```
Input (compressed):
  Current architecture:  [...]
  Historical regressions: [...]
  Affected modules:       [...]
  Known constraints:      [...]
  Risk areas:             [...]

Question: "Best migration strategy minimizing regression risk?"
→ Output: strategic plan with tradeoff analysis
```

Token usage: **massively reduced**. Reasoning quality: **significantly higher**.

---

## 6. Horizontal vs Vertical Scaling

| | Horizontal (local runtime) | Vertical (frontier models) |
|---|---|---|
| **What it does** | Workflows, graph, validation, retrieval, memory, automation | Hard reasoning, synthesis, architecture, planning |
| **Cost** | Near-zero (local CPU) | Expensive (API tokens) |
| **Scaling** | Scales trivially | Scales expensively |
| **Strategy** | Maximize what runs locally | Maximize reasoning density remotely |

> **aihelper's job: absorb complexity before the frontier model is invoked.**
> The frontier model should **THINK**, not **DIG**.

---

## 7. Ecosystem Comparison

The dominant "skills" paradigm (mattpocock/skills 108k★, anthropics/skills 142k★, goose 46k★)
uses **markdown prompts** as skills. The LLM reads the markdown and executes step-by-step —
burning frontier tokens on deterministic orchestration.

**aihelper's differentiation:** Skills compile into executable Python state machines.
The LLM is called only at decision points — not for orchestration.

| Approach | Orchestration | Token Cost | Deterministic Steps |
|---|---|---|---|
| Markdown skills (mattpocock/anthropic) | LLM reads markdown, executes step by step | High (orchestration tokens) | LLM-burned |
| Goose (Block/AAIF) | Rust agent with extensions | Medium | Mixed |
| TypedAI | TypeScript workflows | Medium | Mixed |
| **aihelper v0.0.9** | **Python state machine** | **Near-zero** | **Python-executed** |

---

## 8. Where aihelper Stands Today

### ✅ Already built (aligns with this vision)

| Component | Status | Layer |
|---|---|---|
| Daemon (54 handlers, 0.3ms IPC) | ✅ Production | Layer 1 |
| Symbol graph + dependency graph (SQLite FTS5) | ✅ Production | Layer 1 |
| **Cache invalidation** (`cache_diff`, `build_*_incremental`) | ✅ v0.0.7 | Layer 1 |
| Intent-aware routing (7 intents) | ✅ Production | Layer 1 |
| Capability router (input → pipeline) | ✅ Production | Layer 1 |
| Memory engine (decisions, debugging, preferences) | ✅ Production | Layer 1 |
| Confidence scoring (5 factors) | ✅ Production | Layer 1 |
| Patch planning + structural diff | ✅ Production | Layer 1 |
| Impact graph (transitive analysis) | ✅ Production | Layer 1 |
| Ollama model stack (5 models) | ✅ Production | Layer 2 |
| CrossEncoder reranker | ✅ Production | Layer 2 |
| MCP server (24 tools, 6 editors) | ✅ Production | Layer 1 |

### 🚧 v0.0.9 Priorities

| Priority | Component | Files |
|---|---|---|
| **P0** | `WorkflowEngine` — DSL + state machine | `context_engine/workflow_engine.py` |
| **P0** | `TierRouter` — deterministic/ollama/frontier routing | `context_engine/tier_router.py` |
| **P1** | `VerificationRuntime` — reusable verify commands | `context_engine/verify.py` |
| **P1** | `ContextCompressor` — distilled cognition packages | `context_engine/compressor.py` |
| **P2** | Workflow DSL schema | `context_engine/workflows/*.yaml` |

---

## 9. The Strategic Destination

aihelper is evolving from:

> **AI helper toolkit**

into:

> **Local Engineering Cognition Runtime**

```
                     LOCAL RUNTIME
        ┌────────────────────────────────────┐
        │  • Workflows                        │
        │  • Graph                            │
        │  • Retrieval                        │
        │  • Memory                           │
        │  • Orchestration                    │
        │  • Validation                       │
        │  • Automation                       │
        │  • Git intelligence                 │
        │  • Architecture modeling            │
        └────────────────┬───────────────────┘
                         │
                  distilled cognition
                         │
                         ▼
        ┌────────────────────────────────────┐
        │         FRONTIER MODELS             │
        │  • Synthesis                        │
        │  • Planning                         │
        │  • Strategic reasoning              │
        │  • Uncertainty resolution           │
        │  • Novel design                     │
        └────────────────────────────────────┘
```

> **Skills should compile into executable workflows. Not prompts.**

---

## Related Documents

- [Model Strategy](../core/models.md) — Tiered model architecture
- [Architecture Overview](./README.md) — System design
- [Workflows](../workflows/README.md) — Common workflow patterns
- [v0.0.9 Release Notes](../releases/v0.0.9.md) — Implementation details
