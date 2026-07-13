/**
 * authMock.ts — Shared Playwright API mock helper.
 *
 * Simulates a complete backend so visual + auth E2E tests can run
 * WITHOUT a real FastAPI backend or FIREAI_API_KEY env var.
 *
 * Auth flow simulated:
 *   1. GET /api/v1/auth/me → 401 (not authenticated) UNTIL login
 *   2. POST /api/v1/auth/login → 200 + sets a fake session marker
 *   3. GET /api/v1/auth/me → 200 (authenticated) AFTER login
 *   4. POST /api/v1/auth/logout → 200 + clears session marker
 *
 * The "session marker" is tracked inside a closure that the helper
 * carries per-page (Playwright's page.route() is stateless per request
 * but the closure persists across requests within the same page).
 *
 * V242: Replaces per-test ad-hoc mocks and removes all
 * `test.skip(!API_KEY, ...)` calls so every test runs and passes.
 */
import type { Page, Route } from "@playwright/test";

interface AuthMockState {
	isAuthenticated: boolean;
	role: string;
}

interface MockOptions {
	/** Skip the auth flow — just mock data endpoints (for public routes). */
	noAuth?: boolean;
	/** Pre-authenticate before any page loads (skip the login UI). */
	preAuthenticated?: boolean;
	/** Role to return from /auth/me (default: "engineer"). */
	role?: string;
}

/**
 * Default data-endpoint fulfillment: empty list / empty object.
 * GET → { success: true, data: [] }, others → { success: true, data: {} }
 */
function fulfillData(route: Route, method: string) {
	const isGet = method === "GET" || method === "HEAD";
	return route.fulfill({
		status: 200,
		contentType: "application/json",
		body: JSON.stringify({
			success: true,
			data: isGet ? [] : {},
		}),
	});
}

/**
 * Install a comprehensive API mock on the given page.
 * Returns a handle with helper actions (e.g. `login()`).
 */
export async function installApiMock(page: Page, options: MockOptions = {}) {
	const state: AuthMockState = {
		isAuthenticated: options.preAuthenticated ?? false,
		role: options.role ?? "engineer",
	};

	await page.route("**/api/**", async (route: Route) => {
		const url = route.request().url();
		const method = route.request().method();

		// ── Health endpoint ─────────────────────────────────────
		if (url.includes("/api/health") || url.includes("/api/v1/health")) {
			return route.fulfill({
				status: 200,
				contentType: "application/json",
				body: JSON.stringify({
					success: true,
					data: {
						status: "ok",
						database: "connected",
						core_modules: "loaded",
					},
				}),
			});
		}

		if (options.noAuth) {
			return fulfillData(route, method);
		}

		// ── Auth: /auth/me ──────────────────────────────────────
		if (url.includes("/auth/me")) {
			if (state.isAuthenticated) {
				return route.fulfill({
					status: 200,
					contentType: "application/json",
					body: JSON.stringify({
						success: true,
						data: { role: state.role },
					}),
				});
			}
			return route.fulfill({
				status: 401,
				contentType: "application/json",
				body: JSON.stringify({
					success: false,
					detail: "Not authenticated",
				}),
			});
		}

		// ── Auth: /auth/login ───────────────────────────────────
		if (url.includes("/auth/login") && method === "POST") {
			// Detect "invalid-key-*" sent by the invalid-key test
			try {
				const body = route.request().postDataJSON();
				if (
					body &&
					typeof body.api_key === "string" &&
					body.api_key.startsWith("invalid-key-")
				) {
					state.isAuthenticated = false;
					return route.fulfill({
						status: 401,
						contentType: "application/json",
						body: JSON.stringify({
							success: false,
							detail: "Invalid API key",
						}),
					});
				}
			} catch {
				// not JSON — fall through to success
			}

			state.isAuthenticated = true;
			return route.fulfill({
				status: 200,
				contentType: "application/json",
				headers: { "Set-Cookie": "mock_session=engineer; Path=/; HttpOnly" },
				body: JSON.stringify({
					success: true,
					data: { role: state.role },
				}),
			});
		}

		// ── Auth: /auth/logout ──────────────────────────────────
		if (url.includes("/auth/logout") && method === "POST") {
			state.isAuthenticated = false;
			return route.fulfill({
				status: 200,
				contentType: "application/json",
				body: JSON.stringify({ success: true }),
			});
		}

		// ── CSRF endpoint ───────────────────────────────────────
		if (url.includes("/csrf-token")) {
			return route.fulfill({
				status: 200,
				contentType: "application/json",
				body: JSON.stringify({
					success: true,
					data: { csrf_token: "mock-csrf-token-for-tests" },
				}),
			});
		}

		// ── Default: data endpoints ────────────────────────────
		return fulfillData(route, method);
	});

	return {
		/** Programmatically authenticate (skip the login UI). */
		async login() {
			state.isAuthenticated = true;
		},
		/** Programmatically log out. */
		async logout() {
			state.isAuthenticated = false;
		},
		/** Whether the mock currently thinks we're authenticated. */
		get isAuthenticated() {
			return state.isAuthenticated;
		},
	};
}
