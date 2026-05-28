"""
Adversarial tests: subagent runtime binding.

Verifies that:
1. generate_subagent_prompt() includes all runtime constraints (FORBIDDEN, REQUIRED, graph_boundary, tier)
2. enforce_subagent_boundary() detects out-of-boundary file access
3. validate_subagent_execution() catches frontier usage on local_model tasks
4. compile_cognition_package() returns a package with all required fields
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from context_engine.subagent_wiring import (
    CognitionPackage,
    RUNTIME_CONSTRAINTS_TEMPLATE,
    compile_cognition_package,
    enforce_subagent_boundary,
    generate_subagent_prompt,
    validate_subagent_execution,
)


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


@pytest.fixture
def sample_cognition_package() -> Dict[str, Any]:
    """A minimal CognitionPackage dict for testing prompt generation."""
    return {
        "graph_boundary": {
            "target": "User",
            "callers": ["get_user", "list_users", "update_user"],
            "callees": ["db_query", "validate_email"],
            "max_depth": 2,
            "total_callers": 3,
            "total_callees": 2,
        },
        "context_package": {
            "question": "Create a DTO for the User entity",
            "target": "User",
            "files": ["src/models/user.py", "src/repositories/user_repo.py"],
            "memories": [],
            "modules": {},
        },
        "tier_recommendation": "local_model",
        "allowed_primitives": [
            "graph.analyze_target",
            "memory.recall",
            "context.compress",
        ],
        "invalidation_scope": "symbol",
        "token_budget": 2000,
    }


@pytest.fixture
def sample_graph_boundary() -> Dict[str, Any]:
    """A graph boundary fixture for boundary enforcement tests."""
    return {
        "target": "UserService",
        "callers": [
            {"name": "UserController", "file_path": "src/controllers/user_controller.py"},
            {"name": "UserRoutes", "file_path": "src/routes/user_routes.py"},
        ],
        "callees": [
            {"name": "UserRepository", "file_path": "src/repositories/user_repo.py"},
            {"name": "Database", "file_path": "src/db/database.py"},
        ],
        "max_depth": 2,
        "total_callers": 2,
        "total_callees": 2,
    }


@pytest.fixture
def event_bus_with_escalation():
    """Set up an event bus with a FRONTIER_ESCALATION event on it.

    Returns the task string so tests can reference it.
    """
    from context_engine.event_bus import reset_event_bus, get_event_bus, FRONTIER_ESCALATION

    reset_event_bus()
    bus = get_event_bus()

    task = "create DTO with complex routing logic"
    bus.emit(FRONTIER_ESCALATION, {
        "task": task,
        "expected_tier": "local_model",
        "reason": "confidence > 0.7 in should_escalate_to_frontier",
    })

    return task


# ═══════════════════════════════════════════════════════════════════
# Test 1: Prompt generation includes all runtime constraints
# ═══════════════════════════════════════════════════════════════════

class TestPromptGeneration:
    """Verify generate_subagent_prompt() produces a properly bound prompt."""

    def test_prompt_contains_runtime_constraints(self, sample_cognition_package):
        """Prompt must include the RUNTIME EXECUTION CONSTRAINT section."""
        prompt = generate_subagent_prompt(sample_cognition_package)

        assert "RUNTIME EXECUTION CONSTRAINT" in prompt, \
            "Prompt is missing RUNTIME EXECUTION CONSTRAINT header"
        assert "FORBIDDEN" in prompt, \
            "Prompt is missing FORBIDDEN section"
        assert "REQUIRED" in prompt, \
            "Prompt is missing REQUIRED section"
        assert "MANDATORY" in prompt, \
            "Prompt is missing MANDATORY label"

    def test_prompt_contains_graph_boundary(self, sample_cognition_package):
        """Prompt must include the graph boundary details."""
        prompt = generate_subagent_prompt(sample_cognition_package)

        assert "graph_boundary" in prompt.lower() or "CALL-GRAPH BOUNDARY" in prompt, \
            "Prompt is missing graph boundary information"

    def test_prompt_contains_tier_recommendation(self, sample_cognition_package):
        """Prompt must include the tier recommendation."""
        prompt = generate_subagent_prompt(sample_cognition_package)

        assert "local_model" in prompt.lower(), \
            "Prompt is missing tier recommendation"
        assert "ollama" in prompt.lower(), \
            "Prompt is missing Ollama model reference for local_model tier"

    def test_prompt_contains_forbidden_rules(self, sample_cognition_package):
        """Prompt must explicitly forbid grep/scan and out-of-boundary reads."""
        prompt = generate_subagent_prompt(sample_cognition_package)

        assert "grep" in prompt or "find" in prompt, \
            "Prompt does not forbid grep/find exploration"
        assert "terminal" in prompt.lower(), \
            "Prompt does not forbid terminal usage"
        assert "outside your assigned" in prompt, \
            "Prompt does not forbid out-of-boundary reads"

    def test_prompt_contains_required_tools(self, sample_cognition_package):
        """Prompt must mandate aihelper tool usage."""
        prompt = generate_subagent_prompt(sample_cognition_package)

        assert "aihelper_context" in prompt, \
            "Prompt does not mandate aihelper_context"
        assert "aihelper_symbol_lookup" in prompt, \
            "Prompt does not mandate aihelper_symbol_lookup"
        assert "aihelper_callers" in prompt or "aihelper_callees" in prompt, \
            "Prompt does not mandate aihelper_callers/callees"

    def test_prompt_contains_allowed_primitives(self, sample_cognition_package):
        """Prompt must list allowed primitives."""
        prompt = generate_subagent_prompt(sample_cognition_package)

        assert "ALLOWED_PRIMITIVES" in prompt, \
            "Prompt is missing ALLOWED_PRIMITIVES"
        assert "graph.analyze_target" in prompt, \
            "Prompt is missing graph.analyze_target in ALLOWED_PRIMITIVES"

    def test_prompt_contains_invalidation_scope(self, sample_cognition_package):
        """Prompt must include invalidation scope guidance."""
        prompt = generate_subagent_prompt(sample_cognition_package)

        assert "scope" in prompt.lower() or "invalidation" in prompt.lower(), \
            "Prompt is missing scope/invalidation information"

    def test_prompt_contains_token_budget(self, sample_cognition_package):
        """Prompt must include the token budget."""
        prompt = generate_subagent_prompt(sample_cognition_package)

        assert "TOKEN_BUDGET" in prompt, \
            "Prompt is missing TOKEN_BUDGET"
        assert "2000" in prompt, \
            "Prompt does not contain the token budget value"

    def test_prompt_all_tiers_have_model_guidance(self):
        """All three tier values must produce model guidance in the prompt."""
        tiers = ["deterministic", "local_model", "frontier"]
        tier_indicators = {
            "deterministic": "deterministic execution",
            "local_model": "ollama",
            "frontier": "frontier model",
        }

        for tier_value, indicator in tier_indicators.items():
            pkg = {
                "graph_boundary": {"target": "T", "callers": [], "callees": [],
                                   "max_depth": 1, "total_callers": 0, "total_callees": 0},
                "context_package": {"question": "test", "target": "T",
                                    "files": [], "memories": [], "modules": {}},
                "tier_recommendation": tier_value,
                "allowed_primitives": [],
                "invalidation_scope": "symbol",
                "token_budget": 2000,
            }
            prompt = generate_subagent_prompt(pkg)
            assert indicator in prompt.lower(), \
                f"Tier '{tier_value}' missing indicator '{indicator}' in prompt"


# ═══════════════════════════════════════════════════════════════════
# Test 2: Boundary enforcement detects out-of-boundary file access
# ═══════════════════════════════════════════════════════════════════

class TestBoundaryEnforcement:
    """Verify enforce_subagent_boundary() catches boundary violations."""

    def test_all_files_within_boundary(self, sample_graph_boundary):
        """Files within the graph boundary must pass."""
        touched = [
            "src/controllers/user_controller.py",
            "src/repositories/user_repo.py",
        ]
        result = enforce_subagent_boundary(touched, sample_graph_boundary)

        assert result["valid"] is True, \
            f"Expected valid=True but got violations: {result['boundary_violations']}"
        assert len(result["boundary_violations"]) == 0

    def test_out_of_boundary_files_flagged(self, sample_graph_boundary):
        """Files outside the graph boundary must be flagged."""
        touched = [
            "src/controllers/user_controller.py",
            "src/shared/secret_credentials.py",  # outside boundary
            "src/config/database_passwords.py",  # outside boundary
        ]
        result = enforce_subagent_boundary(touched, sample_graph_boundary)

        assert result["valid"] is False, \
            "Boundary violation not detected"
        violations = result["boundary_violations"]
        assert any("secret_credentials" in v for v in violations), \
            "Missing violation for secret_credentials.py"
        assert any("database_passwords" in v for v in violations), \
            "Missing violation for database_passwords.py"

    def test_empty_touched_files_passes(self, sample_graph_boundary):
        """An empty touched_files list must pass (no violations)."""
        result = enforce_subagent_boundary([], sample_graph_boundary)

        assert result["valid"] is True
        assert len(result["boundary_violations"]) == 0

    def test_empty_graph_boundary_skips_checking(self):
        """When graph boundary has no files, boundary enforcement is lenient."""
        empty_boundary = {
            "target": "T",
            "callers": [],
            "callees": [],
            "max_depth": 1,
            "total_callers": 0,
            "total_callees": 0,
        }
        touched = ["any/file.py", "outside/boundary.py"]
        result = enforce_subagent_boundary(touched, empty_boundary)

        # With no allowed_files, we can't flag anything
        assert result["valid"] is True
        assert result["boundary_count"] == 0

    def test_partial_boundary_violation(self, sample_graph_boundary):
        """Mixed files (some in, some out) must detect only the out ones."""
        touched = [
            "src/repositories/user_repo.py",     # in boundary
            "src/db/database.py",                 # in boundary
            "src/controllers/admin_controller.py", # NOT in boundary
        ]
        result = enforce_subagent_boundary(touched, sample_graph_boundary)

        assert result["valid"] is False
        violation_files = [v for v in result["boundary_violations"]]
        assert any("admin_controller" in v for v in violation_files)
        # Ensure only the out-of-boundary files are flagged
        assert all(
            "user_repo" not in v and "database.py" not in v
            for v in violation_files
        )


# ═══════════════════════════════════════════════════════════════════
# Test 3: Tier violation detection
# ═══════════════════════════════════════════════════════════════════

class TestTierViolationDetection:
    """Verify validate_subagent_execution() catches tier violations."""

    def test_local_model_task_with_escalation_flagged(
        self, event_bus_with_escalation,
    ):
        """A local_model task that triggered a frontier escalation must be flagged."""
        result = validate_subagent_execution(
            task=event_bus_with_escalation,
            tier_recommendation="local_model",
        )

        assert result["valid"] is False, \
            "Expected validation to fail for local_model with frontier escalation"
        assert len(result["violations"]) > 0, \
            "Expected at least one violation"
        assert result["escalation_count"] >= 1, \
            "Expected at least 1 escalation event"
        assert result["tier"] == "local_model"

    def test_frontier_task_with_escalation_not_flagged(
        self, event_bus_with_escalation,
    ):
        """A frontier-tier task with escalation must NOT be flagged."""
        result = validate_subagent_execution(
            task=event_bus_with_escalation,
            tier_recommendation="frontier",
        )

        # Frontier tasks are allowed to escalate — no violation
        assert result["valid"] is True, \
            "Frontier task should not have violations for escalation"
        assert len(result["violations"]) == 0

    def test_no_escalation_events_passes(self):
        """No escalation events in bus must result in valid=True."""
        from context_engine.event_bus import reset_event_bus
        reset_event_bus()

        result = validate_subagent_execution(
            task="simple dto task",
            tier_recommendation="local_model",
        )

        assert result["valid"] is True
        assert result["escalation_count"] == 0

    def test_deterministic_task_ignores_escalation(self, event_bus_with_escalation):
        """A deterministic-tier task with escalation must not be flagged."""
        result = validate_subagent_execution(
            task=event_bus_with_escalation,
            tier_recommendation="deterministic",
        )

        # Deterministic tasks are not subject to the local_model frontier constraint
        assert result["valid"] is True
        assert len(result["violations"]) == 0

    def test_escalation_count_is_accurate(self, event_bus_with_escalation):
        """Escalation count must match the number of events emitted."""
        # Emit a second escalation for the same task
        from context_engine.event_bus import get_event_bus, FRONTIER_ESCALATION

        bus = get_event_bus()
        bus.emit(FRONTIER_ESCALATION, {
            "task": event_bus_with_escalation,
            "expected_tier": "local_model",
            "reason": "second escalation",
        })

        result = validate_subagent_execution(
            task=event_bus_with_escalation,
            tier_recommendation="local_model",
        )

        assert result["escalation_count"] >= 2, \
            f"Expected >=2 escalations, got {result['escalation_count']}"
        assert result["valid"] is False


# ═══════════════════════════════════════════════════════════════════
# Test 4: Cognition package includes required fields
# ═══════════════════════════════════════════════════════════════════

class TestCognitionPackageCompleteness:
    """Verify compile_cognition_package() returns all required fields."""

    def test_package_has_graph_boundary(self, project_root):
        """Cognition package must contain graph_boundary."""
        pkg = compile_cognition_package(
            task="create a DTO for User",
            target="User",
            project_root=project_root,
            max_tokens=2000,
        )

        assert "graph_boundary" in pkg, \
            "Package missing graph_boundary"
        gb = pkg["graph_boundary"]
        assert "target" in gb, \
            "graph_boundary missing target"
        assert "callers" in gb, \
            "graph_boundary missing callers"
        assert "callees" in gb, \
            "graph_boundary missing callees"

    def test_package_has_tier_recommendation(self, project_root):
        """Cognition package must contain tier_recommendation."""
        pkg = compile_cognition_package(
            task="create a DTO for User",
            target="User",
            project_root=project_root,
            max_tokens=2000,
        )

        assert "tier_recommendation" in pkg, \
            "Package missing tier_recommendation"
        assert pkg["tier_recommendation"] in ("deterministic", "local_model", "frontier"), \
            f"Invalid tier: {pkg['tier_recommendation']}"

    def test_package_has_allowed_primitives(self, project_root):
        """Cognition package must contain allowed_primitives."""
        pkg = compile_cognition_package(
            task="create a DTO for User",
            target="User",
            project_root=project_root,
            max_tokens=2000,
        )

        assert "allowed_primitives" in pkg, \
            "Package missing allowed_primitives"
        assert isinstance(pkg["allowed_primitives"], list), \
            "allowed_primitives must be a list"

    def test_package_has_invalidation_scope(self, project_root):
        """Cognition package must contain invalidation_scope."""
        pkg = compile_cognition_package(
            task="create a DTO for User",
            target="User",
            project_root=project_root,
            max_tokens=2000,
        )

        assert "invalidation_scope" in pkg, \
            "Package missing invalidation_scope"
        assert pkg["invalidation_scope"] in ("symbol", "file", "module"), \
            f"Invalid invalidation_scope: {pkg['invalidation_scope']}"

    def test_package_has_token_budget(self, project_root):
        """Cognition package must contain token_budget."""
        pkg = compile_cognition_package(
            task="create a DTO for User",
            target="User",
            project_root=project_root,
            max_tokens=4000,
        )

        assert "token_budget" in pkg, \
            "Package missing token_budget"
        assert pkg["token_budget"] == 4000, \
            f"Expected token_budget=4000, got {pkg['token_budget']}"

    def test_package_has_context_package(self, project_root):
        """Cognition package must contain context_package."""
        pkg = compile_cognition_package(
            task="create a DTO for User",
            target="User",
            project_root=project_root,
            max_tokens=2000,
        )

        assert "context_package" in pkg, \
            "Package missing context_package"
        ctx = pkg["context_package"]
        assert isinstance(ctx, dict), \
            "context_package must be a dict"

    def test_field_types_are_correct(self, project_root):
        """All cognition package fields must have correct types."""
        pkg = compile_cognition_package(
            task="create a DTO for User",
            target="User",
            project_root=project_root,
            max_tokens=2000,
        )

        assert isinstance(pkg.get("graph_boundary"), dict)
        assert isinstance(pkg.get("context_package"), dict)
        assert isinstance(pkg.get("tier_recommendation"), str)
        assert isinstance(pkg.get("allowed_primitives"), list)
        assert isinstance(pkg.get("invalidation_scope"), str)
        assert isinstance(pkg.get("token_budget"), int)


# ═══════════════════════════════════════════════════════════════════
# Test 5: RUNTIME_CONSTRAINTS_TEMPLATE formatability
# ═══════════════════════════════════════════════════════════════════

class TestRuntimeConstraintsTemplate:
    """Verify the RUNTIME_CONSTRAINTS_TEMPLATE formats correctly."""

    def test_template_formats_all_fields(self):
        """Template must accept all format fields without error."""
        formatted = RUNTIME_CONSTRAINTS_TEMPLATE.format(
            graph_boundary="target=User, callers=3, callees=2, max_depth=2",
            tier_recommendation="local_model",
            invalidation_scope="symbol",
            allowed_primitives="graph.analyze_target, memory.recall",
            token_budget=2000,
        )

        assert "target=User" in formatted
        assert "local_model" in formatted
        assert "symbol" in formatted
        assert "graph.analyze_target" in formatted
        assert "2000" in formatted

    def test_template_mentions_execution_shard(self):
        """Template must identify the subagent as an execution shard."""
        formatted = RUNTIME_CONSTRAINTS_TEMPLATE.format(
            graph_boundary="target=T",
            tier_recommendation="local_model",
            invalidation_scope="symbol",
            allowed_primitives="",
            token_budget=1000,
        )

        assert "execution shard" in formatted, \
            "Template must identify subagent as execution shard"
        assert "NOT a free autonomous agent" in formatted, \
            "Template must clarify it's not autonomous"
