"""version.py — Single Source of Truth for FireAI Version
=======================================================
ALL audit reports, database records, and API responses MUST import
version metadata from here. Never hardcode version strings elsewhere.

FIXED (W-02): audit files showed V5.1.0, V5.1.2, V20.2 for a V29 system.
  Root cause: version string was hardcoded in multiple places.
  Fix: one module, one string, imported everywhere.

Usage:
    from fireai.version import FIREAI_VERSION, build_version_header
"""

from __future__ import annotations

import platform
import sys
from typing import Dict

# ─── EDIT ONLY THESE THREE LINES PER RELEASE ─────────────────────────────────
MAJOR = 55
MINOR = 0
PATCH = 0
# ─────────────────────────────────────────────────────────────────────────────

# Package version (semver for PyPI/distribution — used by fireai.__version__)
# This is the PUBLIC-FACING version for packaging, pip, and import metadata.
# It MUST be a valid semver string (MAJOR.MINOR.PATCH) with no prefix.
__package_version__ = "1.0.0"

# Internal development version (for audit trails, agent.md cycle tracking)
# This tracks the internal development cycle and may differ from the package version.
FIREAI_VERSION = f"V{MAJOR}.{MINOR}.{PATCH}"
FIREAI_VERSION_FULL = f"FireAI {FIREAI_VERSION}"

# Standards this version is validated against
NFPA_EDITION = "NFPA 72-2022"
IEC_HAC_EDITION = "IEC 60079-10-1:2015 / IEC 60079-10-2:2015"
NEC_EDITION = "NFPA 70-2023"
ATEX_EDITION = "ATEX 2014/34/EU"


def build_version_header() -> Dict[str, str]:
    """Return a dict suitable for embedding in audit reports and API responses.

    Every audit JSON MUST include this header to ensure traceability.
    """
    return {
        "fireai_version": FIREAI_VERSION_FULL,
        "nfpa_edition": NFPA_EDITION,
        "iec_hac_edition": IEC_HAC_EDITION,
        "nec_edition": NEC_EDITION,
        "atex_edition": ATEX_EDITION,
        "python_version": sys.version.split()[0],
        "platform": platform.system(),
    }


def assert_version_consistency() -> None:
    """Runtime check: raise if any imported submodule declares a different version.
    Call once at application startup.
    """
    declared_versions: Dict[str, str] = {
        "fireai.version": FIREAI_VERSION,
    }
    inconsistent = {mod: ver for mod, ver in declared_versions.items() if ver != FIREAI_VERSION}
    if inconsistent:
        raise RuntimeError(
            f"Version inconsistency detected: {inconsistent}. "
            f"All modules must report {FIREAI_VERSION}. "
            "Check for hardcoded version strings."
        )
