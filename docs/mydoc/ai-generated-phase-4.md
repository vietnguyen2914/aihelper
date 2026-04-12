OK — mình gom toàn bộ đoạn từ **Ollama fallback → discovery → self-healing KB → integrate vào system hiện tại** thành **1 prompt duy nhất, production-grade** cho bạn.

👉 Mục tiêu:

* Codex generate **toàn bộ code**
* plug thẳng vào system hiện tại của bạn
* không phải chắp vá nữa

---

# 🚀 PROMPT CHUẨN: OLLAMA DISCOVERY + SELF-HEALING KB

👉 Paste thẳng vào Codex / GPT-4

---

You are a senior software architect.

Your task is to extend an existing Python-based AI Context Engine with a DISCOVERY + SELF-HEALING system using a local Ollama model (Qwen2.5).

---

# GOAL

When no feature is detected from `/ai`:

* DO NOT assume the feature is new
* Instead:
  → analyze and DISCOVER the feature from the codebase
  → generate structured knowledge
  → optionally update `/ai` knowledge base

---

# SYSTEM CONTEXT

The project already has:

/ai/index/features.json
/ai/index/flows.json
/ai/index/integrations.json

/ai/features/*.json
/ai/flows/*.json

/context_engine/
main.py
executor.py
detect_feature.py
load_context.py

---

# WHAT YOU MUST BUILD

## 1. Ollama integration

Create:

/context_engine/ollama_fallback.py

* call local Ollama API:
  [http://localhost:11434/api/generate](http://localhost:11434/api/generate)
* model: qwen2.5
* function:
  generate_with_ollama(prompt: str) -> str

---

## 2. Discovery prompt builder

Create:

build_discovery_prompt(user_prompt)

---

### Prompt must

* assume feature MAY already exist
* analyze codebase logically
* NOT invent random systems

---

### Required output (STRICT JSON)

{
"feature_name": "...",
"exists_in_codebase": true/false,
"confidence": 0.0-1.0,
"keywords": [],
"components": {
"services": [],
"controllers": [],
"entities": [],
"integrations": []
},
"flows": [
{
"name": "...",
"steps": []
}
],
"suggested_ai_feature": {
"purpose": "...",
"entry_points": [],
"core_entities": [],
"keywords": [],
"notes": []
}
}

---

## 3. Executor integration (CRITICAL)

Modify:

/context_engine/executor.py

---

### Logic

IF detect_features(...) returns empty:

1. call build_discovery_prompt
2. call generate_with_ollama
3. parse JSON result
4. return:

[
{
"step": "discover_feature",
"output": parsed_json
}
]

---

## 4. Auto KB update (OPTIONAL BUT IMPORTANT)

Create:

/context_engine/kb_updater.py

---

Function:

update_ai_kb(discovery_result)

---

Rules:

* only update if:
  exists_in_codebase == true
  confidence >= 0.7

* create:
  /ai/features/<feature>.json
  /ai/flows/<flow>.json

* DO NOT overwrite existing features

* normalize file names (kebab-case)

---

## 5. Keyword enrichment

Ensure:

* extracted keywords are:
  lowercase
  deduplicated
  <= 15 items

---

## 6. Safety rules

* DO NOT trust Ollama blindly
* validate JSON before writing
* fallback safely if parsing fails

---

## 7. Performance

* do NOT call Ollama if feature already exists
* only trigger fallback when needed

---

# OUTPUT STRUCTURE

/context_engine/
ollama_fallback.py
kb_updater.py
(updated executor.py)

---

# RULES

* Python standard library only (except requests)
* clean, readable code
* no over-engineering
* production-ready

---

# FINAL GOAL

Enable this flow:

Input:
"Store files to S3 in structural format"

System:
→ detect fails
→ Ollama discovers feature
→ system returns structured feature
→ optionally updates /ai

---

# OUTPUT

Provide FULL working code.

Do NOT explain anything.

---

# 🧠 Cách bạn dùng sau khi generate

## Bình thường (đã có feature)

```bash
python3 -m context_engine.executor "fix signing timeout"
```

---

## Case missing feature

```bash
python3 -m context_engine.executor "Store files to S3 in structural format"
```

---

👉 Output:

* structured feature
* flow
* keyword
* ready để add vào `/ai`

---

# 🔥 Insight cuối cùng

👉 Prompt này chính là:

> ❗ bridge giữa **AI reasoning (Ollama)**
> và **AI execution system của bạn**

---

👉 Sau bước này system của bạn:

* không còn bị kẹt khi unknown
* tự mở rộng knowledge
* vẫn deterministic

---

# 👉 Nếu muốn step tiếp theo

Mình có thể giúp bạn:

✔ auto validate feature trước khi save
✔ hoặc multi-model voting (Claude + Qwen)

---

Chỉ cần nói: **“feature validation layer”** 👍
