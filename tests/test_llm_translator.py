"""
tests/test_llm_translator.py — Tests for fireai.infrastructure.llm_translator.

Strategy:
  - Mock the LLM provider detection and SDK calls — we don't want
    tests to depend on real API keys or network connectivity.
  - The OpenAI / google.generativeai SDKs are NOT installed in CI —
    we inject fake modules into sys.modules so the lazy imports inside
    the translator succeed.
  - Test the cache, error handling, and integration with the
    input_normalizer (Phase 3 enable_llm_translation=True path).

Coverage:
  - TestInputValidation — edge cases on input validation.
  - TestProviderDetection — graceful handling when no provider available.
  - TestOpenAICompatibleBackend — mock OpenAI-compatible translation path.
  - TestCacheBehavior — in-memory cache TTL, hit/miss, and eviction.
  - TestInputNormalizerIntegration — end-to-end with mocked translator.
  - TestSafetyInvariants — confirmation always required, original preserved.
  - TestConfiguration — sanity checks on module constants.
"""
from __future__ import annotations

import sys
import time
import types
from unittest.mock import MagicMock, patch

import pytest

from fireai.infrastructure import llm_translator
from fireai.infrastructure.llm_translator import (
    DEFAULT_TIMEOUT_S,
    MAX_INPUT_LENGTH,
    TranslationResult,
    clear_translation_cache,
    is_llm_translation_available,
    translate_arabic_to_english,
)


# ═══════════════════════════════════════════════════════════════════════════════
# FAKE SDK MODULES
# ═══════════════════════════════════════════════════════════════════════════════
#
# The translator does lazy `from openai import OpenAI` and
# `import google.generativeai as genai` inside its backend functions.
# In CI neither SDK is installed, so we install fake modules into
# sys.modules BEFORE the test runs. The fake modules return MagicMocks
# that we configure per-test.


class _FakeOpenAI:
    """Fake openai.OpenAI class — returns the configured mock client."""
    _mock_client = MagicMock()

    def __new__(cls, *args, **kwargs):
        return cls._mock_client


def _install_fake_openai() -> None:
    """Install a fake `openai` module in sys.modules."""
    if "openai" not in sys.modules:
        fake = types.ModuleType("openai")
        fake.OpenAI = _FakeOpenAI
        sys.modules["openai"] = fake


def _reset_fake_openai_client() -> None:
    """Reset the mock OpenAI client to a fresh MagicMock."""
    _FakeOpenAI._mock_client = MagicMock()


# ═══════════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def _isolate_state():
    """Ensure each test starts with an empty cache and fresh mock client."""
    clear_translation_cache()
    _install_fake_openai()
    _reset_fake_openai_client()
    yield
    clear_translation_cache()


def _make_provider_config(provider: str = "openai_direct") -> dict:
    """Build a fake provider config matching mem0_setup.py's format."""
    return {
        "provider": provider,
        "api_key": "fake-key-for-testing",
        "llm_provider": "openai",
        "llm_model": "gpt-4o",
        "embedder_provider": "local",
        "embedder_model": "test",
        "embedding_dims": 384,
        "collection_name": "test",
        "base_url": "https://fake.openai.test/v1" if provider != "openai_direct" else None,
    }


def _setup_openai_response(content: str) -> MagicMock:
    """Configure the fake OpenAI client to return `content` from the LLM."""
    fake_response = MagicMock()
    fake_response.choices = [
        MagicMock(message=MagicMock(content=content))
    ]
    _FakeOpenAI._mock_client.chat.completions.create.return_value = fake_response
    return _FakeOpenAI._mock_client


# ═══════════════════════════════════════════════════════════════════════════════
# 1. INPUT VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════


class TestInputValidation:
    """Edge cases on input validation."""

    def test_empty_input_returns_failure(self) -> None:
        result = translate_arabic_to_english("")
        assert result.success is False
        assert result.translated == ""  # original preserved
        assert result.error == "empty input"

    def test_whitespace_only_input_returns_failure(self) -> None:
        result = translate_arabic_to_english("   ")
        assert result.success is False
        assert result.error == "empty input"

    def test_too_long_input_rejected(self) -> None:
        long_text = "ا" * (MAX_INPUT_LENGTH + 1)
        result = translate_arabic_to_english(long_text)
        assert result.success is False
        assert "too long" in result.error
        assert result.translated == long_text  # original preserved


