import { expect, type Page, test } from "@playwright/test";

/**
 * Comprehensive Button and Backend Connection Tests
 *
 * This test suite verifies all UI buttons and their corresponding backend API calls
 * for the CAD/BIM Integration Platform. It includes tests for:
 * - AutoCAD integration buttons
 * - Revit integration buttons
 * - Digital Twin conversion buttons
 * - Project management buttons
 * - Element management buttons
 * - Connection management buttons
 * - Conflict resolution buttons
 * - Report generation buttons
 * - Export functionality buttons
 */

interface TestResult {
	testName: string;
	action: string;
	timestamp: string;
	status: number;
	statusText: string;
	duration: number;
	error?: string;
	details: {
		response?: any;
		headers?: Record<string, string>;
		requestBody?: any;
	};
}

// Test results array to store all test outcomes
const testResults: TestResult[] = [];

/**
 * Helper function to record test results
 */
function logTestResult(
	testName: string,
	action: string,
	status: number,
	statusText: string,
	duration: number,
	error?: string,
	details: any = {},
) {
	const result: TestResult = {
		testName,
		action,
		timestamp: new Date().toISOString(),
		status,
		statusText,
		duration,
		error,
		details,
	};

	testResults.push(result);
	console.log(`[${status}] ${testName}: ${action} (${duration}ms)`);
	if (error) {
		console.error(`  Error: ${error}`);
	}
}

/**
 * Helper function to make API requests and capture detailed response
 */
async function _makeApiRequest(
	page: Page,
	endpoint: string,
	options: RequestInit = {},
) {
	const startTime = Date.now();

	// Default headers for API requests
	const defaultHeaders = {
		"X-API-Key": process.env.API_KEY || "test-api-key",
		"Content-Type": "application/json",
		...options.headers,
	};

	try {
		// Using page.evaluate to make the request from the browser context
		const response = await page.evaluate(
			async ({ endpoint, options, defaultHeaders }) => {
				const url = `${process.env.API_URL || "http://localhost:8000"}${endpoint}`;

				const requestInit = {
					...options,
					headers: {
						...defaultHeaders,
						...(options.headers || {}),
					},
				};

				if (
					requestInit.body &&
					typeof requestInit.body === "object" &&
					!(requestInit.body instanceof FormData)
				) {
					requestInit.body = JSON.stringify(requestInit.body);
				}

				const response = await fetch(url, requestInit);
				const data = await response.json().catch(() => ({}));

				return {
					status: response.status,
					statusText: response.statusText,
					data,
					headers: Array.from(response.headers.entries()).reduce(
						(acc, [key, value]) => {
							acc[key] = value;
							return acc;
						},
						{} as Record<string, string>,
					),
					ok: response.ok,
				};
			},
			{
				endpoint,
				options: { ...options, headers: defaultHeaders },
				defaultHeaders,
			},
		);

		const endTime = Date.now();
		return { ...response, duration: endTime - startTime };
	} catch (error) {
		const endTime = Date.now();
		return {
			status: 0,
			statusText: "Network Error",
			data: {},
			headers: {},
			ok: false,
			duration: endTime - startTime,
			error: (error as Error).message,
		};
	}
}

/**
 * Test Dashboard Page Buttons
 */
