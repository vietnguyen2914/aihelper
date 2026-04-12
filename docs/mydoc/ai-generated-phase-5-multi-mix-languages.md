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
