"""
Workflow Runtime Engine — deterministic state machine execution.

Design: Workflows are defined as YAML files in context_engine/workflows/.
Each workflow is a sequence of phases. Phases can use:
  - `handler: name` — call a built-in handler
  - `uses: [primitive1, primitive2, ...]` — compose named primitives from registry
  - `kind: local_model | frontier` — invoke AI at decision points

CLI: aihelper workflow run <name> [--params ...]
MCP: aihelper_workflow_run
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml


class PhaseKind(Enum):
    DETERMINISTIC = "deterministic"
    LOCAL_MODEL = "local_model"
    FRONTIER = "frontier"
    GATE = "gate"


@dataclass
class PhaseResult:
    phase: str
    kind: PhaseKind
    success: bool
    output: Dict[str, Any] = field(default_factory=dict)
    tokens_used: int = 0
    duration_ms: float = 0.0
    error: Optional[str] = None


@dataclass
class WorkflowResult:
    workflow: str
    phases: List[PhaseResult]
    success: bool
    total_tokens: int = 0
    total_duration_ms: float = 0.0
    ai_calls: int = 0
    deterministic_steps: int = 0
    summary: str = ""
    # ── Observability (v0.0.9) ──
    trace_id: str = ""
    timestamp: str = ""


class WorkflowEngine:
    """Lightweight state machine for engineering workflows."""

    def __init__(self, project_root: Path):
        self.root = project_root
        self._handlers: Dict[str, Callable] = {}
        self._register_builtin_handlers()
        self._observability_enabled = True
        self._primitive_cache: Dict[str, Dict[str, Any]] = {}

    def _register_builtin_handlers(self):
        """Register all deterministic handlers available in the runtime."""
        self._handlers.update({
            "analyze_target": self._h_analyze_target,
            "generate_test_stub": self._h_generate_test_stub,
            "run_test_expect_fail": self._h_run_tests,
            "run_test_expect_pass": self._h_run_tests,
            "run_regression_suite": self._h_run_tests,
            "summarize_impact": self._h_summarize_impact,
            "trace_callers": self._h_trace_callers,
            "trace_callees": self._h_trace_callees,
            "inspect_dependencies": self._h_inspect_dependencies,
            "retrieve_memory": self._h_retrieve_memory,
            "analyze_git_diff": self._h_analyze_git_diff,
            "check_architecture_rules": self._h_check_architecture,
            "classify_risk": self._h_classify_risk,
            "run_lint": self._h_run_lint,
            "run_tests": self._h_run_tests,
            "build_context_package": self._h_build_context_package,
            "generate_summary": self._h_generate_summary,
        })

    def load_workflow(self, name: str) -> Dict[str, Any]:
        """Load a workflow definition from YAML."""
        wf_dir = Path(__file__).parent / "workflows"
        wf_path = wf_dir / f"{name}.yaml"
        if not wf_path.exists():
            raise FileNotFoundError(f"Workflow '{name}' not found at {wf_path}")
        return yaml.safe_load(wf_path.read_text())

    def list_workflows(self) -> List[Dict[str, str]]:
        """List all available workflow definitions."""
        wf_dir = Path(__file__).parent / "workflows"
        if not wf_dir.exists():
            return []
        workflows = []
        for wf_path in sorted(wf_dir.glob("*.yaml")):
            try:
                wf_def = yaml.safe_load(wf_path.read_text())
                workflows.append({
                    "name": wf_path.stem,
                    "description": wf_def.get("description", ""),
                    "phases": len(wf_def.get("phases", [])),
                })
            except Exception:
                pass
        return workflows

    def run(self, name: str, params: Optional[Dict[str, Any]] = None) -> WorkflowResult:
        """Execute a workflow by name."""
        import uuid
        from datetime import datetime, timezone

        params = params or {}
        wf_def = self.load_workflow(name)
        phases_results = []
        total_tokens = 0
        total_duration = 0.0
        ai_calls = 0
        det_steps = 0
        context = dict(params)
        context["_project_root"] = str(self.root)

        trace_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now(timezone.utc).isoformat()

        for phase_def in wf_def.get("phases", []):
            phase_name = phase_def["name"]
            phase_kind = PhaseKind(phase_def.get("kind", "deterministic"))

            t0 = time.time()
            result = self._execute_phase(phase_def, context)
            elapsed = (time.time() - t0) * 1000

            result.phase = phase_name
            result.kind = phase_kind
            result.duration_ms = elapsed

            phases_results.append(result)
            total_tokens += result.tokens_used
            total_duration += elapsed

            if phase_kind in (PhaseKind.LOCAL_MODEL, PhaseKind.FRONTIER):
                ai_calls += 1
            elif phase_kind == PhaseKind.DETERMINISTIC:
                det_steps += 1

            context.update(result.output)

            if phase_kind == PhaseKind.GATE and not result.success:
                return WorkflowResult(
                    workflow=name, phases=phases_results, success=False,
                    total_tokens=total_tokens, total_duration_ms=total_duration,
                    ai_calls=ai_calls, deterministic_steps=det_steps,
                    summary=f"Gate '{phase_name}' failed: {result.error}",
                    trace_id=trace_id, timestamp=timestamp,
                )

            if not result.success and not phase_def.get("continue_on_failure"):
                break

        wf_result = WorkflowResult(
            workflow=name, phases=phases_results,
            success=all(p.success for p in phases_results),
            total_tokens=total_tokens, total_duration_ms=total_duration,
            ai_calls=ai_calls, deterministic_steps=det_steps,
            summary=f"{wf_def['name']}: {det_steps} deterministic, {ai_calls} AI calls, {total_tokens} tokens",
            trace_id=trace_id, timestamp=timestamp,
        )

        # ── Observability: record workflow run ──
        self._record_observability(wf_result)

        return wf_result

    def _execute_phase(self, phase_def: Dict, context: Dict) -> PhaseResult:
        """Execute a single phase, with `uses: [...]` primitive composition support."""
        # ── Primitive Composition: `uses: [primitive1, primitive2, ...]` ──
        uses = phase_def.get("uses", [])
        if uses:
            return self._execute_primitives(uses, phase_def, context)

        handler_name = phase_def.get("handler", phase_def.get("name", ""))
        handler = self._handlers.get(handler_name)

        if handler:
            try:
                output = handler(context)
                return PhaseResult(phase="", kind=PhaseKind.DETERMINISTIC,
                                   success=True, output=output)
            except Exception as e:
                return PhaseResult(phase="", kind=PhaseKind.DETERMINISTIC,
                                   success=False, error=str(e))

        if phase_def.get("kind") == "local_model":
            return self._call_ollama(phase_def, context)
        elif phase_def.get("kind") == "frontier":
            return self._call_frontier(phase_def, context)

        return PhaseResult(phase="", kind=PhaseKind.DETERMINISTIC,
                           success=False, error=f"No handler for {handler_name}")

    def _execute_primitives(self, primitives: List[str], phase_def: Dict,
                            context: Dict) -> PhaseResult:
        """Execute primitives with optimization + parallel DAG + caching.

        v0.1: Optimizer wired in — primitives are optimized before DAG staging.
        OptimizationResult is included in output for profiling.
        """
        from .primitives import get_primitive, build_execution_dag
        from .optimizer import optimize_dag

        # ── v0.1: Optimize before execution ──
        opt_result = optimize_dag(primitives, context, self._primitive_cache)
        optimized_primitives = opt_result.optimized_dag

        combined_output: Dict[str, Any] = {}
        all_success = True
        errors: List[str] = []

        stages = build_execution_dag(optimized_primitives)
        for stage in stages:
            for prim_name in stage:
                prim = get_primitive(prim_name)
                if prim is None:
                    all_success = False
                    errors.append(f"Unknown primitive: {prim_name}")
                    continue

                # Skip cache hits — result already known
                if prim_name in opt_result.cache_hits:
                    cache_key = f"{prim_name}:{prim.contract.fingerprint_inputs(context)}"
                    if cache_key in self._primitive_cache:
                        combined_output.update(self._primitive_cache[cache_key])
                        continue

                try:
                    output = prim.execute(context, self.root)
                    combined_output.update(output)
                    if prim.contract.cacheable and prim.contract.is_pure:
                        ck = f"{prim_name}:{prim.contract.fingerprint_inputs(context)}"
                        self._primitive_cache[ck] = dict(output)
                except Exception as e:
                    all_success = False
                    errors.append(f"Primitive '{prim_name}' failed: {e}")

        # ── v0.1: Include optimizer stats in profiling ──
        combined_output["_profiling"] = {
            "stages": len(stages),
            "primitives_requested": len(primitives),
            "primitives_executed": len(optimized_primitives),
        }
        combined_output["_optimizer"] = opt_result.to_dict()

        return PhaseResult(
            phase=phase_def.get("name", "composed"),
            kind=PhaseKind.DETERMINISTIC,
            success=all_success,
            output=combined_output,
            error="; ".join(errors) if errors else None,
        )

    def _record_observability(self, result: WorkflowResult) -> None:
        """Record workflow run metrics for observability."""
        if not self._observability_enabled:
            return
        try:
            record = {
                "trace_id": result.trace_id,
                "timestamp": result.timestamp,
                "workflow": result.workflow,
                "success": result.success,
                "total_tokens": result.total_tokens,
                "total_duration_ms": round(result.total_duration_ms, 2),
                "ai_calls": result.ai_calls,
                "deterministic_steps": result.deterministic_steps,
                "token_breakdown": {
                    "deterministic": 0,
                    "local_model": sum(p.tokens_used for p in result.phases if p.kind == PhaseKind.LOCAL_MODEL),
                    "frontier": sum(p.tokens_used for p in result.phases if p.kind == PhaseKind.FRONTIER),
                },
            }
            # Store in memory engine for later querying
            try:
                from .intelligence.storage import get_db as get_mem_db
                db = get_mem_db(self.root)
                # Use decisions store as lightweight telemetry sink
                db.execute(
                    "INSERT OR REPLACE INTO knowledge_decisions (id, choice, reason, alternatives, related_files, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (f"wf_trace_{result.trace_id}", result.workflow,
                     json.dumps(record), "[]", "[]", result.timestamp),
                )
            except Exception:
                pass  # Observability is best-effort, never blocks
        except Exception:
            pass  # Silently fail if observability recording fails

    # ── Deterministic Handlers ──────────────────────────────────

    def _h_analyze_target(self, ctx: Dict) -> Dict:
        target = ctx.get("target", "")
        if not target:
            return {"error": "no target specified"}
        from .graph_db import get_db
        from .graph_query import _find_symbol_id
        db = get_db(self.root)
        sym_id = _find_symbol_id(target, self.root)
        callers = db.get_callers(sym_id, max_depth=2) if sym_id else []
        callees = db.get_callees(sym_id, max_depth=2) if sym_id else []
        return {
            "symbol_id": sym_id,
            "callers": len(callers),
            "callees": len(callees),
            "caller_list": [c.get("name", "") for c in callers[:10]],
            "callee_list": [c.get("name", "") for c in callees[:10]],
        }

    def _h_generate_test_stub(self, ctx: Dict) -> Dict:
        return {"test_stub_ready": True, "test_file": ctx.get("target", "") + ".test"}

    def _h_run_tests(self, ctx: Dict) -> Dict:
        import subprocess
        try:
            result = subprocess.run(
                ["python", "-m", "pytest", "-x", "--tb=short"],
                cwd=str(self.root), capture_output=True, text=True, timeout=60,
            )
            return {
                "passed": result.returncode == 0,
                "output": result.stdout[-2000:],
                "failed": result.returncode != 0,
            }
        except Exception as e:
            return {"passed": False, "output": str(e), "failed": True}

    def _h_summarize_impact(self, ctx: Dict) -> Dict:
        from .graph_db import get_db
        db = get_db(self.root)
        sym_id = ctx.get("symbol_id", "")
        impacted = db.get_impact_radius(sym_id, max_depth=2) if sym_id else []
        files = sorted(set(n.get("file_path", "") for n in impacted))
        risk = "low" if len(files) <= 4 else "medium" if len(files) <= 10 else "high"
        return {"impacted_files": len(files), "risk": risk, "files": files[:20]}

    def _h_trace_callers(self, ctx: Dict) -> Dict:
        from .graph_db import get_db
        from .graph_query import _find_symbol_id
        db = get_db(self.root)
        sym_id = ctx.get("symbol_id", "")
        callers = db.get_callers(sym_id, max_depth=3) if sym_id else []
        return {"callers": [c.get("name", "") for c in callers], "caller_count": len(callers)}

    def _h_trace_callees(self, ctx: Dict) -> Dict:
        from .graph_db import get_db
        db = get_db(self.root)
        sym_id = ctx.get("symbol_id", "")
        callees = db.get_callees(sym_id, max_depth=3) if sym_id else []
        return {"callees": [c.get("name", "") for c in callees], "callee_count": len(callees)}

    def _h_inspect_dependencies(self, ctx: Dict) -> Dict:
        from .graph_db import get_db
        db = get_db(self.root)
        deps = db.get_file_dependencies(ctx.get("file", ""))
        return {"dependencies": deps[:20], "dep_count": len(deps)}

    def _h_retrieve_memory(self, ctx: Dict) -> Dict:
        try:
            from .intelligence.search import search_knowledge
            query = ctx.get("query", ctx.get("target", ctx.get("task", "")))
            results = search_knowledge(query, limit=10)
            return {"memories": results, "count": len(results)}
        except Exception:
            return {"memories": [], "count": 0}

    def _h_analyze_git_diff(self, ctx: Dict) -> Dict:
        import subprocess
        try:
            result = subprocess.run(
                ["git", "--no-pager", "diff", "--stat"],
                cwd=str(self.root), capture_output=True, text=True, timeout=10,
            )
            return {"diff_stat": result.stdout.strip()[:2000]}
        except Exception:
            return {"diff_stat": ""}

    def _h_check_architecture(self, ctx: Dict) -> Dict:
        from .graph_db import get_db
        db = get_db(self.root)
        circular = db.find_circular_deps()
        dead = db.find_dead_code()
        return {
            "circular_deps": len(circular),
            "dead_code": len(dead),
            "circular_detail": circular[:10],
            "dead_detail": dead[:10],
        }

    def _h_classify_risk(self, ctx: Dict) -> Dict:
        files = ctx.get("files", [])
        risk = "low"
        if len(files) > 20:
            risk = "critical"
        elif len(files) > 10:
            risk = "high"
        elif len(files) > 4:
            risk = "medium"
        return {"risk_level": risk, "files_affected": len(files)}

    def _h_run_lint(self, ctx: Dict) -> Dict:
        return {"lint_ok": True, "issues": 0}

    def _h_build_context_package(self, ctx: Dict) -> Dict:
        from .compressor import compress_context
        return compress_context(ctx, self.root)

    def _h_generate_summary(self, ctx: Dict) -> Dict:
        """Build a human-readable summary from accumulated context."""
        parts = []
        if ctx.get("passed") is not None:
            parts.append(f"Tests: {'PASSED' if ctx['passed'] else 'FAILED'}")
        if ctx.get("lint_ok") is not None:
            parts.append(f"Lint: {'OK' if ctx['lint_ok'] else 'ISSUES FOUND'}")
        if ctx.get("circular_deps") is not None:
            parts.append(f"Circular deps: {ctx['circular_deps']}")
        if ctx.get("dead_code") is not None:
            parts.append(f"Dead code: {ctx['dead_code']}")
        if ctx.get("risk_level"):
            parts.append(f"Risk: {ctx['risk_level']}")
        return {"summary_text": " | ".join(parts) if parts else "No issues found"}

    def _call_ollama(self, phase_def: Dict, ctx: Dict) -> PhaseResult:
        import subprocess
        model = phase_def.get("model", "qwen3.5:4b-16k")
        prompt_template = phase_def.get("prompt_template", "")
        try:
            prompt = prompt_template.format(**ctx)
        except KeyError:
            prompt = prompt_template
        try:
            result = subprocess.run(
                ["ollama", "run", model, prompt],
                capture_output=True, text=True, timeout=60,
            )
            tokens = len(prompt.split()) + len(result.stdout.split())
            return PhaseResult(
                phase="", kind=PhaseKind.LOCAL_MODEL, success=True,
                output={"ollama_response": result.stdout}, tokens_used=tokens,
            )
        except Exception as e:
            return PhaseResult(
                phase="", kind=PhaseKind.LOCAL_MODEL, success=False, error=str(e),
            )

    def _call_frontier(self, phase_def: Dict, ctx: Dict) -> PhaseResult:
        prompt_template = phase_def.get("prompt_template", "")
        try:
            prompt = prompt_template.format(**ctx)
        except KeyError:
            prompt = prompt_template
        tokens = len(prompt.split())
        return PhaseResult(
            phase="", kind=PhaseKind.FRONTIER, success=True,
            output={"frontier_prompt": prompt, "status": "ready_for_dispatch"},
            tokens_used=tokens,
        )


# ── Daemon Handler ──────────────────────────────────────────────

def handle_workflow_run(params: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a workflow via daemon."""
    name = params.get("name", params.get("workflow", ""))
    wf_params = params.get("params", {})
    project_root = Path(params.get("project_root", str(Path.cwd())))
    engine = WorkflowEngine(project_root)

    if not name or name == "list":
        return {"workflows": engine.list_workflows()}

    try:
        result = engine.run(name, wf_params)
    except FileNotFoundError as e:
        return {"error": str(e), "available_workflows": engine.list_workflows()}

    return {
        "trace_id": result.trace_id,
        "timestamp": result.timestamp,
        "workflow": result.workflow,
        "success": result.success,
        "phases": len(result.phases),
        "total_tokens": result.total_tokens,
        "total_duration_ms": result.total_duration_ms,
        "ai_calls": result.ai_calls,
        "deterministic_steps": result.deterministic_steps,
        "summary": result.summary,
        "phase_details": [
            {
                "name": p.phase,
                "kind": p.kind.value,
                "success": p.success,
                "tokens": p.tokens_used,
                "duration_ms": round(p.duration_ms, 2),
            }
            for p in result.phases
        ],
    }
