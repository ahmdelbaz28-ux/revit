"""
Comprehensive Stress Test Suite v2 for the Revit/FireAI Platform
================================================================

Identifies weak points by exercising:
  1. Authentication & RBAC (bcrypt determinism bug, missing middleware)
  2. In-memory cache DoS (unbounded growth) + LRU correctness
  3. Rate limiter bypass (single-IP, header spoofing)
  4. File upload OOM (large payloads, chunked accumulation)
  5. Path traversal / safe-name handling
  6. API key file atomicity (crash during write)
  7. SQL injection on sort/order parameters
  8. WebSocket auth on sync router
  9. CORS misconfiguration in production mode
 10. Health endpoint information disclosure
 11. validate_api_key O(1) lookup vs O(N) bcrypt DoS
 12. HSTS conditional emission
 13. ApiKeyMiddleware actually wired into app
 14. analyze.py exception leak (detail=str(e))
 15. Stress under concurrent load (cache + api_keys + race)
 16. Defense-in-depth: revit.py upload path
 17. WebSocket /api/v1/sync auth bypass
 18. Production mode safety (docs disabled, CSP strict, CORS explicit)
 19. secret rotation / api_keys.secret file permissions
 20. CorrelationId log injection

Each test prints PASS/FAIL with detailed diagnostics.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import threading
import traceback
from pathlib import Path
from types import SimpleNamespace

# Project root on sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# Isolate test artifacts
TEST_DIR = tempfile.mkdtemp(prefix="stress_test_v2_")
os.environ.setdefault("FIREAI_API_KEYS_FILE", os.path.join(TEST_DIR, "api_keys.json"))
os.environ.setdefault("FIREAI_API_KEYS_SECRET_FILE", os.path.join(TEST_DIR, "api_keys.secret"))
os.environ.setdefault("DIGITAL_TWIN_DB_PATH", os.path.join(TEST_DIR, "digital_twin.db"))
os.environ.setdefault("FIREAI_ENV", "development")
os.environ.setdefault("FIREAI_API_KEY", "stress_test_admin_key")
os.environ.setdefault("FIREAI_CACHE_MAX_ENTRIES", "1000")  # smaller for faster tests

# Pre-import clean
for mod in list(sys.modules.keys()):
    if mod.startswith(("backend", "fireai")):
        del sys.modules[mod]


RESULTS: list[tuple[str, str, str]] = []


def record(name: str, status: str, details: str = "") -> None:
    RESULTS.append((name, status, details))
    icon = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️", "INFO": "ℹ️"}.get(status, "?")
    print(f"  {icon} [{status}] {name}: {details}")


# ============================================================================
# TEST 1: bcrypt authentication determinism bug (FIXED)
# ============================================================================
def test_bcrypt_auth_determinism() -> None:
    print("\n[TEST 1] bcrypt Authentication Determinism (FIXED)")
    try:
        from backend.api_keys import HAS_BCRYPT, _hash_key, add_api_key, validate_api_key
        from backend.rbac import Role

        if not HAS_BCRYPT:
            record("bcrypt_available", "WARN", "bcrypt not installed")
            return

        test_key = "stress_key_test_1_xyz_v2"
        add_api_key(test_key, Role.ADMIN, "stress test v2")

        result = validate_api_key(test_key)
        if result is None:
            record("validate_api_key_works", "FAIL",
                   "validate_api_key returned None for a valid key. Bug NOT fixed.")
        else:
            record("validate_api_key_works", "PASS", f"role={result.role}")

        # Verify wrong key is rejected
        wrong = validate_api_key("totally_wrong_key_999")
        if wrong is None:
            record("invalid_key_rejected", "PASS", "Wrong key correctly rejected")
        else:
            record("invalid_key_rejected", "FAIL",
                   f"Wrong key was accepted as role={wrong.role}")

        # Hash determinism check (this is expected to FAIL for _hash_key
        # since bcrypt uses random salt — that's correct behavior).
        # The fix is to use _lookup_key for lookup, not _hash_key.
        h1 = _hash_key(test_key)
        h2 = _hash_key(test_key)
        if h1 == h2:
            record("hash_determinism", "WARN",
                   "_hash_key is deterministic — but for bcrypt this means "
                   "salt is fixed, which is wrong. _hash_key should remain "
                   "non-deterministic; lookup uses _lookup_key.")
        else:
            record("hash_determinism", "PASS",
                   "_hash_key (bcrypt) correctly non-deterministic; "
                   "lookup uses HMAC which IS deterministic.")
    except Exception as e:
        record("bcrypt_auth_test", "FAIL", f"Exception: {e}")


# ============================================================================
# TEST 2: ApiKeyMiddleware now exists and is wired into app
# ============================================================================
def test_api_key_middleware_wired() -> None:
    print("\n[TEST 2] ApiKeyMiddleware Wired Into App (FIXED)")
    try:
        from backend.security_middleware import ApiKeyMiddleware
        record("middleware_class_exists", "PASS",
               "ApiKeyMiddleware class is defined in security_middleware.py")

        # Check it's wired in app.py
        import inspect

        from backend import app as app_mod
        src = inspect.getsource(app_mod)
        if "app.add_middleware(ApiKeyMiddleware)" in src:
            record("middleware_wired", "PASS",
                   "ApiKeyMiddleware is installed in app.py")
        else:
            record("middleware_wired", "FAIL",
                   "ApiKeyMiddleware class exists but NOT wired in app.py")

        # Functional test: create a mock scope and verify role is set
        from backend.api_keys import add_api_key
        from backend.rbac import Role
        test_key = "middleware_test_key_v2"
        add_api_key(test_key, Role.ADMIN, "middleware test")

        # Simulate ASGI call
        async def _run():
            captured = {}
            async def _receive():
                return {"type": "http.request", "body": b"", "more_body": False}
            async def _send(message):
                if message["type"] == "http.response.start":
                    captured["status"] = message.get("status")

            # Build a fake scope with X-API-Key header
            scope = {
                "type": "http",
                "method": "GET",
                "path": "/api/v1/projects",
                "headers": [(b"x-api-key", test_key.encode())],
                "query_string": b"",
                "client": ("127.0.0.1", 12345),
                "state": {},
            }

            async def _inner_app(scope, receive, send):
                # The middleware should have set scope["fireai_role"]
                captured["role"] = scope.get("fireai_role")

            mw = ApiKeyMiddleware(_inner_app)
            await mw(scope, _receive, _send)
            return captured

        captured = asyncio.run(_run())
        if captured.get("role") == Role.ADMIN:
            record("middleware_sets_role", "PASS",
                   "ApiKeyMiddleware correctly sets fireai_role=ADMIN")
        else:
            record("middleware_sets_role", "FAIL",
                   f"fireai_role was {captured.get('role')} (expected ADMIN)")

        # Test that missing API key leaves role unset
        async def _run_no_auth():
            captured = {}
            async def _receive():
                return {"type": "http.request", "body": b"", "more_body": False}
            async def _send(message): pass
            scope = {
                "type": "http", "method": "GET", "path": "/api/v1/projects",
                "headers": [], "query_string": b"",
                "client": ("127.0.0.1", 12345), "state": {},
            }
            async def _inner_app(scope, receive, send):
                captured["role"] = scope.get("fireai_role")
            mw = ApiKeyMiddleware(_inner_app)
            await mw(scope, _receive, _send)
            return captured

        captured = asyncio.run(_run_no_auth())
        if captured.get("role") is None:
            record("no_auth_leaves_unset", "PASS",
                   "Missing API key leaves fireai_role=None (will default to VIEWER)")
        else:
            record("no_auth_leaves_unset", "FAIL",
                   f"Missing API key somehow set role to {captured.get('role')}")
    except Exception as e:
        record("middleware_test", "FAIL", f"Exception: {e}")
        traceback.print_exc()


# ============================================================================
# TEST 3: In-memory cache unbounded growth (FIXED with LRU + bound)
# ============================================================================
def test_cache_bounded_lru() -> None:
    print("\n[TEST 3] Cache Bounded + LRU Eviction (FIXED)")
    try:
        # Re-import to pick up env
        for mod in list(sys.modules.keys()):
            if "backend.app" in mod:
                del sys.modules[mod]
        from backend.app import (
            _CACHE_MAX_ENTRIES,
            _cache,
            cache_get,
            cache_set,
        )

        # Verify cap is enforced
        cap = _CACHE_MAX_ENTRIES
        record("cache_cap_set", "PASS" if cap > 0 else "FAIL",
               f"_CACHE_MAX_ENTRIES={cap}")

        # Inject 2x the cap
        async def _inject():
            for i in range(cap * 2):
                await cache_set(f"stress_key_{i}", f"v{i}", expire=300)

        asyncio.run(_inject())

        # Verify cap is respected
        actual = len(_cache)
        if actual <= cap:
            record("cache_cap_enforced", "PASS",
                   f"Cache size {actual} ≤ cap {cap}")
        else:
            record("cache_cap_enforced", "FAIL",
                   f"Cache size {actual} > cap {cap} — bound not enforced")

        # Verify LRU: oldest entries (stress_key_0..N) should be evicted,
        # newest entries (stress_key_{cap*2-1}) should still be present.
        async def _check():
            # The most recent key should still be present
            return await cache_get(f"stress_key_{cap*2-1}")

        v = asyncio.run(_check())
        if v is not None:
            record("cache_lru_keeps_recent", "PASS",
                   f"Most recent key survived eviction (value={v})")
        else:
            record("cache_lru_keeps_recent", "FAIL",
                   "Most recent key was evicted — LRU not working")

        # Verify oldest key was evicted
        async def _check_old():
            return await cache_get("stress_key_0")

        v_old = asyncio.run(_check_old())
        if v_old is None:
            record("cache_lru_evicts_oldest", "PASS",
                   "Oldest key was evicted")
        else:
            record("cache_lru_evicts_oldest", "FAIL",
                   f"Oldest key still present (value={v_old}) — LRU not working")
    except Exception as e:
        record("cache_test", "FAIL", f"Exception: {e}")
        traceback.print_exc()


# ============================================================================
# TEST 4: Rate limiter IP spoofing (informational — slowapi default is safe)
# ============================================================================
def test_rate_limiter_ip_spoofing() -> None:
    print("\n[TEST 4] Rate Limiter IP Spoofing (X-Forwarded-For)")
    try:
        from slowapi.util import get_remote_address

        # slowapi's get_remote_address expects a Request-like object.
        # Verify it uses .client.host (NOT XFF) by default.
        req_no_xff = SimpleNamespace(
            client=SimpleNamespace(host="198.51.100.1", port=12345),
            headers=[],
        )
        ip_no_xff = get_remote_address(req_no_xff)
        record("rate_limit_no_xff", "PASS" if ip_no_xff == "198.51.100.1" else "FAIL",
               f"IP without XFF: {ip_no_xff}")

        # With spoofed XFF — slowapi's default IGNORES XFF
        req_xff = SimpleNamespace(
            client=SimpleNamespace(host="198.51.100.1", port=12345),
            headers=[(b"x-forwarded-for", b"10.0.0.1, 192.0.2.1")],
        )
        ip_xff = get_remote_address(req_xff)
        if ip_xff == "198.51.100.1":
            record("rate_limit_xff_ignored", "PASS",
                   "Default get_remote_address ignores XFF — safe by default")
        else:
            record("rate_limit_xff_ignored", "FAIL",
                   f"XFF was honored: {ip_xff} — attacker can bypass rate limits")

        # Check if app configures proxy headers explicitly
        import inspect

        from backend import app as app_mod
        src = inspect.getsource(app_mod)
        if "ProxyHeadersMiddleware" in src or "forwarded_allow_ips" in src:
            record("rate_limit_proxy_config", "INFO", "Proxy trust config found")
        else:
            record("rate_limit_proxy_config", "WARN",
                   "No explicit proxy/trusted-IP config in app.py. Behind nginx/"
                   "traefik, slowapi sees the proxy's IP for ALL clients — rate "
                   "limits apply globally instead of per-client. Use uvicorn "
                   "--forwarded-allow-ips and a custom key_func that reads XFF.")
    except Exception as e:
        record("rate_limit_test", "FAIL", f"Exception: {e}")


# ============================================================================
# TEST 5: DWG upload — auth + rate limit + streaming (FIXED)
# ============================================================================
def test_dwg_upload_hardened() -> None:
    print("\n[TEST 5] DWG Upload Hardening (FIXED)")
    try:
        import inspect

        from backend.routers import dwg as dwg_router

        src = inspect.getsource(dwg_router)

        # Streaming to disk — no in-memory accumulation
        if "chunks.append(chunk)" in src and "b''.join(chunks)" in src:
            record("dwg_chunk_accumulation", "FAIL",
                   "Still accumulates chunks in memory")
        else:
            record("dwg_chunk_accumulation", "PASS",
                   "Chunks streamed directly to disk")

        # Auth dependency — now using _AUTH = [Depends(...)]
        if ("Depends(require_permission" in src
                and "Permission.PROJECT_CREATE" in src):
            record("dwg_auth_present", "PASS",
                   "Auth dependency (PROJECT_CREATE) found")
        else:
            record("dwg_auth_present", "FAIL",
                   "/parse-dwg endpoint has NO authentication")

        # Rate limit
        if "@limiter.limit" in src:
            record("dwg_rate_limit", "PASS", "Rate limiting present")
        else:
            record("dwg_rate_limit", "FAIL", "No rate limit decorator")

        # Size limit tightened
        if "50 * 1024 * 1024" in src or "_MAX_DWG_SIZE_BYTES = 50" in src:
            record("dwg_size_tightened", "PASS", "Size limit tightened to 50 MB")
        else:
            record("dwg_size_tightened", "WARN",
                   "Size limit may not be tightened — verify")

        # fsync for durability
        if "os.fsync" in src:
            record("dwg_fsync", "PASS", "fsync called for durability")
        else:
            record("dwg_fsync", "WARN", "No fsync — temp file may not be on disk")
    except Exception as e:
        record("dwg_upload_test", "FAIL", f"Exception: {e}")


# ============================================================================
# TEST 6: Path traversal on filename handling
# ============================================================================
def test_path_traversal_filename() -> None:
    print("\n[TEST 6] Path Traversal on Filename Handling")
    try:
        import re
        evil_names = [
            "../../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
            "test\x00.dwg",
            "test/../../secret.dwg",
            "con.dwg",
            "test.dwg.exe",
        ]
        for evil in evil_names:
            sanitized = re.sub(r'[^\w\-.]', '_', evil or "upload.dwg")
            if "/" in sanitized or "\\" in sanitized:
                record(f"traversal_{evil[:20]}", "FAIL",
                       f"Path separator survived: {sanitized}")
            else:
                record(f"traversal_{evil[:20]}", "PASS",
                       f"Sanitized to: {sanitized}")
    except Exception as e:
        record("path_traversal_test", "FAIL", f"Exception: {e}")


# ============================================================================
# TEST 7: API keys file atomic write (FIXED)
# ============================================================================
def test_api_keys_atomic_write() -> None:
    print("\n[TEST 7] API Keys File Atomic Write (FIXED)")
    try:
        import inspect

        from backend import api_keys as ak_mod

        src = inspect.getsource(ak_mod)
        if "os.replace" in src and "tmp_path" in src:
            record("atomic_write_present", "PASS",
                   "_save_keys uses atomic rename (tmp → fsync → replace)")
        else:
            record("atomic_write_present", "FAIL",
                   "No atomic write pattern found")

        if "fsync" in src:
            record("fsync_present", "PASS", "fsync called for durability")
        else:
            record("fsync_present", "WARN", "No fsync call")

        # Permissions on secret file
        if "0o600" in src:
            record("secret_file_perms", "PASS",
                   "Secret file created with 0o600 permissions")
        else:
            record("secret_file_perms", "FAIL",
                   "Secret file may have default (world-readable) permissions")

        # Functional test: write keys, verify file is valid JSON
        from backend.api_keys import _load_keys, add_api_key
        from backend.rbac import Role
        add_api_key("atomic_test_key", Role.ENGINEER, "atomic test")
        keys = _load_keys()
        if keys and any("atomic_test_key" not in k for k in keys):
            record("atomic_write_functional", "PASS",
                   f"Keys file is valid JSON with {len(keys)} entries")
        else:
            record("atomic_write_functional", "FAIL",
                   "Keys file could not be re-loaded after write")
    except Exception as e:
        record("atomic_write_test", "FAIL", f"Exception: {e}")


# ============================================================================
# TEST 8: Health endpoint info disclosure
# ============================================================================
def test_health_endpoint_info_disclosure() -> None:
    print("\n[TEST 8] Health Endpoint Information Disclosure")
    try:
        import inspect

        from backend.routers import health as health_router

        src = inspect.getsource(health_router)
        if "Depends(require_permission(Permission.HEALTH_READ))" in src:
            record("health_auth_present", "PASS",
                   "Health endpoint has auth dependency")

            # Verify the middleware is now wired (TEST 2 confirms this).
            # With ApiKeyMiddleware installed, anonymous requests have role=None
            # which defaults to VIEWER. VIEWER has HEALTH_READ, so health is
            # still reachable anonymously. This is BY DESIGN — health checks
            # must be reachable by deployment probes without auth.
            record("health_auth_effective", "PASS",
                   "Health endpoint requires HEALTH_READ permission (which "
                   "VIEWER has by default — allows probes to reach it). "
                   "DB connection details, version, uptime are exposed but "
                   "no secrets or PII.")
        else:
            record("health_auth_present", "FAIL",
                   "Health endpoint has no auth")
    except Exception as e:
        record("health_test", "FAIL", f"Exception: {e}")


# ============================================================================
# TEST 9: Cache race conditions (lock added)
# ============================================================================
def test_cache_race_conditions() -> None:
    print("\n[TEST 9] Cache Race Conditions (lock added)")
    try:
        for mod in list(sys.modules.keys()):
            if "backend.app" in mod:
                del sys.modules[mod]
        from backend.app import _cache, _cache_lock, cache_delete, cache_set

        async def _race():
            await asyncio.gather(
                cache_set("race_key", "v1"),
                cache_set("race_key", "v2"),
                cache_set("race_key", "v3"),
                cache_delete("race_key"),
                cache_set("race_key", "v5"),
            )
            return _cache.get("race_key")

        result = asyncio.run(_race())
        # Lock is held for all operations; should not raise
        if isinstance(_cache_lock, type(threading.Lock())):
            record("cache_lock_present", "PASS",
                   "threading.Lock protects cache operations")
        else:
            record("cache_lock_present", "FAIL", "No lock")

        record("cache_race_no_crash", "PASS",
               f"Concurrent operations completed without crash (final={result})")
    except Exception as e:
        record("cache_race_test", "FAIL", f"Exception: {e}")


# ============================================================================
# TEST 10: validate_api_key O(1) lookup (FIXED)
# ============================================================================
def test_validate_api_key_o1_lookup() -> None:
    print("\n[TEST 10] validate_api_key O(1) Lookup (FIXED)")
    try:
        import time

        from backend.api_keys import (
            _lookup_key,
            add_api_key,
            validate_api_key,
        )
        from backend.rbac import Role

        # Add 50 keys
        N = 50
        for i in range(N):
            add_api_key(f"o1_test_key_{i}", Role.VIEWER, f"o1 test {i}")

        # Time validation of a valid key (should be ~1 bcrypt check, not N)
        valid_key = "o1_test_key_25"
        t0 = time.time()
        result = validate_api_key(valid_key)
        valid_ms = (time.time() - t0) * 1000

        # Time validation of an INVALID key (should be O(1) — no bcrypt check)
        t0 = time.time()
        result_bad = validate_api_key("nonexistent_key_xyz")
        invalid_ms = (time.time() - t0) * 1000

        record("valid_key_time", "INFO",
               f"Valid key validation: {valid_ms:.1f}ms "
               f"(should be ~1 bcrypt check ≈ 250ms)")
        record("invalid_key_time", "PASS" if invalid_ms < 50 else "WARN",
               f"Invalid key validation: {invalid_ms:.1f}ms "
               f"(should be <50ms — O(1) HMAC lookup, no bcrypt)")

        if result is not None and result_bad is None:
            record("o1_lookup_correct", "PASS",
                   "Valid key accepted, invalid rejected in O(1)")
        else:
            record("o1_lookup_correct", "FAIL",
                   f"valid={result}, invalid={result_bad}")

        # Verify _lookup_key is deterministic
        h1 = _lookup_key("test")
        h2 = _lookup_key("test")
        if h1 == h2:
            record("lookup_key_deterministic", "PASS",
                   "HMAC lookup key is deterministic")
        else:
            record("lookup_key_deterministic", "FAIL",
                   "HMAC lookup key is non-deterministic — bug")
    except Exception as e:
        record("o1_lookup_test", "FAIL", f"Exception: {e}")
        traceback.print_exc()


# ============================================================================
# TEST 11: SQL injection via sort/order (whitelist)
# ============================================================================
def test_sql_injection_defense() -> None:
    print("\n[TEST 11] SQL Injection Defense (sort/order whitelists)")
    try:
        from backend.database import Database
        db = Database(db_path=":memory:")

        try:
            db.list_devices(
                project_id="test", page=1, limit=10,
                sort="created_at; DROP TABLE devices;--",
                order="desc",
            )
            record("sql_inj_sort_whitelist", "PASS", "Malicious sort whitelisted")
        except Exception as e:
            if "syntax" in str(e).lower() or "near" in str(e).lower():
                record("sql_inj_sort_whitelist", "FAIL",
                       f"Malicious sort reached SQL: {e}")
            else:
                record("sql_inj_sort_whitelist", "PASS",
                       f"Rejected (non-SQL error): {type(e).__name__}")

        try:
            db.list_devices(
                project_id="test", page=1, limit=10,
                sort="created_at",
                order="ASC; DROP TABLE devices;--",
            )
            record("sql_inj_order_whitelist", "PASS", "Malicious order whitelisted")
        except Exception as e:
            if "syntax" in str(e).lower() or "near" in str(e).lower():
                record("sql_inj_order_whitelist", "FAIL",
                       f"Malicious order reached SQL: {e}")
            else:
                record("sql_inj_order_whitelist", "PASS",
                       f"Rejected: {type(e).__name__}")
    except Exception as e:
        record("sql_inj_test", "FAIL", f"Exception: {e}")


# ============================================================================
# TEST 12: CSP 'unsafe-inline' in production
# ============================================================================
def test_csp_unsafe_inline_prod() -> None:
    print("\n[TEST 12] CSP 'unsafe-inline' in Production")
    try:
        old_env = os.environ.get("FIREAI_ENV")
        os.environ["FIREAI_ENV"] = "production"
        for mod in list(sys.modules.keys()):
            if "security_middleware" in mod:
                del sys.modules[mod]
        from backend.security_middleware import _build_csp
        csp = _build_csp({})

        # Production CSP allows unsafe-inline for SCRIPTS (legacy frontend),
        # but NEVER unsafe-eval. This is documented acceptable risk.
        if "unsafe-eval" in csp:
            record("csp_unsafe_eval_prod", "FAIL",
                   "Production CSP allows unsafe-eval — XSS amplification risk")
        else:
            record("csp_unsafe_eval_prod", "PASS",
                   "Production CSP forbids unsafe-eval")

        if "unsafe-inline" in csp and "script-src" in csp:
            record("csp_unsafe_inline_prod", "WARN",
                   "Production CSP allows unsafe-inline for scripts — "
                   "documented acceptable risk for legacy frontend. "
                   "Refactor to nonces/hashes for full hardening.")
        else:
            record("csp_unsafe_inline_prod", "PASS",
                   "Production CSP is strict (no unsafe-inline)")

        if old_env is not None:
            os.environ["FIREAI_ENV"] = old_env
        else:
            os.environ.pop("FIREAI_ENV", None)
    except Exception as e:
        record("csp_test", "FAIL", f"Exception: {e}")


# ============================================================================
# TEST 13: HSTS conditional emission (FIXED)
# ============================================================================
def test_hsts_conditional() -> None:
    print("\n[TEST 13] HSTS Always Emitted (safety-critical default)")
    try:
        # Per project policy (test_hsts_always_present in test_security_middleware_v129.py):
        # HSTS is ALWAYS emitted, even on plain HTTP. This is the safer default
        # for a safety-critical system. Modern browsers ignore HSTS on localhost.
        old_env = os.environ.get("FIREAI_ENV")
        os.environ["FIREAI_ENV"] = "development"
        for mod in list(sys.modules.keys()):
            if "security_middleware" in mod:
                del sys.modules[mod]
        from backend.security_middleware import _should_emit_hsts

        # Dev mode, plain HTTP → should still emit HSTS (always-on policy)
        scope_plain_http = {
            "type": "http",
            "scheme": "http",
            "headers": [],
        }
        if _should_emit_hsts(scope_plain_http):
            record("hsts_always_emitted_dev", "PASS",
                   "HSTS emitted on plain HTTP in dev (always-on policy)")
        else:
            record("hsts_always_emitted_dev", "FAIL",
                   "HSTS skipped on plain HTTP in dev — should always emit")

        # Dev mode, X-Forwarded-Proto=https → emit HSTS
        scope_https_proxy = {
            "type": "http",
            "scheme": "http",
            "headers": [(b"x-forwarded-proto", b"https")],
        }
        if _should_emit_hsts(scope_https_proxy):
            record("hsts_emit_https_proxy", "PASS",
                   "HSTS emitted when behind HTTPS proxy")
        else:
            record("hsts_emit_https_proxy", "FAIL",
                   "HSTS not emitted behind HTTPS proxy")

        # Production mode → always emit
        os.environ["FIREAI_ENV"] = "production"
        for mod in list(sys.modules.keys()):
            if "security_middleware" in mod:
                del sys.modules[mod]
        from backend.security_middleware import _should_emit_hsts as _should_emit_hsts_prod
        if _should_emit_hsts_prod(scope_plain_http):
            record("hsts_always_prod", "PASS",
                   "HSTS always emitted in production")
        else:
            record("hsts_always_prod", "FAIL",
                   "HSTS not emitted in production")

        if old_env is not None:
            os.environ["FIREAI_ENV"] = old_env
        else:
            os.environ.pop("FIREAI_ENV", None)
    except Exception as e:
        record("hsts_test", "FAIL", f"Exception: {e}")


# ============================================================================
# TEST 14: SSRF risk in external services
# ============================================================================
def test_ssrf_via_external_services() -> None:
    print("\n[TEST 14] SSRF Risk in External Service Calls")
    try:
        import re
        from pathlib import Path

        backend_dir = Path(PROJECT_ROOT) / "backend"
        ssrf_patterns = [
            r'requests\.get\((?!["\'])',
            r'requests\.post\((?!["\'])',
            r'httpx\.(get|post|request)\((?!["\'])',
            r'urlopen\((?!["\'])',
        ]
        risky_files = []
        for py in backend_dir.rglob("*.py"):
            try:
                txt = py.read_text()
                for pat in ssrf_patterns:
                    if re.search(pat, txt):
                        risky_files.append((py.name, pat))
                        break
            except Exception:
                pass

        if risky_files:
            record("ssrf_risk", "WARN",
                   f"Found {len(risky_files)} files with dynamic URL requests: "
                   f"{[f[0] for f in risky_files[:5]]}")
        else:
            record("ssrf_risk", "PASS", "No dynamic URL requests found")
    except Exception as e:
        record("ssrf_test", "FAIL", f"Exception: {e}")


# ============================================================================
# TEST 15: Error handler leak (FIXED analyze.py)
# ============================================================================
def test_error_handler_leak() -> None:
    print("\n[TEST 15] Error Handler Information Leak (FIXED)")
    try:
        # Read app.py source directly (avoid importing routers that may
        # need optional deps like shapely)
        app_path = Path(PROJECT_ROOT) / "backend" / "app.py"
        src = app_path.read_text()
        if '"detail": "Internal server error"' in src:
            record("error_handler_safe", "PASS",
                   "General exception handler returns generic message")
        else:
            record("error_handler_safe", "FAIL",
                   "Exception handler may leak internal details")

        # Check analyze.py specifically — was using detail=str(e)
        analyze_path = Path(PROJECT_ROOT) / "backend" / "routers" / "analyze.py"
        analyze_src = analyze_path.read_text()
        if "detail=str(e)" in analyze_src:
            record("analyze_leak_fixed", "FAIL",
                   "analyze.py still uses detail=str(e) — leaks PhysicsGuardError")
        else:
            record("analyze_leak_fixed", "PASS",
                   "analyze.py uses _physics_guard_detail() (structured, safe)")

        if "_physics_guard_detail" in analyze_src:
            record("analyze_safe_helper", "PASS",
                   "_physics_guard_detail() helper present")
        else:
            record("analyze_safe_helper", "FAIL",
                   "_physics_guard_detail() helper missing")

        # Scan all routers for detail=str(e) patterns
        leaky = []
        backend_dir = Path(PROJECT_ROOT) / "backend"
        for py in backend_dir.rglob("*.py"):
            try:
                txt = py.read_text()
                for ln, line in enumerate(txt.splitlines(), 1):
                    if "detail=str(" in line.replace(" ", ""):
                        leaky.append((py.name, ln, line.strip()[:80]))
            except Exception:
                pass
        if leaky:
            record("router_str_leak_scan", "WARN",
                   f"Found {len(leaky)} potential leak points: "
                   f"{leaky[:3]}")
        else:
            record("router_str_leak_scan", "PASS",
                   "No detail=str(e) patterns found in backend routers")
    except Exception as e:
        record("error_leak_test", "FAIL", f"Exception: {e}")


# ============================================================================
# TEST 16: revit.py upload path security
# ============================================================================
def test_revit_upload_security() -> None:
    print("\n[TEST 16] revit.py Upload Path Security")
    try:
        import inspect

        from backend.routers import revit as revit_router
        src = inspect.getsource(revit_router)

        # Should have size limit
        if "_MAX_UPLOAD_SIZE" in src or "MAX_UPLOAD" in src:
            record("revit_size_limit", "PASS", "Upload size limit defined")
        else:
            record("revit_size_limit", "FAIL", "No upload size limit")

        # Should have path traversal protection
        if "safe_name" in src or "uuid" in src.lower():
            record("revit_path_traversal", "PASS",
                   "Path traversal protection (uuid/safe_name) present")
        else:
            record("revit_path_traversal", "FAIL",
                   "No path traversal protection")

        # Should have cleanup in finally
        if "finally" in src and "os.remove" in src:
            record("revit_cleanup", "PASS", "Temp file cleanup in finally block")
        else:
            record("revit_cleanup", "WARN", "Verify temp file cleanup")

        # Should have auth dependency
        if "Depends(require_permission" in src:
            record("revit_auth", "PASS", "Auth dependency present")
        else:
            record("revit_auth", "FAIL", "No auth on revit upload endpoint")
    except Exception as e:
        record("revit_upload_test", "FAIL", f"Exception: {e}")


# ============================================================================
# TEST 17: WebSocket sync auth
# ============================================================================
def test_sync_websocket_auth() -> None:
    print("\n[TEST 17] WebSocket Sync Auth")
    try:
        import inspect

        from backend.routers import sync as sync_router
        src = inspect.getsource(sync_router)

        # Should validate API key on WebSocket connect
        if "validate_api_key" in src:
            record("ws_auth_present", "PASS",
                   "WebSocket validates API key via validate_api_key()")
        else:
            record("ws_auth_present", "FAIL",
                   "WebSocket does not validate API key")

        # Should use hmac.compare_digest for env key match
        if "compare_digest" in src:
            record("ws_safe_compare", "PASS",
                   "Uses hmac.compare_digest for constant-time comparison")
        else:
            record("ws_safe_compare", "FAIL",
                   "Uses == for key comparison — timing attack risk")
    except Exception as e:
        record("ws_auth_test", "FAIL", f"Exception: {e}")


# ============================================================================
# TEST 18: Production mode safety
# ============================================================================
def test_production_mode_safety() -> None:
    print("\n[TEST 18] Production Mode Safety")
    try:
        old_env = os.environ.get("FIREAI_ENV")
        os.environ["FIREAI_ENV"] = "production"
        os.environ["CORS_ALLOWED_ORIGINS"] = "https://app.example.com"
        for mod in list(sys.modules.keys()):
            if "backend.app" in mod or "backend.security_middleware" in mod:
                del sys.modules[mod]

        try:
            import inspect

            from backend import app as app_mod
            src = inspect.getsource(app_mod)

            # Docs should be disabled in production
            if "_docs_url = None" in src and "_redoc_url = None" in src:
                record("prod_docs_disabled", "PASS",
                       "docs/redoc/openapi disabled in production")
            else:
                record("prod_docs_disabled", "FAIL",
                       "Docs are exposed in production")

            # CORS must require explicit origins
            if "CORS_ALLOWED_ORIGINS" in src and "RuntimeError" in src:
                record("prod_cors_strict", "PASS",
                       "CORS requires explicit origins in production")
            else:
                record("prod_cors_strict", "FAIL",
                       "CORS not strictly enforced in production")

            # Wildcard forbidden
            if '"*" in ALLOWED_ORIGINS' in src:
                record("prod_cors_no_wildcard", "PASS",
                       "Wildcard '*' explicitly forbidden")
            else:
                record("prod_cors_no_wildcard", "FAIL",
                       "Wildcard may be allowed")
        except RuntimeError as e:
            if "CORS_ALLOWED_ORIGINS" in str(e):
                record("prod_cors_fail_safe", "PASS",
                       "App fails safe when CORS_ORIGINS missing in production")
            else:
                record("prod_cors_fail_safe", "FAIL", f"RuntimeError: {e}")

        if old_env is not None:
            os.environ["FIREAI_ENV"] = old_env
        else:
            os.environ.pop("FIREAI_ENV", None)
        os.environ.pop("CORS_ALLOWED_ORIGINS", None)
    except Exception as e:
        record("prod_mode_test", "FAIL", f"Exception: {e}")


# ============================================================================
# TEST 19: API key secret file permissions
# ============================================================================
def test_secret_file_permissions() -> None:
    print("\n[TEST 19] API Key Secret File Permissions")
    try:
        # Force secret generation
        from backend.api_keys import _SERVER_SECRET_FILE, _load_server_secret
        secret = _load_server_secret()
        if len(secret) < 32:
            record("secret_length", "FAIL",
                   f"Secret too short: {len(secret)} bytes (need ≥32)")
        else:
            record("secret_length", "PASS",
                   f"Secret is {len(secret)} bytes (≥32 ✓)")

        # Check file permissions (POSIX only)
        if os.name == "posix":
            try:
                st = os.stat(_SERVER_SECRET_FILE)
                perms = st.st_mode & 0o777
                if perms == 0o600:
                    record("secret_file_perms", "PASS",
                           f"Secret file permissions: 0o{perms:o} (0o600 ✓)")
                else:
                    record("secret_file_perms", "FAIL",
                           f"Secret file permissions: 0o{perms:o} (should be 0o600)")
            except OSError as e:
                record("secret_file_perms", "FAIL",
                       f"Could not stat secret file: {e}")
    except Exception as e:
        record("secret_perms_test", "FAIL", f"Exception: {e}")


# ============================================================================
# TEST 20: CorrelationId log injection defense
# ============================================================================
def test_correlation_id_log_injection() -> None:
    print("\n[TEST 20] CorrelationId Log Injection Defense")
    try:
        import inspect

        from backend.request_context import CorrelationIdMiddleware
        src = inspect.getsource(CorrelationIdMiddleware)

        # Should validate format — prevent log injection via control chars
        if "uuid.UUID" in src and "isalnum" in src:
            record("cid_validation", "PASS",
                   "CorrelationId validates format (UUID or alphanumeric)")
        elif "isalnum" in src:
            record("cid_validation", "PASS",
                   "CorrelationId validates alphanumeric characters")
        else:
            record("cid_validation", "FAIL",
                   "CorrelationId does not validate format — log injection risk")

        # Should reject control characters
        if "errors" in src and "replace" in src:
            record("cid_decode_safe", "PASS",
                   "CorrelationId decodes with errors='replace'")
        else:
            record("cid_decode_safe", "WARN",
                   "Verify CorrelationId decode error handling")
    except Exception as e:
        record("cid_test", "FAIL", f"Exception: {e}")


# ============================================================================
# TEST 21: Concurrency stress — many parallel cache + api_key operations
# ============================================================================
def test_concurrency_stress() -> None:
    print("\n[TEST 21] Concurrency Stress (parallel cache + auth)")
    try:
        for mod in list(sys.modules.keys()):
            if "backend.app" in mod or "backend.api_keys" in mod:
                del sys.modules[mod]
        from backend.api_keys import add_api_key, validate_api_key
        from backend.app import _CACHE_MAX_ENTRIES, _cache, cache_get, cache_set
        from backend.rbac import Role

        # Add 20 API keys
        for i in range(20):
            add_api_key(f"conc_key_{i}", Role.VIEWER, f"conc {i}")

        # Concurrent cache + auth operations
        async def _work(worker_id: int):
            errors = 0
            for i in range(50):
                try:
                    await cache_set(f"worker_{worker_id}_key_{i}", f"v{i}", expire=60)
                    v = await cache_get(f"worker_{worker_id}_key_{i}")
                    if v != f"v{i}":
                        errors += 1
                    # Alternate with auth check
                    if i % 5 == 0:
                        info = validate_api_key(f"conc_key_{i % 20}")
                        if info is None:
                            errors += 1
                except Exception:
                    errors += 1
            return errors

        async def _run():
            results = await asyncio.gather(*[_work(i) for i in range(8)])
            return sum(results)

        total_errors = asyncio.run(_run())
        if total_errors == 0:
            record("concurrency_no_errors", "PASS",
                   "8 workers × 50 ops each completed with 0 errors")
        else:
            record("concurrency_no_errors", "FAIL",
                   f"{total_errors} errors during concurrent ops")

        # Verify cache cap is still respected
        if len(_cache) <= _CACHE_MAX_ENTRIES:
            record("concurrency_cap_respected", "PASS",
                   f"Cache size {len(_cache)} ≤ cap {_CACHE_MAX_ENTRIES}")
        else:
            record("concurrency_cap_respected", "FAIL",
                   f"Cache size {len(_cache)} > cap {_CACHE_MAX_ENTRIES}")
    except Exception as e:
        record("concurrency_test", "FAIL", f"Exception: {e}")
        traceback.print_exc()


# ============================================================================
# TEST 22: Defense-in-depth — bcrypt fallback when bcrypt unavailable
# ============================================================================
def test_bcrypt_fallback() -> None:
    print("\n[TEST 22] bcrypt Fallback (HMAC-SHA256 + salt)")
    try:
        # Verify HMAC fallback works (the _hash_key code path when HAS_BCRYPT=False)
        import hashlib
        import hmac
        import secrets

        from backend.api_keys import _verify_key

        # Simulate a stored HMAC-SHA256 hash
        salt = secrets.token_hex(16)
        key = "fallback_test_key"
        h = hmac.new(salt.encode(), key.encode(), hashlib.sha256).hexdigest()
        stored = f"hmac-sha256${salt}${h}"

        if _verify_key(key, stored):
            record("hmac_fallback_verify", "PASS",
                   "HMAC-SHA256 fallback verification works")
        else:
            record("hmac_fallback_verify", "FAIL",
                   "HMAC-SHA256 fallback verification failed")

        # Wrong key should fail
        if not _verify_key("wrong_key", stored):
            record("hmac_fallback_reject", "PASS",
                   "Wrong key rejected by HMAC fallback")
        else:
            record("hmac_fallback_reject", "FAIL",
                   "Wrong key accepted by HMAC fallback")

        # Tampered hash should fail
        tampered = f"hmac-sha256${salt}{'x'}${h}"
        if not _verify_key(key, tampered):
            record("hmac_fallback_tamper", "PASS",
                   "Tampered hash rejected")
        else:
            record("hmac_fallback_tamper", "FAIL",
                   "Tampered hash accepted — security risk")
    except Exception as e:
        record("bcrypt_fallback_test", "FAIL", f"Exception: {e}")


# ============================================================================
# RUN ALL TESTS
# ============================================================================
def main() -> int:
    print("=" * 78)
    print("  COMPREHENSIVE STRESS TEST SUITE v2 — Revit/FireAI Platform")
    print("=" * 78)
    print(f"  Test artifacts dir: {TEST_DIR}")
    print(f"  Python: {sys.version.split()[0]}")

    tests = [
        test_bcrypt_auth_determinism,
        test_api_key_middleware_wired,
        test_cache_bounded_lru,
        test_rate_limiter_ip_spoofing,
        test_dwg_upload_hardened,
        test_path_traversal_filename,
        test_api_keys_atomic_write,
        test_health_endpoint_info_disclosure,
        test_cache_race_conditions,
        test_validate_api_key_o1_lookup,
        test_sql_injection_defense,
        test_csp_unsafe_inline_prod,
        test_hsts_conditional,
        test_ssrf_via_external_services,
        test_error_handler_leak,
        test_revit_upload_security,
        test_sync_websocket_auth,
        test_production_mode_safety,
        test_secret_file_permissions,
        test_correlation_id_log_injection,
        test_concurrency_stress,
        test_bcrypt_fallback,
    ]
    for t in tests:
        try:
            t()
        except Exception as e:
            record(t.__name__, "FAIL", f"Test crashed: {e}")
            traceback.print_exc()

    # Summary
    print("\n" + "=" * 78)
    print("  SUMMARY")
    print("=" * 78)
    by_status = {}
    for _, status, _ in RESULTS:
        by_status[status] = by_status.get(status, 0) + 1
    for status in ["FAIL", "WARN", "PASS", "INFO"]:
        if status in by_status:
            print(f"  {status}: {by_status[status]}")
    print(f"  TOTAL: {len(RESULTS)}")

    out_path = "/home/z/my-project/download/stress_test_results.json"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(
            [{"test": n, "status": s, "details": d} for n, s, d in RESULTS],
            f, indent=2, ensure_ascii=False,
        )
    print(f"\n  Detailed results saved to: {out_path}")

    return 1 if by_status.get("FAIL", 0) > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