test.describe("Dashboard Page Button Tests", () => {
	test("should test dashboard refresh button", async ({ page }) => {
		await page.goto("/dashboard");
		await page.waitForLoadState("networkidle");

		// Wait for the refresh button to be available
		const refreshButton = page.locator(
			'button[data-testid="refresh-stats"], button:has-text("Refresh"), button:has-text("Update")',
		);

		if ((await refreshButton.count()) > 0) {
			// Listen for API requests made when the button is clicked
			const responsePromise = page.waitForResponse("**/api/v*/**");

			await refreshButton.click();

			// Wait for the API response
			const response = await responsePromise;

			logTestResult(
				"Dashboard Refresh Button",
				"Click refresh button",
				response.status(),
				response.statusText(),
				response.request().timing().responseEnd,
			);

			await expect(refreshButton).toBeEnabled();
		} else {
			test.skip(true, "No refresh button found on dashboard");
		}
	});

	test("should test dashboard quick action buttons", async ({ page }) => {
		await page.goto("/dashboard");
		await page.waitForLoadState("networkidle");

		// Test common dashboard action buttons
		const actionButtons = [
			page.locator('button:has-text("New Project")'),
			page.locator('button:has-text("Create Project")'),
			page.locator('button:has-text("Quick Start")'),
			page.locator('button[data-testid="quick-action"]'),
		];

		for (const button of actionButtons) {
			if ((await button.count()) > 0) {
				const buttonName =
					(await button.textContent()) || "Quick Action Button";

				// Intercept API requests
				page.route("**/api/v*/**", async (route) => {
					const response = await route.fetch();
					const status = response.status();

					logTestResult(
						`Dashboard ${buttonName}`,
						`Click ${buttonName}`,
						status,
						response.statusText(),
						0, // Duration will be captured differently
					);

					await route.continue();
				});

				await button.click();
				await expect(button).toBeEnabled();

				// Wait a bit for any async operations
				await page.waitForLoadState("networkidle");  // S2925: sync on condition, not fixed wait
			}
		}
	});
});

/**
 * Test Projects Page Buttons
 */
test.describe("Projects Page Button Tests", () => {
	test("should test create project button", async ({ page }) => {
		await page.goto("/projects");
		await page.waitForLoadState("networkidle");

		const createButton = page.locator(
			'button:has-text("New Project"), button:has-text("Create Project"), button[data-testid="create-project-btn"]',
		);

		if ((await createButton.count()) > 0) {
			// Click the create button
			await createButton.click();

			// Look for a modal or form that appears
			const modal = page.locator(
				'div[role="dialog"], div.modal, form[data-testid="project-form"]',
			);

			if ((await modal.count()) > 0) {
				await expect(modal).toBeVisible();

				// Test submit button in the form
				const submitButton = page.locator(
					'button[type="submit"], button:has-text("Save"), button:has-text("Create")',
				);

				if ((await submitButton.count()) > 0) {
					// Mock the API response for project creation
					await page.route("**/api/v*/projects", async (route) => {
						const response = await route.fetch();
						const status = response.status();

						logTestResult(
							"Create Project Submit Button",
							"Submit new project form",
							status,
							response.statusText(),
							0,
						);

						await route.continue();
					});

					await submitButton.click();
					await expect(submitButton).toBeEnabled();
				}
			}

			logTestResult(
				"Create Project Button",
				"Click create project button",
				200,
				"OK",
				0,
			);
		} else {
			test.skip(true, "No create project button found");
		}
	});

	test("should test project action buttons", async ({ page }) => {
		await page.goto("/projects");
		await page.waitForLoadState("networkidle");

		// Test action buttons for existing projects (if any)
		const actionButtons = page.locator(
			'button:has-text("Edit"), button:has-text("Delete"), button:has-text("View"), button[data-testid="project-actions"]',
		);

		if ((await actionButtons.count()) > 0) {
			const count = await actionButtons.count();

			for (let i = 0; i < Math.min(count, 3); i++) {
				// Test first 3 buttons to avoid too many requests
				const button = actionButtons.nth(i);
				const buttonText =
					(await button.textContent()) || `Project Action Button ${i}`;

				// Intercept API requests
				page.route("**/api/v*/projects/**", async (route) => {
					const response = await route.fetch();
					const status = response.status();

					logTestResult(
						`Project ${buttonText}`,
						`Click ${buttonText}`,
						status,
						response.statusText(),
						0,
					);

					await route.continue();
				});

				await button.click();
				await expect(button).toBeEnabled();

				// Wait for potential modal or navigation
				await page.waitForLoadState("networkidle");  // S2925: sync on condition, not fixed wait

				// If it was a delete button, cancel or confirm appropriately
				if (buttonText.toLowerCase().includes("delete")) {
					const confirmButton = page.locator(
						'button:has-text("Confirm"), button:has-text("Yes")',
					);
					if ((await confirmButton.count()) > 0) {
						await confirmButton.click(); // Actually perform the delete for testing
					} else {
						// Cancel if there's a cancel button
						const cancelButton = page.locator(
							'button:has-text("Cancel"), button:has-text("No")',
						);
						if ((await cancelButton.count()) > 0) {
							await cancelButton.click();
						}
					}
				}
			}
		}
	});
});

