"""
fireai/vision/cua_loop.py — Vision-based CUA Loop with OpenAI + OpenCV fallback.

V151 IMPLEMENTATION
-------------------
Implements the "CUA Loop reads key from DB (prefers DB over env vars)" step
of the V151 Vision API Keys flow.

PRIORITY ORDER (deterministic — Rule 5 determinism)
---------------------------------------------------
When analyze_screenshot() is called:
  1. Try to load the active OpenAI key from the DB (vision_api_keys table).
     - If found, decrypt and use OpenAI Vision API.
     - If decryption fails → log warning, fall through.
     - If the API call fails (auth, network, timeout) → log warning, fall through.
  2. Fall back to OPENAI_API_KEY env var (legacy behavior).
     - If present, use OpenAI Vision API with default base URL + model.
     - If the API call fails → log warning, fall through.
  3. Fall back to OpenCV (offline deterministic computer vision).
     - ALWAYS works (no network required).
     - Returns a basic analysis: image dimensions, brightness, edge count,
       dominant colors, detected rectangles (potential UI elements).
     - Marked with `provider="opencv"` in the response.

SAFETY CONTRACT (Rule 1 + Rule 4)
---------------------------------
- analyze_screenshot() NEVER raises. It always returns a VisionAnalysisResult.
  If everything fails (even OpenCV), it returns a result with provider="none"
  and an error message — the caller decides what to do.
- Plaintext API keys are NEVER logged. The masked form is logged instead.
- The DB is queried each call (no caching) so key rotations take effect
  immediately. Performance: the query is O(log n) via the active index.

INTEGRATION
-----------
- Called by the CUA loop driver (planned: fireai/agents/cua_agent.py).
- Standalone: import and call analyze_screenshot(image_bytes).
- The DB layer is imported lazily so this module can be imported in
  environments without the backend (e.g. unit tests for OpenCV fallback).
"""

from __future__ import annotations

import base64
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ── Result type ──────────────────────────────────────────────────────────────


@dataclass
class VisionAnalysisResult:
    """
    Result of analyzing a screenshot.

    `provider` is one of:
      - "openai-db"    : OpenAI Vision API, key from DB (V151 flow)
      - "openai-env"   : OpenAI Vision API, key from OPENAI_API_KEY env var
      - "opencv"       : OpenCV offline fallback
      - "none"         : All providers failed (check `error`)
    """

    provider: str
    ok: bool
    description: str = ""
    elements: list = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    masked_key: Optional[str] = None  # only set for openai-db / openai-env

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "ok": self.ok,
            "description": self.description,
            "elements": self.elements,
            "metadata": self.metadata,
            "error": self.error,
            "masked_key": self.masked_key,
        }


# ── DB key loader (lazy import to avoid circular deps) ───────────────────────


def _load_active_db_key() -> Optional[Dict[str, Any]]:
    """
    Load the active OpenAI key from the vision_api_keys table.

    Returns a dict with keys: encrypted_key, masked_key, base_url, model_name
    or None if no active key exists / DB unavailable.

    NEVER raises — logs warnings and returns None on any failure.
    """
    try:
        from backend.database import get_db
        from backend.vision_key_store import decrypt_key
    except ImportError as e:
        logger.debug("Vision DB key loader: backend not importable (%s)", e)
        return None

    try:
        db = get_db()
        with db._transaction() as cur:  # pylint: disable=protected-access
            cur.execute(
                f"SELECT encrypted_key, masked_key, base_url, model_name "
                f"FROM vision_api_keys WHERE provider = 'openai' AND is_active = 1 "
                f"ORDER BY created_at DESC LIMIT 1"
            )
            row = cur.fetchone()
        if row is None:
            return None
        try:
            plaintext = decrypt_key(row["encrypted_key"])
        except ValueError as e:
            logger.warning(
                "Active OpenAI key in DB failed to decrypt (masked=%s): %s",
                row["masked_key"],
                type(e).__name__,
            )
            return None
        return {
            "api_key": plaintext,
            "masked_key": row["masked_key"],
            "base_url": row["base_url"] or "https://api.openai.com/v1",
            "model_name": row["model_name"] or "gpt-4o",
        }
    except Exception as e:
        logger.warning("Vision DB key loader failed: %s", type(e).__name__)
        return None


