/**
 * global-auth-setup.ts — Playwright test extension for CI.
 *
 * Automatically installs API mocks with pre-authentication for all tests
 * when running in CI (CI=true env var). This allows visual regression
 * tests to run without a real backend.
 *
 * V286: Fixes Gate 4b failures where tests got stuck on login screen.
 */
import { test as base } from "@playwright/test";
import { installApiMock } from "../visual/helpers/authMock";

export const test = base.extend<{ autoAuth: void }>({
	autoAuth: async ({ page }, use) => {
		// Only install auth mock in CI environment
		if (process.env.CI === "true") {
			// Pre-authenticate so tests skip the login screen
			await installApiMock(page, { preAuthenticated: true });
		}
		await use();
	},
});

export { expect } from "@playwright/test";
