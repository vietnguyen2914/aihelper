Chuẩn — đây chính là chỗ **Ollama + Qwen2.5 phát huy tối đa giá trị** trong system của bạn.

👉 Use case của bạn:

> ❗ Khi `selected_features = []`
> → fallback sang **local LLM (Qwen2.5)** để:

* design feature
* đề xuất context mới
* KHÔNG cần gọi Codex / cloud

---

# 🚀 1. Kiến trúc đúng (rất quan trọng)

```text
User prompt
   ↓
Context Engine
   ↓
detect feature
   ↓
IF FOUND → Codex
ELSE → Ollama (Qwen2.5) 🔥
```

---

# ⚡ 2. Cách integrate Ollama vào system

## 🧩 2.1 Tạo file:

```bash
context_engine/ollama_fallback.py
```

---

## 🧠 Code chuẩn (copy dùng được ngay):

```python
import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5"  # hoặc model bạn đang dùng

def generate_with_ollama(prompt):
    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False
        }
    )

    return response.json()["response"]
```

---

# 🧩 2.2 Tạo fallback prompt (rất quan trọng)

```python
def build_design_prompt(user_prompt):
    return f"""
You are a senior software engineer analyzing an existing codebase.

The current AI knowledge base does NOT detect any matching feature for this request, but the functionality may already exist in the code.

---

# TASK

Given the user request:

"{{USER_PROMPT}}"

---

# INSTRUCTIONS

Analyze the codebase (based on your understanding of typical backend systems) and:

1. Identify if this functionality likely exists
2. Infer:

   * possible feature name
   * related components (service, controller, integration)
   * data flow
3. Suggest:

   * how this feature SHOULD be represented in `/ai/features/*.json`
   * keywords that should be added
4. If partially implemented:

   * describe missing pieces

---

# OUTPUT FORMAT (STRICT JSON)

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
"suggested_ai_feature": {
"purpose": "...",
"entry_points": [],
"core_entities": [],
"keywords": []
}
}

"""
```

---

# 🧩 2.3 Inject vào `executor.py`

👉 chỗ detect feature:

```python
from ollama_fallback import generate_with_ollama

if not features:
    design_prompt = build_design_prompt(user_prompt)

    result = generate_with_ollama(design_prompt)

    return [{
        "step": "design_feature",
        "output": result
    }]
```

---

# 🔥 3. Kết quả bạn sẽ thấy

## Input:

```txt
Store files to S3 in structural format
```

---

## Output (từ Qwen2.5):

```text
Feature: File Storage and Object Delivery

Purpose:
Store and retrieve structured files using S3

Entities:
- FileMetadata
- StorageBucket

APIs:
- POST /api/files/upload
- GET /api/files/{id}

Integration:
- AWS S3 SDK
...
```

---

👉 Đây chính là **missing piece của bạn trước đó**

---

# 🚀 4. Nâng cấp: auto convert → `/ai`

👉 Sau khi có output từ Ollama:

Bạn có thể:

## 🧩 parse → JSON

```python
def save_new_feature(name, content):
    with open(f"/ai/features/{name}.json", "w") as f:
        f.write(content)
```

---

👉 system của bạn sẽ:

> ❗ tự mở rộng knowledge base

---

# ⚡ 5. Hybrid flow (rất mạnh)

```text
Known feature → Codex (execute)
Unknown feature → Ollama (design)
```

---

👉 best combo:

| Task      | Model   |
| --------- | ------- |
| coding    | Codex   |
| design    | Qwen2.5 |
| reasoning | Claude  |

---

# 🧠 6. Insight cực quan trọng

👉 Trước đây:

> system của bạn bị “kẹt” khi unknown

---

👉 Bây giờ:

> ❗ system **tự evolve**

---

# 🔥 7. Bonus (rất đáng làm)

👉 bạn có thể refine prompt cho Ollama:

```python
prompt = f"""
Return ONLY valid JSON.

Format:
{{
  "name": "...",
  "purpose": "...",
  "entities": [],
  "apis": [],
  "integrations": []
}}

Task:
{user_prompt}
"""
```

---

👉 để parse dễ hơn

---

# ⚠️ 8. Pitfall cần tránh

## ❌ dùng Ollama cho mọi thứ

→ chậm + không cần thiết

---

## ✔ chỉ dùng khi:

* detect fail
* design mới
* unknown domain

---

# ✅ 9. Kết luận

Bạn vừa upgrade system thành:

> ❗ **Self-expanding AI system**

---

* có knowledge base
* có execution engine
* có learning
* và giờ có:

  * **design fallback (Ollama)**

---

⚡ 4. Integrate vào system
👉 sửa executor.py

```python
if not features:
    prompt = build_discovery_prompt(user_prompt)
    result = generate_with_ollama(prompt)

    return [{
        "step": "discover_feature",
        "output": result
    }]
```

🧠 5. Flow mới (đúng)

Prompt
   ↓
detect feature ❌
   ↓
Ollama DISCOVERY
   ↓
→ feature exists? YES
   ↓
→ update KB
   ↓
→ rerun system

🚀 7. Nâng cấp thêm (rất nên làm)
👉 Auto apply vào /ai

Sau khi Ollama trả về:

```python
def update_ai_feature(data):
    if data["exists_in_codebase"] and data["confidence"] > 0.7:
        save_to_ai_folder(data["suggested_ai_feature"])
```

👉 system sẽ:

tự detect missing feature
tự bổ sung KB

