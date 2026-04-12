You are a senior software architect and automation engineer.

Your task is to build an "AI Context System" that supports:

1. Auto-updating `/ai/*.json` when code changes
2. Context selection and ranking (Phase 3, lightweight)
3. Multi-project aggregation (multiple microservices)

The system must be lightweight, file-based, and NOT use vector databases or heavy RAG.

---

# PROJECT ASSUMPTION

There may be multiple microservices like:

/service-auth/
/service-payment/
/service-order/

Each service has its own `/ai/` folder.

---

# GOAL

Create a system that:

* Keeps `/ai/*.json` always up-to-date
* Selects the most relevant context for a given prompt
* Aggregates context across services when needed

---

# OUTPUT STRUCTURE

/context_system/
watcher.py
updater.py
ranker.py
aggregator.py
main.py

---

# 1. watcher.py

* Watch for file changes in project (simple polling is OK)
* Detect changes in:

  * src/
  * ext/
* Trigger updater

---

# 2. updater.py

* Re-generate affected parts of `/ai/*.json`

Rules:

* If file changed → find related feature

* Update only:

  * that feature JSON
  * related flows

* DO NOT regenerate everything

Implement:

* simple file-to-feature mapping (by name or path)
* safe overwrite

---

# 3. ranker.py (Phase 3 core)

Input:

* user_prompt
* list of candidate features

Output:

* ranked list (top 1–3 features)

Implement:

* keyword scoring
* optional heuristic:

  * match entry_points
  * match entities
* simple scoring function

---

# 4. aggregator.py

* Load context from multiple services

Input:

* list of services
* list of features

Output:

* merged JSON context

Rules:

* keep separation by service
* avoid duplication

---

# 5. main.py

CLI tool:

Usage:
python main.py "fix login timeout across services"

Steps:

1. detect candidate features
2. rank them
3. detect involved services
4. aggregate context
5. build final prompt

---

# PROMPT TEMPLATE

Use:

You are working on a distributed JHipster-based system.

Context: <SERVICE-A CONTEXT> <SERVICE-B CONTEXT>

Rules:

* Respect feature boundaries
* Do not break cross-service integration
* Follow ext overrides

Task: <USER PROMPT>

---

# REQUIREMENTS

* Use Python only (standard library)
* Keep everything simple and readable
* Add comments
* Handle missing files safely
* Limit context size (truncate if too large)

---

# OPTIONAL

* cache results
* log updates

---

# IMPORTANT RULES

* DO NOT use embeddings
* DO NOT use external services
* DO NOT over-engineer
* MUST work for multiple independent projects

---

# OUTPUT FORMAT

Provide FULL working code for all files.

Do NOT explain anything.