# ═══════════════════════════════════════════════════════════════════════════════
# 2. PROVIDER DETECTION
# ═══════════════════════════════════════════════════════════════════════════════


class TestProviderDetection:
    """Behavior when no LLM provider is available."""

    def test_no_provider_returns_graceful_failure(self) -> None:
        with patch.object(llm_translator, "_detect_provider", return_value=None):
            result = translate_arabic_to_english("عاوز افتح ملف")
        assert result.success is False
        assert result.translated == "عاوز افتح ملف"  # original preserved
        assert result.error == "no LLM provider available"
        assert result.provider is None

    def test_is_llm_translation_available_false_when_no_provider(self) -> None:
        with patch.object(llm_translator, "_detect_provider", return_value=None):
            assert is_llm_translation_available() is False

    def test_is_llm_translation_available_true_when_provider_exists(self) -> None:
        with patch.object(
            llm_translator,
            "_detect_provider",
            return_value=_make_provider_config(),
        ):
            assert is_llm_translation_available() is True


# ═══════════════════════════════════════════════════════════════════════════════
# 3. TRANSLATION BACKENDS (mocked)
# ═══════════════════════════════════════════════════════════════════════════════


class TestOpenAICompatibleBackend:
    """Mocked tests for the OpenAI-compatible translation path."""

    def test_successful_translation_via_openai_direct(self) -> None:
        """End-to-end: provider detected, OpenAI SDK called, translation returned."""
        fake_client = _setup_openai_response("I want to open a file")

        with patch.object(llm_translator, "_detect_provider",
                          return_value=_make_provider_config("openai_direct")):
            result = translate_arabic_to_english("عاوز افتح ملف")

        assert result.success is True
        assert result.translated == "I want to open a file"
        assert result.provider == "openai_direct"
        assert result.model == "gpt-4o"
        assert result.latency_ms >= 0
        assert result.cached is False
        # Verify the LLM was actually called.
        fake_client.chat.completions.create.assert_called_once()

    def test_successful_translation_via_openrouter(self) -> None:
        _setup_openai_response("Open the project")

        config = _make_provider_config("openrouter")
        with patch.object(llm_translator, "_detect_provider",
                          return_value=config):
            result = translate_arabic_to_english("افتح المشروع")

        assert result.success is True
        assert result.translated == "Open the project"
        assert result.provider == "openrouter"

    def test_empty_llm_response_treated_as_failure(self) -> None:
        _setup_openai_response("")

        with patch.object(llm_translator, "_detect_provider",
                          return_value=_make_provider_config()):
            result = translate_arabic_to_english("عاوز افتح ملف")

        assert result.success is False
        assert "empty" in result.error.lower()
        # Original preserved on failure.
        assert result.translated == "عاوز افتح ملف"

    def test_llm_exception_returns_graceful_failure(self) -> None:
        _FakeOpenAI._mock_client.chat.completions.create.side_effect = \
            RuntimeError("API error")

        with patch.object(llm_translator, "_detect_provider",
                          return_value=_make_provider_config()):
            result = translate_arabic_to_english("عاوز افتح ملف")

        assert result.success is False
        assert "API error" in result.error
        assert result.translated == "عاوز افتح ملف"  # original preserved

    def test_whitespace_only_llm_output_treated_as_failure(self) -> None:
        _setup_openai_response("   \n\t  ")

        with patch.object(llm_translator, "_detect_provider",
                          return_value=_make_provider_config()):
            result = translate_arabic_to_english("عاوز افتح ملف")

        assert result.success is False
        assert "empty" in result.error.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# 4. CACHE BEHAVIOR
# ═══════════════════════════════════════════════════════════════════════════════


