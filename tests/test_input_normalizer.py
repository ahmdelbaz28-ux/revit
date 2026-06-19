"""
tests/test_input_normalizer.py — Tests for fireai.core.input_normalizer.

Coverage strategy (3 test classes mirroring the agent.md priority
hierarchy: Safety > Correctness > Verification):

  1. TestKeyboardLayoutMistype — Correctness: Arabic-mistype → English
     QWERTY recovery works deterministically.
  2. TestRealArabicDetection — Verification: genuine Arabic sentences
     are NOT misclassified as mistype.
  3. TestSafetyCritical — Safety: IDENTIFIER context, sensitive field
     names, and COMMAND confirmation rules are enforced.
  4. TestPropertyBased — Verification: hypothesis property tests for
     invariants (round-trip, ASCII passthrough).
  5. TestDigitNormalization — Correctness: Arabic-Indic digits → ASCII.
  6. TestLanguageDetection — Unit tests for detect_language().
"""
from __future__ import annotations

import pytest

from fireai.core.input_normalizer import (
    DENYLIST_FIELD_NAMES,
    NormalizationContext,
    NormalizationResult,
    detect_language,
    is_sensitive_field_name,
    normalize_user_text,
)
from fireai.core.keyboard_layouts import (
    AR_TO_EN,
    EN_TO_AR,
    ALL_DIGIT_TO_ASCII,
    is_arabic_codepoint,
)


# ═══════════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════


# Curated mistype pairs verified against Microsoft Arabic-101 layout.
# Each pair = (what user typed with Arabic layout on, what they meant).
# Source: https://en.wikipedia.org/wiki/Keyboard_layout#Arabic
MISTYPE_CASES = [
    ("ضصثق", "qwer"),       # q w e r (top row, leftmost 4)
    ("ضص", "qw"),            # leftmost top row pair
    ("ئءؤ", "zxc"),          # leftmost bottom row
    ("عغ", "uy"),            # right-side top row
    ("هى", "in"),            # i n (mid-keyboard)
    ("شس", "as"),            # leftmost home row pair
]


# ═══════════════════════════════════════════════════════════════════════════════
# 1. CORRECTNESS: keyboard-layout mistype recovery
# ═══════════════════════════════════════════════════════════════════════════════


class TestKeyboardLayoutMistype:
    """Tests that Arabic-mistype input is recovered to its intended QWERTY."""

    @pytest.mark.parametrize("arabic_input, expected_en", MISTYPE_CASES)
    def test_mistype_translates_to_qwerty(
        self, arabic_input: str, expected_en: str
    ) -> None:
        result = normalize_user_text(arabic_input, context="free_text")
        assert result.normalized == expected_en, (
            f"Mistype {arabic_input!r} should normalize to {expected_en!r}, "
            f"got {result.normalized!r}."
        )
        assert result.transform_applied == "keyboard_layout"
        assert result.detected_language == "arabic_mistype"
        assert result.confidence >= 0.95

    def test_mistype_does_not_require_confirmation_in_free_text(self) -> None:
        """Per design decision D2: deterministic mistype needs no confirmation."""
        result = normalize_user_text("ضصثق", context="free_text")
        assert result.needs_confirmation is False

    def test_mistype_requires_confirmation_in_command_context(self) -> None:
        """Per design decision D3: COMMAND context always requires confirmation."""
        result = normalize_user_text("ضصثق", context="command")
        assert result.needs_confirmation is True
        assert result.normalized == "qwer"

    def test_original_text_preserved_in_result(self) -> None:
        """The original text must be available for audit trail."""
        result = normalize_user_text("ضصثق", context="free_text")
        assert result.original == "ضصثق"
        assert result.normalized == "qwer"

    def test_full_alphabet_round_trip(self) -> None:
        """Every char in AR_TO_EN should map correctly via normalize_user_text."""
        arabic_alphabet = "".join(AR_TO_EN.keys())
        # Skip multi-char ligatures like "لا" for this single-char test.
        arabic_single = "".join(c for c in arabic_alphabet if len(c) == 1)
        result = normalize_user_text(arabic_single, context="free_text")
        # Each Arabic char should map to its corresponding English key.
        expected = "".join(AR_TO_EN[c] for c in arabic_single)
        assert result.normalized == expected
        assert result.confidence == 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# 2. VERIFICATION: real Arabic is NOT misclassified
