import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright configuration for BAZSpark / FireAI frontend.
 *
 * V144: Visual regression testing for safety-critical fire alarm platform.
 * - Headless Chromium (no extension needed, unlike peek-cli)
 * - Screenshots saved to frontend/test-results/ for CI artifacts
 * - Baseline snapshots in frontend/tests/visual/__snapshots__/
 * - Runs against `vite preview` (production build) on port 4173
 *
 * Safety note: Playwright runs in CI sandbox — no access to user's browser
 * tabs, no extension installation, no authentication bypass. This is the
 * secure alternative to peek-cli for CI visual testing.
 */
export default defineConfig({
	testDir: "./tests", // Changed from './tests/visual' to './tests' to include all test subdirectories
	outputDir: "./test-results",
	fullyParallel: true,
	forbidOnly: !!process.env.CI,
	retries: process.env.CI ? 2 : 0,
	workers: process.env.CI ? 1 : undefined,
	reporter: [["html", { outputFolder: "playwright-report" }], ["list"]],
	use: {
		baseURL: "http://localhost:4173",
		trace: "on-first-retry",
		screenshot: "only-on-failure",
		video: "retain-on-failure",
		viewport: { width: 1280, height: 720 },
		locale: "en-US",
		timezoneId: "UTC",
	},
	projects: [
		{
			name: "chromium",
			use: { ...devices["Desktop Chrome"] },
		},
	],
	webServer: {
		command: "npm run dev -- --port 5173 --strictPort",
		url: "http://localhost:5173",
		reuseExistingServer: !process.env.CI,
		timeout: 60_000,
		cwd: ".",
	},
});
