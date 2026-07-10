// NOSONAR
/**
 * v193-e2e-auth.spec.ts — End-to-end Playwright tests for the V193 auth flow.
 *
 * Tests the complete login → dashboard → logout cycle that was broken before
 * V193 (R1-R5). These tests require:
 *   1. Backend running on http://127.0.0.1:8000 with FIREAI_API_KEY set
 *   2. Frontend running on http://127.0.0.1:5173
 *   3. The FIREAI_API_KEY env var available to the test process
 *
 * Run with: npx playwright test tests/visual/v193-e2e-auth.spec.ts
 */
import { test, expect, type Page } from "@playwright/test";

const FRONTEND_URL = process.env.PLAYWRIGHT_FRONTEND_URL || "http://127.0.0.1:5173";
// S1607: Tests requiring FIREAI_API_KEY are conditionally skipped when the
// env var is not set (e.g., in CI without secrets). This is intentional —
// these tests cannot run without a real backend API key.
const API_KEY = process.env.FIREAI_API_KEY || "test-key-not-set";

/**
 * Helper: perform login via the UI.
 * Fills the API key field and clicks Sign In.
 */
async function loginViaUI(page: Page, apiKey: string = API_KEY) {
        await page.goto("/login");
        await page.waitForLoadState("networkidle");

        // Fill the API key input
        const apiKeyInput = page.getByLabel("API Key");
        await apiKeyInput.fill(apiKey);

        // Click Sign In
        await page.getByRole("button", { name: "Sign In" }).click();

        // Wait for redirect to dashboard (or ?from= target)
        await page.waitForURL(/\/dashboard/, { timeout: 10000 });
}

// ─── Test 1: Unauthenticated access redirects to /login ────────────────────
test("unauthenticated access to /dashboard redirects to /login", async ({ page }) => {
        await page.goto("/dashboard");
        await page.waitForLoadState("networkidle");

        // Should redirect to /login?from=%2Fdashboard
        await expect(page).toHaveURL(/\/login/);
        await expect(page).toHaveURL(/from=%2Fdashboard/);

        // Login page should be visible
        await expect(page.getByRole("heading", { name: /sign in/i })).toBeVisible();
        await expect(page.getByLabel("API Key")).toBeVisible();
});

// ─── Test 2: Unauthenticated access to other protected routes ───────────────
test("unauthenticated access to /projects redirects to /login", async ({ page }) => {
        await page.goto("/projects");
        await page.waitForLoadState("networkidle");
        await expect(page).toHaveURL(/\/login/);
        await expect(page).toHaveURL(/from=%2Fprojects/);
});

// ─── Test 3: /login page renders correctly ─────────────────────────────────
test("login page renders with correct elements", async ({ page }) => {
        await page.goto("/login");
        await page.waitForLoadState("networkidle");

        // Brand header
        await expect(page.getByText("BAZSPARK")).toBeVisible();
        await expect(page.getByText("Safety-Critical Fire Alarm Engineering Platform")).toBeVisible();

        // Sign In heading
        await expect(page.getByRole("heading", { name: /sign in/i })).toBeVisible();

        // API Key input
        await expect(page.getByLabel("API Key")).toBeVisible();

        // Remember checkbox
        await expect(page.getByLabel(/remember/i)).toBeVisible();

        // Sign In button (disabled until input has value)
        const signInButton = page.getByRole("button", { name: "Sign In" });
        await expect(signInButton).toBeDisabled();

        // Show/hide toggle
        await expect(page.getByRole("button", { name: /show api key/i })).toBeVisible();
});

// ─── Test 4: Sign In button enables when API key is entered ─────────────────
test("Sign In button enables when API key is entered", async ({ page }) => {
        await page.goto("/login");
        await page.waitForLoadState("networkidle");

        const signInButton = page.getByRole("button", { name: "Sign In" });
        await expect(signInButton).toBeDisabled();

        await page.getByLabel("API Key").fill("some-test-key");
        await expect(signInButton).toBeEnabled();
});