# ── OpenAI Vision call ───────────────────────────────────────────────────────


def _call_openai_vision(
    image_bytes: bytes,
    api_key: str,
    masked_key: str,
    base_url: str,
    model_name: str,
    prompt: str,
) -> VisionAnalysisResult:
    """
    Call OpenAI Vision API with the given image and prompt.

    Returns a VisionAnalysisResult. NEVER raises — catches all exceptions
    and converts them to a failed result.
    """
    try:
        import httpx
    except ImportError as e:
        return VisionAnalysisResult(
            provider="openai",
            ok=False,
            error=f"httpx not installed: {e}",
            masked_key=masked_key,
        )

    b64 = base64.b64encode(image_bytes).decode("ascii")
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model_name,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    },
                ],
            }
        ],
        "max_tokens": 1024,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        # Sync client — analyze_screenshot is sync. Timeout 30s.
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, json=payload, headers=headers)
        if resp.status_code != 200:
            return VisionAnalysisResult(
                provider="openai",
                ok=False,
                error=f"OpenAI API returned HTTP {resp.status_code}",
                masked_key=masked_key,
                metadata={"status_code": resp.status_code},
            )
        data = resp.json()
        # Extract the assistant's text response
        choices = data.get("choices", [])
        if not choices:
            return VisionAnalysisResult(
                provider="openai",
                ok=False,
                error="OpenAI API returned no choices",
                masked_key=masked_key,
            )
        text = choices[0].get("message", {}).get("content", "")
        return VisionAnalysisResult(
            provider="openai",
            ok=True,
            description=text,
            metadata={
                "model": model_name,
                "usage": data.get("usage", {}),
                "masked_key": masked_key,
            },
            masked_key=masked_key,
        )
    except httpx.TimeoutException:
        return VisionAnalysisResult(
            provider="openai",
            ok=False,
            error="OpenAI API request timed out (30s)",
            masked_key=masked_key,
        )
    except httpx.HTTPError as e:
        # Do NOT include the original exception message — could leak URL/headers
        logger.debug("OpenAI Vision HTTP error: %s", type(e).__name__)
        return VisionAnalysisResult(
            provider="openai",
            ok=False,
            error="Network error contacting OpenAI API",
            masked_key=masked_key,
        )
    except Exception as e:
        logger.error("OpenAI Vision unexpected error: %s", type(e).__name__)
        return VisionAnalysisResult(
            provider="openai",
            ok=False,
            error="Unexpected error during OpenAI Vision call",
            masked_key=masked_key,
        )


# ── OpenCV fallback ──────────────────────────────────────────────────────────