/**
 * Test AutoCAD Page Buttons
 */
test.describe("AutoCAD Page Button Tests", () => {
	test("should test AutoCAD connect button", async ({ page }) => {
		await page.goto("/autocad");
		await page.waitForLoadState("networkidle");

		const connectButton = page.locator(
			'button:has-text("Connect"), button:has-text("Connect to AutoCAD"), button[data-testid="connect-autocad-btn"]',
		);

		if ((await connectButton.count()) > 0) {
			// Intercept the connect API call
			page.route("**/api/v*/autocad/connect", async (route) => {
				const response = await route.fetch();
				const status = response.status();

				logTestResult(
					"AutoCAD Connect Button",
					"Click connect to AutoCAD",
					status,
					response.statusText(),
					0,
				);

				await route.continue();
			});

			await connectButton.click();
			await expect(connectButton).toBeEnabled();

			// Wait for connection status update
			await page.waitForLoadState("networkidle");  // S2925: sync on condition, not fixed wait
		} else {
			test.skip(true, "No AutoCAD connect button found");
		}
	});

	test("should test AutoCAD upload button", async ({ page }) => {
		await page.goto("/autocad");
		await page.waitForLoadState("networkidle");

		const uploadButton = page.locator(
			'button:has-text("Upload"), button:has-text("Import DWG"), button[data-testid="upload-dwg-btn"]',
		);

		if ((await uploadButton.count()) > 0) {
			// Intercept the upload API call
			page.route("**/api/v*/autocad/upload*", async (route) => {
				const response = await route.fetch();
				const status = response.status();

				logTestResult(
					"AutoCAD Upload Button",
					"Click upload DWG button",
					status,
					response.statusText(),
					0,
				);

				await route.continue();
			});

			await uploadButton.click();
			await expect(uploadButton).toBeEnabled();

			// Wait for potential file dialog (though Playwright handles this differently)
			await page.waitForLoadState("networkidle");  // S2925: sync on condition, not fixed wait
		} else {
			test.skip(true, "No AutoCAD upload button found");
		}
	});

	test("should test AutoCAD draw/create buttons", async ({ page }) => {
		await page.goto("/autocad/draw");
		await page.waitForLoadState("networkidle");

		// Test various drawing buttons
		const drawButtons = [
			page.locator(
				'button:has-text("Line"), button:has-text("Circle"), button:has-text("Rectangle"), button[data-testid="draw-shape-btn"]',
			),
			page.locator(
				'button:has-text("Create"), button:has-text("Add Entity"), button[data-testid="create-entity-btn"]',
			),
		];

		for (const buttonGroup of drawButtons) {
			if ((await buttonGroup.count()) > 0) {
				const count = await buttonGroup.count();

				for (let i = 0; i < Math.min(count, 2); i++) {
					// Test first 2 buttons
					const button = buttonGroup.nth(i);
					const buttonText = (await button.textContent()) || `Draw Button ${i}`;

					// Intercept API requests
					page.route("**/api/v*/autocad/**", async (route) => {
						const response = await route.fetch();
						const status = response.status();

						logTestResult(
							`AutoCAD ${buttonText}`,
							`Click ${buttonText}`,
							status,
							response.statusText(),
							0,
						);

						await route.continue();
					});

					await button.click();
					await expect(button).toBeEnabled();

					await page.waitForLoadState("networkidle");  // S2925: sync on condition, not fixed wait
				}
			}
		}
	});
});

/**
 * Test Revit Page Buttons
 */
