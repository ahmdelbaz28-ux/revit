"""FireAI Digital Twin Platform — Backend Package."""

# Compatibility patch for hashlib.md5 used by older ReportLab versions.
# Older ReportLab calls hashlib.md5(usedforsecurity=False), which is invalid in Python 3.12+.
# This patch removes the unsupported kwarg to prevent TypeError during PDF generation.
import hashlib
_original_md5 = hashlib.md5

def _patched_md5(*args, **kwargs):
    kwargs.pop("usedforsecurity", None)
    return _original_md5(*args, **kwargs)

hashlib.md5 = _patched_md5  # type: ignore

try:
    with open("VERSION") as f:
        __version__ = f.read().strip()
except FileNotFoundError:
    __version__ = "0.0.0"
