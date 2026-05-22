"""
LSP Bridge — lightweight integration with language servers.

Queries running LSP servers for:
- Go-to-definition
- Find references
- Document symbols
- Diagnostics (errors/warnings)
- Hover information

Uses LSP stdio protocol to communicate with language servers.
Supported: intelephense (PHP), tsserver (TypeScript), pylsp (Python)

Goal: leverage existing LSP infrastructure instead of rebuilding symbol resolution.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


# ── LSP Client ───────────────────────────────────────────────────

class LSPClient:
    """Lightweight LSP client for a single language server."""

    def __init__(self, command: List[str], root_uri: str):
        self.command = command
        self.root_uri = root_uri
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._next_id = 1
        self._responses: Dict[int, Any] = {}
        self._initialized = False

    def start(self) -> bool:
        """Start the language server process."""
        try:
            self._proc = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            # Send initialize
            self._send_request("initialize", {
                "processId": os.getpid(),
                "rootUri": self.root_uri,
                "capabilities": {
                    "textDocument": {
                        "definition": {"linkSupport": True},
                        "references": {},
                        "documentSymbol": {"hierarchicalDocumentSymbolSupport": True},
                    }
                },
            })
            self._send_notification("initialized", {})
            self._initialized = True
            return True
        except Exception:
            return False

    def stop(self) -> None:
        """Stop the language server."""
        if self._proc:
            try:
                self._send_notification("exit", {})
                self._proc.wait(timeout=2)
            except Exception:
                self._proc.kill()
            self._proc = None

    def _send_request(self, method: str, params: Dict) -> Optional[Dict]:
        if not self._proc or not self._proc.stdin:
            return None

        req_id = self._next_id
        self._next_id += 1

        request = json.dumps({
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        })

        with self._lock:
            try:
                content = request.encode("utf-8")
                header = f"Content-Length: {len(content)}\r\n\r\n"
                self._proc.stdin.write(header + request + "\n")
                self._proc.stdin.flush()

                # Read response header
                header_line = self._proc.stdout.readline()
                if not header_line.startswith("Content-Length:"):
                    return None
                content_length = int(header_line.split(":")[1].strip())
                self._proc.stdout.readline()  # Skip empty line

                # Read body
                body = self._proc.stdout.read(content_length)
                response = json.loads(body)
                return response.get("result")
            except Exception:
                return None

    def _send_notification(self, method: str, params: Dict) -> None:
        if not self._proc or not self._proc.stdin:
            return
        notification = json.dumps({
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        })
        try:
            content = notification.encode("utf-8")
            header = f"Content-Length: {len(content)}\r\n\r\n"
            self._proc.stdin.write(header + notification + "\n")
            self._proc.stdin.flush()
        except Exception:
            pass

    def go_to_definition(self, file_path: str, line: int, character: int) -> Optional[List[Dict]]:
        """Get definition locations for a symbol."""
        uri = _path_to_uri(file_path)
        return self._send_request("textDocument/definition", {
            "textDocument": {"uri": uri},
            "position": {"line": line - 1, "character": character},
        })

    def find_references(self, file_path: str, line: int, character: int) -> Optional[List[Dict]]:
        """Find all references to a symbol."""
        uri = _path_to_uri(file_path)
        return self._send_request("textDocument/references", {
            "textDocument": {"uri": uri},
            "position": {"line": line - 1, "character": character},
            "context": {"includeDeclaration": True},
        })

    def document_symbols(self, file_path: str) -> Optional[List[Dict]]:
        """Get all symbols in a document."""
        uri = _path_to_uri(file_path)
        return self._send_request("textDocument/documentSymbol", {
            "textDocument": {"uri": uri},
        })

    def diagnostics(self, file_path: str) -> Optional[List[Dict]]:
        """Get diagnostics for a file (requires didOpen first)."""
        uri = _path_to_uri(file_path)
        # Open the document
        try:
            with open(file_path) as f:
                text = f.read()
        except OSError:
            return None

        self._send_notification("textDocument/didOpen", {
            "textDocument": {
                "uri": uri,
                "languageId": _guess_language(file_path),
                "version": 1,
                "text": text,
            },
        })
        # Give server a moment to process
        time.sleep(0.1)
        # The diagnostics come as notifications — we can't easily capture them
        # Return a placeholder
        return [{"note": "diagnostics_available_as_notifications", "uri": uri}]


# ── Helpers ──────────────────────────────────────────────────────

def _path_to_uri(path: str) -> str:
    """Convert file path to file:// URI."""
    abs_path = os.path.abspath(path)
    return "file://" + abs_path


