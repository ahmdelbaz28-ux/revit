"""
Root conftest.py — Project-level pytest configuration.

Ensures the project root is in sys.path before any test collection,
so that imports like `from core.models import ...` and
`from parsers.dwg_parser import ...` resolve correctly.

This is required because pytest 9+ defaults to importlib mode,
which does not honor module-level sys.path.insert() in test files.
"""
import sys
import os

# Project root = directory containing this conftest.py
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
