/**
 * @file apiKey.ts
 * @description Single source of truth for API key retrieval.
 *
 * V256 SECURITY FIX: The sessionStorage fallback has been REMOVED.
 * Storing API keys in sessionStorage is XSS-readable — a single XSS
 * vulnerability gives full account takeover. The canonical auth flow
 * uses an HttpOnly session cookie set by POST /auth/login, which
 * JavaScript cannot read.
 *
 * VITE_FIREAI_API_KEY is still supported for SSR/headless builds that
 * can't use cookies. In browser contexts, the HttpOnly cookie is used
 * automatically (credentials: "same-origin" on all fetch calls).
 */

/**
 * Get the API key for backend authentication.
 *
 * Resolution order:
 * 1. VITE_FIREAI_API_KEY env var (baked into bundle at build time)
 * 2. null (no key available — requests use the HttpOnly cookie instead)
 *
 * @returns The API key string, or null if none is configured.
 */
export function getApiKey(): string | null {
	// Build-time env var (only for SSR/headless builds that can't use cookies)
	const envKey = import.meta.env.VITE_FIREAI_API_KEY;
	if (envKey) return envKey;

	// No key available — the HttpOnly cookie will be used instead
	return null;
}
