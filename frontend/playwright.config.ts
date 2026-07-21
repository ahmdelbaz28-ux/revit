import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  timeout: 30000,
  retries: 1,
  // V286: Global setup installs auth mock in CI to bypass login screen
  setup: "./tests/setup/global-auth-setup.ts",
  use: {
    baseURL: "http://localhost:5173",
    headless: true,
    viewport: { width: 1280, height: 720 },
    ignoreHTTPSErrors: true,
  },
  webServer: {
    // V1315 FIX: Use `vite preview` (production build) instead of `vite` (dev server)
    // to match the documented CI intent and activate the preview-api-mock plugin
    // in vite.config.ts (which only fires during `vite preview` via
    // configurePreviewServer). Without this, the API mock plugin is inactive,
    // real API calls fail, and console errors cause Playwright tests to fail.
    command: "npx vite preview --port 5173",
    url: "http://localhost:5173",
    reuseExistingServer: !process.env.CI,
    timeout: 60000,
  },
});