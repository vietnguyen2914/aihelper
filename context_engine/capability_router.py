"""
Capability Router — orchestrates auxiliary AI tools.

Routes input types to optimal processing pipelines:
- PDF → MinerU / PaddleOCR
- Image/screenshot → minicpm-v / PaddleOCR  
- Stack trace → diagnostics → aihelper
- Diff/patch → structural_diff → confidence
- Voice → whisper → intent router
- Query → embeddings → reranker → context

Principle: capability dormant + intent-triggered activation.
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional


INPUT_PATTERNS = {
    "pdf": [r"\.pdf$", r"pdf", r"scanned document"],
    "image": [r"\.(png|jpg|jpeg|gif|webp|bmp)$", r"screenshot", r"image", r"photo"],
    "stacktrace": [r"Error:", r"at\s+\S+\.\S+\(", r"Traceback", r"Exception", r"at \S+:\d+"],
    "diff": [r"^diff --git", r"^@@ -\d+,\d+ +\+\d+,\d+ @@", r"^\+\+\+ b/"],
    "voice": [],  # Detected by runtime
    "code_query": [r"fix\s+", r"refactor\s+", r"implement\s+", r"add\s+", r"write\s+"],
    "search_query": [r"find\s+", r"search\s+", r"locate\s+", r"where\s+", r"how\s+"],
}


def classify_input(input_text: str, file_path: Optional[str] = None) -> Dict[str, float]:
    """Classify input type and return confidence scores for each capability."""
    scores: Dict[str, float] = {}
    text_lower = input_text.lower()

    for input_type, patterns in INPUT_PATTERNS.items():
        score = 0.0
        for pattern in patterns:
            if re.search(pattern, text_lower):
                score = max(score, 0.7)
            if file_path and re.search(pattern, file_path.lower()):
                score = max(score, 0.9)
        if score > 0:
            scores[input_type] = score

    # File extension overrides
    if file_path:
        ext = Path(file_path).suffix.lower()
        if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
            scores["image"] = max(scores.get("image", 0), 1.0)
        elif ext == ".pdf":
            scores["pdf"] = max(scores.get("pdf", 0), 1.0)
        elif ext in (".diff", ".patch"):
            scores["diff"] = max(scores.get("diff", 0), 1.0)

    if not scores:
        scores["code_query"] = 0.5

    return scores


def select_pipeline(input_text: str, file_path: Optional[str] = None) -> Dict[str, Any]:
    """Select the optimal processing pipeline for the input."""
    scores = classify_input(input_text, file_path)
    best = max(scores, key=scores.get) if scores else "code_query"
    confidence = scores.get(best, 0.5)

    pipeline_map = {
        "pdf": ["MinerU", "PaddleOCR", "qwen3.5:4b-16k"],
        "image": ["minicpm-v", "PaddleOCR"],
        "stacktrace": ["diagnostics", "structural_diff", "qwen3.5:4b-16k"],
        "diff": ["structural_diff", "confidence", "qwen3.5:4b-16k"],
        "voice": ["faster-whisper", "intent_router"],
        "code_query": ["qwen3.5:4b-16k"],
        "search_query": ["bge-m3", "nomic-embed-text", "CrossEncoder"],
    }

    return {
        "input_type": best,
        "confidence": round(confidence, 2),
        "all_scores": scores,
        "pipeline": pipeline_map.get(best, ["qwen3.5:4b-16k"]),
        "tools_needed": pipeline_map.get(best, []),
    }


# ── Individual Capability Handlers ──────────────────────────────

def handle_vision(image_path: str, prompt: str = "Describe this image") -> Dict[str, Any]:
    """Analyze an image using minicpm-v."""
    if not Path(image_path).exists():
        return {"error": "image_not_found", "path": image_path}

    try:
        result = subprocess.run(
            ["ollama", "run", "minicpm-v:latest", prompt, "--image", image_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60,
        )
        return {
            "tool": "minicpm-v",
            "output": result.stdout.strip()[:2000],
            "error": result.stderr.strip()[:200] if result.returncode else "",
        }
    except Exception as e:
        return {"error": str(e)}


def handle_ocr(image_path: str, lang: str = "en") -> Dict[str, Any]:
    """Extract text from image using PaddleOCR."""
    if not Path(image_path).exists():
        return {"error": "image_not_found"}

    try:
        result = subprocess.run(
            ["paddleocr", "--image", image_path, "--lang", lang],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60,
        )
        return {
            "tool": "paddleocr",
            "text": result.stdout.strip()[:5000],
            "error": result.stderr.strip()[:200] if result.returncode else "",
        }
    except Exception as e:
        return {"error": str(e)}


def handle_embedding(text: str, model: str = "bge-m3") -> Dict[str, Any]:
    """Generate embeddings for text."""
    try:
        result = subprocess.run(
            ["ollama", "run", model, text],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30,
        )
        return {
            "model": model,
            "text_len": len(text),
            "output": result.stdout.strip()[:1000],
        }
    except Exception as e:
        return {"error": str(e)}


def handle_rerank(query: str, documents: List[str], top_k: int = 5) -> Dict[str, Any]:
    """Rerank documents by relevance to query."""
    try:
        from sentence_transformers import CrossEncoder
        model = CrossEncoder("BAAI/bge-reranker-v2-m3")
        pairs = [(query, doc) for doc in documents]
        scores = model.predict(pairs)
        ranked = sorted(zip(documents, scores), key=lambda x: x[1], reverse=True)
        return {
            "top_k": top_k,
            "results": [
                {"text": doc[:200], "score": round(float(score), 4)}
                for doc, score in ranked[:top_k]
            ],
        }
    except Exception as e:
        return {"error": str(e)}


def handle_stt(audio_path: str) -> Dict[str, Any]:
    """Transcribe audio using faster-whisper."""
    if not Path(audio_path).exists():
        return {"error": "audio_not_found"}

    try:
        result = subprocess.run(
            ["faster-whisper", audio_path, "--model", "tiny", "--language", "en"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120,
        )
        return {
            "tool": "faster-whisper",
            "transcript": result.stdout.strip()[:5000],
        }
    except Exception as e:
        return {"error": str(e)}


# ── Integrated Pipeline ──────────────────────────────────────────

def run_pipeline(input_text: str, file_path: Optional[str] = None) -> Dict[str, Any]:
    """Run the full capability pipeline: classify → route → execute."""
    route = select_pipeline(input_text, file_path)
    results = {}

    tools_to_run = []
    has_file = file_path and Path(file_path).exists()

    if "minicpm-v" in route["tools_needed"] and has_file:
        tools_to_run.append(("vision", lambda: handle_vision(file_path)))

    if "PaddleOCR" in route["tools_needed"] and has_file:
        tools_to_run.append(("ocr", lambda: handle_ocr(file_path)))

    if "CrossEncoder" in route["tools_needed"] and input_text:
        tools_to_run.append(("reranker", lambda: handle_rerank(input_text, [input_text])))

    if "diagnostics" in route["tools_needed"] and file_path:
        from .diagnostics import collect_diagnostics
        tools_to_run.append(("diagnostics", lambda: collect_diagnostics(
            file_path, Path(file_path).parent
        )))

    for name, fn in tools_to_run:
        try:
            results[name] = fn()
        except Exception as e:
            results[name] = {"error": str(e)}

    return {
        "route": route,
        "results": results,
        "tools_executed": len(tools_to_run),
    }


# ── Daemon handler ───────────────────────────────────────────────

def handle_capability_route(params: Dict[str, Any]) -> Dict[str, Any]:
    """Route input to the right capability."""
    input_text = params.get("input", "")
    file_path = params.get("file_path")
    return select_pipeline(input_text, file_path)


def handle_capability_vision(params: Dict[str, Any]) -> Dict[str, Any]:
    """Run vision pipeline."""
    return handle_vision(params.get("image_path", ""), params.get("prompt", "Describe this image"))


def handle_capability_ocr(params: Dict[str, Any]) -> Dict[str, Any]:
    """Run OCR pipeline."""
    return handle_ocr(params.get("image_path", ""), params.get("lang", "en"))


def handle_capability_rerank(params: Dict[str, Any]) -> Dict[str, Any]:
    """Run reranker pipeline."""
    return handle_rerank(params.get("query", ""), params.get("documents", []), params.get("top_k", 5))


def handle_capability_embed(params: Dict[str, Any]) -> Dict[str, Any]:
    """Run embedding pipeline."""
    return handle_embedding(params.get("text", ""), params.get("model", "bge-m3"))