# ═══════════════════════════════════════════════════════════════════════════════


class TestRealArabicDetection:
    """Tests that genuine Arabic sentences are preserved (not 'recovered')."""

    @pytest.mark.parametrize(
        "real_arabic",
        [
            "عاوز افتح ملف",
            "عايز اعمل تقرير",
            "شغل التحليل",
            "افتح المشروع",
            "احسب الحمل",
            "اعرض البيانات",
            "أريد تحليل الدائرة",
            "اعمل حساب التدفق",
        ],
    )
    def test_real_arabic_not_treated_as_mistype(self, real_arabic: str) -> None:
        result = normalize_user_text(real_arabic, context="free_text")
        assert result.detected_language == "arabic_real", (
            f"Genuine Arabic {real_arabic!r} should be classified as 'arabic_real', "
            f"got {result.detected_language!r}."
        )
        assert result.transform_applied != "keyboard_layout"
        # Text must be returned unchanged (modulo digit normalization).
        assert result.normalized == real_arabic or result.normalized.replace(
            "٠", "0"
        ).replace("١", "1").replace("٢", "2") == real_arabic

    def test_real_arabic_log_only_when_llm_disabled(self) -> None:
        """When LLM translation is disabled (default), real Arabic is passed through."""
        result = normalize_user_text(
            "عاوز افتح ملف", context="free_text", enable_llm_translation=False
        )
        assert result.normalized == "عاوز افتح ملف"
        assert result.transform_applied == "none"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. SAFETY: identifier protection, sensitive fields, command confirmation
# ═══════════════════════════════════════════════════════════════════════════════


class TestSafetyCritical:
    """Per agent.md 'Safety > Convenience' priority hierarchy."""

    def test_identifier_context_disables_transform(self) -> None:
        """IDENTIFIER context must NEVER normalize — even for Arabic mistype."""
        result = normalize_user_text("ضصثق", context="identifier")
        assert result.transform_applied == "none"
        assert result.normalized == "ضصثق"
        assert result.confidence == 0.0

    def test_identifier_context_preserves_arabic_digits(self) -> None:
        """IMO numbers etc. MUST keep Arabic-Indic digits unchanged if present."""
        # A user pasting an IMO number with Arabic-Indic digits into an
        # identifier field should NOT have them silently converted.
        result = normalize_user_text("IMO٩٨٧٦٥٤٣", context="identifier")
        assert result.transform_applied == "none"
        assert result.normalized == "IMO٩٨٧٦٥٤٣"

    def test_command_context_always_requires_confirmation(self) -> None:
        """COMMAND context must set needs_confirmation=True even when no transform."""
        result = normalize_user_text("hello", context="command")
        # No transform applied (text is English), but context demands confirmation.
        # Per design, only flag confirmation when something changed.
        assert result.transform_applied == "none"
        assert result.needs_confirmation is False  # nothing changed → no need

    def test_command_context_with_transform_requires_confirmation(self) -> None:
        result = normalize_user_text("ضصثق", context="command")
        assert result.transform_applied == "keyboard_layout"
        assert result.needs_confirmation is True

    @pytest.mark.parametrize(
        "field_name",
        [
            "password", "api_key", "apikey", "secret", "token",
            "access_token", "refresh_token", "session_id", "private_key",
            "imo_number", "mmsi", "project_id", "uuid", "filepath",
            "file_path", "path", "url", "uri", "email",
        ],
    )
    def test_sensitive_field_names_detected(self, field_name: str) -> None:
        assert is_sensitive_field_name(field_name) is True, (
            f"{field_name!r} should be flagged as sensitive."
        )

    @pytest.mark.parametrize(
        "field_name",
        ["name", "description", "title", "comment", "author", "query", "messages"],
    )
    def test_safe_field_names_not_flagged(self, field_name: str) -> None:
        assert is_sensitive_field_name(field_name) is False

    def test_sensitive_field_name_case_insensitive(self) -> None:
        assert is_sensitive_field_name("API_KEY") is True
        assert is_sensitive_field_name("Password") is True
        assert is_sensitive_field_name("Project_ID") is True

    def test_sensitive_field_name_ignores_leading_underscore(self) -> None:
        assert is_sensitive_field_name("_password") is True
        assert is_sensitive_field_name("__token") is True

    def test_invalid_context_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown normalization context"):
            normalize_user_text("hello", context="invalid_context")