class TestCacheBehavior:
    """In-memory cache TTL, hit/miss, and eviction."""

    def test_second_call_uses_cache(self) -> None:
        """A repeated translation should be served from cache, not the LLM."""
        fake_client = _setup_openai_response("I want to open a file")

        with patch.object(llm_translator, "_detect_provider",
                          return_value=_make_provider_config()):
            # First call: hits the LLM.
            r1 = translate_arabic_to_english("عاوز افتح ملف")
            assert r1.cached is False
            assert r1.success is True

            # Second call: should be cached.
            r2 = translate_arabic_to_english("عاوز افتح ملف")
            assert r2.cached is True
            assert r2.success is True
            assert r2.translated == r1.translated

        # LLM was called exactly once.
        assert fake_client.chat.completions.create.call_count == 1

    def test_different_inputs_bypass_cache(self) -> None:
        fake_client = MagicMock()
        resp1 = MagicMock()
        resp1.choices = [MagicMock(message=MagicMock(content="Open the project"))]
        resp2 = MagicMock()
        resp2.choices = [MagicMock(message=MagicMock(content="Calculate load flow"))]
        fake_client.chat.completions.create.side_effect = [resp1, resp2]
        _FakeOpenAI._mock_client = fake_client

        with patch.object(llm_translator, "_detect_provider",
                          return_value=_make_provider_config()):
            r1 = translate_arabic_to_english("افتح المشروع")
            r2 = translate_arabic_to_english("احسب load flow")

        assert r1.translated == "Open the project"
        assert r2.translated == "Calculate load flow"
        assert fake_client.chat.completions.create.call_count == 2

    def test_use_cache_false_bypasses_cache(self) -> None:
        """Even with cache enabled globally, use_cache=False forces a fresh call."""
        fake_client = _setup_openai_response("I want to open a file")

        with patch.object(llm_translator, "_detect_provider",
                          return_value=_make_provider_config()):
            r1 = translate_arabic_to_english("عاوز افتح ملف")
            r2 = translate_arabic_to_english("عاوز افتح ملف", use_cache=False)

        assert r1.cached is False
        assert r2.cached is False  # not from cache
        assert fake_client.chat.completions.create.call_count == 2

    def test_clear_translation_cache_returns_count(self) -> None:
        # Populate cache.
        _setup_openai_response("hi")
        with patch.object(llm_translator, "_detect_provider",
                          return_value=_make_provider_config()):
            translate_arabic_to_english("اختبار")
            translate_arabic_to_english("اختبار آخر")

        # Clear.
        n = clear_translation_cache()
        assert n >= 2  # at least 2 entries evicted


# ═══════════════════════════════════════════════════════════════════════════════
# 5. INTEGRATION WITH input_normalizer
# ═══════════════════════════════════════════════════════════════════════════════


class TestInputNormalizerIntegration:
    """End-to-end tests with normalize_user_text(enable_llm_translation=True)."""

    def test_real_arabic_translated_when_llm_enabled(self) -> None:
        from fireai.core.input_normalizer import normalize_user_text

        fake_translation = TranslationResult(
            original="عاوز افتح ملف",
            translated="I want to open a file",
            success=True,
            provider="openai_direct",
            model="gpt-4o",
            latency_ms=850,
            error=None,
            cached=False,
        )

        with patch(
            "fireai.infrastructure.llm_translator.translate_arabic_to_english",
            return_value=fake_translation,
        ):
            result = normalize_user_text(
                "عاوز افتح ملف",
                context="free_text",
                enable_llm_translation=True,
            )

        assert result.transform_applied == "llm_translation"
        assert result.normalized == "I want to open a file"
        assert result.original == "عاوز افتح ملف"
        assert result.confidence == 0.7
        # CRITICAL: LLM translation ALWAYS requires confirmation.
        assert result.needs_confirmation is True
        assert result.detected_language == "arabic_real"

    def test_real_arabic_preserved_when_llm_disabled(self) -> None:
        from fireai.core.input_normalizer import normalize_user_text

        result = normalize_user_text(
            "عاوز افتح ملف",
            context="free_text",
            enable_llm_translation=False,  # default
        )
        assert result.transform_applied == "none"
        assert result.normalized == "عاوز افتح ملف"
        assert result.needs_confirmation is False  # no transform → no confirm

    def test_real_arabic_preserved_when_llm_fails(self) -> None:
        """If LLM translation fails, original text is preserved (graceful)."""
        from fireai.core.input_normalizer import normalize_user_text

        fake_failure = TranslationResult(
            original="عاوز افتح ملف",
            translated="عاوز افتح ملف",
            success=False,
            provider="openai_direct",
            model="gpt-4o",
            latency_ms=5000,
            error="timeout",
            cached=False,
        )

        with patch(
            "fireai.infrastructure.llm_translator.translate_arabic_to_english",
            return_value=fake_failure,
        ):
            result = normalize_user_text(
                "عاوز افتح ملف",
                context="command",
                enable_llm_translation=True,
            )

        # LLM failed → original preserved.
        assert result.transform_applied != "llm_translation"
        assert result.normalized == "عاوز افتح ملف"
        # COMMAND context still requires confirmation even on failure.
        assert result.needs_confirmation is True

    def test_mistype_path_not_affected_by_llm_flag(self) -> None:
        """The mistype path must NOT invoke the LLM even when enabled."""
        from fireai.core.input_normalizer import normalize_user_text

        with patch(
            "fireai.infrastructure.llm_translator.translate_arabic_to_english"
        ) as mock_translate:
            result = normalize_user_text(
                "ضصثق",
                context="free_text",
                enable_llm_translation=True,
            )

        # Mistype path: deterministic QWERTY recovery, no LLM call.
        assert result.transform_applied == "keyboard_layout"
        assert result.normalized == "qwer"
        mock_translate.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════════
