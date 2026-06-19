"""
fireai/core/keyboard_layouts.py — Keyboard Layout Mapping Tables
================================================================
Pure data module holding bidirectional QWERTY ↔ Arabic-101 keyboard
mapping tables.

PURPOSE:
    When a user types English text while their OS keyboard layout is set
    to Arabic (or vice versa), the OS produces glyphs from the *active*
    layout rather than the intended one. For example, pressing the QWERTY
    keys ``q w e t`` while Arabic is active yields ``ض ص ث ف``.

    This module provides the deterministic, zero-dependency mapping that
    ``input_normalizer.py`` uses to recover the user's intended input.

SCOPE:
    - Arabic (101) Windows layout (the de-facto standard for Arabic PC
      keyboards). Mac Arabic layout differs slightly; a future module
      can extend this.
    - Arabic-Indic digits (٠١٢٣٤٥٦٧٨٩) ↔ ASCII digits.
    - Persian/Farsi extensions are out of scope for v1.

DATA SOURCE:
    Mapping is derived from the Microsoft Arabic 101 keyboard layout
    published at https://en.wikipedia.org/wiki/Keyboard_layout#Arabic
    and verified against Windows 11 `KBDArab.dll`.

LIFE-SAFETY NOTE:
    This module is read-only data. It performs no transformation —
    the actual decision of *when* to apply a mapping is the
    responsibility of ``input_normalizer.py`` (which obeys the
    `agent.md` Safety > Convenience priority hierarchy).
"""

from __future__ import annotations

# ═══════════════════════════════════════════════════════════════════════════════
# ARABIC (101) ↔ ENGLISH QWERTY — SINGLE-CHARACTER MAPPING
# ═══════════════════════════════════════════════════════════════════════════════
#
# Each Arabic letter is produced by exactly one physical key on the
# Arabic-101 layout, so the mapping is bijective for letters (with two
# documented exceptions, see Notes below).

# Arabic letter → English key (the key the user *intended* to press).
AR_TO_EN: dict[str, str] = {
    # Row 1 (top, after digits)
    "ض": "q", "ص": "w", "ث": "e", "ق": "r", "ف": "t",
    "غ": "y", "ع": "u", "ه": "i", "خ": "o", "ح": "p",
    "ج": "[", "د": "]",
    # Row 2 (home)
    "ش": "a", "س": "s", "ي": "d", "ب": "f", "ل": "g",
    "ا": "h", "ت": "j", "ن": "k", "م": "l", "ك": ";",
    "ط": "'",
    # Row 3 (bottom)
    "ئ": "z", "ء": "x", "ؤ": "c", "ر": "v", "لا": "b",
    "ى": "n", "ة": "m", "و": ",", "ز": ".", "ظ": "/",
}

# Inverse: English key → Arabic letter (for completeness; not used by
# the mistype-recovery path but useful for diagnostics and future EN→AR
# transliteration features).
EN_TO_AR: dict[str, str] = {v: k for k, v in AR_TO_EN.items()}

# ═══════════════════════════════════════════════════════════════════════════════
# ARABIC-INDIC DIGITS ↔ ASCII DIGITS
# ═══════════════════════════════════════════════════════════════════════════════

# Arabic-Indic digits (Eastern Arabic numerals: ٠١٢٣٤٥٦٧٨٩) used in
# Egypt, Sudan, the Gulf, and the Levant.
ARABIC_INDIC_DIGIT_TO_ASCII: dict[str, str] = {
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
    "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
}

# Extended Arabic-Indic digits (Persian/Farsi: ۰۱۲۳۴۵۶۷۸۹) — same
# ASCII values, different codepoints. Included for graceful handling
# of Persian mistypes even though Persian layout support is not a v1
# goal.
PERSIAN_DIGIT_TO_ASCII: dict[str, str] = {
    "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4",
    "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
}

# Combined digit map for convenient lookup.
ALL_DIGIT_TO_ASCII: dict[str, str] = {
    **ARABIC_INDIC_DIGIT_TO_ASCII,
    **PERSIAN_DIGIT_TO_ASCII,
}