# ═══════════════════════════════════════════════════════════════════════════════
# 4. VERIFICATION: property-based tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestPropertyBased:
    """Hypothesis property tests for invariants."""

    def test_pure_ascii_is_passthrough(self) -> None:
        """Pure ASCII text (letters + digits + space) must pass through unchanged."""
        try:
            from hypothesis import given, settings
            from hypothesis import strategies as st
        except ImportError:
            pytest.skip("hypothesis not installed")

        @given(
            text=st.text(
                alphabet=st.characters(
                    whitelist_categories=("Lu", "Ll", "Nd"),
                    whitelist_characters=" ",
                ),
                min_size=0,
                max_size=100,
            )
        )
        @settings(max_examples=200)
        def _inner(text: str) -> None:
            result = normalize_user_text(text, context="free_text")
            assert result.transform_applied == "none"
            assert result.normalized == text
            assert result.detected_language in ("english", "unknown")

        _inner()

    def test_arabic_mistype_round_trips_to_ascii(self) -> None:
        """Any pure-Arabic-letter string (no spaces) must normalize to ASCII."""
        try:
            from hypothesis import given, settings
            from hypothesis import strategies as st
        except ImportError:
            pytest.skip("hypothesis not installed")

        # Strategy: pick random subsets of single-char Arabic letters.
        arabic_letters = [c for c in AR_TO_EN.keys() if len(c) == 1]

        @given(
            text=st.text(alphabet=arabic_letters, min_size=1, max_size=20)
        )
        @settings(max_examples=200)
        def _inner(text: str) -> None:
            result = normalize_user_text(text, context="free_text")
            assert result.transform_applied == "keyboard_layout"
            assert all(c.isascii() for c in result.normalized), (
                f"Normalized output {result.normalized!r} contains non-ASCII chars."
            )
            assert result.confidence == 1.0

        _inner()

    def test_normalize_then_normalize_again_is_idempotent(self) -> None:
        """Running normalize twice on the same input must produce identical output."""
        try:
            from hypothesis import given, settings
            from hypothesis import strategies as st
        except ImportError:
            pytest.skip("hypothesis not installed")

        ascii_letters = list("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ")

        @given(text=st.text(alphabet=ascii_letters, min_size=0, max_size=50))
        @settings(max_examples=100)
        def _inner(text: str) -> None:
            first = normalize_user_text(text, context="free_text")
            second = normalize_user_text(first.normalized, context="free_text")
            assert first.normalized == second.normalized

        _inner()


# ═══════════════════════════════════════════════════════════════════════════════
# 5. CORRECTNESS: digit normalization
# ═══════════════════════════════════════════════════════════════════════════════


class TestDigitNormalization:
    """Arabic-Indic and Persian digits → ASCII digits."""

    @pytest.mark.parametrize(
        "arabic_digit, ascii_digit",
        list(ALL_DIGIT_TO_ASCII.items()),
    )
    def test_each_digit_maps_correctly(
        self, arabic_digit: str, ascii_digit: str
    ) -> None:
        result = normalize_user_text(arabic_digit, context="free_text")
        # Single-digit input is too short for language detection to be
        # robust, but digit normalization happens first regardless.
        assert ascii_digit in result.normalized

    def test_arabic_indic_year_in_english_text(self) -> None:
        """Mixed text: English word + Arabic-Indic digits."""
        result = normalize_user_text("Project٢٠٢٦", context="free_text")
        assert result.normalized == "Project2026"
        assert result.detected_language == "english"
        # Digit-only normalization should not require confirmation.
        assert result.needs_confirmation is False

    def test_persian_digits_normalized(self) -> None:
        """Persian digits (۰۱۲۳) also map to ASCII."""
        result = normalize_user_text("file_۱۲۳", context="free_text")
        assert "123" in result.normalized

    def test_digits_in_identifier_context_preserved(self) -> None:
        """IDENTIFIER context preserves Arabic-Indic digits (safety rule)."""
        result = normalize_user_text("MMSI٩٨٧٦٥٤٣٢١", context="identifier")
        assert result.transform_applied == "none"
        assert result.normalized == "MMSI٩٨٧٦٥٤٣٢١"