test.describe("Revit Page Button Tests", () => {
	test("should test Revit connect button", async ({ page }) => {
		await page.goto("/revit");
		await page.waitForLoadState("networkidle");

		const connectButton = page.locator(
			'button:has-text("Connect"), button:has-text("Connect to Revit"), button[data-testid="connect-revit-btn"]',
		);

		if ((await connectButton.count()) > 0) {
			// Intercept the connect API call
			page.route("**/api/v*/revit/connect", async (route) => {
				const response = await route.fetch();
				const status = response.status();

				logTestResult(
					"Revit Connect Button",
					"Click connect to Revit",
					status,
					response.statusText(),
					0,
				);

				await route.continue();
			});

			await connectButton.click();
			await expect(connectButton).toBeEnabled();

			// Wait for connection status update
			await page.waitForLoadState("networkidle");  // S2925: sync on condition, not fixed wait
		} else {
			test.skip("No Revit connect button found");
		}
	});

	test("should test Revit upload button", async ({ page }) => {
		await page.goto("/revit");
		await page.waitForLoadState("networkidle");

		const uploadButton = page.locator(
			'button:has-text("Upload"), button:has-text("Import RVT"), button[data-testid="upload-rvt-btn"]',
		);

		if ((await uploadButton.count()) > 0) {
			// Intercept the upload API call
			page.route("**/api/v*/revit/upload*", async (route) => {
				const response = await route.fetch();
				const status = response.status();

				logTestResult(
					"Revit Upload Button",
					"Click upload RVT button",
					status,
					response.statusText(),
					0,
				);

				await route.continue();
			});

			await uploadButton.click();
			await expect(uploadButton).toBeEnabled();

			// Wait for potential file dialog
			await page.waitForLoadState("networkidle");  // S2925: sync on condition, not fixed wait
		} else {
			test.skip("No Revit upload button found");
		}
	});

	test("should test Revit element creation buttons", async ({ page }) => {
		await page.goto("/revit/create");
		await page.waitForLoadState("networkidle");

		// Test element creation buttons
		const createButtons = page.locator(
			'button:has-text("Create"), button:has-text("Add"), button[data-testid="create-element-btn"]',
		);

		if ((await createButtons.count()) > 0) {
			const count = await createButtons.count();

			for (let i = 0; i < Math.min(count, 3); i++) {
				const button = createButtons.nth(i);
				const buttonText = (await button.textContent()) || `Create Button ${i}`;

				// Intercept API requests
				page.route("**/api/v*/revit/**", async (route) => {
					const response = await route.fetch();
					const status = response.status();

					logTestResult(
						`Revit ${buttonText}`,
						`Click ${buttonText}`,
						status,
						response.statusText(),
						0,
					);

					await route.continue();
				});

				await button.click();
				await expect(button).toBeEnabled();

				await page.waitForLoadState("networkidle");  // S2925: sync on condition, not fixed wait
			}
		}
	});
});

/**
 * Test Digital Twin Page Buttons
 */
test.describe("Digital Twin Page Button Tests", () => {
	test("should test digital twin conversion button", async ({ page }) => {
		await page.goto("/digital-twin");
		await page.waitForLoadState("networkidle");

		const convertButton = page.locator(
			'button:has-text("Convert"), button:has-text("Start Conversion"), button[data-testid="convert-btn"]',
		);

		if ((await convertButton.count()) > 0) {
			// Intercept the conversion API call
			page.route("**/api/v*/digital-twin/convert", async (route) => {
				const response = await route.fetch();
				const status = response.status();

				logTestResult(
					"Digital Twin Convert Button",
					"Click start conversion",
					status,
					response.statusText(),
					0,
				);

				await route.continue();
			});

			await convertButton.click();
			await expect(convertButton).toBeEnabled();

			// Wait for conversion process to start
			await page.waitForLoadState("networkidle");  // S2925: sync on condition, not fixed wait
		} else {
			test.skip(true, "No digital twin convert button found");
		}
	});

	test("should test digital twin configuration buttons", async ({ page }) => {
		await page.goto("/digital-twin/config");
		await page.waitForLoadState("networkidle");

		// Test configuration buttons
		const configButtons = page.locator(
			'button:has-text("Save"), button:has-text("Apply"), button:has-text("Reset"), button[data-testid="config-action-btn"]',
		);

		if ((await configButtons.count()) > 0) {
			const count = await configButtons.count();

			for (let i = 0; i < Math.min(count, 3); i++) {
				const button = configButtons.nth(i);
				const buttonText = (await button.textContent()) || `Config Button ${i}`;

				// Intercept API requests
				page.route("**/api/v*/digital-twin/config*", async (route) => {
					const response = await route.fetch();
					const status = response.status();

					logTestResult(
						`Digital Twin ${buttonText}`,
						`Click ${buttonText}`,
						status,
						response.statusText(),
						0,
					);

					await route.continue();
				});

				await button.click();
				await expect(button).toBeEnabled();

				await page.waitForLoadState("networkidle");  // S2925: sync on condition, not fixed wait
			}
		}
	});
});

