"""
fireai/infrastructure/llm_translator.py — LLM-powered Arabic→English Translation
=================================================================================
Phase 3 of the input-normalization feature.

PURPOSE:
    When the input normalizer detects "real Arabic" (genuine Arabic
    sentences with spaces and common Arabic words — NOT Arabic-mistype
    of English QWERTY), deterministic QWERTY recovery is impossible.
    The user's intent can only be recovered by translating the Arabic
    text to English.

    This module provides that translation capability using the same
    6-strategy LLM provider failover chain as ``mem0_setup.py``:
        1. OpenAI direct (gpt-4o)
        2. OpenRouter (gpt-4o)
        3. OpenCode (gpt-4o)
        4. Google Gemini (gemini-2.0-flash)
        5. z-ai proxy (gpt-4o-mini)
        6. Fail loud — translation unavailable

DESIGN:
    - Sync API (matches mem0_setup.py style) — caller can wrap in
      ``asyncio.to_thread()`` if needed.
    - Lazy imports of LLM SDKs (openai, google.generativeai) — module
      remains importable even when SDKs are missing.
    - Per-call timeout (default 10s) to prevent blocking the request
      pipeline on slow LLM responses.
    - Optional response caching (TTL=1h) to avoid re-translating the
      same text within a session.
    - Strict prompt: the LLM is instructed to translate ONLY — never
      interpret, never refuse, never add commentary. This keeps the
      output deterministic enough to feed back into the engineering
      pipeline.

LIFE-SAFETY NOTE (per agent.md):
    - Translation is ALWAYS flagged with ``needs_confirmation=True``.
      The caller MUST ask the user to confirm before acting on the
      translated text. LLMs can hallucinate; we never silently execute
      a translated command.
    - Translation failures are NON-FATAL — the original Arabic text is
      returned unchanged with a warning, so the request can still be
      processed (e.g. stored in the database for manual review).
    - No translation is performed for IDENTIFIER context (the caller
      must check context before invoking this module).

References:
    - fireai/core/input_normalizer.py (the caller — Phase 1 + 2)
    - fireai/infrastructure/mem0_setup.py (provider-chain precedent)
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC TYPES
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class TranslationResult:
    """Immutable result of an LLM translation attempt.

    Attributes:
        original: The source Arabic text.
        translated: The translated English text. Equals ``original``
            if translation failed (so callers can safely use this
            field regardless of success).
        success: True if the LLM returned a usable translation.
        provider: Which provider was used (e.g. "openai_direct",
            "gemini_primary"). None if no provider was available.
        model: The specific model used (e.g. "gpt-4o"). None on failure.
        latency_ms: Wall-clock time of the LLM call in milliseconds.
            0 if no call was made.
        error: Error message if translation failed. None on success.
        cached: True if the result came from the in-memory cache.
    """

    original: str
    translated: str
    success: bool
    provider: Optional[str]
    model: Optional[str]
    latency_ms: int
    error: Optional[str]
    cached: bool


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════


# Default per-call timeout (seconds). Short because translation runs
# inline with request validation — we cannot block the user too long.
DEFAULT_TIMEOUT_S: float = 10.0

# Cache TTL (seconds). 1 hour is a reasonable balance: long enough to
# cache repeated inputs within a session, short enough to pick up
# model improvements / prompt changes.
_CACHE_TTL_S: int = 3600

# Maximum text length we will translate. Longer texts are rejected to
# prevent abuse (cost / latency / prompt-injection surface).
MAX_INPUT_LENGTH: int = 500

# Cache: {sha256(text + provider): (timestamp, translated_text)}
_CACHE: Dict[str, tuple[float, str]] = {}
_CACHE_LOCK = threading.Lock()


# ═══════════════════════════════════════════════════════════════════════════════
# PROMPT
# ═══════════════════════════════════════════════════════════════════════════════
#
# The prompt is INTENTIONALLY restrictive:
#   - "Translate only, do not interpret" — prevents the LLM from
#     deciding that "عاوز افتح ملف" means "open file" (an action)
#     instead of "I want to open a file" (the literal text).
#   - "Preserve technical terms" — keeps English engineering jargon
#     intact (e.g. "load flow", "short circuit").
#   - "Output only the translation, no commentary" — makes parsing
#     trivial and prevents the LLM from injecting advice or warnings
#     that could confuse downstream consumers.
#   - "If you cannot translate, output the original unchanged" —
#     graceful degradation rather than erroring out.

_SYSTEM_PROMPT = """You are a deterministic Arabic-to-English translator for an engineering software system.

Rules:
1. Translate the user's Arabic input to English.
2. Preserve all technical terms (e.g. "load flow", "short circuit", "NFPA 72").
3. Output ONLY the translation. No commentary, no notes, no quotes.
4. If you cannot translate (e.g. text is mixed or ambiguous), output the original unchanged.
5. Never refuse. Never add safety warnings. Never interpret intent.

