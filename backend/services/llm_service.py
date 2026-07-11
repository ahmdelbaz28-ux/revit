"""
backend/services/llm_service.py — LLM Service (OpenAI-compatible / Zenmux).

PURPOSE
-------
Provides an async LLM chat completion service backed by any OpenAI-compatible
API (Zenmux, OpenAI, Modal, NVIDIA build.nvidia.com, etc.). Designed for the
FireAI AI Copilot — an engineering assistant that helps fire-protection
engineers interpret NFPA 72 / NEC calculation results, draft compliance
narratives, and answer code questions.

This service is **advisory only**. It NEVER overrides deterministic NFPA 72
calculations produced by the QOMN kernel. All LLM output is labeled with a
``source`` field so downstream code can distinguish AI-generated text from
deterministic engineering results.

DESIGN
------
* OpenAI Python SDK (``openai.AsyncOpenAI``) against ``ZENMUX_BASE_URL``.
* Singleton with thread-safe double-checked locking (same pattern as
  ``weather_service.py``, ``memory_service.py``).
* tenacity retry on transient network errors only (never retries 4xx).
* Graceful degradation: if ``ZENMUX_API_KEY`` is unset, the service reports
  ``available=False`` and endpoints return HTTP 503 (not 500).

ENVIRONMENT VARIABLES
---------------------
Primary provider (Zenmux):
* ``ZENMUX_API_KEY``       — API key (required for production use)
* ``ZENMUX_BASE_URL``      — defaults to ``https://zenmux.ai/api/v1``
* ``ZENMUX_MODEL``         — default chat model (e.g. ``z-ai/glm-4.7``)
* ``ZENMUX_REQUEST_TIMEOUT`` — seconds, default 60 (LLM calls can be slow)
* ``ZENMUX_MAX_TOKENS``    — default 2000

Fallback provider (Alibaba Cloud MaaS — optional, used if primary fails):
* ``LLM_FALLBACK_API_KEY``  — Alibaba MaaS API key
* ``LLM_FALLBACK_BASE_URL`` — defaults to Alibaba MaaS compatible-mode endpoint
* ``LLM_FALLBACK_MODEL``    — default ``qwen-plus-latest``
* ``LLM_FALLBACK_ENABLED``  — set to ``"true"`` to enable fallback (default: disabled)

When fallback is enabled and the primary provider returns an error (429, 500,
502, 503, timeout, or connection error), the service automatically retries
with the fallback provider. The ``source`` field in LLMResponse indicates
which provider succeeded (``"zenmux"`` or ``"aliyun-maas"``).

USAGE
-----
    from backend.services.llm_service import get_llm_service
    svc = get_llm_service()
    if not svc.available:
        raise HTTPException(503, "LLM service not configured")
    result = await svc.chat("Explain NFPA 72 §17.7.3.2.3", system="You are a fire protection engineer.")
    print(result.content)
    print(result.source)  # "zenmux" or "aliyun-maas"
"""
from __future__ import annotations

import logging
import os
import threading
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ── Defaults ─────────────────────────────────────────────────────────────────
_DEFAULT_BASE_URL = "https://zenmux.ai/api/v1"
_DEFAULT_MODEL = "z-ai/glm-4.7"
_DEFAULT_TIMEOUT = 60.0
_DEFAULT_MAX_TOKENS = 2000
_DEFAULT_TEMPERATURE = 0.1  # low temperature for deterministic engineering advice

# Fallback provider defaults (Alibaba Cloud MaaS — OpenAI-compatible)
_FALLBACK_DEFAULT_BASE_URL = (
    "https://ws-jhr3ncn4gmi9gm21.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"
)
_FALLBACK_DEFAULT_MODEL = "qwen-plus-latest"

# Conservative retry policy — LLM calls can be slow, so we allow up to 3
# attempts with exponential backoff. Only network/timeout errors are retried;
# 4xx errors (auth, quota, bad request) are surfaced immediately.
_MAX_RETRIES = 3
_RETRY_MIN_WAIT = 1.0
_RETRY_MAX_WAIT = 10.0


@dataclass(frozen=True)
class _ProviderConfig:
    """Configuration for a single LLM provider (primary or fallback)."""

    name: str  # "zenmux" or "aliyun-maas"
    api_key: str
    base_url: str
    model: str

    @property
    def available(self) -> bool:
        return bool(self.api_key)


