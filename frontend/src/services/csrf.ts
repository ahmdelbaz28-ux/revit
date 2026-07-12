
/**
 * csrf.ts — CSRF token manager (Double Submit Cookie pattern).
 *
 * V193 (R5): The backend's CSRFMiddleware enforces X-CSRF-Token header on
 * all POST/PUT/DELETE/PATCH requests (except a small exempt list). The
 * token is issued by GET /api/v2/auth/csrf-token, which sets a
 * __Host-fireai_csrf_token cookie AND returns the token in the response
 * body. The frontend must then include the token in the X-CSRF-Token
 * header on every state-changing request.
 *
 * This module:
 *   1. Lazily fetches the token on first mutation (or on app init)
 *   2. Caches it in memory (the cookie persists; we just need the value
 *      for the header)
 *   3. Re-fetches on 403 (token may have expired or been rotated)
 *   4. Exposes a getCsrfToken() function for fetchWithRetry to use
 *
 * The cookie is HttpOnly=false so JS can read it, but we use the cached
 * value for performance (avoids a document.cookie parse on every request).
 */
import { getApiKey } from "./apiKey";

const CSRF_TOKEN_ENDPOINT = "/api/v2/auth/csrf-token";
const CSRF_HEADER_NAME = "X-CSRF-Token";
const CSRF_COOKIE_NAME = "__Host-fireai_csrf_token";

let cachedToken: string | null = null;
let fetchPromise: Promise<string | null> | null = null;

/**
 * Parse the CSRF token from document.cookie.
 * Returns null if the cookie is not present.
 */
function readCookieToken(): string | null {
        if (typeof document === "undefined") return null;
        const match = document.cookie.match(
                new RegExp(`(?:^|;\\s*)${CSRF_COOKIE_NAME}=([^;]+)`),  // NOSONAR: typescript:S7780
        );
        return match ? decodeURIComponent(match[1]) : null;
}

/**
 * Fetch a fresh CSRF token from the backend.
 * The backend sets the __Host-fireai_csrf_token cookie AND returns the
 * token in the JSON response body. We use the body value (more reliable
 * than cookie parsing across browsers).
 *
 * Requires authentication (X-API-Key header or session cookie). If the
 * user is not authenticated, the endpoint returns 401 and we return null.
 */
async function fetchCsrfToken(): Promise<string | null> {
        try {
                const headers: Record<string, string> = {};
                const apiKey = getApiKey();
                if (apiKey) {
                        headers["X-API-Key"] = apiKey;
                }
                const resp = await fetch(CSRF_TOKEN_ENDPOINT, {
                        method: "GET",
                        credentials: "same-origin",
                        headers,
                });
                if (!resp.ok) {
                        // 401 = not authenticated yet; that's fine, the token will be
                        // fetched after login. 429 = rate-limited; back off.
                        return null;
                }
                const body = await resp.json();
                const token = body?.csrf_token;
                if (typeof token === "string" && token.length > 0) {
                        cachedToken = token;
                        return token;
                }
                return null;
        } catch {
                // Network error or JSON parse error — return null
                return null;
        }
}

/**
 * Get the current CSRF token, fetching it if necessary.
 *
 * Concurrent calls share the same fetch promise (deduplication) to avoid
 * hammering the endpoint on app init when many components mount at once.
 */
export async function getCsrfToken(forceRefresh = false): Promise<string | null> {
        if (cachedToken && !forceRefresh) {
                return cachedToken;
        }

        // Try reading from cookie first (synchronous, avoids a network call)
        const cookieToken = readCookieToken();
        if (cookieToken && !forceRefresh) {
                cachedToken = cookieToken;
                return cookieToken;
        }

        // Dedupe concurrent fetches
        if (!fetchPromise || forceRefresh) {
                fetchPromise = fetchCsrfToken().finally(() => {
                        // Clear the promise so the next call can fetch again if needed
                        fetchPromise = null;
                });
        }
        return fetchPromise;
}

/**
 * Synchronous getter for the cached CSRF token.
 * Returns null if the token hasn't been fetched yet.
 *
 * Useful for fire-and-forget mutations where we don't want to await
 * a token fetch (the backend will return 403 and the caller can retry).
 */
export function getCachedCsrfToken(): string | null {
        if (cachedToken) return cachedToken;
        return readCookieToken();
}

/**
 * Invalidate the cached token. Called when the backend returns 403
 * (token expired or rotated). The next getCsrfToken() call will fetch
 * a fresh one.
 */
export function invalidateCsrfToken(): void {
        cachedToken = null;
}

/**
 * Build the CSRF header object for inclusion in fetch headers.
 * Returns an empty object if no token is cached (caller should await
 * getCsrfToken() first if a mutation is critical).
 */
export function csrfHeader(): Record<string, string> {
        const token = getCachedCsrfToken();
        return token ? { [CSRF_HEADER_NAME]: token } : {};
}

/**
 * Prefetch the CSRF token on app init.
 * Called by AuthProvider after successful login.
 *
 * V193 FIX: Use a microtask delay to ensure the login response's
 * Set-Cookie header has been fully processed by the browser before
 * we fetch the CSRF token (which requires the session cookie).
 */
export async function prefetchCsrfToken(): Promise<void> {
        // Wait for the next tick so the browser processes the Set-Cookie
        // from the login response before we fetch the CSRF token.
        await new Promise((resolve) => setTimeout(resolve, 50));
        try {
                await getCsrfToken();
        } catch {
                // Best-effort — if this fails, the first mutation will
                // trigger a 403 and retry with a fresh token.
        }
}

export { CSRF_HEADER_NAME, CSRF_COOKIE_NAME };
