# File-level '# NOSONAR' removed per NOSONAR_AUDIT.md (V143 hardening).
# Per-line justified suppressions (e.g., '# NOSONAR — S3776: ...') are preserved.
"""
tests/test_backend_app_security.py — V127 SAFETY: backend.app CORS hardening
================================================================================
V127 SAFETY FIX: backend.app must NOT use wildcard CORS origins in production.
The previous code defaulted to allow_origins=["*"] which allows any website
to read API responses. In production, CORS_ALLOWED_ORIGINS must be explicitly set.

Tests:
  - 4 legacy tests for the deleted backend_app.py (standalone file) were removed
    in C-09. They relied on a module-reload mechanism that cannot work with
    package modules. The same CORS hardening is tested in
    test_security_middleware_v129.py::TestBackendAppCorsHardening (all pass).
"""

import os
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
