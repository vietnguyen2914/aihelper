# Why Semantic Routing Beats Giant Prompts

AI coding agents often fail for a boring reason: they are given too much of the
wrong context.

The common workflow is expensive:

1. scan the repo,
2. stuff tens of thousands of tokens into a prompt,
3. ask a model to infer what matters,
4. hope the edit lands in the right place.

aihelper takes the opposite path. It builds a local semantic runtime that routes
the task first, then assembles only the context the agent needs.

## The Pain

Giant prompts create four problems:

- latency: every call pays for context assembly and model processing,
- cost: irrelevant files still consume tokens,
- accuracy: noisy context makes hallucinated edits easier,
- workflow friction: agents feel slow even on small tasks.

## The Runtime

aihelper keeps deterministic project knowledge close to the machine:

- symbol graph,
- dependency graph,
- semantic fingerprints,
- diagnostics,
- editor awareness,
- patch planning,
- daemon telemetry.

Instead of asking "what files should I read?" on every run, aihelper routes the
task to a small set of symbols, files, and tool pipelines.

## The Workflow

```text
compiler error
-> diagnostics
-> semantic routing
-> compact context
-> patch plan
-> confidence scoring
-> safe apply
```

This turns AI coding from a full-repo prompt problem into a local runtime problem.

## Why It Matters

The best coding assistant is not always the largest model. It is often the model
with the right context, at the right time, with a patch path that can be checked.

Semantic routing helps local models, cloud models, and editor agents all start
from a smaller and more relevant view of the codebase.

## Try It

```bash
git clone https://github.com/vietnguyen2914/aihelper.git
cd aihelper
bash scripts/bootstrap.sh
./bin/aihelper doctor
```

Then run:

```bash
aihelper cache build
aihelper route "fix bug"
```
