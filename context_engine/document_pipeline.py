"""
Document & Presentation Pipeline — AI-native document generation.

Flow: aihelper summaries → LLM structured markdown → diagrams → render → export

Tools:
- Content: qwen3.5:4b-16k (writing), phi4-mini (diagram DSL)
- Diagrams: Mermaid, DBML, Vega-Lite
- Render: Marp (slides), PptxGenJS (corporate PPTX)
- Conversion: Pandoc, LibreOffice
- Parsing: Docling, MinerU, PaddleOCR
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional


# ── Diagram Generation ───────────────────────────────────────────

MERMAID_TEMPLATES = {
    "flowchart": "```mermaid\ngraph TD\n    A[Start] --> B[End]\n```",
    "sequence": "```mermaid\nsequenceDiagram\n    A->>B: Message\n    B-->>A: Response\n```",
    "gantt": "```mermaid\ngantt\n    title Project\n    section Phase\n    Task :a1, 2024-01-01, 30d\n```",
    "class": "```mermaid\nclassDiagram\n    class Service {\n        +operation()\n    }\n```",
    "entity": "```mermaid\nerDiagram\n    ENTITY {\n        int id PK\n        string name\n    }\n```",
}

DBML_TEMPLATES = {
    "table": """Table users {
  id int [pk, increment]
  name varchar(100)
  email varchar(255) [unique]
  created_at timestamp
}""",
    "reference": """Ref: orders.user_id > users.id""",
}

VEGA_TEMPLATES = {
    "bar": """{
  "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
  "mark": "bar",
  "encoding": {
    "x": {"field": "category", "type": "nominal"},
    "y": {"field": "value", "type": "quantitative"}
  }
}""",
}


def generate_mermaid(diagram_type: str = "flowchart", spec: str = "") -> Dict[str, Any]:
    """Generate Mermaid diagram string."""
    if spec:
        return {"diagram": f"```mermaid\n{spec}\n```", "type": "mermaid"}
    template = MERMAID_TEMPLATES.get(diagram_type, MERMAID_TEMPLATES["flowchart"])
    return {"diagram": template, "type": "mermaid", "template": diagram_type}


def render_mermaid(diagram_text: str, output_path: str, format: str = "png") -> Dict[str, Any]:
    """Render Mermaid to PNG/SVG using mermaid-cli."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".mmd", delete=False) as tmp:
        # Strip markdown fences
        clean = diagram_text.replace("```mermaid", "").replace("```", "").strip()
        tmp.write(clean)
        mmd_path = tmp.name

    try:
        result = subprocess.run(
            ["mmdc", "-i", mmd_path, "-o", output_path, "-f", format],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30,
        )
        return {
            "rendered": result.returncode == 0,
            "output": output_path,
            "error": result.stderr.strip()[:200] if result.returncode else "",
        }
    except Exception as e:
        return {"rendered": False, "error": str(e)}
    finally:
        os.unlink(mmd_path)


# ── Presentation Generation ──────────────────────────────────────

def generate_marp_deck(markdown_slides: str, output_path: str, format: str = "pptx") -> Dict[str, Any]:
    """Generate presentation from markdown using Marp."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as tmp:
        # Add Marp frontmatter
        full_md = f"""---
marp: true
theme: uncover
class: invert
---

{markdown_slides}
"""
        tmp.write(full_md)
        md_path = tmp.name

    export_format = "--pptx" if format == "pptx" else "--pdf" if format == "pdf" else "--html"

    try:
        result = subprocess.run(
            ["marp", md_path, export_format, "-o", output_path, "--allow-local-files"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60,
        )
        return {
            "generated": result.returncode == 0,
            "output": output_path,
            "format": format,
            "error": result.stderr.strip()[:300] if result.returncode else "",
        }
    except Exception as e:
        return {"generated": False, "error": str(e)}
    finally:
        os.unlink(md_path)


def generate_pptxgenjs(spec_json: str, output_path: str) -> Dict[str, Any]:
    """Generate PPTX from JSON spec using PptxGenJS."""
    js_code = f"""