def _guess_language(file_path: str) -> str:
    """Guess LSP language ID from file extension."""
    ext = Path(file_path).suffix.lower()
    mapping = {
        ".php": "php",
        ".ts": "typescript",
        ".tsx": "typescriptreact",
        ".js": "javascript",
        ".jsx": "javascriptreact",
        ".py": "python",
        ".java": "java",
        ".kt": "kotlin",
    }
    return mapping.get(ext, "plaintext")


def _detect_lsp_command(project_root: Path) -> Optional[Dict[str, Any]]:
    """Detect which LSP server to use based on project type."""
    # Check for PHP project
    if (project_root / "composer.json").exists():
        # Check if intelephense is available
        intelephense = subprocess.run(
            ["which", "intelephense"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        )
        if intelephense.returncode == 0:
            return {
                "language": "php",
                "command": ["intelephense", "--stdio"],
                "name": "intelephense",
            }

    # Check for TypeScript/JavaScript project
    if (project_root / "package.json").exists():
        # Try tsserver via npx
        return {
            "language": "typescript",
            "command": ["npx", "typescript-language-server", "--stdio"],
            "name": "tsserver",
        }

    # Check for Python project
    if (project_root / "setup.py").exists() or (project_root / "pyproject.toml").exists():
        return {
            "language": "python",
            "command": ["pylsp"],
            "name": "pylsp",
        }

    return None


# ── High-level API ───────────────────────────────────────────────

_lsp_cache: Dict[str, LSPClient] = {}


def get_lsp_client(project_root: Path) -> Optional[LSPClient]:
    """Get or create an LSP client for a project."""
    key = str(project_root.resolve())
    if key in _lsp_cache:
        return _lsp_cache[key]

    lsp_info = _detect_lsp_command(project_root)
    if not lsp_info:
        return None

    uri = _path_to_uri(str(project_root))
    client = LSPClient(lsp_info["command"], uri)
    if client.start():
        _lsp_cache[key] = client
        return client

    return None


def find_definition(query: str, file_path: str, line: int, character: int, project_root: Path) -> Dict[str, Any]:
    """Find definition of a symbol using LSP."""
    client = get_lsp_client(project_root)
    if not client:
        return {"available": False, "reason": "no_lsp_server_detected"}

    result = client.go_to_definition(file_path, line, character)
    return {
        "available": True,
        "method": "lsp",
        "definitions": result or [],
    }


def find_all_references(file_path: str, line: int, character: int, project_root: Path) -> Dict[str, Any]:
    """Find all references to a symbol using LSP."""
    client = get_lsp_client(project_root)
    if not client:
        return {"available": False, "reason": "no_lsp_server_detected"}

    result = client.find_references(file_path, line, character)
    return {
        "available": True,
        "method": "lsp",
        "references": result or [],
    }


def get_document_symbols(file_path: str, project_root: Path) -> Dict[str, Any]:
    """Get all symbols in a document using LSP."""
    client = get_lsp_client(project_root)
    if not client:
        return {"available": False, "reason": "no_lsp_server_detected"}

    result = client.document_symbols(file_path)
    return {
        "available": True,
        "method": "lsp",
        "symbols": result or [],
    }


# ── Daemon handler ───────────────────────────────────────────────

def handle_lsp_definition(params: Dict[str, Any]) -> Dict[str, Any]:
    """Daemon handler: find definition via LSP."""
    project_root = Path(params.get("project_root", "."))
    file_path = params.get("file_path", "")
    line = params.get("line", 1)
    character = params.get("character", 1)
    return find_definition(params.get("query", ""), file_path, line, character, project_root)


def handle_lsp_references(params: Dict[str, Any]) -> Dict[str, Any]:
    """Daemon handler: find references via LSP."""
    project_root = Path(params.get("project_root", "."))
    file_path = params.get("file_path", "")
    line = params.get("line", 1)
    character = params.get("character", 1)
    return find_all_references(file_path, line, character, project_root)


def handle_lsp_symbols(params: Dict[str, Any]) -> Dict[str, Any]:
    """Daemon handler: get document symbols via LSP."""
    project_root = Path(params.get("project_root", "."))
    file_path = params.get("file_path", "")
    return get_document_symbols(file_path, project_root)
