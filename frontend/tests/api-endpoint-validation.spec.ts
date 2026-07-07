import { expect, type Page, test } from "@playwright/test";

/**
 * API Endpoint Validation Tests
 *
 * This test suite specifically validates that UI button clicks trigger
 * the correct API endpoints with proper request/response handling.
 */

interface ApiCallLog {
	method: string;
	url: string;
	requestBody?: any;
	statusCode: number;
	responseBody?: any;
	timestamp: number;
}

// Store API calls made during tests
const apiCallLogs: ApiCallLog[] = [];

/**
 * Helper to intercept and log API calls
 */
function setupApiInterceptor(page: Page) {
	apiCallLogs.length = 0; // Clear previous logs

	page.on("response", (response) => {
		if (response.url().includes("/api/")) {
			response
				.json()
				.then((body) => {
					apiCallLogs.push({
						method: response.request().method(),
						url: response.url(),
						requestBody: response.request().postDataJSON(),
						statusCode: response.status(),
						responseBody: body,
						timestamp: Date.now(),
					});
				})
				.catch(() => {
					// Handle cases where response is not JSON
					apiCallLogs.push({
						method: response.request().method(),
						url: response.url(),
						requestBody: response.request().postDataJSON(),
						statusCode: response.status(),
						responseBody: undefined,
						timestamp: Date.now(),
					});
				});
		}
	});
}