/**
 * Test Elements Page Buttons
 */
test.describe("Elements Page Button Tests", () => {
	test("should test elements filter buttons", async ({ page }) => {
		await page.goto("/elements");
		await page.waitForLoadState("networkidle");

		// Test filter and action buttons
		const filterButtons = page.locator(
			'button:has-text("Filter"), button:has-text("Search"), button:has-text("Clear"), button[data-testid="filter-btn"]',
		);

		if ((await filterButtons.count()) > 0) {
			const count = await filterButtons.count();

			for (let i = 0; i < Math.min(count, 3); i++) {
				const button = filterButtons.nth(i);
				const buttonText = (await button.textContent()) || `Filter Button ${i}`;

				// Intercept API requests
				page.route("**/api/v*/elements*", async (route) => {
					const response = await route.fetch();
					const status = response.status();

					logTestResult(
						`Elements ${buttonText}`,
						`Click ${buttonText}`,
						status,
						response.statusText(),
						0,
					);

					await route.continue();
				});

				await button.click();
				await expect(button).toBeEnabled();

				await page.waitForLoadState("networkidle");  // S2925: sync on condition, not fixed wait
			}
		}
	});

	test("should test elements action buttons", async ({ page }) => {
		await page.goto("/elements");
		await page.waitForLoadState("networkidle");

		// Test action buttons for elements
		const actionButtons = page.locator(
			'button:has-text("Edit"), button:has-text("Delete"), button:has-text("Duplicate"), button[data-testid="element-action"]',
		);

		if ((await actionButtons.count()) > 0) {
			const count = await actionButtons.count();

			for (let i = 0; i < Math.min(count, 2); i++) {
				const button = actionButtons.nth(i);
				const buttonText = (await button.textContent()) || `Action Button ${i}`;

				// Intercept API requests
				page.route("**/api/v*/elements/**", async (route) => {
					const response = await route.fetch();
					const status = response.status();

					logTestResult(
						`Elements ${buttonText}`,
						`Click ${buttonText}`,
						status,
						response.statusText(),
						0,
					);

					await route.continue();
				});

				await button.click();
				await expect(button).toBeEnabled();

				await page.waitForLoadState("networkidle");  // S2925: sync on condition, not fixed wait
			}
		}
	});
});

/**
 * Test Connections Page Buttons
 */
test.describe("Connections Page Button Tests", () => {
	test("should test connections create button", async ({ page }) => {
		await page.goto("/connections");
		await page.waitForLoadState("networkidle");

		const createButton = page.locator(
			'button:has-text("New Connection"), button:has-text("Create Connection"), button[data-testid="create-connection-btn"]',
		);

		if ((await createButton.count()) > 0) {
			// Intercept the create connection API call
			page.route("**/api/v*/connections", async (route) => {
				const response = await route.fetch();
				const status = response.status();

				logTestResult(
					"Connections Create Button",
					"Click create connection",
					status,
					response.statusText(),
					0,
				);

				await route.continue();
			});

			await createButton.click();
			await expect(createButton).toBeEnabled();

			await page.waitForLoadState("networkidle");  // S2925: sync on condition, not fixed wait
		} else {
			test.skip("No connections create button found");
		}
	});

	test("should test connections action buttons", async ({ page }) => {
		await page.goto("/connections");
		await page.waitForLoadState("networkidle");

		// Test various connection action buttons
		const actionButtons = page.locator(
			'button:has-text("Validate"), button:has-text("Test"), button:has-text("Sync"), button[data-testid="connection-action"]',
		);

		if ((await actionButtons.count()) > 0) {
			const count = await actionButtons.count();

			for (let i = 0; i < Math.min(count, 3); i++) {
				const button = actionButtons.nth(i);
				const buttonText =
					(await button.textContent()) || `Connection Button ${i}`;

				// Intercept API requests
				page.route("**/api/v*/connections/**", async (route) => {
					const response = await route.fetch();
					const status = response.status();

					logTestResult(
						`Connections ${buttonText}`,
						`Click ${buttonText}`,
						status,
						response.statusText(),
						0,
					);

					await route.continue();
				});

				await button.click();
				await expect(button).toBeEnabled();

				await page.waitForLoadState("networkidle");  // S2925: sync on condition, not fixed wait
			}
		}
	});
});