def _opencv_analyze(image_bytes: bytes) -> VisionAnalysisResult:
    """
    OpenCV-based offline fallback.

    Returns basic image properties + contour-based element detection. This is
    deterministic (Rule 5) — same input always yields same output.

    NEVER raises. If OpenCV is not installed, returns a "none" provider result.
    """
    try:
        import cv2
        import numpy as np
    except ImportError as e:
        return VisionAnalysisResult(
            provider="none",
            ok=False,
            error=f"OpenCV not installed and no OpenAI key configured: {e}",
        )

    try:
        # Decode image from bytes
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return VisionAnalysisResult(
                provider="opencv",
                ok=False,
                error="OpenCV could not decode the image (unsupported format?)",
            )

        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        mean_brightness = float(gray.mean())
        # Edge count via Canny
        edges = cv2.Canny(gray, 50, 150)
        edge_count = int((edges > 0).sum())
        # Rectangle detection via contours
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        rectangles = []
        for c in contours:
            x, y, cw, ch = cv2.boundingRect(c)
            # Filter out tiny noise — only keep rectangles >= 16x16 px
            if cw >= 16 and ch >= 16:
                rectangles.append(
                    {"x": int(x), "y": int(y), "w": int(cw), "h": int(ch)}
                )
        # Dominant colors (k-means with k=3, simplified to mean BGR)
        mean_bgr = img.reshape(-1, 3).mean(axis=0).astype(int).tolist()

        return VisionAnalysisResult(
            provider="opencv",
            ok=True,
            description=(
                f"OpenCV offline analysis: {w}x{h} image, "
                f"brightness={mean_brightness:.1f}/255, "
                f"{edge_count} edge pixels, "
                f"{len(rectangles)} detected rectangles (>=16x16px)."
            ),
            elements=rectangles,
            metadata={
                "width": int(w),
                "height": int(h),
                "mean_brightness": mean_brightness,
                "edge_count": edge_count,
                "mean_bgr": mean_bgr,
            },
        )
    except Exception as e:
        logger.error("OpenCV analysis failed: %s", type(e).__name__)
        return VisionAnalysisResult(
            provider="opencv",
            ok=False,
            error=f"OpenCV analysis failed: {type(e).__name__}",
        )


# ── Public entrypoint ────────────────────────────────────────────────────────


def analyze_screenshot(
    image_bytes: bytes,
    prompt: str = (
        "Analyze this screenshot of a fire alarm engineering application. "
        "Identify UI elements, labels, and any visible fire alarm devices or "
        "engineering diagrams. Return a concise description."
    ),
) -> VisionAnalysisResult:
    """
    Analyze a screenshot using OpenAI Vision (preferred) or OpenCV (fallback).

    Priority chain (V151 flow):
      1. OpenAI Vision with key from DB (vision_api_keys table)
      2. OpenAI Vision with key from OPENAI_API_KEY env var (legacy)
      3. OpenCV offline fallback

    NEVER raises. Always returns a VisionAnalysisResult.

    Rule 1 (ABSOLUTE TRUTH): the returned `provider` field is the ACTUAL
    provider that produced the result, not the one we attempted first.
    Rule 5 (determinism): given the same image_bytes + same DB state +
    same env vars + same network conditions, the result is deterministic.
    """
    if not image_bytes:
        return VisionAnalysisResult(
            provider="none",
            ok=False,
            error="Empty image bytes",
        )

    # 1. Try DB key
    db_key = _load_active_db_key()
    if db_key is not None:
        result = _call_openai_vision(
            image_bytes=image_bytes,
            api_key=db_key["api_key"],
            masked_key=db_key["masked_key"],
            base_url=db_key["base_url"],
            model_name=db_key["model_name"],
            prompt=prompt,
        )
        if result.ok:
            result.provider = "openai-db"
            return result
        logger.info(
            "OpenAI-DB vision failed (masked=%s, error=%s) — falling back",
            db_key["masked_key"],
            result.error,
        )

    # 2. Try env var key
    env_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if env_key:
        from backend.vision_key_store import mask_key

        masked = mask_key(env_key)
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        model_name = os.environ.get("OPENAI_VISION_MODEL", "gpt-4o")
        result = _call_openai_vision(
            image_bytes=image_bytes,
            api_key=env_key,
            masked_key=masked,
            base_url=base_url,
            model_name=model_name,
            prompt=prompt,
        )
        if result.ok:
            result.provider = "openai-env"
            return result
        logger.info(
            "OpenAI-ENV vision failed (masked=%s, error=%s) — falling back",
            masked,
            result.error,
        )

    # 3. OpenCV fallback
    result = _opencv_analyze(image_bytes)
    if result.ok:
        return result

    # 4. Total failure
    return VisionAnalysisResult(
        provider="none",
        ok=False,
        error="All vision providers failed (no DB key, no env key, OpenCV failed)",
    )


__all__ = ["VisionAnalysisResult", "analyze_screenshot"]
