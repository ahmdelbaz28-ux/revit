"""
backend/csp.py — Content Security Policy builder.

Extracted from backend/app.py (V300 architecture improvement) to reduce the
monolithic app.py from 1056 lines and improve testability.

Builds a CSP header value that is environment-aware:
  - Production (default): 'unsafe-eval' is OFF unless explicitly enabled.
  - Development: 'unsafe-eval' is ON unless explicitly disabled.

Operators may override either default by setting CSP_UNSAFE_EVAL=true|false.

SAFETY: A safety-critical fire alarm engineering UI must not be vulnerable
to XSS amplification via 'unsafe-eval'. Modern frontend libraries
(recharts >=2.x, three.js >=0.150) work without it in production builds.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def build_csp() -> str:  # NOSONAR — S3776: cognitive complexity is inherent to the safety-critical algorithm
    """
    Build a Content-Security-Policy header value.

    Environment-aware:
      - FIREAI_ENV=production (default): 'unsafe-eval' is OFF unless explicitly enabled.
      - FIREAI_ENV=development:           'unsafe-eval' is ON  unless explicitly disabled.

    Operators may override either default by setting CSP_UNSAFE_EVAL=true|false.

    Production + unsafe-eval=on is logged at ERROR level (V119 escalation)
    so the misconfiguration cannot hide in log noise.
    """
    # Truthy values that enable unsafe-eval (backward compatible with pre-V119).
    # Defined INSIDE the function so the function is fully self-contained and
    # can be exec'd in isolation by tests/test_csp_security.py.
    _truthy = {"true", "1", "yes"}

    env = os.getenv("FIREAI_ENV", "production").lower()
    is_dev = env == "development"

    # Resolve CSP_UNSAFE_EVAL with environment-aware default.
    unsafe_eval_raw = os.getenv("CSP_UNSAFE_EVAL")
    if unsafe_eval_raw is not None:
        unsafe_eval = unsafe_eval_raw.strip().lower() in _truthy
    else:
        unsafe_eval = is_dev  # dev: True, prod: False

    if unsafe_eval and not is_dev:
        logger.error(
            "CSP 'unsafe-eval' ENABLED in production (FIREAI_ENV=%s). "
            "This is a security risk for a safety-critical UI - "
            "set CSP_UNSAFE_EVAL=false to disable.",
            env,
        )

    # 'unsafe-inline' is kept for style-src (Tailwind CSS requires it).
    # For scripts, production uses 'self' only (React doesn't need inline scripts).
    # Development keeps 'unsafe-inline' for Vite HMR.
    if is_dev:
        script_src = "'self' 'unsafe-inline'" + (" 'unsafe-eval'" if unsafe_eval else "")
    else:
        # Production: no unsafe-inline for scripts (only unsafe-eval if explicitly enabled)
        script_src = "'self'" + (" 'unsafe-eval'" if unsafe_eval else "")
    style_src = "'self' 'unsafe-inline'"
    img_src = "'self' data: blob:"

    # connect-src: development allows localhost (Vite HMR / websockets);
    # production uses CSP_CONNECT_SRC env var if provided, else 'self'.
    if is_dev:
        connect_src = "'self' http://localhost:* ws://localhost:* http://127.0.0.1:* ws://127.0.0.1:*"
        custom_connect = os.getenv("CSP_CONNECT_SRC")
        if custom_connect:
            connect_src += f" {custom_connect}"
    else:
        custom_connect = os.getenv("CSP_CONNECT_SRC")
        connect_src = "'self'" + (f" {custom_connect}" if custom_connect else "")

    parts = [
        "default-src 'self'",
        f"script-src {script_src}",
        f"style-src {style_src}",
        f"img-src {img_src}",
        f"connect-src {connect_src}",
        "font-src 'self' data:",
        "object-src 'none'",
        "base-uri 'self'",
        "frame-ancestors 'none'",
    ]
    return "; ".join(parts)