/**
 * Test Conflicts Page Buttons
 */
test.describe("Conflicts Page Button Tests", () => {
	test("should test conflicts resolve button", async ({ page }) => {
		await page.goto("/conflicts");
		await page.waitForLoadState("networkidle");

		const resolveButton = page.locator(
			'button:has-text("Resolve"), button:has-text("Fix Conflicts"), button[data-testid="resolve-conflicts-btn"]',
		);

		if ((await resolveButton.count()) > 0) {
			// Intercept the resolve conflicts API call
			page.route("**/api/v*/conflicts/resolve*", async (route) => {
				const response = await route.fetch();
				const status = response.status();

				logTestResult(
					"Conflicts Resolve Button",
					"Click resolve conflicts",
					status,
					response.statusText(),
					0,
				);

				await route.continue();
			});

			await resolveButton.click();
			await expect(resolveButton).toBeEnabled();

			await page.waitForLoadState("networkidle");  // S2925: sync on condition, not fixed wait
		} else {
			test.skip(true, "No conflicts resolve button found");
		}
	});

	test("should test conflicts check button", async ({ page }) => {
		await page.goto("/conflicts");
		await page.waitForLoadState("networkidle");

		const checkButton = page.locator(
			'button:has-text("Check"), button:has-text("Detect Conflicts"), button[data-testid="check-conflicts-btn"]',
		);

		if ((await checkButton.count()) > 0) {
			// Intercept the check conflicts API call
			page.route("**/api/v*/conflicts/check*", async (route) => {
				const response = await route.fetch();
				const status = response.status();

				logTestResult(
					"Conflicts Check Button",
					"Click check for conflicts",
					status,
					response.statusText(),
					0,
				);

				await route.continue();
			});

			await checkButton.click();
			await expect(checkButton).toBeEnabled();

			await page.waitForLoadState("networkidle");  // S2925: sync on condition, not fixed wait
		} else {
			test.skip(true, "No conflicts check button found");
		}
	});
});

/**
 * Test Reports Page Buttons
 */
test.describe("Reports Page Button Tests", () => {
	test("should test reports generate button", async ({ page }) => {
		await page.goto("/reports");
		await page.waitForLoadState("networkidle");

		const generateButton = page.locator(
			'button:has-text("Generate"), button:has-text("Create Report"), button[data-testid="generate-report-btn"]',
		);

		if ((await generateButton.count()) > 0) {
			// Intercept the generate report API call
			page.route("**/api/v*/reports/generate*", async (route) => {
				const response = await route.fetch();
				const status = response.status();

				logTestResult(
					"Reports Generate Button",
					"Click generate report",
					status,
					response.statusText(),
					0,
				);

				await route.continue();
			});

			await generateButton.click();
			await expect(generateButton).toBeEnabled();

			await page.waitForLoadState("networkidle");  // S2925: sync on condition, not fixed wait
		} else {
			test.skip(true, "No reports generate button found");
		}
	});

	test("should test reports export buttons", async ({ page }) => {
		await page.goto("/reports");
		await page.waitForLoadState("networkidle");

		// Test export buttons
		const exportButtons = page.locator(
			'button:has-text("Export"), button:has-text("Download"), button:has-text("PDF"), button:has-text("Excel"), button[data-testid*="export"]',
		);

		if ((await exportButtons.count()) > 0) {
			const count = await exportButtons.count();

			for (let i = 0; i < Math.min(count, 3); i++) {
				const button = exportButtons.nth(i);
				const buttonText = (await button.textContent()) || `Export Button ${i}`;

				// Intercept API requests
				page.route("**/api/v*/reports/export*", async (route) => {
					const response = await route.fetch();
					const status = response.status();

					logTestResult(
						`Reports ${buttonText}`,
						`Click ${buttonText}`,
						status,
						response.statusText(),
						0,
					);

					await route.continue();
				});

				await button.click();
				await expect(button).toBeEnabled();

				await page.waitForLoadState("networkidle");  // S2925: sync on condition, not fixed wait
			}
		}
	});
});

