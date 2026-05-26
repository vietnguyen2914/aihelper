"""
ast_extractor.py — Tree-sitter AST extraction engine.

Bổ sung cho regex extraction hiện tại.
Khi tree-sitter grammar có sẵn → AST extraction (chính xác).
Khi không → fallback regex (như hiện tại).

Kiến trúc: ExtractionStrategy pattern.
Hỗ trợ: Python, JavaScript, TypeScript, Java, Go, Rust, PHP, C, C++.

Performance: files parse trong worker threads, result aggregated.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import tree_sitter
    HAS_TREE_SITTER = True
except ImportError:
    HAS_TREE_SITTER = False

# ── Language Detection ────────────────────────────────────────────

EXT_TO_TS_LANG = {
    ".py": "python",
    ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "tsx",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".php": "php",
    ".c": "c", ".h": "c",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp",
    ".rb": "ruby",
    ".swift": "swift",
    ".kt": "kts", ".kts": "kts",
    ".cs": "csharp",
    ".lua": "lua",
    ".dart": "dart",
}

# ── AST Query Templates ───────────────────────────────────────────

QUERIES = {
    "python": """
        (function_definition
            name: (identifier) @function.name
            parameters: (parameters) @function.params
            body: (block) @function.body) @function.def

        (class_definition
            name: (identifier) @class.name
            superclasses: (argument_list) @class.parents
            body: (block) @class.body) @class.def

        (decorated_definition
            (decorator) @decorator
            definition: (function_definition
                name: (identifier) @function.name)) @decorated.func

        (call
            function: (identifier) @call.target) @call.expr

        (call
            function: (attribute
                object: (identifier) @call.obj
                attribute: (identifier) @call.attr)) @method.call

        (import_statement
            name: (dotted_name) @import.module) @import.stmt

        (import_from_statement
            module_name: (dotted_name) @import.from
            name: (dotted_name) @import.name) @import.from_stmt
    """,

    "javascript": """
        (function_declaration
            name: (identifier) @function.name
            parameters: (formal_parameters) @function.params
            body: (statement_block) @function.body) @function.def

        (arrow_function
            parameters: (formal_parameters) @function.params
            body: (statement_block) @function.body) @arrow.func

        (method_definition
            name: (property_identifier) @function.name
            parameters: (formal_parameters) @function.params
            body: (statement_block) @function.body) @function.def

        (class_declaration
            name: (identifier) @class.name
            body: (class_body) @class.body) @class.def

        (call_expression
            function: (identifier) @call.target) @call.expr

        (call_expression
            function: (member_expression
                object: (identifier) @call.obj
                property: (property_identifier) @call.attr)) @method.call

        (import_statement
            source: (string) @import.source) @import.stmt

        (export_statement
            source: (string) @import.source) @export.stmt
    """,

    "typescript": """
        (function_declaration
            name: (identifier) @function.name
            parameters: (formal_parameters) @function.params
            body: (statement_block) @function.body) @function.def

        (method_definition
            name: (property_identifier) @function.name
            parameters: (formal_parameters) @function.params
            body: (statement_block) @function.body) @function.def

        (class_declaration
            name: (type_identifier) @class.name
            body: (class_body) @class.body) @class.def

        (interface_declaration
            name: (type_identifier) @interface.name) @interface.def

        (call_expression
            function: (identifier) @call.target) @call.expr

        (call_expression
            function: (member_expression
                property: (property_identifier) @call.attr)) @method.call

        (import_statement
            source: (string) @import.source) @import.stmt
    """,

    "java": """
        (method_declaration
            name: (identifier) @function.name
            parameters: (formal_parameters) @function.params
            body: (block) @function.body) @function.def

        (class_declaration
            name: (identifier) @class.name
            body: (class_body) @class.body) @class.def

        (interface_declaration
            name: (identifier) @interface.name) @interface.def

        (method_invocation
            name: (identifier) @call.target) @call.expr

        (method_invocation
            object: (identifier) @call.obj
            name: (identifier) @call.attr) @method.call

        (import_declaration
            (scoped_identifier) @import.module) @import.stmt
    """,

    "go": """
        (function_declaration
            name: (identifier) @function.name
            parameters: (parameter_list) @function.params
            body: (block) @function.body) @function.def

        (method_declaration
            name: (field_identifier) @function.name
            parameters: (parameter_list) @function.params
            body: (block) @function.body) @function.def

        (type_declaration
            (type_spec
                name: (type_identifier) @type.name
                type: (struct_type) @struct.body)) @struct.def

        (call_expression
            function: (identifier) @call.target) @call.expr

        (call_expression
            function: (selector_expression
                field: (field_identifier) @call.attr)) @method.call

        (import_declaration
            (import_spec
                path: (interpreted_string_literal) @import.path)) @import.stmt
    """,

    "php": """
        (method_declaration
            name: (name) @function.name
            parameters: (formal_parameters) @function.params
            body: (compound_statement) @function.body) @function.def

        (function_definition
            name: (name) @function.name) @function.def

        (class_declaration
            name: (name) @class.name
            body: (declaration_list) @class.body) @class.def

        (function_call_expression
            function: (name) @call.target) @call.expr

        (scoped_call_expression
            scope: (name) @call.obj
            name: (name) @call.attr) @method.call

        (use_declaration
            (qualified_name) @import.module) @import.stmt
    """,

    "rust": """
        (function_item
            name: (identifier) @function.name
            parameters: (parameters) @function.params
            body: (block) @function.body) @function.def

        (struct_item
            name: (type_identifier) @struct.name) @struct.def

        (impl_item
            type: (type_identifier) @impl.type
            body: (declaration_list) @impl.body) @impl.def

        (trait_item
            name: (type_identifier) @trait.name) @trait.def

        (call_expression
            function: (identifier) @call.target) @call.expr

        (call_expression
            function: (scoped_identifier
                name: (identifier) @call.attr)) @method.call

        (use_declaration
            argument: (scoped_identifier) @import.path) @import.stmt
    """,

    "c": """
        (function_definition
            declarator: (function_declarator
                declarator: (identifier) @function.name)
            parameters: (parameter_list) @function.params
            body: (compound_statement) @function.body) @function.def

        (call_expression
            function: (identifier) @call.target) @call.expr

        (preproc_include
            path: (string_literal) @import.include) @include.stmt
    """,

    "cpp": """
        (function_definition
            declarator: (function_declarator
                declarator: (identifier) @function.name)
            parameters: (parameter_list) @function.params
            body: (compound_statement) @function.body) @function.def

        (class_specifier
            name: (type_identifier) @class.name
            body: (field_declaration_list) @class.body) @class.def

        (call_expression
            function: (identifier) @call.target) @call.expr

        (call_expression
            function: (field_expression
                field: (field_identifier) @call.attr)) @method.call
    """,
}

# ── AST Extractor ─────────────────────────────────────────────────

class ASTExtractor:
    """Extract symbols + edges từ source code dùng tree-sitter AST."""

    def __init__(self):
        self._parsers: Dict[str, Any] = {}
        self._queries: Dict[str, Any] = {}
        self._init_grammars()

    def _init_grammars(self):
        if not HAS_TREE_SITTER:
            return
        lang_map = {
            "python": "tree_sitter_python",
            "javascript": "tree_sitter_javascript",
            "typescript": "tree_sitter_typescript",
            "tsx": "tree_sitter_typescript",
            "java": "tree_sitter_java",
            "go": "tree_sitter_go",
            "rust": "tree_sitter_rust",
            "php": "tree_sitter_php",
            "c": "tree_sitter_c",
            "cpp": "tree_sitter_cpp",
        }
        for lang_name, module_name in lang_map.items():
            try:
                mod = __import__(module_name, fromlist=["language"])
                lang_obj = tree_sitter.Language(mod.language())
                parser = tree_sitter.Parser()
                parser.set_language(lang_obj)
                self._parsers[lang_name] = parser
                if lang_name in QUERIES:
                    self._queries[lang_name] = lang_obj.query(QUERIES[lang_name])
            except (ImportError, AttributeError, Exception):
                pass

        # TSX shares TypeScript parser
        if "typescript" in self._parsers and "tsx" not in self._parsers:
            try:
                mod = __import__("tree_sitter_typescript", fromlist=["language"])
                lang_obj = tree_sitter.Language(mod.language_tsx())
                parser = tree_sitter.Parser()
                parser.set_language(lang_obj)
                self._parsers["tsx"] = parser
                if "typescript" in self._queries:
                    self._queries["tsx"] = lang_obj.query(QUERIES["typescript"])
            except Exception:
                pass

    def can_parse(self, language: str) -> bool:
        return HAS_TREE_SITTER and language in self._parsers

    @property
    def supported_languages(self) -> List[str]:
        return sorted(self._parsers.keys())

    def extract(self, file_path: str, content: str,
                language: str) -> Dict[str, Any]:
        """Extract symbols + edges từ source code."""
        if not self.can_parse(language):
            return {"symbols": [], "edges": [], "unresolved": []}

        parser = self._parsers[language]
        query = self._queries.get(language)
        if not query:
            return {"symbols": [], "edges": [], "unresolved": []}

        try:
            tree = parser.parse(bytes(content, "utf-8"))
        except Exception:
            return {"symbols": [], "edges": [], "unresolved": []}

        if not tree.root_node:
            return {"symbols": [], "edges": [], "unresolved": []}

        # Group captures by node
        captures: Dict[str, List[Any]] = {}
        try:
            for capture_name, nodes in query.captures(tree.root_node).items():
                if nodes:
                    captures.setdefault(capture_name, []).extend(nodes)
        except Exception:
            return {"symbols": [], "edges": [], "unresolved": []}

        return self._process_captures(captures, file_path, content, language)

    def _process_captures(self, captures: Dict[str, List[Any]],
                          file_path: str, content: str,
                          language: str) -> Dict[str, Any]:
        symbols: List[Dict] = []
        edges: List[Dict] = []
        unresolved: List[Dict] = []
        seen_ids: set = set()

        func_defs: Dict[str, Dict] = {}
        class_defs: Dict[str, Dict] = {}
        calls: List[Dict] = []

        for group_key, nodes in captures.items():
            node = nodes[0]
            line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            try:
                node_text = content[node.start_byte:node.end_byte]
            except IndexError:
                continue

            if group_key in ("function.def", "decorated.func"):
                name = self._find_name(captures, "function.name", content)
                if not name:
                    name = self._find_name(captures, "function.def", content)
                    if name:
                        name = _extract_func_name(name)
                if name:
                    sym_id = f"{file_path}::{name}"
                    if sym_id not in seen_ids:
                        seen_ids.add(sym_id)
                        sig = node_text.split("\n")[0][:240] if node_text else ""
                        func_defs[sym_id] = {
                            "id": sym_id, "kind": self._classify_function(node_text, language),
                            "name": name, "qualified_name": sym_id,
                            "file_path": file_path, "language": language,
                            "start_line": line, "end_line": end_line,
                            "signature": sig,
                            "fingerprint": hashlib.sha1(sig.encode()).hexdigest(),
                        }

            elif group_key == "class.def":
                name = self._find_name(captures, "class.name", content)
                if name:
                    sym_id = f"{file_path}::{name}"
                    if sym_id not in seen_ids:
                        seen_ids.add(sym_id)
                        class_defs[sym_id] = {
                            "id": sym_id, "kind": "class",
                            "name": name, "qualified_name": sym_id,
                            "file_path": file_path, "language": language,
                            "start_line": line, "end_line": end_line,
                            "fingerprint": hashlib.sha1(node_text.encode()).hexdigest(),
                        }

            elif group_key == "interface.def":
                name = self._find_name(captures, "interface.name", content)
                if name:
                    sym_id = f"{file_path}::{name}"
                    if sym_id not in seen_ids:
                        seen_ids.add(sym_id)
                        symbols.append({
                            "id": sym_id, "kind": "interface",
                            "name": name, "qualified_name": sym_id,
                            "file_path": file_path, "language": language,
                            "start_line": line, "end_line": end_line,
                            "fingerprint": hashlib.sha1(node_text.encode()).hexdigest(),
                        })

            elif group_key == "struct.def" or group_key == "struct.body":
                name = self._find_name(captures, "struct.name", content) or \
                       self._find_name(captures, "type.name", content)
                if name:
                    sym_id = f"{file_path}::{name}"
                    if sym_id not in seen_ids:
                        seen_ids.add(sym_id)
                        symbols.append({
                            "id": sym_id, "kind": "struct",
                            "name": name, "qualified_name": sym_id,
                            "file_path": file_path, "language": language,
                            "start_line": line, "end_line": end_line,
                            "fingerprint": hashlib.sha1(node_text.encode()).hexdigest(),
                        })

            elif group_key in ("call.expr", "method.call", "scoped.call"):
                target_name = self._find_name(captures, "call.target", content)
                if not target_name and group_key == "method.call":
                    target_name = self._find_name(captures, "call.attr", content)
                if target_name:
                    calls.append({"target": target_name, "line": line, "file": file_path})

        # Merge all symbols
        all_symbols = list(class_defs.values()) + list(func_defs.values())
        symbols.extend(all_symbols)

        # Build call edges
        for call in calls:
            target_name = call["target"]
            target_id = f"{call['file']}::{target_name}"
            enclosing = self._find_enclosing(call["line"], func_defs, class_defs)
            if target_id in seen_ids and enclosing:
                edges.append({
                    "source": enclosing, "target": target_id,
                    "kind": "calls", "line": call["line"],
                    "provenance": "tree-sitter",
                })
            elif enclosing:
                unresolved.append({
                    "from_node_id": enclosing,
                    "reference_name": target_name,
                    "reference_kind": "calls",
                    "line": call["line"],
                    "col": 0,
                    "file_path": call["file"],
                    "language": language,
                })

        # Class hierarchy edges
        for sym_id, info in class_defs.items():
            parent_name = self._find_name(captures, "class.parents", content)
            if parent_name:
                parent_id = f"{file_path}::{parent_name}"
                edges.append({
                    "source": sym_id, "target": parent_id,
                    "kind": "extends", "line": info["start_line"],
                    "provenance": "tree-sitter",
                })

        return {"symbols": symbols, "edges": edges, "unresolved": unresolved}

    def _find_name(self, captures: Dict[str, List[Any]],
                   key: str, content: str) -> Optional[str]:
        nodes = captures.get(key, [])
        if not nodes:
            return None
        node = nodes[0]
        try:
            return content[node.start_byte:node.end_byte].strip()
        except IndexError:
            return None

    def _classify_function(self, text: str, language: str) -> str:
        text_stripped = text.strip()
        if "class " in text_stripped[:20] or "interface " in text_stripped[:20]:
            return "class"
        if text_stripped.startswith("@") and language == "python":
            return "method"
        if "def " in text_stripped[:10]:
            return "method" if "self" in text or "cls" in text else "function"
        return "function"

    def _find_enclosing(self, line: int, func_defs: Dict[str, Dict],
                        class_defs: Dict[str, Dict]) -> Optional[str]:
        best = None
        best_start = 0
        for sym_id, info in {**func_defs, **class_defs}.items():
            if info["start_line"] <= line <= info.get("end_line", info["start_line"]):
                if info["start_line"] > best_start:
                    best = sym_id
                    best_start = info["start_line"]
        return best


def _extract_func_name(text: str) -> Optional[str]:
    m = re.search(r'(?:def|function|func)\s+([A-Za-z_][A-Za-z0-9_]*)', text)
    return m.group(1) if m else None


# ── Strategy Pattern ──────────────────────────────────────────────

class ExtractionOrchestrator:
    """Chọn tree-sitter nếu có grammar, fallback regex."""

    def __init__(self):
        self.ast = ASTExtractor() if HAS_TREE_SITTER else None
        self._regex_extractor = None  # Lazy import to avoid circular deps

    def extract(self, file_path: str, content: str) -> Dict[str, Any]:
        language = EXT_TO_TS_LANG.get(Path(file_path).suffix.lower(), "unknown")

        if self.ast and self.ast.can_parse(language):
            result = self.ast.extract(file_path, content, language)
            if result["symbols"]:
                return result
            # Fall through to regex if AST extraction yields nothing

        return self._regex_extract(file_path, content)

    def _regex_extract(self, file_path: str, content: str) -> Dict[str, Any]:
        """Fallback: dùng regex extraction như hiện tại."""
        from .cache import SYMBOL_PATTERNS
        from .common import normalize_identifier

        symbols = []
        for pattern, kind, flags in SYMBOL_PATTERNS:
            try:
                matches = list(re.finditer(pattern, content, flags))
            except re.error:
                continue
            for m in matches:
                if m.lastindex and m.lastindex >= 1:
                    name = m.group(1)
                else:
                    name = m.group(0).split()[-1] if m.group(0).split() else ""
                    name = name.strip("():, ")
                if not name or len(name) < 2:
                    continue
                line = content[:m.start()].count("\n") + 1
                sym_id = f"{file_path}::{name}"
                sig = m.group(0)[:240] if m.group(0) else ""
                symbols.append({
                    "id": sym_id, "kind": kind,
                    "name": name, "qualified_name": sym_id,
                    "file_path": file_path,
                    "language": EXT_TO_TS_LANG.get(Path(file_path).suffix.lower(), "unknown"),
                    "start_line": line, "end_line": line,
                    "signature": sig,
                    "fingerprint": hashlib.sha1(sig.encode()).hexdigest(),
                })

        return {"symbols": symbols, "edges": [], "unresolved": []}

    @property
    def supported_ast_languages(self) -> List[str]:
        return self.ast.supported_languages if self.ast else []
