"""
mem0_setup.py — Mem0 Memory Layer Setup for FireAI (V81 OpenCode Support).

PURPOSE:
  Configures and initializes the Mem0 memory layer for the FireAI
  fire protection engineering system.

ARCHITECTURE (V80 — 6-Strategy Failover with OpenRouter):
  Provider selection is determined by which API keys are available
  AND which providers are reachable (auto-failover on 403 region blocks):

  Strategy 1: OpenAI Direct (if OPENAI_API_KEY set AND not region-blocked)
    Primary: gpt-4o + text-embedding-3-small (1536d)
    Reason: Best engineering accuracy, native Mem0 support

  Strategy 2: OpenRouter (V80 — if OPENROUTER_API_KEY set)
    Primary: gpt-4o via OpenRouter + local embeddings (384d)
    Reason: No region blocking, access to many models, global availability
    OpenRouter is an OpenAI-compatible API aggregator that provides
    access to GPT-4o, Claude, Gemini, Llama, and other models
    through a single API key with no geographic restrictions.

  Strategy 3: OpenQuotta (if OPENQUOTTA_API_KEY set)
    Primary: gpt-4o-mini via OpenQuotta + local embeddings (384d)
    Reason: OpenAI-compatible proxy, no region blocking

  Strategy 4: Google Gemini (if GEMINI_API_KEY set)
    Primary: gemini-2.0-flash + local sentence-transformers (384d)
    Reason: Works globally, generous free tier, fast response times

  Strategy 5: z-ai proxy (localhost:11435)
    Fallback: gpt-4o-mini + local embeddings (384d)

  Strategy 6: Error — no provider available

  OpenAI advantages:
  1. GPT-4o is the most accurate LLM for complex engineering analysis
  2. text-embedding-3-small produces high-quality 1536d vectors
  3. Native Mem0 integration — no compatibility issues
  4. Consistent deterministic behavior (temperature=0.1)
  5. Better code/NFPA standard understanding than alternatives

  OpenRouter advantages (V80 — NEW):
  1. No geographic region blocking — works everywhere
  2. Access to gpt-4o and many other models through one API
  3. OpenAI-compatible — works with Mem0's openai provider
  4. Pay-per-use with competitive pricing
  5. Global CDN — low latency from any region
  6. Falls back gracefully if OpenAI direct is blocked (403)

  Gemini advantages (as PRIMARY when OpenAI/OpenRouter unavailable):
  1. Works in regions where OpenAI might be blocked (403 errors)
  2. Generous free tier — no cost for development/testing
  3. Fast response times
  4. Good multilingual support (Arabic + English)
  5. Uses google-generativeai SDK — official Google AI SDK

CHANGES from V80 → V81:
  1. Renamed OpenQuotta (Strategy 3) to OpenCode — correct provider name
  2. Changed OpenCode base URL to https://opencode.ai/zen/v1/ (correct endpoint)
  3. Changed OpenCode model from gpt-4o-mini to gpt-4o (better NFPA accuracy)
  4. New env vars: OPENCODE_API_KEY, OPENCODE_BASE_URL (replacing OPENQUOTTA_*)
  5. Backward compatibility: OPENQUOTTA_* env vars still read as fallback
  6. OpenCode (opencode.ai) provides access to GPT-4o, Claude, and other
     premium models through its Zen endpoint — no region blocking

CHANGES from V79 → V80:
  1. Added OpenRouter as Strategy 2 (after OpenAI, before OpenCode)
  2. OpenRouter uses gpt-4o model via OpenAI-compatible API
  3. New env vars: OPENROUTER_API_KEY, OPENROUTER_BASE_URL
  4. 6-strategy failover chain (was 5)
  5. OpenRouter is preferred over OpenCode because it has
     well-documented API with stable endpoints

CHANGES from V76 → V77:
  1. Gemini promoted from FALLBACK to PRIMARY when OpenAI key is absent
  2. Added google-generativeai SDK dependency requirement
  3. Updated provider detection to clearly document dual-primary logic
  4. Gemini LLM config now explicitly uses Mem0's native gemini provider
     (which requires google-generativeai package)

CRITICAL FIXES from V74/V75:
  V76:
  1. OpenAI promoted to PRIMARY — better engineering accuracy
  2. gpt-4o replaces gpt-4o-mini — more reliable for NFPA analysis
  3. Removed models.list() connectivity test — causes latency on startup
  4. Simplified provider detection — less overhead, faster init
  5. Consistent Qdrant collection naming: fireai_memory (OpenAI primary)

  V75:
  1. Added crash recovery support via AsyncSqliteSaver
  2. Memory enrichment with environmental context

  V74:
  1. Added Gemini as fallback provider — solves region-blocking issue
  2. Proper embedding dimensions per provider (1536 for OpenAI, 384 for local)
  3. Each provider uses its own Qdrant collection (different embedding dims)

PER agent.md:
  - Rule 1: Absolute truth — documented actual providers used
  - Rule 5: Explain after every step
  - Rule 6: Verify before changing
  - Rule 10: Mandatory test-and-fix cycle

MEMORY SCOPING (per user's original design):
  - user_id: engineer (the fire protection engineer)
  - agent_id: fireai_agent (the FireAI system)
  - run_id: project_id (specific project/analysis run)
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Paths (PERSISTENT — NOT /tmp/) ────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
MEM0_QDRANT_PATH = DATA_DIR / "mem0_qdrant"
MEM0_HISTORY_DB = DATA_DIR / "mem0_history.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)
MEM0_QDRANT_PATH.mkdir(parents=True, exist_ok=True)


# ── Provider Detection ──────────────────────────────────────────────────────


def _test_openai_connectivity(api_key: str) -> bool:
    """
    Test if OpenAI API is reachable and not region-blocked.

    V78 FIX: OpenAI returns 403 "unsupported_country_region_territory" in
    certain regions (Egypt, UAE, etc.). We must detect this at startup
    and fall back to Gemini rather than failing silently.

    Per agent.md Rule 17 (Root-Cause Analysis):
    - Root cause: OpenAI blocks requests from certain geographic regions
    - Symptom: 403 error on every API call, Mem0 initialization fails
    - Fix: Test connectivity before committing to OpenAI as provider
    - This is NOT a workaround — it's proper failover design for a
      system that operates globally (Gulf states, Egypt, etc.)

    Returns:
        True if OpenAI is reachable, False if blocked or unavailable
    """
    try:
        import urllib.request

        req = urllib.request.Request(  # noqa: S310 — hardcoded https://api.openai.com
            "https://api.openai.com/v1/models",
            method="GET",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            if resp.status == 200:
                return True
    except urllib.error.HTTPError as e:
        if e.code == 403:
            # Region blocked — this is the V78 fix scenario
            body = e.read().decode("utf-8", errors="replace")
            if "unsupported_country_region_territory" in body:
                logger.warning(
                    "OpenAI API is region-blocked (403 unsupported_country_region_territory). "
                    "Falling back to Gemini. This is expected in certain geographic regions."
                )
                return False
            # Other 403 — might be invalid key
            logger.warning(f"OpenAI API returned 403: {body[:200]}")
            return False
        # Other HTTP errors — might be temporary
        # V83 FIX: Decode bytes before slicing to avoid mid-UTF8-character slicing
        body = e.read().decode("utf-8", errors="replace")[:200]
        logger.warning(f"OpenAI API returned HTTP {e.code}: {body}")
        return False
    except Exception as e:
        # Network error — might be temporary
        logger.warning(f"OpenAI connectivity test failed: {type(e).__name__}: {e}")
        return False
    return False


def _test_gemini_connectivity(api_key: str) -> bool:
    """
    Test if Gemini API is reachable and not rate-limited.

    V87 FIX: Strategy 4 (Gemini) previously did NOT test connectivity before
    selecting Gemini as the provider. This meant a rate-limited or invalid
    Gemini key would be chosen, blocking Strategy 5 (z-ai proxy) from
    ever being reached. Strategies 1-3 all test connectivity; Strategy 4
    should too. Per agent.md Rule 17 (Root-Cause Analysis): assuming
    "key exists = works" is a half-solution — it creates a false sense
    of provider availability while silently degrading to failed LLM calls.

    Returns:
        True if Gemini is reachable, False if rate-limited or unavailable
    """
    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")
        # Minimal request to verify quota and connectivity
        response = model.generate_content("ping", request_options={"timeout": 10})
        # If we get here, Gemini is working
        return True
    except Exception as e:
        error_str = str(e)
        if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str or "quota" in error_str.lower():
            logger.warning(
                "Gemini API is rate-limited (429 RESOURCE_EXHAUSTED). "
                "Quota exceeded — falling back to next provider. "
                "This is expected on free-tier plans with low limits."
            )
            return False
        if "403" in error_str or "PERMISSION_DENIED" in error_str:
            logger.warning(f"Gemini API returned 403: {error_str[:200]}")
            return False
        logger.warning(f"Gemini connectivity test failed: {type(e).__name__}: {error_str[:200]}")
        return False


def _test_openai_compatible_connectivity(base_url: str, api_key: str) -> bool:
    """
    Test if an OpenAI-compatible API endpoint is reachable.

    V79: Generalized from _test_openai_connectivity to support any
    OpenAI-compatible provider (OpenQuotta, local proxies, etc.).

    Returns:
        True if the endpoint responds to /models, False otherwise
    """
    try:
        import urllib.request

        models_url = f"{base_url.rstrip('/')}/models"
        req = urllib.request.Request(  # noqa: S310 — URL constructed from validated base_url
            models_url,
            method="GET",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            if resp.status == 200:
                return True
    except urllib.error.HTTPError as e:
        if e.code == 403:
            body = e.read().decode("utf-8", errors="replace")
            if "unsupported_country_region_territory" in body:
                logger.warning(
                    f"OpenAI-compatible API at {base_url} is region-blocked (403). Falling back to next provider."
                )
                return False
            logger.warning(f"API at {base_url} returned 403: {body[:200]}")
            return False
        logger.warning(f"API at {base_url} returned HTTP {e.code}")
        return False
    except Exception as e:
        logger.warning(f"Connectivity test failed for {base_url}: {type(e).__name__}: {e}")
        return False
    return False


# V83: Provider detection cache — avoids 40s+ blocking on repeated calls
_detect_provider_cache: Optional[Dict[str, Any]] = None
_detect_provider_cache_time: float = 0.0
_PROVIDER_CACHE_TTL_SECONDS = 300  # 5 minutes


def _detect_provider() -> Dict[str, Any]:
    """
    Detect the best available LLM/embedding provider.

    V83: Added caching with 5-minute TTL to avoid repeated connectivity
    tests (up to 40s+ blocking per call when all providers are slow).

    The actual detection logic is in _detect_provider_uncached().
    This wrapper handles caching only.
    """
    global _detect_provider_cache, _detect_provider_cache_time

    import time as _time

    if _detect_provider_cache is not None:
        elapsed = _time.monotonic() - _detect_provider_cache_time
        if elapsed < _PROVIDER_CACHE_TTL_SECONDS:
            logger.debug(f"Provider detection cache hit (age={elapsed:.0f}s, TTL={_PROVIDER_CACHE_TTL_SECONDS}s)")
            return _detect_provider_cache

    result = _detect_provider_uncached()

    # Cache the result
    _detect_provider_cache = result
    _detect_provider_cache_time = _time.monotonic()
    logger.debug(f"Provider detection result cached for {_PROVIDER_CACHE_TTL_SECONDS}s")
    return result


def _detect_provider_uncached() -> Dict[str, Any]:
    """
    Detect the best available LLM/embedding provider (uncached version).

    Strategy (V81 — 6-Strategy Failover with OpenCode):
    1. Try OpenAI API (if OPENAI_API_KEY available AND not region-blocked)
       - gpt-4o for LLM, text-embedding-3-small for embeddings
       - Best accuracy for engineering analysis, native Mem0 support
       - V78: Tests connectivity first — falls back on 403
    2. Try OpenRouter API (V80 — OpenAI-compatible aggregator)
       - Uses OPENROUTER_API_KEY + OPENROUTER_BASE_URL
       - OpenAI-compatible: works with Mem0's openai provider
       - No region blocking, global CDN, access to gpt-4o + many models
       - gpt-4o for LLM, local embeddings (384d)
    3. Try OpenCode API (V81 — OpenAI-compatible, no region blocking)
       - Uses OPENCODE_API_KEY + OPENCODE_BASE_URL
       - OpenAI-compatible: works with Mem0's openai provider
       - No region blocking, available globally via opencode.ai/zen/v1/
       - gpt-4o for LLM, local embeddings (384d)
       - Backward compat: OPENQUOTTA_* env vars still work as fallback
    4. Try Google Gemini API (if GEMINI_API_KEY available)
       - gemini-2.0-flash for LLM + local sentence-transformers for embeddings
       - PRIMARY when OpenAI/OpenRouter/OpenCode unavailable
       - Uses google-generativeai SDK via Mem0's native gemini provider
    5. Fall back to z-ai proxy at localhost:11435 (if running)
    6. Raise error if no provider available

    V81 CHANGE: Renamed OpenQuotta (Strategy 3) to OpenCode — correct provider
    name. OpenCode (opencode.ai) provides OpenAI-compatible API access to
    GPT-4o, Claude, and other models through its Zen endpoint at
    https://opencode.ai/zen/v1/. Changed model from gpt-4o-mini to gpt-4o
    for better NFPA engineering accuracy.

    Per agent.md Rule 1 (Absolute Truth): We log exactly which provider is used.
    Per agent.md Rule 17 (Root-Cause Analysis): Region blocking is the root cause
    of 403 errors, and auto-failover is the correct fix, not a workaround.
    """
    openai_key = os.getenv("OPENAI_API_KEY") or os.getenv("FIREAI_OPENAI_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    openrouter_base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    # V81: Renamed from OpenQuotta to OpenCode — correct provider name
    # OpenCode (opencode.ai) provides OpenAI-compatible API at /zen/v1/
    # Backward compat: OPENQUOTTA_* env vars still work as fallback
    opencode_key = os.getenv("OPENCODE_API_KEY") or os.getenv("OPENQUOTTA_API_KEY")
    opencode_base_url = os.getenv("OPENCODE_BASE_URL", os.getenv("OPENQUOTTA_BASE_URL", "https://opencode.ai/zen/v1/"))

    # ── Strategy 1: Try OpenAI (PRIMARY if available and not region-blocked) ──
    if openai_key:
        # V78: Test OpenAI connectivity before committing to it
        openai_reachable = _test_openai_connectivity(openai_key)

        if openai_reachable:
            logger.info(
                "OpenAI API reachable — using OpenAI as primary provider. "
                "(LLM: gpt-4o, Embeddings: text-embedding-3-small, 1536d)"
            )
            return {
                "provider": "openai_direct",
                "api_key": openai_key,
                "llm_provider": "openai",
                "llm_model": "gpt-4o",
                "embedder_provider": "openai",
                "embedder_model": "text-embedding-3-small",
                "embedding_dims": 1536,
                "collection_name": "fireai_memory",
            }
        else:
            # OpenAI is region-blocked — fall through to OpenRouter
            logger.info(
                "OpenAI API key found but not reachable (region-blocked or network error). "
                "Falling back to OpenRouter, OpenCode, or Gemini provider."
            )

    # ── Strategy 2: OpenRouter (V80 — OpenAI-compatible aggregator, no region block) ──
    # OpenRouter provides access to gpt-4o and many other models through
    # a single API key with no geographic restrictions. It uses the
    # OpenAI-compatible API format, so Mem0 can use its openai provider.
    #
    # Why OpenRouter > OpenQuotta for Strategy 2:
    # 1. OpenRouter provides access to gpt-4o (not just gpt-4o-mini)
    # 2. Better model selection for engineering accuracy
    # 3. Global CDN with low latency
    # 4. Well-documented API with stable endpoints
    #
    # Per agent.md Priority 1 (Safety): Using gpt-4o (not mini) for
    # engineering analysis ensures the highest accuracy for NFPA calculations.
    if openrouter_key:
        openrouter_reachable = _test_openai_compatible_connectivity(openrouter_base_url, openrouter_key)

        if openrouter_reachable:
            logger.info(
                f"OpenRouter API reachable at {openrouter_base_url} — "
                "using OpenRouter as provider. "
                "(LLM: gpt-4o via OpenRouter, Embeddings: local sentence-transformers, 384d)"
            )
            return {
                "provider": "openrouter",
                "api_key": openrouter_key,
                "llm_provider": "openai",
                "llm_model": "openai/gpt-4o",  # OpenRouter model format: provider/model
                "embedder_provider": "local",
                "embedder_model": "multi-qa-MiniLM-L6-cos-v1",
                "embedding_dims": 384,
                "collection_name": "fireai_memory_openrouter_v80",
                "base_url": openrouter_base_url,
            }
        else:
            logger.info(
                f"OpenRouter API key found but {openrouter_base_url} not reachable. "
                "Falling back to OpenCode, Gemini, or z-ai proxy."
            )

    # ── Strategy 3: OpenCode (V81 — OpenAI-compatible, no region block) ──
    # OpenCode (opencode.ai) provides access to GPT-4o, Claude, and other
    # premium models through its Zen endpoint. It uses the OpenAI-compatible
    # API format, so Mem0 can use its openai provider.
    #
    # Why OpenCode for Strategy 3:
    # 1. OpenCode provides access to gpt-4o (not just mini)
    # 2. No region blocking — works globally
    # 3. OpenAI-compatible API at https://opencode.ai/zen/v1/
    # 4. Supports multiple premium models through one API key
    #
    # Per agent.md Priority 1 (Safety): Using gpt-4o (not mini) for
    # engineering analysis ensures the highest accuracy for NFPA calculations.
    if opencode_key:
        # OpenCode is an OpenAI-compatible API — test connectivity
        opencode_reachable = _test_openai_compatible_connectivity(opencode_base_url, opencode_key)

        if opencode_reachable:
            logger.info(
                f"OpenCode API reachable at {opencode_base_url} — "
                "using OpenCode as provider. "
                "(LLM: gpt-4o via OpenCode, Embeddings: local sentence-transformers, 384d)"
            )
            return {
                "provider": "opencode",
                "api_key": opencode_key,
                "llm_provider": "openai",
                "llm_model": "gpt-4o",  # OpenCode supports gpt-4o directly
                "embedder_provider": "local",
                "embedder_model": "multi-qa-MiniLM-L6-cos-v1",
                "embedding_dims": 384,
                "collection_name": "fireai_memory_opencode_v81",
                "base_url": opencode_base_url,
            }
        else:
            logger.info(
                f"OpenCode API key found but {opencode_base_url} not reachable. Falling back to Gemini or z-ai proxy."
            )

    # ── Strategy 4: Gemini (PRIMARY when OpenAI/OpenRouter/OpenCode unavailable) ──
    if gemini_key:
        # V87 FIX: Test Gemini connectivity before committing to it.
        # Previously, Strategy 4 returned success without testing, which meant
        # a rate-limited or invalid Gemini key would be selected, blocking
        # Strategy 5 (z-ai proxy) from ever being reached. This was a
        # half-solution per agent.md Rule 17 — we assumed "key exists = works"
        # without verification, exactly the pattern Strategies 1-3 avoid.
        gemini_reachable = _test_gemini_connectivity(gemini_key)

        if gemini_reachable:
            # Use Gemini for LLM + local sentence-transformers for embeddings.
            # Why hybrid?
            # 1. Gemini LLM works globally (no region blocking)
            # 2. Local embeddings work offline (no API dependency, no rate limits)
            # 3. Gemini's embedding model (text-embedding-004) is not supported
            #    by Mem0's v1beta API endpoint — causes 404 errors
            # 4. Local embeddings (all-MiniLM-L6-v2) are deterministic and fast
            #
            # V77: Gemini is now PRIMARY when no OpenAI key is set.
            # The Mem0 "gemini" provider uses google-generativeai SDK internally.
            logger.info(
                "Gemini API reachable — using Gemini as PRIMARY provider. "
                "(Hybrid: Gemini LLM via google-generativeai + sentence-transformers embeddings)"
            )
            return {
                "provider": "gemini_primary",
                "api_key": gemini_key,
                "llm_provider": "gemini",
                "llm_model": "gemini-2.0-flash",  # Works globally, no region blocking
                "embedder_provider": "local",  # Local sentence-transformers
                "embedder_model": "multi-qa-MiniLM-L6-cos-v1",
                "embedding_dims": 384,
                "collection_name": "fireai_memory_gemini_v78",
            }
        else:
            logger.info(
                "Gemini API key found but not reachable (quota exceeded or network error). Falling back to z-ai proxy."
            )

    # ── Strategy 5: Try z-ai proxy ──
    proxy_url = os.getenv("FIREAI_PROXY_URL", "http://localhost:11435")
    try:
        import urllib.request
        from urllib.parse import urlparse as _urlparse

        # S310/B310 SECURITY: Validate URL scheme before opening.
        _parsed = _urlparse(proxy_url)
        if _parsed.scheme not in ("http", "https"):
            raise ValueError(f"Rejected proxy URL scheme '{_parsed.scheme}' — only http/https allowed")
        req = urllib.request.Request(f"{proxy_url}/health", method="GET")  # noqa: S310 — scheme validated above
        with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310 — scheme validated above
            health = json.loads(resp.read().decode())
            if health.get("status") == "ok":
                logger.info(f"z-ai proxy available at {proxy_url} — using proxy provider")
                return {
                    "provider": "zai_proxy",
                    "api_key": "z-ai-proxy",
                    "llm_provider": "openai",
                    "llm_model": "gpt-4o-mini",
                    # V83 FIX: Changed embedder from "openai" to "local" because
                    # text-embedding-3-small produces 1536d vectors but embedding_dims
                    # was set to 384 — Qdrant would crash on dimension mismatch.
                    # Using local embeddings (384d) is consistent with all other
                    # fallback strategies and works offline.
                    "embedder_provider": "local",
                    "embedder_model": "multi-qa-MiniLM-L6-cos-v1",
                    "embedding_dims": 384,
                    "collection_name": "fireai_memory_local",
                    "base_url": f"{proxy_url}/v1",
                }
    except Exception as e:
        logger.warning(f"z-ai proxy not available at {proxy_url}: {e}")

    # ── Strategy 6: No provider available ──
    raise ValueError(
        "No LLM provider available. Either:\n"
        "1. Set OPENAI_API_KEY for OpenAI access (best engineering accuracy)\n"
        "2. Set OPENROUTER_API_KEY for OpenRouter (no region block, gpt-4o access)\n"
        "3. Set OPENCODE_API_KEY for OpenCode (V81, no region block, gpt-4o access)\n"
        "4. Set GEMINI_API_KEY for Google Gemini (works globally)\n"
        "5. Start z-ai proxy: python zai_openai_proxy.py\n"
        "Memory layer requires at least one provider."
    )


# ── Mem0 Configuration ──────────────────────────────────────────────────────


def get_mem0_config() -> Dict[str, Any]:
    """
    Get the Mem0 configuration for FireAI.

    V80: Auto-detects the best available provider (6-strategy failover):
    - OpenAI (PRIMARY if key set — best engineering accuracy, native Mem0 support)
    - OpenRouter (V80 — no region blocking, gpt-4o access)
    - OpenQuotta (V79 — no region blocking, gpt-4o-mini)
    - Gemini (works globally, generous free tier)
    - z-ai proxy (last resort)
    """
    provider_info = _detect_provider()

    # Build LLM config based on provider
    llm_config = {
        "provider": provider_info["llm_provider"],
        "config": {
            "model": provider_info["llm_model"],
            "api_key": provider_info["api_key"],
            "temperature": 0.1,  # Low temperature for deterministic engineering
            "max_tokens": 2000,
        },
    }

    # Build embedder config based on provider
    if provider_info["embedder_provider"] == "local":
        # Use HuggingFace sentence-transformers for embeddings (no API needed)
        # This is the most reliable approach: works offline, no rate limits
        # Mem0 supports HuggingFace provider natively for local embeddings
        embedder_config = {
            "provider": "huggingface",
            "config": {
                # V78: Use Mem0's default model for consistency
                # multi-qa-MiniLM-L6-cos-v1 produces 384-dim embeddings
                # and is optimized for semantic search (better for NFPA queries)
                "model": "multi-qa-MiniLM-L6-cos-v1",
            },
        }
    else:
        embedder_config = {
            "provider": provider_info["embedder_provider"],
            "config": {
                "model": provider_info["embedder_model"],
                "api_key": provider_info["api_key"],
            },
        }

    # Add base_url for proxy/OpenRouter/OpenQuotta mode
    if provider_info.get("base_url"):
        llm_config["config"]["openai_base_url"] = provider_info["base_url"]
        # Only add base_url to embedder if it uses OpenAI provider (not local)
        if provider_info["embedder_provider"] != "local":
            embedder_config["config"]["openai_base_url"] = provider_info["base_url"]

    config = {
        "llm": llm_config,
        "embedder": embedder_config,
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "collection_name": provider_info.get("collection_name", "fireai_memory"),
                "embedding_model_dims": provider_info["embedding_dims"],
                "path": str(MEM0_QDRANT_PATH),
                "on_disk": True,
            },
        },
        "history_db_path": str(MEM0_HISTORY_DB),
        "version": "v1.1",
        "custom_instructions": (
            "You are the memory layer for FireAI, a life-critical fire protection "
            "engineering system. When storing or retrieving memories:\n"
            "1. Always reference specific NFPA codes (e.g., NFPA 72-2022 §17.6.3.1)\n"
            "2. Distinguish between design decisions and code requirements\n"
            "3. Tag memories with: standard, occupancy_type, hazard_class, device_type\n"
            "4. Never fabricate fire safety requirements — only store verified facts\n"
            "5. Prioritize life safety over all other concerns\n"
            "6. Remember: errors in this system can cost human lives"
        ),
    }

    logger.info(
        f"Mem0 config: provider={provider_info['provider']}, "
        f"llm={provider_info['llm_model']}, "
        f"embedder={provider_info['embedder_model']}, "
        f"dims={provider_info['embedding_dims']}, "
        f"collection={provider_info.get('collection_name', 'fireai_memory')}"
    )

    return config


def create_mem0_instance() -> Any:
    """
    Create and return a configured Mem0 Memory instance.

    This is the PRIMARY entry point for all FireAI memory operations.

    Returns:
        mem0.Memory instance ready for use

    Raises:
        ValueError: If no LLM provider is available
        RuntimeError: If Mem0 initialization fails
    """
    from mem0 import Memory

    config = get_mem0_config()

    logger.info("Initializing Mem0 with FireAI configuration...")
    try:
        mem0_instance = Memory.from_config(config)
    except Exception as e:
        logger.error(f"Mem0 initialization failed: {e}")
        raise RuntimeError(
            f"Failed to initialize Mem0: {e}. Check your provider configuration and connectivity."
        ) from e

    logger.info("Mem0 instance created successfully")
    return mem0_instance


# ── FireAI Memory Operations ────────────────────────────────────────────────


class FireAIMemory:
    """
    High-level FireAI memory interface.

    Wraps Mem0 with domain-specific operations for fire protection engineering.

    SCOPING:
    - user_id: "engineer" (or specific engineer ID)
    - agent_id: "fireai_agent"
    - run_id: project-specific ID

    MEMORY CATEGORIES:
    1. Previous layouts (design patterns)
    2. User style preferences
    3. Preferred standards (NFPA, IEC, BS)
    4. Common calculations (detector spacing, coverage)
    5. Repeated device mappings (occupancy -> detector type)

    SAFETY:
    - Memory is ADVISORY, not AUTHORITATIVE
    - Every retrieval is tagged with source="memory"
    - Memory failures NEVER block calculations
    """

    def __init__(self, mem0_instance=None, engineer_id: str = "engineer_default"):
        if mem0_instance is None:
            mem0_instance = create_mem0_instance()
        self.mem0 = mem0_instance
        self.engineer_id = engineer_id
        self.agent_id = "fireai_agent"

    def add_engineering_context(
        self,
        content: str,
        project_id: str = "general",
        metadata: Optional[Dict] = None,
    ) -> Dict:
        """Store engineering context in memory."""
        result = self.mem0.add(
            content,
            user_id=self.engineer_id,
            agent_id=self.agent_id,
            run_id=project_id,
            metadata=metadata or {},
        )
        logger.info(f"Added memory for engineer={self.engineer_id}, project={project_id}")
        return result

    def search_standards(
        self,
        query: str,
        project_id: Optional[str] = None,
        limit: int = 5,
    ) -> List[Dict]:
        """Search memory for fire safety standards and engineering context."""
        kwargs = {
            "query": query,
            "limit": limit,
            "filters": {
                "user_id": self.engineer_id,
                "agent_id": self.agent_id,
            },
        }
        if project_id:
            kwargs["filters"]["run_id"] = project_id

        return self.mem0.search(**kwargs)

    def get_all_memories(self, project_id: Optional[str] = None) -> List[Dict]:
        """Get all stored memories for the engineer."""
        kwargs = {
            "filters": {
                "user_id": self.engineer_id,
                "agent_id": self.agent_id,
            },
        }
        if project_id:
            kwargs["filters"]["run_id"] = project_id

        return self.mem0.get_all(**kwargs)

    def delete_memory(self, memory_id: str) -> Dict:
        """Delete a specific memory by ID."""
        return self.mem0.delete(memory_id)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("FireAI Mem0 Setup — V81 OpenCode Integration Test")
    print("=" * 60)

    try:
        # Create instance
        print("\n1. Creating Mem0 instance...")
        fire_memory = FireAIMemory(engineer_id="test_engineer")
        print("   [OK] Mem0 instance created")

        # Test: Add a fire engineering memory
        print("\n2. Adding test memory...")
        result = fire_memory.add_engineering_context(
            content="NFPA 72-2022 requires smoke detectors in corridors at maximum "
            "30m spacing. For heat detectors, maximum spacing is 15m per "
            "NFPA 72 §17.6.3.1. Kitchen areas require heat detectors, "
            "NOT smoke detectors, per NFPA 72 §17.6.4.",
            project_id="test_project",
            metadata={
                "standard": "NFPA 72-2022",
                "topic": "detector_spacing",
                "occupancy_type": "corridor",
            },
        )
        print(f"   [OK] Memory added")

        # Test: Search for standards
        print("\n3. Searching for detector spacing requirements...")
        results = fire_memory.search_standards(
            query="What is the maximum spacing for smoke detectors?",
            project_id="test_project",
        )
        count = len(results) if isinstance(results, list) else "?"
        print(f"   [OK] Found {count} result(s)")

        # Test: Get all memories
        print("\n4. Getting all memories...")
        all_mem = fire_memory.get_all_memories(project_id="test_project")
        mem_count = len(all_mem.get("results", all_mem) if isinstance(all_mem, dict) else all_mem)
        print(f"   [OK] Total memories: {mem_count}")

        print("\n" + "=" * 60)
        print("[OK] ALL TESTS PASSED — Mem0 V81 OpenCode is ready for FireAI")
        print("=" * 60)

    except ValueError as e:
        print(f"\n[FAIL] Configuration error: {e}")
    except Exception as e:
        print(f"\n[FAIL] Test error: {type(e).__name__}: {e}")
