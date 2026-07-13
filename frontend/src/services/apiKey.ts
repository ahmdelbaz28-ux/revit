/**
 * @file apiKey.ts
 * @description Single source of truth for API key retrieval.
 *
 * V184 FIX: getApiKey() was duplicated in 4 places:
 *   - src/services/api.ts:35
 *   - src/services/digitalTwinApi.ts:579 (class method)
 *   - src/services/digitalTwinApi.ts:741 (free function)
 *   - src/services/fullApi.ts:51
 *
 * Each duplicate had the SAME logic (env var → sessionStorage fallback), but
 * maintaining 4 copies meant bugs could diverge. This file is the canonical
 * implementation. All API clients should import from here.
 *
 * V243 SECURITY: The sessionStorage fallback is DEPRECATED and kept only for
 * backward compatibility with the Settings page. The canonical auth flow is
 * the HttpOnly session cookie set by POST /auth/login, which JavaScript
 * cannot read. API keys should NOT be stored in sessionStorage long-term
 * because it's XSS-readable. This fallback will be removed in v2.0.
 *
 * @deprecated The sessionStorage fallback will be removed in v2.0. Use the
 * HttpOnly cookie auth flow exclusively.
 */

/**
 * Get the API key for backend authentication.
 *
 * Resolution order:
 * 1. VITE_FIREAI_API_KEY env var (baked into bundle at build time)
 * 2. sessionStorage 'fireai_settings' object's apiKey field (DEPRECATED — legacy)
 * 3. null (no key available — requests will use the HttpOnly cookie instead)
 *
 * @returns The API key string, or null if none is configured.
 * @deprecated Prefer HttpOnly cookie auth via POST /auth/login
 */
export function getApiKey(): string | null {
	// 1. Build-time env var (preferred — set in Vercel project settings)
	const envKey = import.meta.env.VITE_FIREAI_API_KEY;
	if (envKey) return envKey;

	// 2. Runtime sessionStorage (DEPRECATED — V243: XSS-readable, will be removed in v2.0)
	// Kept for backward compatibility with the Settings page.
	try {
		const stored = sessionStorage.getItem("fireai_settings");
		if (stored) {
			const settings = JSON.parse(stored);
			if (
				settings?.apiKey &&
				typeof settings.apiKey === "string" &&
				settings.apiKey.trim()
			) {
				return settings.apiKey.trim();
			}
		}
	} catch {
		// Invalid JSON in sessionStorage — ignore (corrupt entry, don't crash)
	}

	// 3. No key available — the HttpOnly cookie will be used instead
	return null;
}
