Câu này rất quan trọng — nếu không xử lý tốt thì **toàn bộ system sẽ fail ngầm** khi dùng thực tế.

Bạn đang gặp đúng bài toán:

> ❗ **Multilingual + mixed-language prompts (EN + VI + code terms)**

---

# 🧠 1. Vấn đề thực sự

Hiện tại system của bạn:

* keywords = tiếng Anh (từ codebase)
* prompt = có thể:

  * tiếng Việt
  * tiếng Anh
  * mix

👉 ví dụ:

```txt
lỗi timeout khi upload file lên S3
```

---

👉 detect_feature hiện tại:

```text
"timeout", "upload", "s3"
```

→ match được 1 phần
→ miss phần "lỗi", "file", "lên"

---

# 🚀 2. Cách giải đúng (KHÔNG dùng ML)

👉 bạn cần:

> ❗ **Keyword normalization layer (multilingual mapping)**

---

# ⚙️ 3. Kiến trúc chuẩn

```text
User prompt
   ↓
Normalize (VI → EN)
   ↓
Detect feature (EN keywords)
```

---

# 🔥 4. PROMPT: MULTILINGUAL KEYWORD SYSTEM

👉 Paste vào Codex

---

You are a senior software engineer.

Your task is to extend the AI Context Engine to support MULTILINGUAL (Vietnamese + English + mixed) prompts.

---

# GOAL

* Normalize user prompts into a unified keyword space
* Allow detection to work regardless of language

---

# OUTPUT STRUCTURE

/context_engine/
multilingual.py
synonyms.json

---

# 1. synonyms.json

Create a mapping:

{
"timeout": ["timeout", "hết hạn", "quá thời gian"],
"upload": ["upload", "tải lên", "up file"],
"file": ["file", "tệp", "tập tin"],
"error": ["error", "lỗi"],
"storage": ["storage", "lưu trữ"],
"s3": ["s3", "bucket", "aws"]
}

---

# 2. multilingual.py

Implement:

## normalize_prompt(prompt)

Steps:

1. lowercase
2. replace Vietnamese words with English equivalents using synonyms.json
3. remove accents (optional)
4. return normalized string

---

Example:

Input:
"lỗi upload file lên s3"

Output:
"error upload file s3"

---

## expand_keywords(feature_keywords)

Given:
["upload", "file"]

Return:
["upload", "file", "tải lên", "tệp", "tập tin"]

---

# 3. INTEGRATION

Modify detect_feature:

* normalize user prompt first
* match against:

  * original keywords
  * expanded keywords

---

# 4. RULES

* keep mapping simple
* no ML, no translation API
* deterministic
* fast

---

# 5. OPTIONAL

* support removing Vietnamese accents
* support phrase mapping

---

# OUTPUT

Provide FULL working Python code.

Do NOT explain anything.

---

# ⚡ 5. Sau khi build xong

## Input:

```txt
lỗi upload file lên s3
```

---

## System sees:

```txt
error upload file s3
```

---

👉 detect chuẩn:

```json
feature: File Storage and Object Delivery
```

---

# 🔥 6. Nâng cấp cực mạnh (nên làm thêm)

👉 Khi generate keywords (Phase 1):

## Thay vì:

```json
"keywords": ["upload", "file"]
```

---

## 👉 lưu luôn:

```json
"keywords": ["upload", "file"],
"keywords_vi": ["tải lên", "tệp", "tập tin"]
```

---

👉 detect sẽ mạnh hơn nữa

---

# 🧠 7. Insight cực quan trọng

👉 Bạn không cần:

* translate prompt
* dùng LLM

---

👉 bạn chỉ cần:

> ❗ **normalize keyword space**

---

# 🚀 8. Best practice cho bạn

## Rule:

* feature keywords = English (canonical)
* synonyms = multilingual
* prompt → normalize → match

---

# ⚠️ 9. Pitfall cần tránh

## ❌ Dùng Google Translate API

→ chậm + không ổn định

---

## ❌ Mapping quá lớn

→ noise

---

👉 giữ:

* 5–20 từ / keyword là đủ

---

# ✅ 10. Kết luận

Bạn cần thêm:

✔ multilingual normalize
✔ synonym mapping
✔ keyword expansion

---

👉 Sau bước này system của bạn:

> ❗ hoạt động tốt với:

* English
* Vietnamese
* mixed prompt

---

# 👉 Nếu muốn bước tiếp theo

Mình có thể giúp bạn:

