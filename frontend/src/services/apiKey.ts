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
 */

/**
 * Get the API key for backend authentication.
 *
 * Resolution order:
 * 1. VITE_FIREAI_API_KEY env var (baked into bundle at build time)
 * 2. sessionStorage 'fireai_settings' object's apiKey field (runtime, user-set)
 * 3. null (no key available — requests will fail with 401)
 *
 * @returns The API key string, or null if none is configured.
 */
export function getApiKey(): string | null {
	// 1. Build-time env var (preferred — set in Vercel project settings)
	const envKey = import.meta.env.VITE_FIREAI_API_KEY;
	if (envKey) return envKey;

	// 2. Runtime sessionStorage (user can set via Settings page)
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

	// 3. No key available
	return null;
}
