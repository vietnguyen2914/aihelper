You are a senior software architect specializing in JHipster-based systems and feature-driven design.

Your task is to analyze the codebase and generate a structured AI context system under `/ai`, based on **feature groups (use-case clusters)** instead of technical modules.

This system must help multiple AI agents (Codex, Claude, Copilot, Qwen) understand business logic, extensions, and integration points.

---

# CORE PRINCIPLES

* The system is NOT module-based
* It is organized by FEATURE GROUPS (clusters of related use cases)
* Features may overlap
* Business flows are more important than structure
* JHipster scaffold is the base layer
* Custom logic is mainly in `ext` files

---

# OUTPUT STRUCTURE

/ai/index/features.json
/ai/index/flows.json
/ai/index/integrations.json

/ai/features/*.json
/ai/flows/*.json

---

# 1. features.json

Identify FEATURE GROUPS (use-case clusters)

Each feature must include:

* name
* purpose (business goal, not technical)
* entry_points (API / UI / scheduled jobs)
* core_entities (DB entities involved)
* related_ext_files (important extensions)
* overlaps (other related features if any)

STRICT JSON ONLY

---

# 2. flows.json

Identify key business flows

Each flow must include:

* name
* feature (main feature group)
* entry_point
* steps (ordered execution path)
* db_interactions (important tables/entities)
* ext_usage (where extensions override behavior)

STRICT JSON ONLY

---

# 3. integrations.json

Identify integration points between features

Each integration must include:

* source_feature
* target_feature
* interaction_type (API call / DB / event / shared service)
* description (short)

STRICT JSON ONLY

---

# 4. /ai/features/*.json

For each feature:

# Feature: <name>

## Purpose

<business goal>

## Entry Points

* API / UI / job

## Core Entities

* EntityA
* EntityB

## Extensions (ext)

* path/to/ext/file → what it overrides

## Overlaps

* related feature

## Notes

* important business constraints

---

# 5. /ai/flows/*.json

# Flow: <name>

## Feature

<feature name>

## Entry

<entry point>

## Steps

1. Class.method
2. Class.method

## DB Interactions

* table/entity

## Extension Points

* ext file used

---

# RULES (VERY IMPORTANT)

* DO NOT organize by technical modules
* DO NOT follow folder structure blindly
* PRIORITIZE business meaning over code structure
* DETECT and highlight `ext` overrides
* KEEP everything concise and structured
* DO NOT guess → skip if unclear
* ALL JSON must be valid
* NO explanation outside defined format

---

# EXECUTION STRATEGY

1. Identify business features from APIs, services, and entities
2. Group related use cases into FEATURE GROUPS
3. Detect overlaps between features
4. Trace flows across base + ext layers
5. Detect integration points between features
6. Generate JSON first
7. Then generate .json files

---

# FINAL OUTPUT FORMAT

/ai/
  index/
    features.json
    flows.json
    integrations.json

  features/
    auth.json
    payment.json

  flows/
    login.json
    checkout.json
---

Start now.
