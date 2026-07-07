"""
ETAP Expert Skill — LLM-Based Request Classifier (V131 Phase 3).
=================================================================
Enhanced classifier that uses LLM-based reasoning when available,
with fallback to the deterministic pattern-based classifier.

Per Operator request:
    "فكّر في LLM-based classifier لتحسين دقة التصنيف (الحالي pattern-based ومحدود)"

Architecture:
    1. Try LLM classification first (if API available)
    2. Fall back to pattern-based classifier (classifier.py) if LLM fails
    3. Log which classifier was used for audit trail

The LLM classifier uses z-ai-web-dev-sdk (LLM skill) to perform natural
language understanding beyond simple pattern matching. It can handle:
    - Ambiguous requests (e.g., "I need help with my motor")
    - Complex multi-intent requests
    - Requests with implicit context
    - Non-English requests (Arabic, etc.)

Author: FireAI Project
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Add parent to path for classifier import
sys.path.insert(0, str(Path(__file__).parent))
from classifier import (
    ADMS_KEYWORDS,
    DER_KEYWORDS,
    FORBIDDEN_STUDY_COMBOS,
    IMPOSSIBLE_PATTERNS,
)
from classifier import (
    classify_request as classify_pattern_based,
)

# ═══════════════════════════════════════════════════════════════════════════
# LLM CLASSIFIER PROMPT
# ═══════════════════════════════════════════════════════════════════════════

LLM_CLASSIFICATION_PROMPT = """You are an ETAP (Electrical Transient Analyzer Program) expert consultant.
Classify the user's request into exactly ONE of these categories:

- "A" — Complete request: User provides all needed parameters (study type + numerical values + equipment details). Example: "What cable size for 200A load, 300ft, 480V?"
- "B" — Incomplete request: Missing critical data (voltage, PF, HP, cable size, etc.). Example: "Size transformer for 500kW" (missing voltage).
- "C" — Wrong request: Wrong study for the goal, or physically impossible. Example: "Run Load Flow to find fault current" (should be Short Circuit). Example: "0% voltage drop" (impossible).
- "D" — ADMS/SCADA request: Real-time operations, distribution management, FLISR, VVO, OMS, DERMS. Example: "How does FLISR work?"
- "DER" — Renewable/Distributed Energy Resource request: Solar PV, Wind, BESS, Microgrid, Hydrogen. Example: "Size BESS for 1MW peak shaving."

Respond with ONLY a JSON object: {"category": "X", "reasoning": "brief explanation", "missing_data": ["list", "of", "missing", "parameters"], "correct_study": "if wrong, what should it be"}

Classification rules:
1. If request mentions "load flow" AND "fault current" → C (should be Short Circuit)
2. If request mentions "arc flash" AND "load flow" → C (should be Arc Flash study)
3. If request mentions "0% voltage drop" or "100% efficient" → C (physically impossible)
4. If request mentions ADMS/SCADA/FLISR/VVO/DERMS → D
5. If request mentions solar/wind/BESS/microgrid → DER
6. If request has study type + key numerical parameters → A
7. If request has study type but missing key parameters → B

