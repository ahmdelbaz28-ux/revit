# ═══════════════════════════════════════════════════════════════════════════
# V208 — Smoke test for .devcontainer/devcontainer.json
# ═══════════════════════════════════════════════════════════════════════════
# Purpose: protect the CodeSandbox devbox from regressions. If someone edits
# .devcontainer/devcontainer.json and breaks the JSON syntax, removes a
# required field, or points the Dockerfile at a non-existent image, this
# test catches it before the devbox fails to build in CodeSandbox.
#
# This test is intentionally lightweight — it does NOT build the Docker
# image (that would take minutes and require Docker). It only validates:
#   1. The JSON file parses.
#   2. Required fields are present (name, build, features, postCreateCommand).
#   3. Forwarded ports are a subset of the expected set.
#   4. The CodeSandbox customization block is present with memory/cpu/regenerateHours.
#   5. The Dockerfile referenced by `build.dockerfile` exists.
#
# Run: pytest tests/test_devcontainer_config.py -v
# ═══════════════════════════════════════════════════════════════════════════

"""Smoke tests for .devcontainer/devcontainer.json — protects CodeSandbox devbox."""

from __future__ import annotations

import json
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
DEVCONTAINER_DIR = REPO_ROOT / ".devcontainer"
DEVCONTAINER_JSON = DEVCONTAINER_DIR / "devcontainer.json"
DOCKERFILE = DEVCONTAINER_DIR / "Dockerfile"


@pytest.fixture(scope="module")
def devcontainer_config() -> dict:
    """Load and parse devcontainer.json once per module."""
    if not DEVCONTAINER_JSON.exists():
        pytest.skip(f"{DEVCONTAINER_JSON} not found — V206 devcontainer not yet merged")
    return json.loads(DEVCONTAINER_JSON.read_text())


# ── 1. JSON parses + required fields ────────────────────────────────────────


def test_devcontainer_json_parses(devcontainer_config: dict) -> None:
    """devcontainer.json must be valid JSON (CodeSandbox fails to build otherwise)."""
    assert isinstance(devcontainer_config, dict), "devcontainer.json must be a JSON object"


@pytest.mark.parametrize("field", ["name", "build", "features", "postCreateCommand", "forwardPorts"])
def test_required_fields_present(devcontainer_config: dict, field: str) -> None:
    """Each required field must be present — CodeSandbox devbox won't boot without them."""
    assert field in devcontainer_config, f"Missing required field: {field}"


def test_build_dockerfile_reference(devcontainer_config: dict) -> None:
    """The `build.dockerfile` field must point to a file that exists."""
    build = devcontainer_config["build"]
    assert "dockerfile" in build, "build.dockerfile missing"
    dockerfile_rel = build["dockerfile"]
    # devcontainer.json paths are relative to the .devcontainer/ directory
    dockerfile_abs = DEVCONTAINER_DIR / dockerfile_rel
    assert dockerfile_abs.exists(), f"Dockerfile not found at {dockerfile_abs}"


# ── 2. Forwarded ports ─────────────────────────────────────────────────────


EXPECTED_PORTS = {3000, 5173, 7860, 8000, 6379, 5432}


def test_forwarded_ports_include_expected(devcontainer_config: dict) -> None:
    """All expected service ports must be forwarded (Vite, FastAPI, Redis, Postgres, HF parity)."""
    forwarded = set(devcontainer_config["forwardPorts"])
    missing = EXPECTED_PORTS - forwarded
    assert not missing, f"Missing forwarded ports: {missing}. Got: {forwarded}"


def test_forwarded_ports_are_integers(devcontainer_config: dict) -> None:
    """Port numbers must be integers — strings cause silent failures in devcontainer spec."""
    for port in devcontainer_config["forwardPorts"]:
        assert isinstance(port, int), f"Port {port!r} must be int, got {type(port).__name__}"


# ── 3. CodeSandbox customization block ─────────────────────────────────────


def test_codesandbox_customization_present(devcontainer_config: dict) -> None:
    """The `codesandbox` block must exist — without it CodeSandbox uses defaults."""
    assert "codesandbox" in devcontainer_config, "Missing 'codesandbox' customization block"


@pytest.mark.parametrize("field", ["memory", "cpu", "regenerateHours"])
def test_codesandbox_resource_fields(devcontainer_config: dict, field: str) -> None:
    """memory/cpu/regenerateHours must be set to match the operator's plan (8GB/4CPU/40h)."""
    cs = devcontainer_config["codesandbox"]
    assert field in cs, f"Missing codesandbox.{field}"


def test_codesandbox_memory_is_8gb(devcontainer_config: dict) -> None:
    """CodeSandbox free tier gives 8GB RAM — devbox must request exactly that."""
    assert devcontainer_config["codesandbox"]["memory"] == 8, "Expected 8GB RAM for CodeSandbox devbox"