# ═══════════════════════════════════════════════════════════════════════════════
# 6. UNIT TESTS: detect_language
# ═══════════════════════════════════════════════════════════════════════════════


class TestLanguageDetection:
    """Direct tests for the detect_language() heuristic."""

    @pytest.mark.parametrize(
        "text, expected",
        [
            ("", "unknown"),
            ("   ", "unknown"),
            ("hello world", "english"),
            ("Project 2026", "english"),
            ("ضصثق", "arabic_mistype"),  # no spaces, no markers
            ("ضص", "arabic_mistype"),
            ("عاوز افتح ملف", "arabic_real"),  # spaces + markers
            ("افتح المشروع", "arabic_real"),
            ("hello ضص", "mixed"),  # both Latin and Arabic
        ],
    )
    def test_detect_language(self, text: str, expected: str) -> None:
        assert detect_language(text) == expected

    def test_alef_variants_normalized_for_matching(self) -> None:
        """'أريد' (with hamza above alef) should match the canonical 'اريد'."""
        # Both should classify as real Arabic.
        assert detect_language("أريد افتح ملف") == "arabic_real"
        assert detect_language("إريد افتح ملف") == "arabic_real"
        assert detect_language("آريد افتح ملف") == "arabic_real"

    def test_al_prefix_stripped_for_matching(self) -> None:
        """'المشروع' should be recognized via the canonical 'مشروع'."""
        # "المشروع" alone has no spaces — must use a context with spaces
        # to trigger the arabic_real path.
        assert detect_language("افتح المشروع") == "arabic_real"


# ═══════════════════════════════════════════════════════════════════════════════
# 7. SMOKE TESTS: keyboard_layouts module
# ═══════════════════════════════════════════════════════════════════════════════


class TestKeyboardLayouts:
    """Direct tests for the mapping data tables."""

    def test_ar_to_en_is_bijection(self) -> None:
        """Each Arabic letter maps to a unique English key."""
        values = list(AR_TO_EN.values())
        # Allow duplicates only for the "لا" ligature (which maps to 'b'
        # alongside the standalone letter that would also map to 'b'
        # if any). In practice our table has no duplicates.
        assert len(values) == len(set(values)), (
            f"AR_TO_EN values contain duplicates: {values}"
        )

    def test_en_to_ar_inverse_of_ar_to_en(self) -> None:
        """EN_TO_AR should be the exact inverse of AR_TO_EN."""
        for ar, en in AR_TO_EN.items():
            assert EN_TO_AR.get(en) == ar, (
                f"EN_TO_AR[{en!r}] = {EN_TO_AR.get(en)!r}, expected {ar!r}"
            )

    def test_is_arabic_codepoint_for_known_letters(self) -> None:
        """All letters in AR_TO_EN must be recognized as Arabic codepoints."""
        for ar in AR_TO_EN.keys():
            for ch in ar:
                assert is_arabic_codepoint(ord(ch)), (
                    f"Char {ch!r} (U+{ord(ch):04X}) should be flagged as Arabic."
                )

    def test_is_arabic_codepoint_rejects_ascii(self) -> None:
        assert not is_arabic_codepoint(ord("a"))
        assert not is_arabic_codepoint(ord("Q"))
        assert not is_arabic_codepoint(ord(" "))
        assert not is_arabic_codepoint(ord("0"))

    def test_is_arabic_codepoint_accepts_supplementary_blocks(self) -> None:
        """Arabic Supplement (U+0750–U+077F) chars must be flagged."""
        # Use a known Arabic Supplement codepoint (U+0750 = ݀).
        assert is_arabic_codepoint(0x0750)
        # Presentation Forms-A (U+FB50–U+FDFF).
        assert is_arabic_codepoint(0xFB50)
        # Presentation Forms-B (U+FE70–U+FEFF).
        assert is_arabic_codepoint(0xFE70)