const PptxGenJS = require('pptxgenjs');
const fs = require('fs');
const spec = JSON.parse({json.dumps(spec_json)});
const pptx = new PptxGenJS();
for (const slide of spec.slides) {{
    const s = pptx.addSlide();
    if (slide.title) {{
        s.addText(slide.title, {{ x: 1, y: 0.5, w: 8, h: 1, fontSize: 28, bold: true }});
    }}
    if (slide.content) {{
        s.addText(slide.content, {{ x: 1, y: 2, w: 8, h: 4, fontSize: 16 }});
    }}
    if (slide.bullets) {{
        s.addText(slide.bullets.map(b => '• ' + b).join('\\n'), {{ x: 1, y: 2, w: 8, h: 4, fontSize: 14 }});
    }}
}}
pptx.writeFile({{ fileName: '{output_path}' }}).then(() => console.log('DONE'));
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as tmp:
        tmp.write(js_code)
        js_path = tmp.name

    try:
        result = subprocess.run(
            ["node", js_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30,
        )
        return {
            "generated": "DONE" in result.stdout,
            "output": output_path,
            "error": result.stderr.strip()[:300] if "DONE" not in result.stdout else "",
        }
    except Exception as e:
        return {"generated": False, "error": str(e)}
    finally:
        os.unlink(js_path)


# ── Office Conversion ─────────────────────────────────────────────

def convert_with_pandoc(input_path: str, output_path: str, from_format: str = "markdown", to_format: str = "pptx") -> Dict[str, Any]:
    """Convert documents using Pandoc."""
    try:
        result = subprocess.run(
            ["pandoc", input_path, "-f", from_format, "-t", to_format, "-o", output_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60,
        )
        return {
            "converted": result.returncode == 0,
            "output": output_path,
            "error": result.stderr.strip()[:200] if result.returncode else "",
        }
    except Exception as e:
        return {"converted": False, "error": str(e)}


def convert_with_libreoffice(input_path: str, output_format: str = "pdf") -> Dict[str, Any]:
    """Convert documents using LibreOffice headless."""
    try:
        result = subprocess.run(
            ["/Applications/LibreOffice.app/Contents/MacOS/soffice",
             "--headless", "--convert-to", output_format, input_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120,
        )
        return {
            "converted": result.returncode == 0,
            "output_dir": str(Path(input_path).parent),
            "error": result.stderr.strip()[:200] if result.returncode else "",
        }
    except Exception as e:
        return {"converted": False, "error": str(e)}


# ── Document Parsing ─────────────────────────────────────────────

def parse_with_docling(file_path: str) -> Dict[str, Any]:
    """Parse document structure using Docling."""
    if not Path(file_path).exists():
        return {"error": "file_not_found"}
    try:
        result = subprocess.run(
            ["docling", file_path, "--output", str(Path(file_path).parent)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60,
        )
        return {
            "parsed": result.returncode == 0,
            "output": result.stdout.strip()[:2000],
            "error": result.stderr.strip()[:200] if result.returncode else "",
        }
    except Exception as e:
        return {"parsed": False, "error": str(e)}


# ── Full Pipeline ────────────────────────────────────────────────

def generate_presentation(
    title: str,
    slides: List[Dict[str, Any]],
    output_path: str,
    format: str = "pptx",
    include_diagrams: bool = True,
) -> Dict[str, Any]:
    """End-to-end presentation generation pipeline."""
    markdown_parts = [f"# {title}\n"]

    for i, slide in enumerate(slides):
        markdown_parts.append(f"\n---\n## {slide.get('title', f'Slide {i+1}')}\n")
        if "content" in slide:
            markdown_parts.append(slide["content"])
        if "bullets" in slide:
            for bullet in slide["bullets"]:
                markdown_parts.append(f"- {bullet}")
        if "diagram" in slide and include_diagrams:
            diagram = generate_mermaid(slide["diagram"]["type"], slide["diagram"].get("spec", ""))
            markdown_parts.append(diagram["diagram"])

    markdown_content = "\n".join(markdown_parts)

    # Stage 1: Marp generates deck
    marp_result = generate_marp_deck(markdown_content, output_path, format)

    return {
        "title": title,
        "slide_count": len(slides),
        "output": output_path,
        "format": format,
        "marp_result": marp_result,
        "markdown": markdown_content,
    }


# ── Daemon handlers ──────────────────────────────────────────────

def handle_generate_mermaid(params: Dict[str, Any]) -> Dict[str, Any]:
    diag = params.get("diagram", params.get("diagram_type", "flowchart"))
    spec = params.get("spec", "")
    return generate_mermaid(diag, spec)


def handle_render_diagram(params: Dict[str, Any]) -> Dict[str, Any]:
    return render_mermaid(
        params.get("diagram_text", ""),
        params.get("output_path", "/tmp/diagram.png"),
        params.get("format", "png"),
    )


def handle_generate_presentation(params: Dict[str, Any]) -> Dict[str, Any]:
    return generate_presentation(
        params.get("title", "Untitled"),
        params.get("slides", []),
        params.get("output_path", "/tmp/presentation.pptx"),
        params.get("format", "pptx"),
    )


def handle_convert_document(params: Dict[str, Any]) -> Dict[str, Any]:
    tool = params.get("tool", "pandoc")
    if tool == "libreoffice":
        return convert_with_libreoffice(params.get("input_path", ""), params.get("format", "pdf"))
    return convert_with_pandoc(
        params.get("input_path", ""),
        params.get("output_path", "/tmp/output.pptx"),
        params.get("from_format", "markdown"),
        params.get("to_format", "pptx"),
    )


def handle_parse_document(params: Dict[str, Any]) -> Dict[str, Any]:
    return parse_with_docling(params.get("file_path", ""))