✔ auto learn Vietnamese keywords từ prompt
✔ hoặc domain-specific dictionary (y tế, tài chính...)

---

Chỉ cần nói: **“domain dictionary”** 👍

---------------------------------------------------------------------

Chuẩn — đây là bước nâng cấp rất “thực chiến” cho case của bạn (VI + EN + domain y tế).

Mình sẽ đưa bạn **1 prompt duy nhất** để Codex build luôn:

* auto learn Vietnamese keywords từ prompt (adaptive multilingual)
* domain-specific dictionary (y tế)
* integrate thẳng vào detect_feature hiện tại

---

# 🚀 PROMPT: ADAPTIVE MULTILINGUAL + MEDICAL DOMAIN DICTIONARY

👉 Paste vào Codex / GPT-4

---

You are a senior software engineer.

Your task is to extend the AI Context Engine with:

1. Adaptive multilingual keyword learning (Vietnamese + English)
2. Domain-specific dictionary for healthcare (medical domain)

The system must remain lightweight, deterministic, and file-based.

---

# GOAL

* Learn Vietnamese keywords from user prompts automatically
* Map them to existing English keywords
* Improve feature detection over time
* Add domain knowledge for healthcare systems

---

# OUTPUT STRUCTURE

/context_engine/
multilingual_adaptive.py
vi_keyword_store.json
medical_dictionary.json

---

# 1. medical_dictionary.json

Create a predefined healthcare dictionary:

{
"patient": ["bệnh nhân"],
"doctor": ["bác sĩ"],
"hospital": ["bệnh viện"],
"medical_record": ["hồ sơ bệnh án", "bệnh án"],
"prescription": ["đơn thuốc"],
"appointment": ["lịch hẹn", "cuộc hẹn"],
"insurance": ["bảo hiểm", "bhyt"],
"diagnosis": ["chẩn đoán"],
"treatment": ["điều trị"],
"test": ["xét nghiệm"],
"result": ["kết quả"],
"image": ["ảnh", "hình"],
"upload": ["tải lên"],
"file": ["tệp", "tập tin"],
"timeout": ["hết hạn", "quá thời gian"],
"error": ["lỗi"]
}

---

# 2. vi_keyword_store.json

Structure:

{
"mapping": {
"tải": "upload",
"lỗi": "error"
},
"count": {
"tải": 3,
"lỗi": 5
}
}

---

# 3. multilingual_adaptive.py

Implement:

## A. normalize_prompt(prompt)

* lowercase
* split words
* replace Vietnamese words using:

  1. medical_dictionary.json
  2. vi_keyword_store.json
* return normalized prompt

---

## B. learn_vi_keywords(prompt, detected_features)

* extract Vietnamese words
* map them to detected feature keywords
* increase count
* if count >= threshold (e.g. 3):

  * add to mapping

---

## C. merge_dictionaries()

Combine:

* base synonyms
* medical dictionary
* learned keywords

---

## D. detect Vietnamese words

Simple rule:

* words with accents OR not in English dictionary
  → treat as Vietnamese

---

# 4. INTEGRATION

Modify detect_feature:

1. normalize prompt first
2. detect features
3. AFTER detection:
   → call learn_vi_keywords()

---

# 5. RULES

* DO NOT overwrite base keywords
* learned keywords must be stored separately
* limit learned mapping size (max 100 entries)
* avoid noise:

  * ignore numbers
  * ignore words < 2 chars

---

# 6. OPTIONAL

* remove Vietnamese accents before matching
* support phrase mapping (e.g. "bệnh án")

---

# 7. EXAMPLE

Input:
"lỗi upload ảnh bệnh nhân"

After normalization:
"error upload image patient"

---

# 8. OUTPUT

Provide FULL working Python code.

Do NOT explain anything.

---

# ⚡ Sau khi build xong

## Lần đầu

```txt id="1y6azf"
lỗi upload ảnh bệnh nhân
```

→ system hiểu 50–70%

---

## Sau vài lần

```json
{
  "mapping": {
    "ảnh": "image",
    "bệnh": "patient"
  }
}
```

---

→ lần sau detect gần như perfect

---

# 🔥 Insight cực quan trọng

👉 Bạn vừa build:

> ❗ “Domain-aware + language-aware AI system”

---

* hiểu tiếng Việt
* hiểu domain y tế
* tự học theo usage

---

# 🚀 Level hệ thống của bạn bây giờ

✔ Multilingual
✔ Adaptive
✔ Domain-aware (medical)
✔ Cross-project
✔ Self-healing KB

