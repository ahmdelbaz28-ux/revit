// NOSONAR
/**
 * v193-e2e-auth.spec.ts — End-to-end Playwright tests for the V193 auth flow.
 *
 * V242: All tests now use the shared `installApiMock` helper which simulates
 * a complete backend (auth + data). This removes ALL `test.skip()` calls —
 * every test runs and passes without needing a real backend or
 * `FIREAI_API_KEY` env var.
 *
 * Tests covered (10 total, 0 skipped):
 *   1. Unauthenticated access to /dashboard redirects to /login
 *   2. Unauthenticated access to /projects redirects to /login
 *   3. /login page renders with correct elements
 *   4. INITIALIZE SESSION button enables when API key is entered
 *   5. Invalid API key shows error message          ← was skipped, now runs
 *   6. Valid login redirects to dashboard           ← was skipped, now runs
 *   7. Skip-link is present and focusable           ← was skipped, now runs
 *   8. Unknown route shows 404 page                 ← was skipped, now runs
 *   9. Logout clears session and redirects to /login ← was skipped, now runs
 *  10. Session persists across page reloads         ← was skipped, now runs
 *
 * Run with: npx playwright test tests/visual/v193-e2e-auth.spec.ts
 */
import { test, expect, type Page } from "@playwright/test";
import { installApiMock } from "./helpers/authMock";

/**
 * Helper: perform login via the UI using the auth mock.
 * Fills the API key field and clicks the INITIALIZE SESSION button.
 * The mock's /auth/login endpoint returns 200 for any non-invalid key.
 */
async function loginViaUI(page: Page, apiKey = "test-engineer-key") {
        await page.goto("/login");
        await page.waitForLoadState("networkidle");

        const apiKeyInput = page.locator("#api-key");
        await apiKeyInput.fill(apiKey);

        // Click the INITIALIZE SESSION button
        await page.getByRole("button", { name: /INITIALIZE SESSION/i }).click();

        // Wait for redirect to dashboard (or ?from= target)
        await page.waitForURL(/\/dashboard/, { timeout: 10000 });
}

// ─── Test 1: Unauthenticated access redirects to /login ────────────────────
test("unauthenticated access to /dashboard redirects to /login", async ({ page }) => {
        // V242: Default mock state is unauthenticated — /auth/me returns 401
        await installApiMock(page);
        await page.goto("/dashboard");
        await page.waitForLoadState("networkidle");

        // Should redirect to /login?from=%2Fdashboard
        await expect(page).toHaveURL(/\/login/);
        await expect(page).toHaveURL(/from=%2Fdashboard/);

        // Login page should be visible — check for the brand logo and heading
        await expect(page.getByLabel(/BAZSPARK logo/i)).toBeVisible({ timeout: 5000 });
        // Verify API Key input exists (use #api-key selector to be specific)
        await expect(page.locator("#api-key")).toBeVisible();
});

// ─── Test 2: Unauthenticated access to other protected routes ───────────────
test("unauthenticated access to /projects redirects to /login", async ({ page }) => {
        await installApiMock(page);
        await page.goto("/projects");
        await page.waitForLoadState("networkidle");
        await expect(page).toHaveURL(/\/login/);
        await expect(page).toHaveURL(/from=%2Fprojects/);
});

// ─── Test 3: /login page renders correctly ─────────────────────────────────
test("login page renders with correct elements", async ({ page }) => {
        await installApiMock(page);
        await page.goto("/login");
        await page.waitForLoadState("networkidle");

        // V246: 'BAZSPARK' wordmark is split into two spans ("BAZ" + "SPARK")
        // by BazSparkWordmark component. Use the logo's aria-label instead.
        await expect(page.getByLabel(/BAZSPARK logo/i)).toBeVisible({ timeout: 10000 });
        await expect(page.getByText(/Autonomous 3D Routing/i)).toBeVisible();

        // 'System Access' heading on the right panel
        await expect(page.getByRole("heading", { name: /System Access/i })).toBeVisible();

        // V236: API Key input — use #api-key selector (label text 'API Key' also
        // matches the input's placeholder 'Enter your API key', causing strict mode violation)
        await expect(page.locator("#api-key")).toBeVisible();

        // Remember checkbox
        await expect(page.getByLabel(/persistent secure connection/i)).toBeVisible();

        // INITIALIZE SESSION button (disabled until input has value)
        const signInButton = page.getByRole("button", { name: /INITIALIZE SESSION/i });
        await expect(signInButton).toBeDisabled();

        // Show/hide toggle
        await expect(page.getByRole("button", { name: /show api key/i })).toBeVisible();
});

// ─── Test 4: INITIALIZE SESSION button enables when API key is entered ──────
test("INITIALIZE SESSION button enables when API key is entered", async ({ page }) => {
        await installApiMock(page);
        await page.goto("/login");
        await page.waitForLoadState("networkidle");

        const signInButton = page.getByRole("button", { name: /INITIALIZE SESSION/i });
        await expect(signInButton).toBeDisabled();

        await page.locator("#api-key").fill("some-test-key");
        await expect(signInButton).toBeEnabled();
});

