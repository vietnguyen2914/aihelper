# Hacker News Launch Post

## Title

```text
I replaced 50K-token repo scans with semantic routing and a 0.3ms daemon
```

## Post

AI coding tools often feel slow and expensive for a simple reason: they send too
much context.

The common pattern is:

- scan a large repo,
- stuff tens of thousands of tokens into a prompt,
- ask a model to figure out which files matter,
- hope the edit lands in the right place.

I built aihelper to test the opposite approach: route first, prompt second.

aihelper is a local semantic runtime for coding agents. It builds a symbol graph,
dependency graph, semantic fingerprints, diagnostics context, editor context, and
patch planning metadata. Then it routes the task to a tiny context bundle instead
of asking the model to infer relevance from a giant prompt.

The basic workflow is:

```text
compiler error
-> diagnostics
-> semantic routing
-> compact context
-> patch plan
-> confidence scoring
-> safe apply
```

On my M1 Pro, the daemon hot path gets common operations into sub-millisecond to
low-millisecond territory:

- route: 0.7ms via daemon
- cache_status: 0.3ms via daemon
- context: 0.5ms via daemon
- symbol_find: 3.1ms via daemon

The main idea is not "use a smaller model." It is: give any model, local or
cloud, a smaller and more relevant view of the repo.

Repo:

https://github.com/vietnguyen2914/aihelper

I would especially like feedback on:

- semantic routing versus full-repo prompt stuffing,
- the daemon/runtime boundary,
- patch-first editing,
- whether this should stay a local CLI/MCP runtime or become a team service too.