// ─── Test 5: Invalid API key shows error message ───────────────────────────
test("invalid API key shows error message", async ({ page }) => {
        await page.goto("/login");
        await page.waitForLoadState("networkidle");

        await page.getByLabel("API Key").fill("invalid-key-1234567890");
        await page.getByRole("button", { name: "Sign In" }).click();

        // Should show error alert (not redirect)
        await expect(page.getByRole("alert")).toBeVisible({ timeout: 5000 });
        await expect(page.getByText(/invalid api key/i)).toBeVisible();

        // Should still be on /login
        await expect(page).toHaveURL(/\/login/);
});

// ─── Test 6: Valid login redirects to dashboard ────────────────────────────
test("valid login redirects to dashboard", async ({ page }) => {
        test.skip(!API_KEY || API_KEY === "test-key-not-set", "FIREAI_API_KEY not set");  // NOSONAR — S1607: TODO kept for tracking

        await loginViaUI(page);

        // Should be on dashboard
        await expect(page).toHaveURL(/\/dashboard/);

        // Dashboard should show the brand
        await expect(page.getByText("BAZSPARK").first()).toBeVisible();

        // Dashboard should show real data (not loading skeleton)
        await expect(page.getByText(/projects/i).first()).toBeVisible();
});

// ─── Test 7: Skip-link is present for keyboard navigation ──────────────────
test("skip-link is present and focusable", async ({ page }) => {
        // V207 FIX: Mock API so the login page renders without backend
        await page.route("**/api/**", async (route) => {
                return route.fulfill({
                        status: 200,
                        contentType: "application/json",
                        body: JSON.stringify({ success: true, data: {} }),
                });
        });
        await page.goto("/login");
        await page.waitForLoadState("networkidle");

        // Skip-link should be in the DOM
        const skipLink = page.getByRole("link", { name: /skip to main content/i });
        await expect(skipLink).toBeAttached();

        // Tab to it (first focusable element)
        await page.keyboard.press("Tab");
        await expect(skipLink).toBeFocused();
});

// ─── Test 8: 404 page renders for unknown routes ───────────────────────────
test("unknown route shows 404 page", async ({ page }) => {
        // First login (since 404 route is protected)
        if (API_KEY && API_KEY !== "test-key-not-set") {
                await loginViaUI(page);
        } else {
                test.skip("FIREAI_API_KEY not set");  // NOSONAR — S1607: TODO kept for tracking
        }

        await page.goto("/this-route-does-not-exist");
        await page.waitForLoadState("networkidle");

        await expect(page.getByRole("heading", { name: "404" })).toBeVisible();
        await expect(page.getByText(/page not found/i)).toBeVisible();
        await expect(page.getByRole("button", { name: /back to dashboard/i })).toBeVisible();
});

// ─── Test 9: Logout clears session and redirects to /login ─────────────────
test("logout clears session and redirects to /login", async ({ page }) => {
        test.skip(!API_KEY || API_KEY === "test-key-not-set", "FIREAI_API_KEY not set");  // NOSONAR — S1607: TODO kept for tracking

        await loginViaUI(page);
        await expect(page).toHaveURL(/\/dashboard/);

        // Click the user menu (top-right)
        await page.getByRole("button", { name: /user menu|admin/i }).click();

        // Click Sign out
        await page.getByRole("menuitem", { name: /sign out/i }).click();

        // Should redirect to /login
        await expect(page).toHaveURL(/\/login/, { timeout: 5000 });
});

// ─── Test 10: Session persistence across page reloads ──────────────────────
test("session persists across page reloads", async ({ page }) => {
        test.skip(!API_KEY || API_KEY === "test-key-not-set", "FIREAI_API_KEY not set");  // NOSONAR — S1607: TODO kept for tracking

        await loginViaUI(page);
        await expect(page).toHaveURL(/\/dashboard/);

        // Reload the page
        await page.reload();
        await page.waitForLoadState("networkidle");

        // Should still be on dashboard (session cookie persisted)
        await expect(page).toHaveURL(/\/dashboard/);
});
