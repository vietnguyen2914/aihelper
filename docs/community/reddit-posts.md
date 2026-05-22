# Reddit Launch Drafts

These drafts should be adapted per subreddit. Lead with the outcome, not with
"look at my project."

## r/LocalLLaMA

Title:

```text
How I reduced AI coding context by 95% with local semantic routing
```

Body:

```markdown
I have been experimenting with a local-first runtime for AI coding workflows.

The problem: most coding agents still rely on giant repo scans and huge prompts.
That gets slow, expensive, and noisy fast.

The approach I tried:

- build a local symbol/dependency graph,
- route tasks by intent,
- assemble compact context,
- keep a daemon hot path for low-latency calls,
- generate patch plans instead of raw rewrites.

On my M1 Pro, common daemon calls are in the sub-ms to low-ms range, and the
workflow reduces full-repo context from ~50K tokens to around 750 tokens for
routed tasks.

Repo: https://github.com/vietnguyen2914/aihelper

Curious if others here are also building local context-routing layers around
small/medium coding models instead of just increasing model size.
```

## r/programming

Title:

```text
Semantic routing beats giant prompts for AI coding workflows
```

Body:

```markdown
I built a small local runtime that tries to solve a pain I keep hitting with AI
coding agents: they send too much context.

Instead of scanning the whole repo and sending a giant prompt, it builds local
indexes and routes each task to the relevant symbols/files first.

Workflow:

compiler error -> diagnostics -> semantic routing -> compact context -> patch
plan -> confidence scoring -> safe apply

The repo includes demo GIFs, latency/token charts, and install docs:
https://github.com/vietnguyen2914/aihelper

I would love feedback on the design tradeoff: keep this as a local CLI/MCP
runtime, or evolve it toward a shared team service?
```

## r/selfhosted

Title:

```text
Self-hosted semantic context routing for AI coding agents
```

Body:

```markdown
I built aihelper as a local-first semantic runtime for coding agents.

It keeps repo context local: symbols, dependencies, semantic fingerprints,
diagnostics, telemetry, and patch planning. Cloud models are optional; the core
routing/context path works without local LLMs too.

The goal is to avoid sending giant repo prompts when a compact routed context is
enough.

Repo: https://github.com/vietnguyen2914/aihelper
```