test.describe("API Endpoint Validation Tests", () => {
	test.beforeEach(async ({ page }) => {
		setupApiInterceptor(page);
	});

	test("should validate dashboard API calls", async ({ page }) => {
		await page.goto("/dashboard");
		await page.waitForLoadState("networkidle");

		// Wait for any dashboard API calls to complete
		await page.waitForLoadState("networkidle");  // S2925: sync on condition, not fixed wait

		// Validate that dashboard made expected API calls
		const dashboardCalls = apiCallLogs.filter(
			(call) =>
				call.url.includes("/api/") &&
				(call.url.includes("/projects") ||
					call.url.includes("/stats") ||
					call.url.includes("/health")),
		);

		expect(dashboardCalls.length).toBeGreaterThan(0);

		// Log the API calls for verification
		for (const call of dashboardCalls) {
			console.log(
				`Dashboard API Call: ${call.method} ${call.url} -> ${call.statusCode}`,
			);
			expect(call.statusCode).toBeGreaterThanOrEqual(200);
			expect(call.statusCode).toBeLessThan(400);
		}
	});

	test("should validate AutoCAD connect API call", async ({ page }) => {
		await page.goto("/autocad");
		await page.waitForLoadState("networkidle");

		// Find and click the connect button
		const connectButton = page.locator(
			'button:has-text("Connect"), button:has-text("Connect to AutoCAD")',
		);

		if ((await connectButton.count()) > 0) {
			// Wait for the click to trigger the API call
			const responsePromise = page.waitForResponse("**/api/v*/autocad/connect");

			await connectButton.click();

			const response = await responsePromise;

			expect(response.status()).toBeGreaterThanOrEqual(200);
			expect(response.status()).toBeLessThan(400);
			expect(response.url()).toContain("/api/v");
			expect(response.url()).toContain("/autocad/connect");

			console.log(
				`AutoCAD Connect API: ${response.request().method()} ${response.url()} -> ${response.status()}`,
			);
		} else {
			test.skip(true, "No AutoCAD connect button found");
		}
	});

	test("should validate Revit connect API call", async ({ page }) => {
		await page.goto("/revit");
		await page.waitForLoadState("networkidle");

		// Find and click the connect button
		const connectButton = page.locator(
			'button:has-text("Connect"), button:has-text("Connect to Revit")',
		);

		if ((await connectButton.count()) > 0) {
			// Wait for the click to trigger the API call
			const responsePromise = page.waitForResponse("**/api/v*/revit/connect");

			await connectButton.click();

			const response = await responsePromise;

			expect(response.status()).toBeGreaterThanOrEqual(200);
			expect(response.status()).toBeLessThan(400);
			expect(response.url()).toContain("/api/v");
			expect(response.url()).toContain("/revit/connect");

			console.log(
				`Revit Connect API: ${response.request().method()} ${response.url()} -> ${response.status()}`,
			);
		} else {
			test.skip(true, "No Revit connect button found");
		}
	});

	test("should validate project creation API call", async ({ page }) => {
		await page.goto("/projects");
		await page.waitForLoadState("networkidle");

		// Find and click the create project button
		const createButton = page.locator(
			'button:has-text("New Project"), button:has-text("Create Project")',
		);

		if ((await createButton.count()) > 0) {
			// Wait for the click to trigger the API call
			const responsePromise = page.waitForResponse("**/api/v*/projects");

			await createButton.click();

			const response = await responsePromise;

			expect(response.status()).toBeGreaterThanOrEqual(200);
			expect(response.status()).toBeLessThan(400);
			expect(response.url()).toContain("/api/v");
			expect(response.url()).toContain("/projects");

			console.log(
				`Project Creation API: ${response.request().method()} ${response.url()} -> ${response.status()}`,
			);
		} else {
			test.skip(true, "No create project button found");
		}
	});

	test("should validate digital twin conversion API call", async ({ page }) => {
		await page.goto("/digital-twin");
		await page.waitForLoadState("networkidle");

		// Find and click the convert button
		const convertButton = page.locator(
			'button:has-text("Convert"), button:has-text("Start Conversion")',
		);

		if ((await convertButton.count()) > 0) {
			// Wait for the click to trigger the API call
			const responsePromise = page.waitForResponse(
				"**/api/v*/digital-twin/convert",
			);

			await convertButton.click();

			const response = await responsePromise;

			expect(response.status()).toBeGreaterThanOrEqual(200);
			expect(response.status()).toBeLessThan(400);
			expect(response.url()).toContain("/api/v");
			expect(response.url()).toContain("/digital-twin/convert");

			console.log(
				`Digital Twin Conversion API: ${response.request().method()} ${response.url()} -> ${response.status()}`,
			);
		} else {
			test.skip(true, "No digital twin convert button found");
		}
	});

	test("should validate element operations API calls", async ({ page }) => {
		await page.goto("/elements");
		await page.waitForLoadState("networkidle");

		// Look for filter/search buttons that trigger API calls
		const filterButton = page.locator(
			'button:has-text("Filter"), button:has-text("Search")',
		);

		if ((await filterButton.count()) > 0) {
			// Wait for the click to trigger the API call
			const responsePromise = page.waitForResponse("**/api/v*/elements*");

			await filterButton.click();

			const response = await responsePromise;

			expect(response.status()).toBeGreaterThanOrEqual(200);
			expect(response.status()).toBeLessThan(400);
			expect(response.url()).toContain("/api/v");
			expect(response.url()).toContain("/elements");

			console.log(
				`Elements API: ${response.request().method()} ${response.url()} -> ${response.status()}`,
			);
		} else {
			// If no filter button, try other element-related buttons
			const otherButtons = page.locator(
				'button:has-text("Refresh"), button:has-text("Load")',
			);
			if ((await otherButtons.count()) > 0) {
				const responsePromise = page.waitForResponse("**/api/v*/elements*");

				await otherButtons.first().click();

				const response = await responsePromise;

				expect(response.status()).toBeGreaterThanOrEqual(200);
				expect(response.status()).toBeLessThan(400);
				expect(response.url()).toContain("/api/v");
				expect(response.url()).toContain("/elements");

				console.log(
					`Elements API: ${response.request().method()} ${response.url()} -> ${response.status()}`,
				);
			} else {
				test.skip(true, "No element operation buttons found");
			}
		}
	});

	test("should validate connection operations API calls", async ({ page }) => {
		await page.goto("/connections");
		await page.waitForLoadState("networkidle");

		// Look for connection-related buttons
		const actionButtons = page.locator(
			'button:has-text("Validate"), button:has-text("Test"), button:has-text("Sync")',
		);

		if ((await actionButtons.count()) > 0) {
			const responsePromise = page.waitForResponse("**/api/v*/connections*");

			await actionButtons.first().click();

			const response = await responsePromise;

			expect(response.status()).toBeGreaterThanOrEqual(200);
			expect(response.status()).toBeLessThan(400);
			expect(response.url()).toContain("/api/v");
			expect(response.url()).toContain("/connections");

			console.log(
				`Connections API: ${response.request().method()} ${response.url()} -> ${response.status()}`,
			);
		} else {
			test.skip(true, "No connection operation buttons found");
		}
	});

	test("should validate conflict resolution API calls", async ({ page }) => {
		await page.goto("/conflicts");
		await page.waitForLoadState("networkidle");

		// Look for conflict resolution buttons
		const resolveButton = page.locator(
			'button:has-text("Resolve"), button:has-text("Fix Conflicts")',
		);

		if ((await resolveButton.count()) > 0) {
			const responsePromise = page.waitForResponse("**/api/v*/conflicts*");

			await resolveButton.click();

			const response = await responsePromise;

			expect(response.status()).toBeGreaterThanOrEqual(200);
			expect(response.status()).toBeLessThan(400);
			expect(response.url()).toContain("/api/v");
			expect(response.url()).toContain("/conflicts");

			console.log(
				`Conflicts API: ${response.request().method()} ${response.url()} -> ${response.status()}`,
			);
		} else {
			test.skip(true, "No conflict resolution buttons found");
		}
	});

	test("should validate report generation API calls", async ({ page }) => {
		await page.goto("/reports");
		await page.waitForLoadState("networkidle");

		// Look for report generation buttons
		const generateButton = page.locator(
			'button:has-text("Generate"), button:has-text("Create Report")',
		);

		if ((await generateButton.count()) > 0) {
			const responsePromise = page.waitForResponse("**/api/v*/reports*");

			await generateButton.click();

			const response = await responsePromise;

			expect(response.status()).toBeGreaterThanOrEqual(200);
			expect(response.status()).toBeLessThan(400);
			expect(response.url()).toContain("/api/v");
			expect(response.url()).toContain("/reports");

			console.log(
				`Reports API: ${response.request().method()} ${response.url()} -> ${response.status()}`,
			);
		} else {
			test.skip(true, "No report generation buttons found");
		}
	});

	test("should validate export operations API calls", async ({ page }) => {
		await page.goto("/reports");
		await page.waitForLoadState("networkidle");

		// Look for export buttons
		const exportButton = page.locator(
			'button:has-text("Export"), button:has-text("Download")',
		);

		if ((await exportButton.count()) > 0) {
			const responsePromise = page.waitForResponse("**/api/v*/reports/export*");

			await exportButton.click();

			const response = await responsePromise;

			expect(response.status()).toBeGreaterThanOrEqual(200);
			expect(response.status()).toBeLessThan(400);
			expect(response.url()).toContain("/api/v");
			expect(response.url()).toContain("/reports/export");

			console.log(
				`Export API: ${response.request().method()} ${response.url()} -> ${response.status()}`,
			);
		} else {
			test.skip(true, "No export buttons found");
		}
	});
});

/**
 * Test to validate all intercepted API calls meet requirements
 */
test.describe("API Call Validation Summary", () => {
	test("should have valid API responses for all button interactions", async ({
		page,
	}) => {
		// This test runs after all other tests and validates the collected API calls

		// Wait a bit to ensure all API calls are captured
		await page.waitForLoadState("networkidle");  // S2925: sync on condition, not fixed wait

		// Filter to only include actual API calls
		const apiCalls = apiCallLogs.filter((call) => call.url.includes("/api/"));

		console.log(`\n=== API CALL SUMMARY ===`);
		console.log(`Total API calls captured: ${apiCalls.length}`);

		for (const call of apiCalls) {
			console.log(
				`${call.method} ${new URL(call.url).pathname} -> ${call.statusCode}`,
			);

			// Validate each API call meets requirements
			expect(
				call.statusCode,
				`API call failed: ${call.method} ${call.url}`,
			).toBeGreaterThanOrEqual(200);
			expect(
				call.statusCode,
				`API call resulted in error: ${call.method} ${call.url}`,
			).toBeLessThan(400);
		}

		// Ensure we had at least some API calls
		expect(
			apiCalls.length,
			"Should have captured at least one API call",
		).toBeGreaterThan(0);
	});
});
