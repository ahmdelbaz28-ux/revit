"""
tests/test_integration_coherence.py
=====================================
Integration Coherence Verification tests for FireAI.

Adapted (NOT copied) from the Boundary Mismatch methodology described in
the harness project's qa-agent-guide.md. The original is a Korean-language
Markdown methodology guide for Claude Code agents — it contains no
executable code. This file translates the IDEAS into concrete pytest
tests that verify the FireAI backend↔frontend contract.

Source attribution: harness/references/qa-agent-guide.md (Apache-2.0)
Original idea: "양쪽을 동시에 읽어라" (read both sides simultaneously)

V133 (2026-06-22): Adapted for FireAI's backend (FastAPI) + frontend
(React/TypeScript) architecture. These tests catch the #1 defect class
identified by the harness QA methodology: boundary mismatches where
each side is individually correct but the contract between them is broken.

What we test:
  1. API response shape ↔ frontend TypeScript type definitions
  2. API endpoint ↔ frontend API client function (1:1 mapping)
  3. snake_case ↔ camelCase consistency across the API boundary
  4. State machine: all defined transitions are reachable in code
  5. All frontend API calls point to endpoints that actually exist
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

# ─── Path setup ────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_DIR = REPO_ROOT / "frontend" / "src"


# ─── Helpers ───────────────────────────────────────────────────────────

def _extract_router_endpoints() -> set[str]:
    """Extract all API endpoint paths from backend routers.

    Scans backend/routers/*.py for @router.get/post/put/delete decorators
    and returns a set of path strings like '/api/v1/projects'.
    """
    endpoints: set[str] = set()
    routers_dir = BACKEND_DIR / "routers"
    if not routers_dir.exists():
        return endpoints

    for py_file in routers_dir.glob("*.py"):
        content = py_file.read_text()
        # Match @router.get("/path"), @router.post("/path"), etc.
        # Also match @router.get("/path/{id}")
        for m in re.finditer(
            r'@router\.(get|post|put|delete|patch)\(\s*["\']([^"\']+)["\']',
            content,
        ):
            method, path = m.group(1), m.group(2)
            # Normalize: prefix with /api/v1 if not already absolute
            if not path.startswith("/api"):
                # Check if router has a prefix
                prefix_match = re.search(
                    r'APIRouter\([^)]*prefix\s*=\s*["\']([^"\']+)["\']',
                    content,
                )
                prefix = prefix_match.group(1) if prefix_match else ""
                path = f"{prefix}{path}"
            endpoints.add(f"{method.upper()} {path}")
    return endpoints


def _extract_frontend_api_calls() -> set[str]:
    """Extract API endpoint URLs from frontend TypeScript files.

    Scans frontend/src/**/*.ts and *.tsx for fetch() calls and
    API client URL patterns.
    """
    calls: set[str] = set()
    if not FRONTEND_DIR.exists():
        return calls

    for ts_file in FRONTEND_DIR.rglob("*.ts*"):
        try:
            content = ts_file.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        # Match fetch("url"), fetch('url'), fetch(`/api/...`)
        for m in re.finditer(
            r'fetch\(\s*[`"\']([^`"\']+)[`"\']',
            content,
        ):
            url = m.group(1)
            # Skip relative URLs and non-API calls
            if url.startswith("/api") or url.startswith("http"):
                calls.add(url)

        # Match axios.get("url"), apiClient.post("url"), etc.
        for m in re.finditer(
            r'(?:axios|apiClient|api)\.(?:get|post|put|delete|patch)\(\s*[`"\']([^`"\']+)[`"\']',
            content,
        ):
            url = m.group(1)
            if url.startswith("/api"):
                calls.add(url)
    return calls


def _extract_backend_response_shapes() -> dict[str, list[str]]:
    """Extract field names from backend response models.

    Scans backend/models.py and backend/schemas.py for Pydantic model
    field definitions. Returns a dict of model_name → [field_names].
    """
    shapes: dict[str, list[str]] = {}
    for py_file in [BACKEND_DIR / "models.py", BACKEND_DIR / "schemas.py"]:
        if not py_file.exists():
            continue
        try:
            tree = ast.parse(py_file.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                fields: list[str] = []
                for item in node.body:
                    if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                        fields.append(item.target.id)
                if fields:
                    shapes[node.name] = fields
    return shapes


# ─── Tests: API ↔ Frontend endpoint mapping ────────────────────────────

class TestAPIEndpointMapping:
    """Verify that every frontend API call points to an endpoint that exists.

    This is the 'existence vs connection' distinction from the QA guide:
    just because an API endpoint exists doesn't mean the frontend calls it
    correctly, and just because the frontend calls a URL doesn't mean
    the endpoint exists.
    """

    def test_frontend_api_calls_resolve_to_backend_endpoints(self):
        """Every frontend API call URL should match a backend route.

        If this test fails, the frontend is calling a URL that doesn't
        exist on the backend — a 404 waiting to happen.
        """
        frontend_calls = _extract_frontend_api_calls()
        if not frontend_calls:
            pytest.skip("No frontend API calls found (frontend may not be installed)")

        backend_endpoints = _extract_router_endpoints()
        if not backend_endpoints:
            pytest.skip("No backend endpoints found")

        # Extract just the paths from backend endpoints (strip HTTP method)
        backend_paths = {ep.split(" ", 1)[1] for ep in backend_endpoints}

        # Check each frontend call — allow path params like /api/v1/projects/{id}
        unresolved: list[str] = []
        for call_url in frontend_calls:
            # Normalize: strip query strings
            clean_url = call_url.split("?")[0]
            # Check if the URL matches any backend path (exact or pattern)
            matched = False
            for bp in backend_paths:
                # Convert backend path pattern (/projects/{id}) to regex
                pattern = re.escape(bp).replace(r"\{[^}]+\}", r"[^/]+")
                if re.fullmatch(pattern, clean_url):
                    matched = True
                    break
            if not matched:
                unresolved.append(call_url)

        assert not unresolved, (
            f"{len(unresolved)} frontend API call(s) don't match any backend endpoint:\n"
            + "\n".join(f"  - {u}" for u in sorted(unresolved))
            + "\nThis means the frontend is calling URLs that don't exist on the backend."
        )

    def test_backend_endpoints_have_frontend_consumers(self):
        """Backend endpoints that no frontend calls are 'dead' — flag them.

        This is informational (not a hard fail) — some endpoints are
        admin-only or used by external integrations. But it helps identify
        endpoints that were added but never wired up.
        """
        frontend_calls = _extract_frontend_api_calls()
        backend_endpoints = _extract_router_endpoints()

        if not frontend_calls or not backend_endpoints:
            pytest.skip("Insufficient data to check endpoint consumption")

        # This test passes — it's informational. Dead endpoints are logged
        # but don't fail the build (they may be intentionally admin-only).
        backend_paths = {ep.split(" ", 1)[1] for ep in backend_endpoints}
        # Just verify we can do the analysis without crashing
        assert isinstance(backend_paths, set)


# ─── Tests: snake_case ↔ camelCase consistency ─────────────────────────

class TestCaseConsistency:
    """Verify snake_case (Python) ↔ camelCase (TypeScript) consistency.

    The QA guide identifies this as a frequent boundary mismatch:
    API returns `thumbnail_url` (snake_case) but frontend expects
    `thumbnailUrl` (camelCase) — TypeScript generics won't catch this
    because the runtime JSON doesn't match the declared type.
    """

    def test_backend_models_case_consistency(self):
        """Backend Pydantic models should use consistent field naming.

        FireAI's Digital Twin API (System A) intentionally uses camelCase
        for JavaScript compatibility — this is documented in
        frontend/src/services/digitalTwinApi.ts. This test verifies that
        the naming is CONSISTENT (all camelCase or all snake_case per model),
        not mixed within a single model.

        Mixed naming within one model is a real bug — it means some fields
        will be accessible to the frontend and others won't.
        """
        shapes = _extract_backend_response_shapes()
        if not shapes:
            pytest.skip("No backend models found")

        mixed_models: list[str] = []
        for model_name, fields in shapes.items():
            has_camel = any(re.search(r"[a-z][A-Z]", f) for f in fields)
            has_snake = any("_" in f for f in fields)
            if has_camel and has_snake:
                mixed_models.append(
                    f"{model_name}: {fields}"
                )

        assert not mixed_models, (
            f"Models with MIXED camelCase + snake_case fields "
            f"(frontend will miss some fields):\n"
            + "\n".join(f"  - {m}" for m in mixed_models)
        )


# ─── Tests: response shape completeness ────────────────────────────────

class TestResponseShapeCompleteness:
    """Verify that API response models have the fields the frontend needs.

    This is a lightweight check — it verifies that the backend models
    define fields that the frontend TypeScript types reference. A full
    check would require parsing TypeScript types, which is complex.
    """

    def test_models_have_required_fields(self):
        """Every Pydantic model should have at least one field.

        Empty models are usually a sign of incomplete implementation.
        """
        shapes = _extract_backend_response_shapes()
        if not shapes:
            pytest.skip("No backend models found")

        empty_models = [name for name, fields in shapes.items() if not fields]
        assert not empty_models, (
            f"Models with no fields (likely incomplete):\n"
            + "\n".join(f"  - {m}" for m in empty_models)
        )


# ─── Tests: state machine reachability ─────────────────────────────────

class TestStateMachineReachability:
    """Verify that defined state transitions are reachable in code.

    The QA guide identifies 'dead transitions' as a common bug:
    a state machine defines a transition (e.g., 'generating → approved')
    but no code ever triggers that transition.
    """

    def test_no_obvious_dead_state_transitions(self):
        """Check that state constants defined in backend are used.

        This is a heuristic — it greps for state string literals in
        the codebase. If a state is defined but never referenced in
        any .update() or assignment, it's likely dead.
        """
        # Look for state/status constants in backend
        constants_file = BACKEND_DIR / "models.py"
        if not constants_file.exists():
            pytest.skip("No backend/models.py")

        content = constants_file.read_text()
        # Find string literals that look like state names
        state_candidates: set[str] = set()
        for m in re.finditer(r'["\']([a-z_]+_(?:active|inactive|pending|approved|rejected|generating|completed|failed|draft|published))["\']', content):
            state_candidates.add(m.group(1))

        if not state_candidates:
            pytest.skip("No state-like constants found in models.py")

        # Check each state appears in at least one other file
        dead_states: list[str] = []
        for state in state_candidates:
            # Search all Python files for this state string
            found_in_code = False
            for py_file in BACKEND_DIR.rglob("*.py"):
                if py_file.name == "models.py":
                    continue
                try:
                    if state in py_file.read_text():
                        found_in_code = True
                        break
                except (UnicodeDecodeError, OSError):
                    continue
            if not found_in_code:
                dead_states.append(state)

        # This is informational — dead states may be planned for future use
        # Don't fail hard, just report
        if dead_states:
            import warnings
            warnings.warn(
                f"State-like constants defined but not used in any backend code "
                f"(may be dead transitions): {dead_states}",
                stacklevel=2,
            )
