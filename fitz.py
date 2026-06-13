"""fitz.py — PyMuPDF compatibility shim.

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
"""

try:
    from pymupdf import *
    import pymupdf as _pymupdf

    # Re-export all symbols from pymupdf for backward compatibility
    Document = _pymupdf.Document
    open = _pymupdf.open

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
        def __getattr__(self, name):
            raise ImportError(
                f"pymupdf is not installed. Cannot access fitz.{name}. "
                "Install with: pip install pymupdf"
            )
        def __call__(self, *args, **kwargs):
            raise ImportError(
                "pymupdf is not installed. PDF operations are unavailable. "
                "Install with: pip install pymupdf"
            )

    _pymupdf = _PymupdfNotInstalled()
    Document = _PymupdfNotInstalled
    open = _PymupdfNotInstalled()
