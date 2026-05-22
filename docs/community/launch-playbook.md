# Launch Playbook

This playbook keeps launch content focused on what aihelper does for developers:
smaller context, lower latency, and safer patches.

## Core Message

```text
Stop sending giant prompts.
```

aihelper is an AI-native semantic runtime for low-latency coding workflows.
It replaces giant repo scans with semantic routing, compact context, daemon IPC,
and patch-first editing.

## Hacker News Draft

Title options:

- I replaced 50K-token repo scans with semantic routing and a 0.3ms daemon
- AI-native runtime for coding agents: semantic routing instead of giant prompts

Post outline:

1. The pain: full repo scans, slow agents, expensive prompts, hallucinated rewrites.
2. The approach: symbol/dependency graph, semantic routing, compact context.
3. The runtime: daemonized hot path with sub-millisecond IPC.
4. The workflow: diagnostics -> routing -> context -> patch plan -> confidence -> safe apply.
5. The proof: GIFs, latency chart, token reduction chart, and install command.

## Reddit Draft Angles

| Community | Angle |
|---|---|
| r/LocalLLaMA | Local-first semantic runtime for coding agents |
| r/programming | Reducing AI coding context by 95% |
| r/selfhosted | Self-hosted AI context routing for development |
| r/ZedEditor | Zed MCP workflow with semantic routing |
| r/ClaudeAI | Smaller context for agentic coding workflows |

Avoid "look at my project." Lead with the result:

```text
How I reduced AI coding context by 95%
```

## Weekly Content Cadence

| Week | Post |
|---|---|
| 1 | Semantic routing benchmark |
| 2 | Daemon latency demo |
| 3 | Diagnostics -> patch workflow |
| 4 | OCR -> structured extraction |
| 5 | Local-first runtime stack |
| 6 | AI orchestration architecture |

## Release Checklist

- README visual proof is current.
- `CHANGELOG.md` has a release section.
- GitHub release notes include GIFs and benchmark charts.
- Discussions are enabled and seeded.
- Issues are triaged within 24-48 hours during launch week.
