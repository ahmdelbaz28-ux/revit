// NOSONAR
/**
 * ETAP Integration Page — Visual Smoke Test.
 *
 * Tests that the ETAP page loads correctly with all tabs and forms.
 */
import { expect, test } from "@playwright/test";
import { installApiMock } from "./helpers/authMock";

async function mockEtapApiResponses(page: import("@playwright/test").Page) {
        await page.route("**/api/v1/integrations/etap/**", async (route) => {
                const url = route.request().url();
                const method = route.request().method();

                if (url.includes("/status")) {
                        return route.fulfill({
                                status: 200,
                                contentType: "application/json",
                                body: JSON.stringify({ success: true, data: { enabled: false, configured: false, last_sync: null } }),
                        });
                }

                if (url.includes("/projects") && method === "GET") {
                        return route.fulfill({
                                status: 200,
                                contentType: "application/json",
                                body: JSON.stringify({
                                        success: true,
                                        data: [
                                                { project_id: "etap-1", name: "Fire Alarm System v2", modified_at: "2026-07-20T10:00:00Z", size_mb: 12.5, is_remote: true },
                                                { project_id: "etap-2", name: "Building Power Distribution", modified_at: "2026-07-19T15:30:00Z", size_mb: 8.3, is_remote: true },
                                        ],
                                }),
                        });
                }

                if (url.includes("/projects/local") && method === "GET") {
                        return route.fulfill({
                                status: 200,
                                contentType: "application/json",
                                body: JSON.stringify({
                                        success: true,
                                        data: [{ id: "default", name: "Default Project", status: "active" }],
                                }),
                        });
                }

                if (url.includes("/settings") && method === "GET") {
                        return route.fulfill({
                                status: 200,
                                contentType: "application/json",
                                body: JSON.stringify({
                                        success: true,
                                        data: { id: "settings-1", project_id: "default", host: "", port: 9876, username: "", enabled: false, created_at: "", updated_at: "" },
                                }),
                        });
                }

                if (url.includes("/settings") && method === "POST") {
                        return route.fulfill({
                                status: 200,
                                contentType: "application/json",
                                body: JSON.stringify({ success: true, data: { id: "settings-1", project_id: "default", host: "etap.example.com", port: 9876, username: "admin", enabled: false, created_at: "", updated_at: "" } }),
                        });
                }

                if (url.includes("/logs") && method === "GET") {
                        return route.fulfill({
                                status: 200,
                                contentType: "application/json",
                                body: JSON.stringify({ success: true, data: { items: [], total: 0, page: 1, page_size: 50 } }),
                        });
                }

                if (url.includes("/connect") && method === "POST") {
                        return route.fulfill({
                                status: 200,
                                contentType: "application/json",
                                body: JSON.stringify({ success: true, data: { success: true, message: "Connection successful", latency_ms: 42, server_version: "ETAP 2024.1" } }),
                        });
                }

                if (url.includes("/export") && method === "POST") {
                        return route.fulfill({
                                status: 200,
                                contentType: "application/json",
                                body: JSON.stringify({ success: true, data: { project_id: "default", format: "csv", loads_csv: "Bus,Load_Name,Type,kW,pf,Category\n", sources_csv: "Source,Type,kV,kVA,X_R\n", records_exported: 2 } }),
                        });
                }

                if (url.includes("/import") && method === "POST") {
                        return route.fulfill({
                                status: 200,
                                contentType: "application/json",
                                body: JSON.stringify({ success: true, data: { project_id: "default", etap_project_id: "etap-1", records_imported: 0, message: "Import completed" } }),
                        });
                }

                return route.fulfill({
                        status: 200,
                        contentType: "application/json",
                        body: JSON.stringify({ success: true, data: {} }),
                });
        });
}

test.describe("ETAP Integration Page", () => {
        test.beforeEach(async ({ page }) => {
                await installApiMock(page, { preAuthenticated: true });
        });

        test("ETAP page loads without console errors", async ({ page }) => {
                await mockEtapApiResponses(page);
                const errors: string[] = [];
                page.on("console", (msg) => {
                        if (msg.type() === "error") {
                                errors.push(msg.text());
                        }
                });

                await page.goto("/etap");
                await page.waitForSelector("h1", { timeout: 15000 });

                // Check for critical UI elements — use getByRole for unique heading
                await expect(page.getByRole("heading", { name: "ETAP Integration" })).toBeVisible();
                await expect(page.getByRole("button", { name: "Test Connection" })).toBeVisible();

                // Filter out known non-critical errors
                const criticalErrors = errors.filter(
                        (e) => !e.includes("frame-ancestors") && !e.includes("X-Frame-Options") && !e.includes("Applying inline style violates"),
                );
                expect(criticalErrors).toEqual([]);
        });

        test("ETAP page has visible connection form", async ({ page }) => {
                await mockEtapApiResponses(page);
                await page.goto("/etap");
                await page.waitForSelector("h1", { timeout: 15000 });

                // Connection tab should be active by default
                await expect(page.locator("text=Connection Settings")).toBeVisible();
                await expect(page.locator("#host")).toBeVisible();
                await expect(page.locator("#port")).toBeVisible();
                await expect(page.locator("#username")).toBeVisible();
                await expect(page.locator("#password")).toBeVisible();
        });

        test("ETAP page has tabs for Connection, Projects, Sync, Logs", async ({ page }) => {
                await mockEtapApiResponses(page);
                await page.goto("/etap");
                await page.waitForSelector("h1", { timeout: 15000 });

                await expect(page.locator("text=Connection")).toBeVisible();
                await expect(page.locator("text=Projects")).toBeVisible();
                await expect(page.locator("text=Synchronization")).toBeVisible();
                await expect(page.locator("text=Sync Logs")).toBeVisible();
        });

        test("ETAP page shows connection status badge", async ({ page }) => {
                await mockEtapApiResponses(page);
                await page.goto("/etap");
                await page.waitForSelector("h1", { timeout: 15000 });

                // Should show disconnected status by default
                await expect(page.locator("text=Disconnected")).toBeVisible();
        });

        test("ETAP page has export and import forms in Sync tab", async ({ page }) => {
                await mockEtapApiResponses(page);
                await page.goto("/etap");
                await page.waitForSelector("h1", { timeout: 15000 });

                // Switch to Sync tab
                await page.click("text=Synchronization");
                await expect(page.locator("text=Export to ETAP")).toBeVisible();
                await expect(page.locator("text=Import from ETAP")).toBeVisible();
        });

        test("ETAP page logs tab shows no logs message when empty", async ({ page }) => {
                await mockEtapApiResponses(page);
                await page.goto("/etap");
                await page.waitForSelector("h1", { timeout: 15000 });

                // Switch to Logs tab
                await page.click("text=Sync Logs");
                await expect(page.locator("text=No sync logs available")).toBeVisible();
        });
});
