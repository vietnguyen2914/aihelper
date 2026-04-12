# Workflows

## Purpose

Workflow docs describe the ordered execution path across controllers, services, jobs, integrations, and persistence.

## Required Format

```mermaid
flowchart LR
  A["Entry Point"] --> B["Step 1"]
  B --> C["Step 2"]
  C --> D["Persistence"]
  D --> E["External Call"]
```

## What To Include

- The business flow name
- The owning feature
- The entry point
- Ordered steps
- Database interactions
- Override points

