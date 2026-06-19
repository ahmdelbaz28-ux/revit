"""
fireai/core/input_normalizer.py — User Input Normalization
==========================================================
Detects non-English user input (especially Arabic typed on an English
QWERTY keyboard layout, e.g. "ضصثق" intended as "qwet") and
deterministically recovers the user's intended English text.

PURPOSE:
    When a user's OS keyboard layout is set to Arabic while they intend
    to type English, every keystroke produces an Arabic glyph instead of
    the intended Latin one. The user typically notices only after
    pressing Enter — and currently must delete and retype the input
    manually. This module eliminates that friction by recovering the
    intended English text from the Arabic glyphs.

SCOPE (v1 — Mistype Recovery only):
    - Deterministic Arabic-letter → English-QWERTY-key mapping.
    - Arabic-Indic and Persian digit → ASCII digit conversion.
    - Heuristic to distinguish "Arabic mistype" (recoverable) from
      "real Arabic text" (NOT recoverable by simple mapping — requires
      LLM translation, which is a Phase 3 feature).

OUT OF SCOPE (deferred to Phase 3):
    - LLM-based translation of genuine Arabic sentences
      (e.g. "عاوز افتح ملف" → "I want to open a file").
    - Persian / Urdu / Hebrew / Cyrillic keyboard layouts.

ARCHITECTURE:
    Pure functions only. No I/O, no global state, no side effects.
    Every public function is referentially transparent and safe to
    call from any thread or async context. This matches the design
    of ``bim_input_sanitizer.py`` (the existing input-sanitization
    module this layer extends).

LIFE-SAFETY NOTE (per agent.md "Safety > Convenience"):
    - Identifiers (project_id, imo_number, api_key, file paths) MUST
      NOT be normalized — see ``NormalizationContext.IDENTIFIER``.
    - Normalization is OFF by default in production; it must be
      explicitly enabled via ``FIREAI_INPUT_NORMALIZATION_ENABLED=true``.
    - All transformations are logged for audit trail.

References:
    - fireai/core/bim_input_sanitizer.py (precedent for input-handling modules)
    - fireai/core/keyboard_layouts.py (mapping data tables)
    - agent.md Rule: "Never trust input from outside the system boundary"
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Literal

from fireai.core.keyboard_layouts import (
    ALL_DIGIT_TO_ASCII,
    AR_TO_EN,
    is_arabic_codepoint,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC TYPES
# ═══════════════════════════════════════════════════════════════════════════════


class NormalizationContext(str, Enum):
    """Where the text is being used — drives safety policy.

    - IDENTIFIER: project_id, imo_number, file paths, API keys. NEVER
      normalize (could break lookups, leak secrets, or change semantics).
    - FREE_TEXT: project name, description, comment. Safe to normalize.
    - COMMAND: a natural-language command meant for execution. Normalize
      but ALWAYS set ``needs_confirmation=True`` so the caller can ask
      the user to confirm before running.
    """

    IDENTIFIER = "identifier"
    FREE_TEXT = "free_text"
    COMMAND = "command"


@dataclass(frozen=True)
class NormalizationResult:
    """Immutable result of normalizing one user-input string.

    Matches the project's value-object convention (frozen dataclass,
    see ``fireai/env_config.py:FireAIConfig`` and
    ``fireai/agents/tool_selector.py``).

    Attributes:
        original: The raw user input, unchanged.
        normalized: The text to use going forward. Equals ``original``
            when no transform was applied.
        transform_applied: Which transform (if any) was performed.
        confidence: Heuristic confidence in the transform, in [0.0, 1.0].
            1.0 = deterministic mistype recovery. 0.0 = no transform.
        needs_confirmation: True if the caller should ask the user to
            confirm the normalized text before acting on it (always
            True for COMMAND context and for any LLM-based transform).
        detected_language: Best-guess language of the original text:
            "arabic_mistype", "arabic_real", "english", "mixed", or
            "unknown".
    """

    original: str
    normalized: str
    transform_applied: Literal["none", "keyboard_layout", "digit_normalize"]
    confidence: float
    needs_confirmation: bool
    detected_language: Literal[
        "arabic_mistype", "arabic_real", "english", "mixed", "unknown"
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# DETECTION HEURISTICS
# ═══════════════════════════════════════════════════════════════════════════════
#
# The core question: "Is this Arabic text a keyboard mistype, or is it
# genuine Arabic the user typed intentionally?"
#
# Heuristic — three signals combined:
#   1. SPACES: Real Arabic sentences contain spaces between words.
#      A mistype is almost always a single "token" with no spaces.
#   2. COMMON-WORD MARKERS: Real Arabic contains common function words
#      (في, من, عاوز, عايز, أريد, افتح, etc.). Mistype output is
#      statistically very unlikely to spell any of these by accident.
#   3. ARABIC RATIO: If the text is mostly Arabic letters (and few or
#      no ASCII), it's more likely real Arabic.

# Common Arabic function words / verbs that strongly indicate real Arabic
# (not mistype). Curated for Modern Standard Arabic + Egyptian colloquial.
# Source: high-frequency words from Arabic Wikipedia + Egyptian Arabic
# corpora. Adding a word here makes the detector more conservative
# (less likely to misclassify real Arabic as mistype).
_REAL_ARABIC_MARKERS: frozenset[str] = frozenset(
    {
        # Prepositions / conjunctions
        "في", "من", "على", "إلى", "الى", "عن", "مع", "هذا", "هذه", "ذلك",
        "التي", "الذي", "الذين", "كان", "كانت", "قد", "لقد", "كل", "بعض",
        # Verbs (MSA)
        "أريد", "اريد", "افتح", "افتحي", "افتحوا", "شغل", "شغلي", "احسب",
        "اعمل", "اعملي", "اعرض", "اعرضي", "اطبع", "ابحث", "ادخل", "اخرج",
        "اكتب", "اقرأ", "اقرا", "اعد", "اعدد", "حلل", "حللها", "صمم",
        "صممها", "ابني", "انشئ", "أنشئ", "حدد", "حددها", "تحقق", "تأكد",
        "تاكد", "افحص", "افحصي", "راجع", "راجعي", "نفذ", "نفذي", "ابدأ",
        "ابدا", "ابدأي", "توقف", "توقفي", "الغي", "ألغي", "الغيها",
        # Egyptian colloquial verbs
        "عاوز", "عايز", "عاوزة", "عايزة", "عاوزين", "عايزين", "هخلي",
        "هعمل", "هاعمل", "اعملك", "اعملها", "شوف", "شوفي", "روح", "روحي",
        "جيب", "جيبي", "دي", "ده", "ديه", "كده", "ومكش", "دلوقتي",
        # Common nouns (fire-engineering context)
        "ملف", "ملفات", "مشروع", "مشروعات", "مشاريع", "تقرير", "تقارير",
        "حساب", "حسابات", "تحليل", "تحليلات", "بيانات", "نظام", "أنظمة",
        "انظمة", "كود", "اكواد", "سفينة", "سفن", "حريق", "حرائق", "مضخة",
        "مضخات", "خزان", "خزانات", "كاشف", "كواشف", "إنذار", "انذار",
        "كهرباء", "محرك", "محركات", "غرفة", "غرف", "ممر", "ممرات",
        "سلالم", "سلم", "باب", "أبواب", "ابواب", "شبكة", "شبكات",
        # Common command phrases
        "افتح الملف", "افتح المشروع", "شغل التحليل", "اعمل تقرير",
        "اعرض البيانات", "احسب الحمل", "تحليل الدائرة", "حساب التدفق",
    }
)


def _arabic_char_ratio(text: str) -> float:
    """Return the fraction of [a-zA-Z0-9 Arabic] characters that are Arabic.

    Spaces, punctuation, and symbols are excluded from both numerator
    and denominator. Returns 0.0 for empty / whitespace-only input.
    """
    relevant = 0
    arabic = 0
    for ch in text:
        if ch.isspace() or not ch.isalpha():
            continue
        relevant += 1
        if is_arabic_codepoint(ord(ch)):
            arabic += 1
    if relevant == 0:
        return 0.0
    return arabic / relevant


def _contains_real_arabic_marker(text: str) -> bool:
    """Return True if any token in ``text`` matches a known Arabic word.

    Tokenization is intentionally simple: split on whitespace and
    punctuation. We don't need linguistic accuracy — we just need to
    recognize when the user typed a real Arabic word.
    """
    # Strip leading "ال" (the definite article) so we catch "المشروع"
    # by also checking against "مشروع".
    normalized_tokens = set()
    for tok in text.split():
        # Also normalize alef variants (أ إ آ → ا) for matching.
        canon = tok.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
        normalized_tokens.add(tok)
        normalized_tokens.add(canon)
        if canon.startswith("ال") and len(canon) > 3:
            normalized_tokens.add(canon[2:])
    return bool(normalized_tokens & _REAL_ARABIC_MARKERS)


def detect_language(text: str) -> Literal[
    "arabic_mistype", "arabic_real", "english", "mixed", "unknown"
]:
    """Classify the dominant language of ``text``.

    Decision tree:
      1. Empty / whitespace-only → "unknown"
      2. Arabic ratio == 0.0 → "english" (if there's any alpha) or "unknown"
      3. Arabic ratio >= 0.5 AND has spaces AND has common Arabic words
         → "arabic_real" (genuine Arabic, requires translation)
      4. Arabic ratio >= 0.5 AND no spaces AND no common Arabic words
         → "arabic_mistype" (QWERTY mistype — recoverable by mapping)
      5. Otherwise → "mixed" (both English and Arabic letters present)

    Args:
        text: The user input to classify.

    Returns:
        One of "arabic_mistype", "arabic_real", "english", "mixed",
        "unknown".
    """
    if not text or not text.strip():
        return "unknown"

    ratio = _arabic_char_ratio(text)
    has_alpha = any(ch.isalpha() for ch in text)

    if ratio == 0.0:
        return "english" if has_alpha else "unknown"

    if ratio < 0.5:
        # Mostly Latin with some Arabic — ambiguous mixed input.
        return "mixed"

    # From here on, the text is majority-Arabic.
    has_spaces = " " in text.strip()
    has_markers = _contains_real_arabic_marker(text)

    if has_spaces and has_markers:
        return "arabic_real"
    if not has_spaces and not has_markers:
        return "arabic_mistype"
    # Edge case: Arabic chars + spaces but no recognized words, OR
    # Arabic chars + recognized word but no spaces. Be conservative —
    # treat as real Arabic so we don't accidentally mistranslate a
    # short real-Arabic phrase.
    return "arabic_real"


# ═══════════════════════════════════════════════════════════════════════════════
# TRANSFORM FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════


def _transliterate_arabic_to_qwerty(text: str) -> tuple[str, int, int]:
    """Map each Arabic char to its intended QWERTY key.

    Returns a tuple of (output_string, mapped_count, unmapped_count).
    Unmapped Arabic characters are passed through unchanged and counted
    so the caller can lower the confidence accordingly.
    """
    out_chars: list[str] = []
    mapped = 0
    unmapped_arabic = 0
    for ch in text:
        if ch in AR_TO_EN:
            out_chars.append(AR_TO_EN[ch])
            mapped += 1
        elif ch in ALL_DIGIT_TO_ASCII:
            out_chars.append(ALL_DIGIT_TO_ASCII[ch])
            mapped += 1
        elif is_arabic_codepoint(ord(ch)):
            # Arabic char not in our table — pass through, but flag.
            out_chars.append(ch)
            unmapped_arabic += 1
        else:
            # ASCII or other — pass through unchanged.
            out_chars.append(ch)
    return "".join(out_chars), mapped, unmapped_arabic


def _normalize_arabic_digits_only(text: str) -> str:
    """Convert Arabic-Indic / Persian digits to ASCII digits, leave rest.

    This is applied even when the rest of the text is English — common
    case: user typed an English project name but used Arabic-Indic
    digits for the year ("Project٢٠٢٦" → "Project2026").
    """
    if not any(ch in ALL_DIGIT_TO_ASCII for ch in text):
        return text
    return "".join(ALL_DIGIT_TO_ASCII.get(ch, ch) for ch in text)


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════


# Field names that must NEVER be normalized regardless of context.
# These are identifiers / credentials where any modification could
# break lookups, leak secrets, or change semantics.
DENYLIST_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "password",
        "password_hash",
        "api_key",
        "apikey",
        "secret",
        "secret_key",
        "token",
        "access_token",
        "refresh_token",
        "id_token",
        "session_id",
        "csrf_token",
        "private_key",
        "certificate",
        "imo_number",  # IMO number is a strict 7-digit identifier
        "mmsi",  # Maritime Mobile Service Identity — strict 9-digit
        "project_id",
        "uuid",
        "hash",
        "checksum",
        "etag",
        "filepath",
        "file_path",
        "path",
        "url",
        "uri",
        "email",
    }
)


def normalize_user_text(
    text: str,
    *,
    context: NormalizationContext | str = NormalizationContext.FREE_TEXT,
    enable_llm_translation: bool = False,
) -> NormalizationResult:
    """Normalize one user-input string.

    Pipeline (executed in order, short-circuits on first applicable
    transform):

      1. Always normalize Arabic-Indic / Persian digits to ASCII
         (safe, unambiguous, applies regardless of language detected).
      2. Detect language of the (digit-normalized) text.
      3. If context == IDENTIFIER → no further transform, return as-is.
      4. If language == "arabic_mistype" → apply QWERTY recovery.
      5. If language == "arabic_real" and enable_llm_translation is
         False → return as-is with a warning logged (Phase 3 will add
         LLM translation here).
      6. If language in ("english", "mixed", "unknown") → no further
         transform.

    Args:
        text: The raw user input. May be empty.
        context: Where this text will be used (drives safety policy).
            Accepts either a ``NormalizationContext`` enum or its
            string value (e.g. "identifier") for ergonomic calling
            from Pydantic validators.
        enable_llm_translation: If True, allow LLM-based translation of
            genuine Arabic to English. Currently a no-op (Phase 3
            feature) but accepted so callers can write forward-
            compatible code.

    Returns:
        A ``NormalizationResult`` describing what (if anything) was
        changed. Always returns a value — never raises on user input.

    Safety:
        - IDENTIFIER context: ALWAYS returns ``transform_applied="none"``
          (after digit normalization, which is safe for identifiers
          too because digits are positional, not lexical).
          Actually — for IDENTIFIER we skip digit normalization too,
          because IMO numbers etc. MUST be passed through verbatim.
        - COMMAND context: ALWAYS sets ``needs_confirmation=True``
          regardless of which transform was applied.
        - DENYLIST fields (password, api_key, etc.) must be filtered
          by the caller BEFORE calling this function — this function
          has no way to know the field name. The
          ``is_sensitive_field_name()`` helper below supports that.
    """
    # Coerce string context to enum.
    if isinstance(context, str):
        try:
            context = NormalizationContext(context)
        except ValueError as e:
            raise ValueError(
                f"Unknown normalization context {context!r}. "
                f"Must be one of: {[c.value for c in NormalizationContext]}"
            ) from e

    # IDENTIFIER context: zero transformation, zero trust in heuristics.
    if context is NormalizationContext.IDENTIFIER:
        return NormalizationResult(
            original=text,
            normalized=text,
            transform_applied="none",
            confidence=0.0,
            needs_confirmation=False,
            detected_language=detect_language(text),
        )

    # Stage 1: digit normalization (safe for FREE_TEXT and COMMAND).
    digit_normalized = _normalize_arabic_digits_only(text)
    digit_changed = digit_normalized != text

    # Stage 2: language detection on the digit-normalized text.
    detected = detect_language(digit_normalized)

    # Stage 3: QWERTY recovery for Arabic mistypes.
    if detected == "arabic_mistype":
        qwerty, mapped, unmapped = _transliterate_arabic_to_qwerty(
            digit_normalized
        )
        # Confidence: mapped chars / (mapped + unmapped). Drops fast
        # if we hit unmapped Arabic codepoints.
        total_arabic = mapped + unmapped
        confidence = mapped / total_arabic if total_arabic > 0 else 0.0

        needs_confirmation = context is NormalizationContext.COMMAND

        transform: Literal["none", "keyboard_layout", "digit_normalize"]
        if digit_changed and qwerty == digit_normalized:
            transform = "digit_normalize"
        else:
            transform = "keyboard_layout"

        logger.info(
            "input_normalized",
            extra={
                "transform": transform,
                "confidence": round(confidence, 3),
                "detected_language": detected,
                "context": context.value,
                "mapped_chars": mapped,
                "unmapped_arabic_chars": unmapped,
            },
        )
        return NormalizationResult(
            original=text,
            normalized=qwerty,
            transform_applied=transform,
            confidence=round(confidence, 4),
            needs_confirmation=needs_confirmation,
            detected_language=detected,
        )

    # Stage 4: genuine Arabic detected (would need LLM translation).
    if detected == "arabic_real":
        if enable_llm_translation:
            # Phase 3 placeholder — log the request for now.
            logger.info(
                "llm_translation_requested_but_unimplemented",
                extra={"text_preview": text[:80], "context": context.value},
            )
        else:
            logger.info(
                "real_arabic_input_preserved",
                extra={"text_preview": text[:80], "context": context.value},
            )
        # Pass through unchanged.
        transform = "digit_normalize" if digit_changed else "none"
        return NormalizationResult(
            original=text,
            normalized=digit_normalized,
            transform_applied=transform,
            confidence=0.0,
            needs_confirmation=context is NormalizationContext.COMMAND,
            detected_language=detected,
        )

    # Stage 5: English / mixed / unknown — return digit-normalized text.
    transform = "digit_normalize" if digit_changed else "none"
    return NormalizationResult(
        original=text,
        normalized=digit_normalized,
        transform_applied=transform,
        confidence=0.0 if transform == "none" else 1.0,
        needs_confirmation=context is NormalizationContext.COMMAND
        and transform != "none",
        detected_language=detected,
    )


def is_sensitive_field_name(field_name: str) -> bool:
    """Return True if ``field_name`` looks like a sensitive identifier.

    Use this to filter which fields the Pydantic validator applies
    normalization to. Case-insensitive, ignores leading underscores.

    Examples:
        >>> is_sensitive_field_name("password")
        True
        >>> is_sensitive_field_name("api_key")
        True
        >>> is_sensitive_field_name("name")
        False
        >>> is_sensitive_field_name("_project_id")
        True
    """
    if not field_name:
        return False
    name = field_name.lstrip("_").lower()
    return name in DENYLIST_FIELD_NAMES


__all__ = [
    "NormalizationContext",
    "NormalizationResult",
    "DENYLIST_FIELD_NAMES",
    "normalize_user_text",
    "is_sensitive_field_name",
    "detect_language",
]