---

# ⚠️ Pitfall cần tránh

## ❌ học sai mapping

Ví dụ:

```json
"bệnh": "error"
```

---

## ✅ Fix

* chỉ learn khi feature detect CONFIDENT (>0.7)
* limit số lần học

---

# 👉 Nếu bạn muốn bước tiếp theo (rất mạnh)

Mình có thể giúp bạn:

✔ **domain expansion (tài chính, bảo hiểm, HIS)**
✔ hoặc **context-aware intent (medical-specific intent)**

---

Chỉ cần nói: **“expand domain HIS”** 👍

------------------------------------------------------------------------

Ngắn gọn: **Có — và nên làm.**
Nhưng dùng **model nhỏ chỉ cho đúng việc “ngôn ngữ” (normalize, map VI↔EN, intent nhẹ)**, không thay thế model lớn cho design/analysis.

---

# 🧠 1. Chọn model local phù hợp

## 🎯 Mục tiêu của bạn

* normalize VI ↔ EN
* map keyword / synonym
* intent detection nhẹ
* chạy cực nhanh (<50–100ms)

---

## ✅ Gợi ý model (Ollama)

### ⚡ Rất nhẹ + nhanh

* Qwen2.5 1.5B

👉 dùng cho:

* normalize prompt
* keyword extraction
* intent classification

---

### ⚖️ Cân bằng (khuyên dùng)

* Mistral 3
* Qwen2.5 3B

👉 dùng cho:

* fallback discovery
* feature inference

---

### 🧱 Model lớn (giữ lại)

* Qwen2.5 7B (bạn đang dùng)

👉 chỉ dùng khi:

* discovery phức tạp
* design feature

---

# 🚀 2. Kiến trúc chuẩn (multi-model local)

```text
Prompt
   ↓
Intent + normalize → (tiny model ⚡)
   ↓
Detect feature → (rule-based + keyword)
   ↓
IF fail:
   ↓
Discovery → (medium model)
```

---

# ⚡ 3. Cách integrate (rất đơn giản)

## 🧩 sửa `ollama_fallback.py`

```python
import requests

OLLAMA_URL = "http://localhost:11434/api/generate"

MODELS = {
    "tiny": "qwen2.5:1.5b",
    "medium": "qwen3.5:4b",
    "large": "qwen2.5:7b"
}

def call_ollama(prompt, model_type="tiny"):
    model = MODELS[model_type]

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": model,
            "prompt": prompt,
            "stream": False
        }
    )

    return response.json()["response"]
```

---

# 🧠 4. Dùng model nhỏ cho multilingual

## 👉 thay normalize rule-based bằng LLM nhỏ

```python
def normalize_with_llm(prompt):
    llm_prompt = f"""
Normalize this text into English keywords.

Input:
{prompt}

Output ONLY keywords:
"""

    return call_ollama(llm_prompt, "tiny")
```

---

👉 ví dụ:

```txt
lỗi upload ảnh bệnh nhân
```

→ output:

```txt
error upload image patient
```

---

# 🔥 5. Khi nào dùng model nào?

| Task               | Model      |
| ------------------ | ---------- |
| normalize VI/EN    | tiny       |
| intent detect      | tiny       |
| keyword expand     | tiny       |
| feature detect     | rule-based |
| fallback discovery | medium     |
| design complex     | large      |

---

# ⚠️ 6. Sai lầm cần tránh

## ❌ Dùng model lớn cho mọi thứ

→ chậm + tốn

---

## ❌ Dùng model nhỏ cho discovery

→ hallucinate / thiếu depth

---

# 💡 7. Insight quan trọng

👉 Bạn đang tiến tới:

> ❗ **Model specialization architecture**

---

Không phải:

* 1 model làm tất cả

---

Mà:

* mỗi model làm đúng việc

---

# 🚀 8. Nâng cấp nên làm tiếp

👉 thêm routing:

```python
if task == "normalize":
    use tiny
elif task == "discovery":
    use medium
```

---

# ✅ 9. Kết luận

✔ Có thể dùng Ollama local cho multilingual
✔ Nên dùng model nhỏ (Qwen 1.5B)
✔ Giữ model lớn cho discovery

---

# 👉 Nếu bạn muốn step tiếp theo

Mình có thể giúp bạn:

✔ auto model routing (system tự chọn model)
✔ hoặc benchmark model nào nhanh nhất cho case của bạn

---

Chỉ cần nói: **“auto model routing”** 👍