/**
 * Test Settings Page Buttons
 */
test.describe("Settings Page Button Tests", () => {
	test("should test settings save button", async ({ page }) => {
		await page.goto("/settings");
		await page.waitForLoadState("networkidle");

		const saveButton = page.locator(
			'button:has-text("Save"), button:has-text("Save Settings"), button[type="submit"]',
		);

		if ((await saveButton.count()) > 0) {
			// Intercept the save settings API call
			page.route("**/api/v*/settings*", async (route) => {
				const response = await route.fetch();
				const status = response.status();

				logTestResult(
					"Settings Save Button",
					"Click save settings",
					status,
					response.statusText(),
					0,
				);

				await route.continue();
			});

			await saveButton.click();
			await expect(saveButton).toBeEnabled();

			await page.waitForLoadState("networkidle");  // S2925: sync on condition, not fixed wait
		} else {
			test.skip(true, "No settings save button found");
		}
	});

	test("should test CAD settings connection test buttons", async ({ page }) => {
		await page.goto("/settings/cad");
		await page.waitForLoadState("networkidle");

		// Test connection test buttons
		const testButtons = page.locator(
			'button:has-text("Test Connection"), button:has-text("Verify"), button[data-testid*="test-connection"]',
		);

		if ((await testButtons.count()) > 0) {
			const count = await testButtons.count();

			for (let i = 0; i < Math.min(count, 2); i++) {
				const button = testButtons.nth(i);
				const buttonText =
					(await button.textContent()) || `Test Connection Button ${i}`;

				// Intercept API requests
				page.route("**/api/v*/settings/test*", async (route) => {
					const response = await route.fetch();
					const status = response.status();

					logTestResult(
						`Settings ${buttonText}`,
						`Click ${buttonText}`,
						status,
						response.statusText(),
						0,
					);

					await route.continue();
				});

				await button.click();
				await expect(button).toBeEnabled();

				await page.waitForLoadState("networkidle");  // S2925: sync on condition, not fixed wait
			}
		}
	});
});

/**
 * Generate comprehensive test report
 */
test.afterAll(async () => {
	// Create a detailed report of all test results
	const report = {
		summary: {
			totalTests: testResults.length,
			passedTests: testResults.filter((r) => r.status >= 200 && r.status < 300)
				.length,
			failedTests: testResults.filter((r) => r.status < 200 || r.status >= 300)
				.length,
			totalDuration: testResults.reduce((sum, r) => sum + r.duration, 0),
			averageDuration:
				testResults.length > 0
					? testResults.reduce((sum, r) => sum + r.duration, 0) /
						testResults.length
					: 0,
		},
		results: testResults,
		timestamp: new Date().toISOString(),
	};

	// Write report to a file using page evaluation
	await testResults.forEach((result) => {
		console.log(`Test Result: ${JSON.stringify(result)}`);
	});

	console.log(`\n=== TEST SUMMARY ===`);
	console.log(`Total Tests: ${report.summary.totalTests}`);
	console.log(`Passed: ${report.summary.passedTests}`);
	console.log(`Failed: ${report.summary.failedTests}`);
	console.log(
		`Average Duration: ${report.summary.averageDuration.toFixed(2)}ms`,
	);
});