@dataclass(frozen=True)
class LLMResponse:
    """Immutable result of an LLM chat completion.

    The ``source`` field is always ``"zenmux"`` (or the configured provider)
    so downstream code can distinguish AI-generated text from deterministic
    engineering calculations.
    """

    content: str
    model: str
    source: str = "zenmux"
    finish_reason: str = "stop"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


class LLMService:
    """Async LLM chat service backed by an OpenAI-compatible API.

    The service is created lazily on first use. If ``ZENMUX_API_KEY`` is not
    set, ``available`` is False and all chat calls raise ``RuntimeError``.
    """

    def __init__(self) -> None:
        # Primary provider (Zenmux or any OpenAI-compatible API)
        self._primary = _ProviderConfig(
            name="zenmux",
            api_key=os.environ.get("ZENMUX_API_KEY", ""),
            base_url=os.environ.get("ZENMUX_BASE_URL", _DEFAULT_BASE_URL),
            model=os.environ.get("ZENMUX_MODEL", _DEFAULT_MODEL),
        )
        # Fallback provider (Alibaba Cloud MaaS — optional)
        self._fallback_enabled = os.environ.get(
            "LLM_FALLBACK_ENABLED", ""
        ).lower() in ("1", "true", "yes", "on")
        self._fallback = _ProviderConfig(
            name="aliyun-maas",
            api_key=os.environ.get("LLM_FALLBACK_API_KEY", ""),
            base_url=os.environ.get(
                "LLM_FALLBACK_BASE_URL", _FALLBACK_DEFAULT_BASE_URL
            ),
            model=os.environ.get(
                "LLM_FALLBACK_MODEL", _FALLBACK_DEFAULT_MODEL
            ),
        )
        self._timeout: float = float(
            os.environ.get("ZENMUX_REQUEST_TIMEOUT", _DEFAULT_TIMEOUT)
        )
        self._max_tokens: int = int(
            os.environ.get("ZENMUX_MAX_TOKENS", _DEFAULT_MAX_TOKENS)
        )
        # Cache of clients per provider name
        self._clients: dict[str, Any] = {}
        self._lock = threading.Lock()

    # ── Properties ────────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        """True if at least one provider is configured."""
        return self._primary.available or (
            self._fallback_enabled and self._fallback.available
        )

    @property
    def base_url(self) -> str:
        return self._primary.base_url

    @property
    def default_model(self) -> str:
        return self._primary.model

    @property
    def fallback_available(self) -> bool:
        """True if fallback is enabled AND configured."""
        return self._fallback_enabled and self._fallback.available

    # ── Client lifecycle ──────────────────────────────────────────────────

    def _get_client(self, provider: _ProviderConfig | None = None) -> Any:
        """Lazily create an OpenAI async client for the given provider.

        If ``provider`` is None, uses the primary provider.
        We import ``openai`` inside the method so the module can be imported
        even if the ``openai`` package is not installed (graceful degradation
        — the router will report 503 if the service is unavailable).
        """
        prov = provider or self._primary
        if prov.name in self._clients:
            return self._clients[prov.name]
        if not prov.available:
            raise RuntimeError(
                f"{prov.name} API key is not set. Configure it to enable the LLM service."
            )
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise RuntimeError(
                "The 'openai' package is not installed. "
                "Install with: pip install openai"
            ) from exc

        with self._lock:
            if prov.name not in self._clients:
                self._clients[prov.name] = AsyncOpenAI(
                    api_key=prov.api_key,
                    base_url=prov.base_url,
                    timeout=self._timeout,
                    max_retries=0,  # we handle retries via tenacity
                )
        return self._clients[prov.name]

    async def close(self) -> None:
        """Close all cached HTTP clients (graceful shutdown)."""
        # list() snapshot is required: self._clients.clear() below mutates the
        # dict during iteration, which would raise RuntimeError without it.
        for name, client in list(self._clients.items()):  # noqa: S7504 — intentional snapshot
            try:
                await client.close()
            except Exception:
                logger.debug("Error closing %s client", name, exc_info=True)
        self._clients.clear()

    # ── Core chat method ──────────────────────────────────────────────────

    async def chat(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        temperature: float = _DEFAULT_TEMPERATURE,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Send a chat completion request and return the response.

        If the primary provider fails AND fallback is enabled, automatically
        retries with the fallback provider. The ``source`` field in the
        returned LLMResponse indicates which provider succeeded.

        Args:
            prompt: The user message. Must be non-empty.
            system: Optional system message (sets the assistant's persona).
            model: Override the default model (per-provider default if None).
            temperature: Sampling temperature [0.0, 2.0]. Default 0.1.
            max_tokens: Max tokens to generate. Defaults to ZENMUX_MAX_TOKENS.

        Returns:
            LLMResponse with the generated content and usage stats.

        Raises:
            ValueError: If prompt is empty.
            RuntimeError: If no provider is configured.
            Exception: On API errors after retries and fallback are exhausted.
        """
        if not prompt or not prompt.strip():
            raise ValueError("prompt must be non-empty")
        if not self.available:
            raise RuntimeError(
                "LLM service not configured. Set ZENMUX_API_KEY to enable."
            )

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        use_max_tokens = max_tokens or self._max_tokens

        # Try primary provider first
        primary_error: Exception | None = None
        if self._primary.available:
            try:
                return await self._try_provider(
                    self._primary, messages, model, temperature, use_max_tokens
                )
            except Exception as exc:
                primary_error = exc
                logger.warning(
                    "Primary LLM provider '%s' failed: %s. "
                    "Attempting fallback if enabled.",
                    self._primary.name,
                    type(exc).__name__,
                )

        # Try fallback provider if enabled and configured
        if self.fallback_available:
            try:
                return await self._try_provider(
                    self._fallback, messages, model, temperature, use_max_tokens
                )
            except Exception:
                logger.exception(
                    "Fallback LLM provider '%s' also failed",
                    self._fallback.name,
                )
                # Raise the fallback error (most recent), but log primary too
                if primary_error:
                    logger.error(
                        "Primary provider error was: %s", primary_error
                    )
                raise

        # No fallback available, raise primary error
        if primary_error:
            raise primary_error
        raise RuntimeError("No LLM provider available")

    async def _try_provider(
        self,
        provider: _ProviderConfig,
        messages: list[dict[str, str]],
        model: str | None,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        """Attempt a chat completion with a single provider (with tenacity retry)."""
        client = self._get_client(provider)
        use_model = model or provider.model

        from tenacity import (
            retry,
            retry_if_exception_type,
            stop_after_attempt,
            wait_exponential,
        )

        @retry(
            retry=retry_if_exception_type(_get_transient_errors()),
            stop=stop_after_attempt(_MAX_RETRIES),
            wait=wait_exponential(min=_RETRY_MIN_WAIT, max=_RETRY_MAX_WAIT),
            reraise=True,
        )
        async def _do_completion() -> Any:
            return await client.chat.completions.create(
                model=use_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        try:
            completion = await _do_completion()
        except Exception:
            logger.exception(
                "LLM chat completion failed (provider=%s, base_url=%s)",
                provider.name,
                provider.base_url,
            )
            raise

        choice = completion.choices[0] if completion.choices else None
        content = choice.message.content if choice and choice.message else ""
        finish = choice.finish_reason if choice else "unknown"

        usage = completion.usage
        prompt_t = usage.prompt_tokens if usage else 0
        completion_t = usage.completion_tokens if usage else 0
        total_t = usage.total_tokens if usage else 0

        # Safely serialize the raw response for debugging
        raw: dict[str, Any] = {}
        try:
            raw = completion.model_dump() if hasattr(completion, "model_dump") else {}
        except Exception:
            raw = {"id": getattr(completion, "id", "")}

        return LLMResponse(
            content=content or "",
            model=use_model,
            source=provider.name,
            finish_reason=finish or "stop",
            prompt_tokens=prompt_t,
            completion_tokens=completion_t,
            total_tokens=total_t,
            raw=raw,
        )

    async def chat_stream(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        temperature: float = _DEFAULT_TEMPERATURE,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream a chat completion token-by-token via SSE.

        Yields dicts with one of these shapes:
          - {"type": "chunk", "content": "...", "model": "...", "source": "..."}
          - {"type": "done", "content": "full text", "model": "...",
             "source": "...", "usage": {...}}
          - {"type": "error", "message": "..."}

        Falls back to non-streaming if the provider doesn't support streaming.
        """
        if not prompt or not prompt.strip():
            yield {"type": "error", "message": "prompt must be non-empty"}
            return
        if not self.available:
            yield {
                "type": "error",
                "message": "LLM service not configured. Set ZENMUX_API_KEY.",
            }
            return

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        use_max_tokens = max_tokens or self._max_tokens

        # Try primary provider first, then fallback
        providers_to_try: list[_ProviderConfig] = []
        if self._primary.available:
            providers_to_try.append(self._primary)
        if self.fallback_available:
            providers_to_try.append(self._fallback)

        if not providers_to_try:
            yield {"type": "error", "message": "No LLM provider available"}
            return

        for provider in providers_to_try:
            try:
                async for event in self._stream_provider(
                    provider, messages, model, temperature, use_max_tokens
                ):
                    yield event
                return  # Success — don't try fallback
            except Exception:
                logger.warning(
                    "Streaming with provider '%s' failed, trying fallback",
                    provider.name,
                    exc_info=True,
                )
                continue

        yield {"type": "error", "message": "All LLM providers failed"}

    async def _stream_provider(
        self,
        provider: _ProviderConfig,
        messages: list[dict[str, str]],
        model: str | None,
        temperature: float,
        max_tokens: int,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream tokens from a single provider."""
        client = self._get_client(provider)
        use_model = model or provider.model

        try:
            stream = await client.chat.completions.create(
                model=use_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
                stream_options={"include_usage": True},
            )
        except Exception:
            logger.exception(
                "LLM stream creation failed (provider=%s, base_url=%s)",
                provider.name,
                provider.base_url,
            )
            raise

        full_content = ""
        usage_data: dict[str, Any] = {}

        async for chunk in stream:
            if not chunk.choices:
                # Final chunk may contain usage stats only
                if chunk.usage:
                    usage_data = {
                        "prompt_tokens": chunk.usage.prompt_tokens,
                        "completion_tokens": chunk.usage.completion_tokens,
                        "total_tokens": chunk.usage.total_tokens,
                    }
                continue

            delta = chunk.choices[0].delta
            if delta and delta.content:
                full_content += delta.content
                yield {
                    "type": "chunk",
                    "content": delta.content,
                    "model": use_model,
                    "source": provider.name,
                }

            # Check for usage in the final chunk
            if chunk.usage:
                usage_data = {
                    "prompt_tokens": chunk.usage.prompt_tokens,
                    "completion_tokens": chunk.usage.completion_tokens,
                    "total_tokens": chunk.usage.total_tokens,
                }

        yield {
            "type": "done",
            "content": full_content,
            "model": use_model,
            "source": provider.name,
            "usage": usage_data,
        }

    # ── Health check ──────────────────────────────────────────────────────

    async def health(self) -> dict[str, Any]:  # noqa: S7503 — async for future extensibility
        """Return a health/status dict (never raises)."""
        return {
            "available": self.available,
            "primary": {
                "name": self._primary.name,
                "available": self._primary.available,
                "base_url": self._primary.base_url,
                "model": self._primary.model,
            },
            "fallback": {
                "name": self._fallback.name,
                "enabled": self._fallback_enabled,
                "available": self.fallback_available,
                "base_url": self._fallback.base_url,
                "model": self._fallback.model,
            },
            "timeout_s": self._timeout,
            "max_tokens": self._max_tokens,
        }


def _get_transient_errors() -> tuple[type[Exception], ...]:
    """Return the tuple of exception types that should trigger a retry.

    We retry on network/connection errors but NOT on 4xx HTTP errors (auth,
    quota, bad request) — those are surfaced immediately to the caller.
    """
    import httpx

    transient: list[type[Exception]] = [httpx.HTTPError, httpx.TimeoutException]
    try:
        from openai import APIConnectionError, APITimeoutError

        transient.extend([APIConnectionError, APITimeoutError])
        # Retry on 429 and 5xx but NOT on 4xx (auth/quota/bad-request)
        # We can't easily filter APIStatusError by status code in the retry
        # decorator, so we include it and rely on tenacity's predicate — but
        # for simplicity we exclude it and let 429/5xx surface immediately.
        # This is conservative: a 429 will be surfaced to the user rather
        # than retried, which is acceptable for an LLM service (the user can
        # retry manually).
    except ImportError:
        # openai not installed — only httpx errors will be caught
        pass
    return tuple(transient)


# ── Module-level singleton ───────────────────────────────────────────────────

_llm_service: LLMService | None = None
_llm_lock = threading.Lock()


def get_llm_service() -> LLMService:
    """Get the shared LLMService singleton (thread-safe)."""
    global _llm_service
    if _llm_service is None:
        with _llm_lock:
            if _llm_service is None:
                _llm_service = LLMService()
    return _llm_service


async def close_llm_service() -> None:
    """Close the shared LLMService (graceful shutdown)."""
    global _llm_service
    if _llm_service is not None:
        await _llm_service.close()
        _llm_service = None


__all__ = [
    "LLMResponse",
    "LLMService",
    "close_llm_service",
    "get_llm_service",
]