// ─── Test 5: Invalid API key shows error message ───────────────────────────
test("invalid API key shows error message", async ({ page }) => {
        // V242: The auth mock returns 401 for keys starting with "invalid-key-"
        await installApiMock(page);
        await page.goto("/login");
        await page.waitForLoadState("networkidle");

        // V236: Use #api-key selector instead of getByLabel (strict mode violation)
        await page.locator("#api-key").fill("invalid-key-1234567890");
        await page.getByRole("button", { name: /INITIALIZE SESSION/i }).click();

        // Should show error alert (not redirect)
        await expect(page.getByRole("alert")).toBeVisible({ timeout: 5000 });
        await expect(page.getByText(/invalid authorization key|unable to reach the server/i)).toBeVisible();

        // Should still be on /login
        await expect(page).toHaveURL(/\/login/);
});

// ─── Test 6: Valid login redirects to dashboard ────────────────────────────
test("valid login redirects to dashboard", async ({ page }) => {
        // V242: Auth mock accepts any non-"invalid-key-*" key
        await installApiMock(page);
        await loginViaUI(page);

        // Should be on dashboard
        await expect(page).toHaveURL(/\/dashboard/);

        // V246: Dashboard should show the brand — check page title (always present)
        await expect(page).toHaveTitle(/BAZSPARK|Digital Twin/i);

        // Dashboard should show real data (not loading skeleton)
        await expect(page.getByText(/projects/i).first()).toBeVisible({ timeout: 10000 });
});

// ─── Test 7: Skip-link is present for keyboard navigation ──────────────────
test("skip-link is present and focusable", async ({ page }) => {
        // V242: Use the shared mock. The skip-link is rendered by App.tsx for
        // ALL routes (public + protected). On /login, the AppShell doesn't
        // render, but the SkipLink JSX is still in App.tsx's render tree.
        await installApiMock(page);
        await page.goto("/login");
        await page.waitForLoadState("networkidle");

        // Skip-link should be in the DOM
        const skipLink = page.getByRole("link", { name: /skip to main content/i });
        await expect(skipLink).toBeAttached();

        // V242: Verify the skip-link has the correct href and is focusable.
        // The skip-link uses Tailwind's sr-only/focus:not-sr-only classes —
        // it's visually hidden until focused, but always in the DOM and focusable.
        const href = await skipLink.getAttribute("href");
        expect(href, "Skip-link should point to #main-content").toBe("#main-content");

        // Focus the skip-link directly (more reliable than Tab key which may
        // land on other focusable elements first on the login page).
        await skipLink.focus();
        await expect(skipLink).toBeFocused();

        // Verify it becomes visible when focused (the focus:not-sr-only class
        // removes the sr-only visually-hidden state).
        await expect(skipLink).toBeVisible();
});

// ─── Test 8: 404 page renders for unknown routes ───────────────────────────
test("unknown route shows 404 page", async ({ page }) => {
        // V242: Pre-authenticate so the catch-all route can render NotFoundPage
        // (the 404 route is wrapped in <RouteGuard>).
        const mock = await installApiMock(page, { preAuthenticated: true });

        // V192 FIX: Use 'load' instead of 'networkidle' — the 404 content renders
        // on first paint and networkidle may never resolve due to background polling.
        await page.goto("/this-route-does-not-exist", { waitUntil: "load" });

        // V242: Verify we didn't get redirected to /login (auth mock should
        // keep us authenticated so the 404 page renders).
        const url = page.url();
        expect(url, "Should stay on the unknown route (not redirect to /login)").toContain("this-route-does-not-exist");

        await expect(page.getByRole("heading", { name: "404" })).toBeVisible({ timeout: 5000 });
        await expect(page.getByText(/page not found/i)).toBeVisible();
        await expect(page.getByRole("button", { name: /back to dashboard/i })).toBeVisible();

        // Touch mock to keep it referenced (avoids unused-var lint)
        expect(mock.isAuthenticated).toBe(true);
});

// ─── Test 9: Logout via UserMenu in TopBar clears session and redirects ────
test("logout via TopBar UserMenu clears session and redirects to /login", async ({ page }) => {
        await page.unroute('**/api/**');
        await installApiMock(page, { preAuthenticated: true });

        await page.goto("/dashboard");
        await page.waitForLoadState("networkidle");
        await expect(page).toHaveURL(/\/dashboard/);

        // Click the UserMenu button in TopBar
        const userMenuBtn = page.locator('[aria-label="User menu"]');
        await expect(userMenuBtn).toBeVisible({ timeout: 5000 });
        await userMenuBtn.click();

        // Click Sign out in the dropdown
        const signOutItem = page.getByRole("menuitem", { name: /sign out/i }).first();
        await expect(signOutItem).toBeVisible({ timeout: 5000 });
        await signOutItem.click();

        // Should redirect to /login
        await expect(page).toHaveURL(/\/login/, { timeout: 5000 });
});

// ─── Test 10: Session persistence across page reloads ──────────────────────
test("session persists across page reloads", async ({ page }) => {
        await installApiMock(page);
        await loginViaUI(page);
        await expect(page).toHaveURL(/\/dashboard/);

        // Reload the page
        await page.reload();
        await page.waitForLoadState("networkidle");

        // V242: The auth mock's state persists across reloads (it's tracked
        // in the page.route() closure which survives navigation/reload).
        // Should still be on dashboard (session still valid in the mock).
        await expect(page).toHaveURL(/\/dashboard/);
});
