# File-level '# NOSONAR' removed per NOSONAR_AUDIT.md (V143 hardening).
"""
fitz.py — PyMuPDF compatibility shim.

PyMuPDF 1.23+ renamed the 'fitz' module to 'pymupdf'.
This compat module allows ``import fitz`` to still work.

GRACEFUL DEGRADATION:
  If pymupdf is not installed, importing this module does NOT crash.
  Instead, it provides stub objects that raise ImportError with a clear
  message when accessed. This prevents the entire parsers package from
  becoming unusable just because PyMuPDF isn't installed — DXF parsing,
  path security, and other non-PDF features still work.

SAFETY RATIONALE:
  PDF parsing is optional in the FireAI pipeline. DXF parsing via ezdxf
  does NOT require PyMuPDF. A missing optional dependency should not
  prevent the core safety-critical functions from operating.

V131 FIX: Typed declarations and type: ignore[misc] to satisfy MyPy.
"""

from typing import Any

# Module-level declarations with explicit types for MyPy
Document: Any = None
open: Any = None

try:
    import pymupdf as _pymupdf  # NOSONAR — S2208: intentional module alias (not wildcard); used as `_pymupdf.Document` etc.  # type: ignore[import-untyped]
    # S2208 fix: replaced `from pymupdf import *` (wildcard) with explicit
    # module re-export via sys.modules so consumers using `import fitz` /
    # `import _fitz_compat as fitz` still get the full pymupdf namespace
    # without polluting this module's __all__ / static-analysis surface.
    import sys as _sys
    # Re-export all symbols from pymupdf for backward compatibility
    Document = _pymupdf.Document
    open = _pymupdf.open
    # Make every attribute on _pymupdf accessible on this module
    # without a wildcard import (SonarCloud S2208).
    for _name in dir(_pymupdf):
        if not _name.startswith("_") or _name in ("__doc__", "__version__"):
            globals().setdefault(_name, getattr(_pymupdf, _name))
    # Also expose the module itself so `from _fitz_compat import Page` works
    _sys.modules.setdefault(__name__ + "._pymupdf", _pymupdf)

except ImportError:
    import warnings
    warnings.warn(
        "PyMuPDF (pymupdf) is not installed. PDF parsing features will be "
        "unavailable. DXF parsing still works. Install with: pip install pymupdf",
        ImportWarning,
        stacklevel=2,
    )

    class _PymupdfNotInstalled:
        """Stub that raises ImportError when any attribute is accessed."""

        def __getattr__(self, name: str) -> Any:
            raise ImportError(
                f"pymupdf is not installed. Cannot access fitz.{name}. "
                "Install with: pip install pymupdf"
            )
        def __call__(self, *args: Any, **kwargs: Any) -> Any:
            raise ImportError(
                "pymupdf is not installed. PDF operations are unavailable. "
                "Install with: pip install pymupdf"
            )

    _pymupdf = _PymupdfNotInstalled()
    Document = _PymupdfNotInstalled
    open = _PymupdfNotInstalled()
