/**
 * csrf.test.ts — Unit tests for the CSRF token manager (V193 R5).
 *
 * Tests the caching, force-refresh, and invalidation logic without
 * hitting the network (fetch is mocked).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
	getCachedCsrfToken,
	getCsrfToken,
	invalidateCsrfToken,
	csrfHeader,
	CSRF_HEADER_NAME,
} from "../csrf";

// Mock fetch globally
const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

// Mock document.cookie for the cookie-reading path
const mockCookie = (token: string | null) => {
	if (token === null) {
		Object.defineProperty(document, "cookie", {
			value: "",
			configurable: true,
		});
	} else {
		Object.defineProperty(document, "cookie", {
			value: `__Host-fireai_csrf_token=${encodeURIComponent(token)}`,
			configurable: true,
		});
	}
};

describe("csrf module", () => {
	beforeEach(() => {
		// Reset module state before each test
		invalidateCsrfToken();
		mockFetch.mockReset();
		mockCookie(null);
	});

	afterEach(() => {
		invalidateCsrfToken();
	});

	describe("getCsrfToken", () => {
		it("returns null when fetch returns non-OK", async () => {
			mockFetch.mockResolvedValueOnce({
				ok: false,
				status: 401,
				json: async () => ({}),
			});

			const token = await getCsrfToken();
			expect(token).toBeNull();
		});

		it("returns the token from a successful fetch response", async () => {
			const expectedToken = "test-csrf-token-abc123";
			mockFetch.mockResolvedValueOnce({
				ok: true,
				status: 200,
				json: async () => ({ csrf_token: expectedToken }),
			});

			const token = await getCsrfToken();
			expect(token).toBe(expectedToken);
			expect(mockFetch).toHaveBeenCalledWith(
				"/api/v2/auth/csrf-token",
				expect.objectContaining({
					method: "GET",
					credentials: "same-origin",
				}),
			);
		});

		it("caches the token after first fetch", async () => {
			const token1 = "cached-token-1";
			mockFetch.mockResolvedValueOnce({
				ok: true,
				status: 200,
				json: async () => ({ csrf_token: token1 }),
			});

			await getCsrfToken();
			const cached = await getCsrfToken(); // should NOT call fetch again

			expect(cached).toBe(token1);
			expect(mockFetch).toHaveBeenCalledTimes(1);
		});

		it("force-refresh bypasses cache and fetches new token", async () => {
			const token1 = "token-v1";
			const token2 = "token-v2";
			mockFetch
				.mockResolvedValueOnce({
					ok: true,
					status: 200,
					json: async () => ({ csrf_token: token1 }),
				})
				.mockResolvedValueOnce({
					ok: true,
					status: 200,
					json: async () => ({ csrf_token: token2 }),
				});

			const first = await getCsrfToken();
			const refreshed = await getCsrfToken(true);

			expect(first).toBe(token1);
			expect(refreshed).toBe(token2);
			expect(mockFetch).toHaveBeenCalledTimes(2);
		});

		it("reads from cookie if present (avoids network call)", async () => {
			const cookieToken = "cookie-based-token";
			mockCookie(cookieToken);

			const token = await getCsrfToken();
			expect(token).toBe(cookieToken);
			expect(mockFetch).not.toHaveBeenCalled();
		});
	});

	describe("getCachedCsrfToken", () => {
		it("returns null when no token has been fetched", () => {
			expect(getCachedCsrfToken()).toBeNull();
		});

		it("returns the cached token after getCsrfToken is called", async () => {
			mockFetch.mockResolvedValueOnce({
				ok: true,
				status: 200,
				json: async () => ({ csrf_token: "cached" }),
			});
			await getCsrfToken();

			expect(getCachedCsrfToken()).toBe("cached");
		});
	});

	describe("invalidateCsrfToken", () => {
		it("clears the cached token", async () => {
			mockFetch.mockResolvedValueOnce({
				ok: true,
				status: 200,
				json: async () => ({ csrf_token: "to-invalidate" }),
			});
			await getCsrfToken();
			expect(getCachedCsrfToken()).not.toBeNull();

			invalidateCsrfToken();
			expect(getCachedCsrfToken()).toBeNull();
		});
	});

	describe("csrfHeader", () => {
		it("returns empty object when no token cached", () => {
			expect(csrfHeader()).toEqual({});
		});

		it("returns header with token when cached", async () => {
			mockFetch.mockResolvedValueOnce({
				ok: true,
				status: 200,
				json: async () => ({ csrf_token: "header-token" }),
			});
			await getCsrfToken();

			expect(csrfHeader()).toEqual({
				[CSRF_HEADER_NAME]: "header-token",
			});
		});
	});

	describe("CSRF_HEADER_NAME constant", () => {
		it("equals X-CSRF-Token", () => {
			expect(CSRF_HEADER_NAME).toBe("X-CSRF-Token");
		});
	});
});