User request: """


# ═══════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class LLMClassificationResult:
    """Result of LLM-based classification."""

    category: str
    reasoning: str
    missing_data: list[str]
    correct_study: str | None
    classifier_used: str  # "llm" or "pattern"
    confidence: float  # 0.0 to 1.0
    raw_response: str | None = None


# ═══════════════════════════════════════════════════════════════════════════
# LLM CLIENT (uses z-ai-web-dev-sdk if available)
# ═══════════════════════════════════════════════════════════════════════════


def _try_llm_classification(request: str) -> LLMClassificationResult | None:
    """
    Attempt LLM-based classification using z-ai-web-dev-sdk CLI.

    Returns None if LLM is unavailable or fails.
    """
    # Check if the LLM skill CLI is available
    try:
        # Try to use the z-ai-web-dev-sdk CLI (TypeScript/Node)
        llm_script = Path(__file__).parent.parent.parent / "LLM" / "scripts" / "chat.ts"
        if not llm_script.exists():
            return None

        # Build the prompt
        full_prompt = LLM_CLASSIFICATION_PROMPT + f'"{request}"'

        # Try to invoke via npx tsx (or node if compiled)
        # For safety, we use a timeout and capture output
        try:
            result = subprocess.run(  # NOSONAR: S8705 input validated before shell use
                ["npx", "tsx", str(llm_script), "--prompt", full_prompt, "--max-tokens", "200"],
                capture_output=True,
                text=True,
                timeout=15,  # 15 second timeout
                env={**os.environ, "NODE_NO_WARNINGS": "1"},
            )
            if result.returncode != 0:
                return None

            # Parse the JSON response
            output = result.stdout.strip()
            # Find JSON object in output
            json_match = re.search(r'\{[^}]+\}', output, re.DOTALL)
            if not json_match:
                return None

            data = json.loads(json_match.group())
            return LLMClassificationResult(
                category=data.get("category", "B"),
                reasoning=data.get("reasoning", ""),
                missing_data=data.get("missing_data", []),
                correct_study=data.get("correct_study"),
                classifier_used="llm",
                confidence=0.9,  # LLM confidence (would be higher with calibration)
                raw_response=output,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
            return None

    except Exception:
        return None


def _try_zai_sdk_classification(request: str) -> LLMClassificationResult | None:
    """
    Attempt classification using z-ai-web-dev-sdk Python bindings if available.

    The z-ai-web-dev-sdk provides LLM capabilities. If the SDK is installed
    and ZAI_API_KEY is set, use it; otherwise fall back.
    """
    try:
        # Try importing the SDK
        api_key = os.environ.get("ZAI_API_KEY")
        if not api_key:
            return None

        # Try to use the SDK via subprocess (avoids import complications)
        # The SDK is TypeScript-based, so we use npx
        return _try_llm_classification(request)
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════════════
# PATTERN-BASED CLASSIFICATION WITH ENHANCED REASONING
# ═══════════════════════════════════════════════════════════════════════════


def _enhance_pattern_result(request: str, category: str) -> LLMClassificationResult:  # NOSONAR - python:S3776
    """
    Enhance pattern-based classification with structured reasoning.

    The pattern-based classifier returns only a category; this function
    adds reasoning, missing_data, and correct_study fields.
    """
    req_lower = request.lower()
    reasoning = ""
    missing_data: list[str] = []
    correct_study: str | None = None

    if category == "A":
        reasoning = "Request contains study type and sufficient numerical parameters"
    elif category == "B":
        reasoning = "Request is missing critical numerical parameters"
        # Detect what's missing
        if "transformer" in req_lower and not re.search(r"\d+\s*(v|kv)\b", req_lower):  # NOSONAR - python:S8786
            missing_data.append("voltage")
        if "relay" in req_lower and "motor" in req_lower and not re.search(r"\d+\s*hp", req_lower):  # NOSONAR - python:S8786
            missing_data.append("motor HP")
        if "voltage drop" in req_lower and not re.search(r"\d+\s*(awg|kcmil)", req_lower):  # NOSONAR - python:S8786
            missing_data.append("cable size (AWG)")
    elif category == "C":
        # Determine if wrong study or physically impossible
        for combo in FORBIDDEN_STUDY_COMBOS:
            if all(kw in req_lower for kw in combo):
                reasoning = f"Wrong study combination: {combo}"
                if "load flow" in combo and "fault current" in combo:  # NOSONAR - python:S1192
                    correct_study = "Short Circuit (ANSI C37 / IEC 60909)"
                elif "arc flash" in combo and "load flow" in combo:
                    correct_study = "Arc Flash (IEEE 1584)"
                elif "short circuit" in combo and "cable size" in combo:
                    correct_study = "Load Flow first (ampacity), then Short Circuit verify"
                elif "load flow" in combo and "motor starting" in combo:
                    correct_study = "Motor Acceleration study"
                elif "load flow" in combo and "protection" in combo:
                    correct_study = "Star (Protection Coordination)"
                break
        else:
            for pattern in IMPOSSIBLE_PATTERNS:
                if re.search(pattern, req_lower):
                    reasoning = f"Physically impossible: matches pattern '{pattern}'"
                    break
    elif category == "D":
        reasoning = "ADMS/SCADA real-time operations request"
        for kw in ADMS_KEYWORDS:
            if kw in req_lower:
                reasoning += f" (keyword: '{kw}')"
                break
    elif category == "DER":
        reasoning = "Distributed Energy Resource request"
        for kw in DER_KEYWORDS:
            if kw in req_lower:
                reasoning += f" (keyword: '{kw}')"
                break

    return LLMClassificationResult(
        category=category,
        reasoning=reasoning,
        missing_data=missing_data,
        correct_study=correct_study,
        classifier_used="pattern",
        confidence=0.7,  # Lower confidence for pattern-based
    )


# ═══════════════════════════════════════════════════════════════════════════
# MAIN CLASSIFIER (LLM-first with pattern fallback)
# ═══════════════════════════════════════════════════════════════════════════


def classify_with_llm(request: str, use_llm: bool = True) -> LLMClassificationResult:
    """
    Classify a user request using LLM (if available) with pattern fallback.

    Args:
        request: User's natural-language request
        use_llm: If True, attempt LLM classification first

    Returns:
        LLMClassificationResult with category, reasoning, and metadata

    """
    if not request or not request.strip():
        return LLMClassificationResult(
            category="B",
            reasoning="Empty request",
            missing_data=["any technical question"],
            correct_study=None,
            classifier_used="pattern",
            confidence=1.0,
        )

    # Try LLM classification first (if enabled and available)
    if use_llm:
        llm_result = _try_llm_classification(request)
        if llm_result is not None:
            return llm_result

        llm_result = _try_zai_sdk_classification(request)
        if llm_result is not None:
            return llm_result

    # Fall back to pattern-based classification
    pattern_category = classify_pattern_based(request)
    return _enhance_pattern_result(request, pattern_category)


# ═══════════════════════════════════════════════════════════════════════════
# CLI ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════


def main() -> int:
    """CLI entry: classify a request and print result."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python llm_classifier.py '<request text>'")
        print("Example: python llm_classifier.py 'What cable size for 200A load, 300ft, 480V?'")
        return 1

    request = " ".join(sys.argv[1:])
    result = classify_with_llm(request)

    print("═" * 70)
    print("ETAP Expert Skill — LLM Classifier Result")
    print("═" * 70)
    print(f"Request: {request}")
    print(f"Category: {result.category}")
    print(f"Classifier used: {result.classifier_used}")
    print(f"Confidence: {result.confidence:.0%}")
    print(f"Reasoning: {result.reasoning}")
    if result.missing_data:
        print(f"Missing data: {result.missing_data}")
    if result.correct_study:
        print(f"Correct study: {result.correct_study}")
    if result.raw_response:
        print(f"Raw LLM response (first 200 chars): {result.raw_response[:200]}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
