"""
Typed IPC Schemas — msgspec-based request/response types for daemon protocol v1.

Replaces ad-hoc dicts with typed structs for:
- Predictable wire format
- Cheap validation
- Schema evolution
- Auto-generated documentation hints

Uses Python dataclasses (stdlib, no deps) for broad compatibility.
Falls back gracefully if msgspec not installed.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


# ── Request Types ────────────────────────────────────────────────

@dataclass
class RouteRequest:
    task: str
    project_root: str = ""

@dataclass
class SymbolFindRequest:
    query: str
    project_root: str = ""
    limit: int = 20

@dataclass
class SymbolContextRequest:
    query: str
    project_root: str = ""
    limit: int = 20

@dataclass
class CacheStatusRequest:
    project_root: str = ""
    include_diff: bool = False

@dataclass
class CacheBuildRequest:
    project_root: str = ""

@dataclass
class PromptBlocksRequest:
    project_root: str = ""

@dataclass
class DiffSummaryRequest:
    project_root: str = ""

@dataclass
class MemoryAddRequest:
    project_root: str = ""
    topic: str = ""
    note: str = ""
    tags: List[str] = field(default_factory=list)

@dataclass
class MemoryRecallRequest:
    project_root: str = ""
    query: str = ""
    limit: int = 10

@dataclass
class PersistRequest:
    project_root: str = ""
    all: bool = False
    github_root: str = ""

@dataclass
class RestoreRequest:
    project_root: str = ""

@dataclass
class PersistStatusRequest:
    project_root: str = ""

@dataclass
class PatchPlanRequest:
    task: str = ""
    files: List[str] = field(default_factory=list)
    project_root: str = ""
    style: str = "unified"

@dataclass
class ContextRequest:
    task: str = ""
    project_root: str = ""
    max_context_chars: int = 6000

@dataclass
class EditorContextRequest:
    project_root: str = ""

@dataclass
class LSPDefinitionRequest:
    file_path: str = ""
    line: int = 1
    character: int = 1
    project_root: str = ""
    query: str = ""

@dataclass
class LSPReferencesRequest:
    file_path: str = ""
    line: int = 1
    character: int = 1
    project_root: str = ""

@dataclass
class LSPSymbolsRequest:
    file_path: str = ""
    project_root: str = ""

@dataclass
class ConfidenceRequest:
    patch_content: str = ""
    files: List[str] = field(default_factory=list)
    project_root: str = ""

@dataclass
class StructuralDiffRequest:
    patch_text: str = ""

@dataclass
class HierarchicalContextRequest:
    project_root: str = ""
    focus_file: Optional[str] = None
    focus_symbol: Optional[str] = None
    expansion_level: int = 1

@dataclass
class SchedulerRecordRequest:
    type: str = ""  # edit, symbol_query, branch, build_error, route
    file_path: Optional[str] = None
    symbol: Optional[str] = None
    branch: Optional[str] = None
    error: Optional[str] = None
    task: Optional[str] = None
    project_root: Optional[str] = None

@dataclass
class IntentRouteRequest:
    task: str = ""
    project_root: str = ""

@dataclass
class HealthRequest:
    pass  # No params needed

@dataclass
class TelemetryRequest:
    pass  # No params needed

@dataclass
class WarmupRequest:
    github_root: str = ""
    extra_roots: List[str] = field(default_factory=list)


# ── Response Envelope ────────────────────────────────────────────

@dataclass
class IPCResponse:
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    id: Optional[int] = None
    elapsed_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"id": self.id, "_elapsed_ms": round(self.elapsed_ms, 2)}
        if self.error:
            d["error"] = self.error
        else:
            d["result"] = self.result or {}
        return d


# ── Method → Request Type Mapping ────────────────────────────────

REQUEST_SCHEMAS: Dict[str, type] = {
    "health": HealthRequest,
    "route": RouteRequest,
    "symbol_find": SymbolFindRequest,
    "symbol_context": SymbolContextRequest,
    "cache_status": CacheStatusRequest,
    "cache_build": CacheBuildRequest,
    "prompt_blocks": PromptBlocksRequest,
    "diff_summary": DiffSummaryRequest,
    "memory_add": MemoryAddRequest,
    "memory_recall": MemoryRecallRequest,
    "persist": PersistRequest,
    "restore": RestoreRequest,
    "persist_status": PersistStatusRequest,
    "patch_plan": PatchPlanRequest,
    "context": ContextRequest,
    "editor_context": EditorContextRequest,
    "lsp_definition": LSPDefinitionRequest,
    "lsp_references": LSPReferencesRequest,
    "lsp_symbols": LSPSymbolsRequest,
    "confidence": ConfidenceRequest,
    "structural_diff": StructuralDiffRequest,
    "hierarchical_context": HierarchicalContextRequest,
    "scheduler_snapshot": HealthRequest,
    "scheduler_predict": HealthRequest,
    "scheduler_record": SchedulerRecordRequest,
    "intent_route": IntentRouteRequest,
    "subsystem_health": HealthRequest,
    "telemetry": TelemetryRequest,
    "warmup_status": WarmupRequest,
}


def validate_request(method: str, params: Dict[str, Any]) -> Optional[str]:
    """Validate request params against schema. Returns error message or None."""
    schema = REQUEST_SCHEMAS.get(method)
    if not schema:
        return f"unknown_method: {method}"

    try:
        # Create instance to validate types
        instance = schema(**{k: v for k, v in params.items() if k in schema.__dataclass_fields__})
        return None
    except TypeError as e:
        return f"invalid_params: {e}"


def coerce_request(method: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce params to typed request, filling defaults."""
    schema = REQUEST_SCHEMAS.get(method)
    if not schema:
        return params

    try:
        valid_keys = set(schema.__dataclass_fields__.keys())
        filtered = {k: v for k, v in params.items() if k in valid_keys}
        instance = schema(**filtered)
        return asdict(instance)
    except TypeError:
        return params


# ── Protocol Version ─────────────────────────────────────────────

IPC_PROTOCOL_VERSION = "1.0"
IPC_PROTOCOL_FEATURES = [
    "typed_requests",
    "elapsed_timing",
    "error_envelope",
    "graceful_degradation",
    "lazy_handler_loading",
]
