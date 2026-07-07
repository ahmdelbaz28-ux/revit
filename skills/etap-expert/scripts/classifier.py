"""
ETAP Expert Skill — Request Classifier.
=======================================
Implements Step 1 (PARSE & CLASSIFY) of the 6-step expert workflow.

Routes user requests to one of 4 response templates:
    A → Complete request → Expert Answer
    B → Incomplete request → Clarification
    C → Wrong request → Correction & Education
    D → ADMS request → ADMS-specific response
    DER → DER/PV request → DER-specific response

This classifier uses pattern matching (not LLM) — it's a deterministic
reference implementation. The skill itself recommends LLM-based understanding
for production use, but this gives a testable baseline.

Author: FireAI Project
"""

from __future__ import annotations

import re

# ═══════════════════════════════════════════════════════════════════════════
# ROUTING CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════

# Mistake Category 1: Forbidden study combinations (order-agnostic)
# If both keywords appear, request is WRONG (Template C)
# Note: multiple phrasings covered for same intent (e.g., "cable size" vs "size cable")
FORBIDDEN_STUDY_COMBOS = [
    {"load flow", "fault current"},
    {"arc flash", "load flow"},
    {"short circuit", "cable size"},
    {"short circuit", "size cable"},  # "Size cable with Short Circuit"
    {"short circuit", "cable sizing"},
    {"short circuit", "size cables"},
    {"load flow", "motor starting"},
    {"load flow", "protection"},
]

# Mistake Category 3: Physically impossible requests
IMPOSSIBLE_PATTERNS = [
    r"0%\s*voltage\s*drop",
    r"100%\s*efficient\s*transformer",
    r"infinite\s*fault\s*current",
]

# ADMS keywords (Template D)
ADMS_KEYWORDS = [
    "adms", "scada", "dms", "oms", "derms",
    "flisr", "vvo", "cvr", "state estimation",
]

# DER keywords (Template DER)
DER_KEYWORDS = [
    "solar pv", "wind turbine", "bess", "battery storage",
    "der ", "microgrid", "fuel cell", "electrolyzer",
]

# Recognized study types (for completeness check)
STUDY_TYPES = [
    "load flow", "short circuit", "arc flash", "motor starting",
    "protection", "harmonic", "transient", "cable sizing", "cable size",
    "transformer", "battery", "relay coordination", "voltage drop",
]

# Incomplete request patterns: (regex, missing_info_key)
# Returns B only if the missing info is genuinely absent
INCOMPLETE_PATTERNS = [
    # "Size transformer for 500kW" — need voltage
    (r"size\s+transformer\s+for\s+\d+\s*kw", "voltage"),
    # "Set relay for motor" — need HP
    (r"set\s+relay\s+for\s+motor", "hp"),
    # "Calculate voltage drop" — need cable size + length
    (r"calculate\s+voltage\s+drop", "cable"),
]


# CLASSIFIER
# ═══════════════════════════════════════════════════════════════════════════


def _has_voltage(text: str) -> bool:
    """Check if text contains a voltage value (e.g., '480V', '13.8kV')."""
    return bool(re.search(r"\d+(\.\d+)?\s*(v|kv|mv)\b", text))


def _has_hp(text: str) -> bool:
    """Check if text contains a horsepower value."""
    return bool(re.search(r"\d+\s*hp\b", text))


def _has_cable_info(text: str) -> bool:
    """Check if text contains cable-related info (size or length)."""
    return bool(
        re.search(r"\d+\s*(awg|kcmil)\b", text)
        or re.search(r"\d+\s*(ft|feet|foot|m|meter)\b", text)
        or "cable" in text
    )


def classify_request(request: str) -> str:
    """
    Classify a user request as A / B / C / D / DER.

    Implements Step 1 (PARSE & CLASSIFY) of the 6-step workflow.

    Args:
        request: User's natural-language request

    Returns:
        One of: "A" (complete), "B" (incomplete), "C" (wrong), "D" (ADMS), "DER"

    """
    if not request or not request.strip():
        return "B"  # Empty request is incomplete

    req_lower = request.lower()

    # ── Mistake 1: Forbidden study combinations (Template C) ───────────
    # Order-agnostic: check if all keywords in any combo appear together
    for combo in FORBIDDEN_STUDY_COMBOS:
        if all(kw in req_lower for kw in combo):
            return "C"

    # ── Mistake 3: Physically impossible (Template C) ──────────────────
    for pattern in IMPOSSIBLE_PATTERNS:
        if re.search(pattern, req_lower):
            return "C"

    # ── ADMS routing (Template D) ──────────────────────────────────────
    if any(kw in req_lower for kw in ADMS_KEYWORDS):
        return "D"

    # ── DER routing (Template DER) ─────────────────────────────────────
    if any(kw in req_lower for kw in DER_KEYWORDS):
        return "DER"

    # ── Mistake 2: Missing critical data (Template B) ──────────────────
    # Only return B if the missing info is genuinely absent
    for pattern, missing_key in INCOMPLETE_PATTERNS:
        if re.search(pattern, req_lower):
            if missing_key == "voltage" and not _has_voltage(req_lower):
                return "B"
            if missing_key == "hp" and not _has_hp(req_lower):
                return "B"
            if missing_key == "cable" and not _has_cable_info(req_lower):
                return "B"

    # ── No study type identified → incomplete ─────────────────────────
    has_study = any(st in req_lower for st in STUDY_TYPES)
    if not has_study:
        return "B"

    # ── No numerical values → incomplete ─────────────────────────────
    has_numbers = bool(re.search(r"\d+", request))
    if not has_numbers:
        return "B"

    # ── All checks passed → complete ─────────────────────────────────
    return "A"