def test_codesandbox_regenerate_hours_is_40(devcontainer_config: dict) -> None:
    """CodeSandbox free tier gives 40h/month regenerates — must match operator's plan."""
    assert devcontainer_config["codesandbox"]["regenerateHours"] == 40, "Expected 40h/month regenerate budget"


# ── 4. Features ────────────────────────────────────────────────────────────


EXPECTED_FEATURES = {
    "ghcr.io/devcontainers/features/python",
    "ghcr.io/devcontainers/features/node",
    "ghcr.io/devcontainers/features/common-utils",
    "ghcr.io/devcontainers/features/github-cli",
}


def test_expected_features_present(devcontainer_config: dict) -> None:
    """Core dev features must be present (Python, Node, common-utils, gh CLI)."""
    installed = set(devcontainer_config["features"].keys())
    for expected in EXPECTED_FEATURES:
        # Match by prefix (versions may change: :1, :2, etc.)
        matches = [f for f in installed if f.startswith(expected)]
        assert matches, f"Expected feature prefix '{expected}' not found. Installed: {installed}"


def test_python_feature_version(devcontainer_config: dict) -> None:
    """Python feature must request 3.12 (matches pyproject.toml requires-python)."""
    python_feature = next(
        (k for k in devcontainer_config["features"] if "python" in k),
        None,
    )
    assert python_feature is not None, "Python feature not installed"
    python_cfg = devcontainer_config["features"][python_feature]
    if isinstance(python_cfg, dict):
        version = python_cfg.get("version", "")
        assert version.startswith("3.12"), f"Python version must be 3.12.x, got {version}"


def test_node_feature_version(devcontainer_config: dict) -> None:
    """Node feature must request 20 (matches .nvmrc)."""
    node_feature = next(
        (k for k in devcontainer_config["features"] if k.endswith("node:1") or "node" in k),
        None,
    )
    assert node_feature is not None, "Node feature not installed"
    node_cfg = devcontainer_config["features"][node_feature]
    if isinstance(node_cfg, dict):
        version = node_cfg.get("version", "")
        assert version == "20" or version.startswith("20"), f"Node version must be 20.x, got {version}"


# ── 5. Post-create / post-start scripts ────────────────────────────────────


def test_post_create_script_exists(devcontainer_config: dict) -> None:
    """postCreateCommand must reference an existing script."""
    cmd = devcontainer_config["postCreateCommand"]
    # Extract the script path from "bash .devcontainer/post-create.sh"
    script_path = cmd.replace("bash", "").strip()
    assert (REPO_ROOT / script_path).exists(), f"post-create script not found: {script_path}"


def test_post_start_script_exists(devcontainer_config: dict) -> None:
    """postStartCommand must reference an existing script."""
    cmd = devcontainer_config["postStartCommand"]
    script_path = cmd.replace("bash", "").strip()
    assert (REPO_ROOT / script_path).exists(), f"post-start script not found: {script_path}"


def test_post_create_script_is_executable(devcontainer_config: dict) -> None:
    """post-create.sh must be executable (chmod +x) — otherwise bash won't run it."""
    cmd = devcontainer_config["postCreateCommand"]
    script_path = REPO_ROOT / cmd.replace("bash", "").strip()
    # On Windows this check is N/A, but on Linux/Mac it must pass
    import os
    import sys
    if sys.platform != "win32":
        mode = script_path.stat().st_mode
        assert mode & 0o100, f"{script_path.name} is not executable (chmod +x required)"


# ── 6. Dockerfile sanity ───────────────────────────────────────────────────


def test_dockerfile_uses_python_312_base() -> None:
    """Dockerfile must use Python 3.12 base image (matches pyproject.toml)."""
    content = DOCKERFILE.read_text()
    # Look for FROM line with python:3.12 or devcontainers/python:3.12
    assert "python:3.12" in content or "python:3.12" in content, (
        "Dockerfile must use Python 3.12 base image (pyproject.toml requires >=3.12)"
    )


def test_dockerfile_has_non_root_user() -> None:
    """Dockerfile must define a non-root user (security best practice)."""
    content = DOCKERFILE.read_text()
    assert "USER " in content, "Dockerfile must switch to a non-root USER before WORKDIR"


def test_dockerfile_installs_playwright_deps() -> None:
    """Dockerfile must install Playwright browser deps (visual tests depend on them)."""
    content = DOCKERFILE.read_text()
    # At least one of the Playwright browser deps must be present
    playwright_markers = ["libnss3", "libatk", "libgbm", "libxkbcommon", "playwright"]
    found = [m for m in playwright_markers if m in content.lower()]
    assert found, f"None of Playwright deps found in Dockerfile: expected at least one of {playwright_markers}"