# 6. SAFETY-CRITICAL INVARIANTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestSafetyInvariants:
    """Properties that MUST hold for safety reasons."""

    def test_llm_translation_always_sets_needs_confirmation(self) -> None:
        """Even in FREE_TEXT context, LLM translations require confirmation."""
        from fireai.core.input_normalizer import normalize_user_text

        fake_translation = TranslationResult(
            original="x", translated="x translated", success=True,
            provider="openai_direct", model="gpt-4o",
            latency_ms=100, error=None, cached=False,
        )
        with patch(
            "fireai.infrastructure.llm_translator.translate_arabic_to_english",
            return_value=fake_translation,
        ):
            # FREE_TEXT context — normally doesn't require confirmation,
            # but LLM translation overrides this.
            result = normalize_user_text(
                "عاوز افتح ملف",
                context="free_text",
                enable_llm_translation=True,
            )
        assert result.needs_confirmation is True

    def test_identifier_context_never_invokes_llm(self) -> None:
        """IDENTIFIER context must NEVER invoke LLM translation."""
        from fireai.core.input_normalizer import normalize_user_text

        with patch(
            "fireai.infrastructure.llm_translator.translate_arabic_to_english"
        ) as mock_translate:
            result = normalize_user_text(
                "عاوز افتح ملف",
                context="identifier",
                enable_llm_translation=True,  # even if enabled
            )

        assert result.transform_applied == "none"
        assert result.normalized == "عاوز افتح ملف"
        mock_translate.assert_not_called()

    def test_translate_never_raises(self) -> None:
        """translate_arabic_to_english must NEVER raise — always returns a result."""
        # Even if the underlying SDK raises something weird.
        _FakeOpenAI._mock_client.chat.completions.create.side_effect = \
            Exception("catastrophic failure")

        with patch.object(llm_translator, "_detect_provider",
                          return_value=_make_provider_config()):
            result = translate_arabic_to_english("عاوز افتح ملف")

        assert isinstance(result, TranslationResult)
        assert result.success is False
        assert "catastrophic failure" in result.error
        assert result.translated == "عاوز افتح ملف"  # original preserved


# ═══════════════════════════════════════════════════════════════════════════════
# 7. CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════


class TestConfiguration:
    """Sanity checks on module-level constants."""

    def test_default_timeout_is_reasonable(self) -> None:
        # 10s is the documented default — must not exceed 30s (would
        # block request validation too long).
        assert DEFAULT_TIMEOUT_S == 10.0
        assert DEFAULT_TIMEOUT_S <= 30.0

    def test_max_input_length_limits_cost(self) -> None:
        # 500 chars is enough for typical UI input but blocks abuse.
        assert MAX_INPUT_LENGTH == 500
        assert MAX_INPUT_LENGTH <= 1000