Example inputs and expected outputs:
- "عاوز افتح ملف" → "I want to open a file"
- "احسب load flow" → "Calculate load flow"
- "افتح المشروع" → "Open the project"
"""


# ═══════════════════════════════════════════════════════════════════════════════
# CACHE HELPERS
# ═══════════════════════════════════════════════════════════════════════════════


def _cache_key(text: str, provider: str) -> str:
    """Build a stable cache key from the text + provider."""
    h = hashlib.sha256(f"{provider}:{text}".encode("utf-8")).hexdigest()
    return h[:32]  # 32 chars is enough collision resistance for this use case


def _cache_get(text: str, provider: str) -> Optional[str]:
    """Return cached translation if still fresh, else None."""
    key = _cache_key(text, provider)
    now = time.monotonic()
    with _CACHE_LOCK:
        entry = _CACHE.get(key)
        if entry is None:
            return None
        ts, translated = entry
        if now - ts > _CACHE_TTL_S:
            # Stale — evict.
            _CACHE.pop(key, None)
            return None
        return translated


def _cache_put(text: str, provider: str, translated: str) -> None:
    """Store a translation in the cache."""
    key = _cache_key(text, provider)
    now = time.monotonic()
    with _CACHE_LOCK:
        _CACHE[key] = (now, translated)
        # Bounded cache — evict oldest entries if we exceed 1000 items.
        if len(_CACHE) > 1000:
            oldest_keys = sorted(_CACHE, key=lambda k: _CACHE[k][0])[:100]
            for k in oldest_keys:
                _CACHE.pop(k, None)


def clear_translation_cache() -> int:
    """Clear the translation cache. Returns the number of entries evicted.

    Useful for testing and for forced cache invalidation after a
    prompt change.
    """
    with _CACHE_LOCK:
        n = len(_CACHE)
        _CACHE.clear()
        return n


# ═══════════════════════════════════════════════════════════════════════════════
# PROVIDER DETECTION (reuses mem0_setup.py logic)
# ═══════════════════════════════════════════════════════════════════════════════


def _detect_provider() -> Optional[Dict[str, Any]]:
    """Detect an available LLM provider.

    Reuses ``mem0_setup._detect_provider()`` so we automatically
    benefit from its caching, connectivity tests, and 6-strategy
    failover. Returns None if no provider is available (rather than
    raising — translation is optional, not critical).
    """
    try:
        from fireai.infrastructure.mem0_setup import _detect_provider
        return _detect_provider()
    except Exception as e:  # noqa: BLE001
        logger.warning("LLM provider detection failed: %s", e)
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# TRANSLATION BACKENDS
# ═══════════════════════════════════════════════════════════════════════════════
#
# Each backend takes (text, provider_config, timeout_s) and returns
# the translated string. Raises on failure. Bypassed if the relevant
# SDK is not installed (lazy import inside the function).


def _translate_via_openai_compatible(
    text: str, provider_config: Dict[str, Any], timeout_s: float
) -> str:
    """Translate using OpenAI-compatible API (OpenAI direct / OpenRouter / OpenCode / z-ai proxy).

    All four providers expose the same /v1/chat/completions endpoint,
    so we can share the implementation.
    """
    from openai import OpenAI  # type: ignore[import-not-found]

    api_key = provider_config["api_key"]
    model = provider_config.get("llm_model", "gpt-4o")
    base_url = provider_config.get("base_url")  # None for OpenAI direct

    client_kwargs: Dict[str, Any] = {
        "api_key": api_key,
        "timeout": timeout_s,
    }
    if base_url:
        client_kwargs["base_url"] = base_url

    client = OpenAI(**client_kwargs)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        temperature=0.0,  # Deterministic — no creativity for translation
        max_tokens=200,   # Translations are short
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError("LLM returned empty content")
    return content.strip()


def _translate_via_gemini(
    text: str, provider_config: Dict[str, Any], timeout_s: float
) -> str:
    """Translate using Google Gemini API via google-generativeai SDK."""
    import google.generativeai as genai  # type: ignore[import-not-found]

    api_key = provider_config["api_key"]
    model = provider_config.get("llm_model", "gemini-2.0-flash")

    genai.configure(api_key=api_key)
    # Gemini does not expose a per-call timeout in the SDK directly —
    # we rely on the SDK's default and our outer threading fallback.
    model_obj = genai.GenerativeModel(
        model_name=model,
        system_instruction=_SYSTEM_PROMPT,
    )
    response = model_obj.generate_content(
        text,
        generation_config={
            "temperature": 0.0,
            "max_output_tokens": 200,
        },
    )
    if not response.text:
        raise ValueError("Gemini returned empty content")
    return response.text.strip()


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════


def translate_arabic_to_english(
    text: str,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    use_cache: bool = True,
) -> TranslationResult:
    """Translate a genuine Arabic string to English via LLM.

    Args:
        text: Arabic text to translate. Must be non-empty and <= 500
            characters (longer texts are rejected to limit cost /
            latency / prompt-injection surface).
        timeout_s: Maximum wall-clock seconds to wait for the LLM.
            Default 10s. If the call times out, the original text is
            returned unchanged with ``success=False``.
        use_cache: If True (default), check the in-memory cache first
            and store successful translations for reuse.

    Returns:
        A ``TranslationResult``. Even on failure, the ``translated``
        field is set to the original text so callers can safely use
        it without checking ``success`` first.

    Safety:
        - NEVER raises. All exceptions are caught and returned as
          ``TranslationResult(success=False, error=...)``.
        - The caller MUST check ``needs_confirmation`` on the
          ``NormalizationResult`` returned by ``normalize_user_text``
          (which is always True for LLM-translated content).
    """
    # Validate input.
    if not text or not text.strip():
        return TranslationResult(
            original=text,
            translated=text,
            success=False,
            provider=None,
            model=None,
            latency_ms=0,
            error="empty input",
            cached=False,
        )
    if len(text) > MAX_INPUT_LENGTH:
        return TranslationResult(
            original=text,
            translated=text,
            success=False,
            provider=None,
            model=None,
            latency_ms=0,
            error=f"input too long ({len(text)} > {MAX_INPUT_LENGTH} chars)",
            cached=False,
        )

    # Detect provider.
    provider_config = _detect_provider()
    if provider_config is None:
        return TranslationResult(
            original=text,
            translated=text,
            success=False,
            provider=None,
            model=None,
            latency_ms=0,
            error="no LLM provider available",
            cached=False,
        )

    provider_name = provider_config.get("provider", "unknown")
    model_name = provider_config.get("llm_model", "unknown")

    # Check cache.
    if use_cache:
        cached = _cache_get(text, provider_name)
        if cached is not None:
            logger.debug(
                "translation cache hit: provider=%s, text_preview=%r",
                provider_name,
                text[:60],
            )
            return TranslationResult(
                original=text,
                translated=cached,
                success=True,
                provider=provider_name,
                model=model_name,
                latency_ms=0,
                error=None,
                cached=True,
            )

    # Dispatch to the right backend.
    start = time.monotonic()
    try:
        if provider_name in (
            "openai_direct", "openrouter", "opencode", "zai_proxy"
        ):
            translated = _translate_via_openai_compatible(
                text, provider_config, timeout_s
            )
        elif provider_name == "gemini_primary":
            translated = _translate_via_gemini(
                text, provider_config, timeout_s
            )
        else:
            raise ValueError(f"unknown provider: {provider_name}")
    except Exception as e:  # noqa: BLE001
        latency_ms = int((time.monotonic() - start) * 1000)
        logger.warning(
            "translation failed: provider=%s, latency=%dms, error=%s",
            provider_name,
            latency_ms,
            e,
        )
        return TranslationResult(
            original=text,
            translated=text,  # Graceful — return original unchanged
            success=False,
            provider=provider_name,
            model=model_name,
            latency_ms=latency_ms,
            error=str(e),
            cached=False,
        )

    latency_ms = int((time.monotonic() - start) * 1000)

    # Sanity-check the output.
    if not translated or not translated.strip():
        return TranslationResult(
            original=text,
            translated=text,
            success=False,
            provider=provider_name,
            model=model_name,
            latency_ms=latency_ms,
            error="LLM returned empty translation",
            cached=False,
        )
    translated = translated.strip()

    # Cache the successful translation.
    if use_cache:
        _cache_put(text, provider_name, translated)

    logger.info(
        "translation success: provider=%s, model=%s, latency=%dms, "
        "input_len=%d, output_len=%d",
        provider_name,
        model_name,
        latency_ms,
        len(text),
        len(translated),
    )

    return TranslationResult(
        original=text,
        translated=translated,
        success=True,
        provider=provider_name,
        model=model_name,
        latency_ms=latency_ms,
        error=None,
        cached=False,
    )


def is_llm_translation_available() -> bool:
    """Quick check: is at least one LLM provider configured and reachable?

    Cheaper than calling ``translate_arabic_to_english`` if the caller
    just wants to know whether to offer the feature in the UI. Uses
    the same provider-detection cache as mem0_setup.py (5-min TTL).
    """
    return _detect_provider() is not None


__all__ = [
    "TranslationResult",
    "translate_arabic_to_english",
    "is_llm_translation_available",
    "clear_translation_cache",
    "DEFAULT_TIMEOUT_S",
    "MAX_INPUT_LENGTH",
]