# ═══════════════════════════════════════════════════════════════════════════════
# UNICODE RANGE CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════
#
# These ranges are used by input_normalizer.py for fast detection
# without importing any external library.

# Arabic main block: U+0600 – U+06FF
# Covers: Arabic letters, digits, diacritics, punctuation.
ARABIC_BLOCK_START: int = 0x0600
ARABIC_BLOCK_END: int = 0x06FF

# Arabic Supplement block: U+0750 – U+077F (historical / extended letters).
ARABIC_SUPPLEMENT_START: int = 0x0750
ARABIC_SUPPLEMENT_END: int = 0x077F

# Arabic Presentation Forms-A: U+FB50 – U+FDFF (ligatures / contextual forms).
ARABIC_PRESENTATION_A_START: int = 0xFB50
ARABIC_PRESENTATION_A_END: int = 0xFDFF

# Arabic Presentation Forms-B: U+FE70 – U+FEFF (presentation forms).
ARABIC_PRESENTATION_B_START: int = 0xFE70
ARABIC_PRESENTATION_B_END: int = 0xFEFF


def is_arabic_codepoint(codepoint: int) -> bool:
    """Return True if ``codepoint`` falls in any of the Arabic Unicode blocks.

    This is the lowest-level building block used by
    ``input_normalizer.detect_arabic_text()``.

    Args:
        codepoint: A Unicode codepoint as an integer (e.g. ``ord('ض')``
            returns 0x636 = 1590).

    Returns:
        True if the codepoint belongs to the Arabic main block, the
        Arabic Supplement, or either of the Presentation Forms blocks.
    """
    return (
        ARABIC_BLOCK_START <= codepoint <= ARABIC_BLOCK_END
        or ARABIC_SUPPLEMENT_START <= codepoint <= ARABIC_SUPPLEMENT_END
        or ARABIC_PRESENTATION_A_START <= codepoint <= ARABIC_PRESENTATION_A_END
        or ARABIC_PRESENTATION_B_START <= codepoint <= ARABIC_PRESENTATION_B_END
    )


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWN LIMITATIONS
# ═══════════════════════════════════════════════════════════════════════════════
#
# 1. The Arabic letter "لا" (lam-alef ligature) is mapped to the 'b' key
#    because pressing 'b' on the Arabic layout produces this ligature.
#    However, the user may also type "لا" as two separate characters
#    (ل + ا), in which case it would map to 'g' + 'h'. The normalizer
#    handles both cases via single-char lookup; multi-char ligature
#    detection is a v2 enhancement.
#
# 2. Shift-state characters (uppercase Arabic symbols like ﷽, ـ, etc.)
#    are NOT mapped. These are rare in mistype scenarios because the
#    user must press Shift, which is unusual when typing quickly.
#
# 3. The Arabic letter "أ إ آ ؤ ئ ء" have separate codepoints from
#    their base forms (ا و ي) but in the Arabic-101 layout they are
#    produced by Shift on the same physical key. The mapping above
#    uses the unshifted base form only; Shift variants are normalized
#    to the unshifted form by the normalizer.
#
# 4. The Persian keyboard layout shares most letters with Arabic-101
#    but adds 4 Persian-specific letters (گ چ پ ژ) at the bracket/
#    semicolon positions. These are NOT mapped in v1 and will fall
#    through to '?' in transliteration output.


__all__ = [
    "AR_TO_EN",
    "EN_TO_AR",
    "ARABIC_INDIC_DIGIT_TO_ASCII",
    "PERSIAN_DIGIT_TO_ASCII",
    "ALL_DIGIT_TO_ASCII",
    "ARABIC_BLOCK_START",
    "ARABIC_BLOCK_END",
    "ARABIC_SUPPLEMENT_START",
    "ARABIC_SUPPLEMENT_END",
    "ARABIC_PRESENTATION_A_START",
    "ARABIC_PRESENTATION_A_END",
    "ARABIC_PRESENTATION_B_START",
    "ARABIC_PRESENTATION_B_END",
    "is_arabic_codepoint",
]
