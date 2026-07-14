"""Shared utility for safe logging of user-controlled data.

V225 FIX (SonarCloud duplicated_lines): _safe_str() was defined 4 times
in backend/routers/digital_twin.py, backend/services/digital_twin_service.py,
backend/services/autocad_service.py, and backend/services/revit_service.py.

Extracted to this shared module to eliminate duplication.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def safe_str(value: object, max_len: int = 200) -> str:
    """Sanitize a value for safe logging.

    V216 FIX (SonarCloud pythonsecurity:S5145): user-controlled data must not
    be logged verbatim because newlines/control characters can be used for
    log injection. This helper:

    1. Coerces the value to str (defensive — handles None, int, etc.)
    2. Replaces newlines/tabs/carriage returns with underscores
    3. Truncates to max_len characters
    4. Strips non-printable characters outside the basic ASCII + Latin-1 range

    Used by all logger calls that include user-controlled data (handles,
    paths, names, identifiers).
    """
    if value is None:
        return "<None>"
    s = str(value)
    # Replace control characters that could enable log injection
    s = s.replace("\r", "_").replace("\n", "_").replace("\t", "_")
    # Strip other control characters (ASCII 0-31 except already-handled ones)
    s = "".join(ch if (ord(ch) >= 32 or ch == "_") else "_" for ch in s)
    if len(s) > max_len:
        s = s[:max_len] + "...<truncated>"
    return s