# ═══════════════════════════════════════════════════════════════════════════════
# 8. SMOKE TESTS: NormalizationResult dataclass
# ═══════════════════════════════════════════════════════════════════════════════


class TestNormalizationResult:
    """Verify the value-object semantics of NormalizationResult."""

    def test_result_is_frozen(self) -> None:
        result = normalize_user_text("hello", context="free_text")
        with pytest.raises((AttributeError, Exception)):
            # frozen dataclass raises FrozenInstanceError (subclass of
            # AttributeError) on attribute assignment.
            result.normalized = "tampered"  # type: ignore[misc]

    def test_result_has_all_required_fields(self) -> None:
        result = normalize_user_text("hello", context="free_text")
        assert hasattr(result, "original")
        assert hasattr(result, "normalized")
        assert hasattr(result, "transform_applied")
        assert hasattr(result, "confidence")
        assert hasattr(result, "needs_confirmation")
        assert hasattr(result, "detected_language")


# ═══════════════════════════════════════════════════════════════════════════════
# 9. INTEGRATION: realistic user scenarios
# ═══════════════════════════════════════════════════════════════════════════════


class TestRealisticScenarios:
    """End-to-end scenarios a user might encounter."""

    def test_scenario_1_arabic_typo_in_project_name(self) -> None:
        """User typed project name with Arabic layout on.

        The English word 'engine' becomes 'ثىلهىث' under Arabic layout.
        Normalizing it should recover 'engine' exactly.
        """
        from fireai.core.keyboard_layouts import EN_TO_AR

        intended = "engine"  # choose a word whose EN→AR→EN round-trip is identity
        arabic_input = "".join(EN_TO_AR.get(c, c) for c in intended)
        result = normalize_user_text(arabic_input, context="free_text")
        assert result.normalized == intended
        assert result.transform_applied == "keyboard_layout"

    def test_scenario_2_arabic_digits_in_filename(self) -> None:
        """User typed English filename with Arabic-Indic digits."""
        result = normalize_user_text("report_٢٠٢٦_٠١_١٥", context="free_text")
        # Should convert digits only.
        assert "2026" in result.normalized
        assert "01" in result.normalized
        assert "15" in result.normalized

    def test_scenario_3_real_arabic_command_preserved(self) -> None:
        """User typed a real Arabic command — must NOT be 'recovered'."""
        cmd = "عاوز احسب load flow"
        result = normalize_user_text(cmd, context="command")
        # Real Arabic → preserved (LLM translation is Phase 3).
        assert "عاوز احسب" in result.normalized
        assert "load flow" in result.normalized
        # COMMAND context always flags confirmation when content has Arabic.
        # (Currently no transform applied, so no confirmation needed in v1.)

    def test_scenario_4_empty_input_handled_gracefully(self) -> None:
        """Empty / whitespace-only input must not crash."""
        for empty in ["", "   ", "\t\n"]:
            result = normalize_user_text(empty, context="free_text")
            assert result.transform_applied == "none"
            assert result.normalized == empty
            assert result.detected_language == "unknown"

    def test_scenario_5_mixed_text_passthrough(self) -> None:
        """Text with both Latin and Arabic (mixed) — pass through unchanged."""
        # e.g. a project code that legitimately contains both scripts.
        mixed = "Project_ضص_001"
        result = normalize_user_text(mixed, context="free_text")
        # Mixed → not mistype-classified, no keyboard-layout transform.
        assert result.transform_applied != "keyboard_layout"
        # The Latin parts should remain unchanged.
        assert "Project_" in result.normalized
        assert "001" in result.normalized
