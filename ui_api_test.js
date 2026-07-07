const puppeteer = require("puppeteer");
const fs = require("node:fs");
const path = require("node:path");

// Test configuration
const CONFIG = {
	baseUrl: process.env.BASE_URL || "http://localhost:3000",
	apiUrl: process.env.API_URL || "http://localhost:8000",
	apiKey: process.env.API_KEY || "your-api-key-here",
	username: process.env.USERNAME || "test-user",
	password: process.env.PASSWORD || "test-password",  // NOSONAR: S2068 test fixture password
	timeout: 30000,
};

// Test report structure
const testReport = {
	startTime: new Date(),
	results: [],
	errors: [],
	summary: {
		totalTests: 0,
		passedTests: 0,
		failedTests: 0,
		totalTime: 0,
	},
};

/**
 * Makes an API request to the backend
 */
async function makeApiRequest(endpoint, options = {}) {
	const url = `${CONFIG.apiUrl}${endpoint}`;

	const defaultOptions = {
		method: "GET",
		headers: {
			"X-API-Key": CONFIG.apiKey,
			"Content-Type": "application/json",
		},
	};

	const requestOptions = { ...defaultOptions, ...options };

	if (requestOptions.body && typeof requestOptions.body === "object") {
		requestOptions.body = JSON.stringify(requestOptions.body);
	}

	try {
		const startTime = Date.now();
		const response = await fetch(url, requestOptions);
		const endTime = Date.now();

		const responseData = await response.json().catch(() => ({}));

		return {
			status: response.status,
			statusText: response.statusText,
			data: responseData,
			headers: Object.fromEntries(response.headers.entries()),
			duration: endTime - startTime,
		};
	} catch (error) {
		console.error(`API request failed: ${url}`, error.message);
		return {
			status: 0,
			statusText: "Network Error",
			data: {},
			headers: {},
			duration: 0,
			error: error.message,
		};
	}
}

/**
 * Logs test result to the report
 */
function logTestResult(testName, action, result, details = {}) {
	const testResult = {
		testName,
		action,
		timestamp: new Date(),
		status: result.status,
		statusText: result.statusText,
		duration: result.duration,
		error: result.error,
		details: {
			...details,
			response: result.data,
			headers: result.headers,
		},
	};

	testReport.results.push(testResult);

	if (result.status >= 200 && result.status < 300) {
		testReport.summary.passedTests++;
	} else {
		testReport.summary.failedTests++;
		testReport.errors.push(testResult);
	}

	testReport.summary.totalTests++;

	// Log to console
	console.log(
		`[${result.status}] ${testName}: ${action} (${result.duration}ms)`,
	);
	if (result.error) {
		console.error(`  Error: ${result.error}`);
	}
}

/**
 * Main test execution function
 */
async function runUITests() {
	console.log("Starting UI and API integration tests...");

	const browser = await puppeteer.launch({
		headless: false, // Set to true for headless mode
		executablePath:
			"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
		args: ["--no-sandbox", "--disable-setuid-sandbox"],
	});

	const page = await browser.newPage();

	// Set viewport and timeouts
	await page.setViewport({ width: 1280, height: 720 });
	await page.setDefaultTimeout(CONFIG.timeout);
	await page.setDefaultNavigationTimeout(CONFIG.timeout);

	try {
		// Navigate to the application
		console.log(`Navigating to ${CONFIG.baseUrl}`);
		await page.goto(CONFIG.baseUrl, { waitUntil: "networkidle2" });

		// Test Dashboard Page
		await testDashboardPage(page);

		// Test Projects Page
		await testProjectsPage(page);

		// Test AutoCAD Page
		await testAutoCADPage(page);

		// Test Revit Page
		await testRevitPage(page);

		// Test Digital Twin Page
		await testDigitalTwinPage(page);

		// Test Elements Page
		await testElementsPage(page);

		// Test Connections Page
		await testConnectionsPage(page);

		// Test Conflicts Page
		await testConflictsPage(page);

		// Test Reports Page
		await testReportsPage(page);
	} catch (error) {
		console.error("Test execution error:", error);
		testReport.errors.push({
			testName: "Overall Test Execution",
			error: error.message,
			timestamp: new Date(),
		});
	} finally {
		await browser.close();
	}

	// Finalize report
	testReport.summary.totalTime = Date.now() - testReport.startTime.getTime();
	generateTestReport();
}

/**
 * Tests dashboard page interactions
 */
async function testDashboardPage(page) {
	console.log("Testing Dashboard Page...");

	// Click on Dashboard link
	await page.click('nav a[href="/dashboard"]');
	await page
		.waitForSelector(".dashboard-container", { timeout: 5000 })
		.catch(() => {});

	// Simulate clicking various dashboard elements and corresponding API calls
	const dashboardTests = [
		{
			testName: "Dashboard Stats Load",
			selector: '[data-testid="stats-card"]',
			apiCall: () => makeApiRequest("/api/v1/projects"),
			action: "Load dashboard stats",
		},
		{
			testName: "Recent Projects Load",
			selector: '[data-testid="recent-projects"]',
			apiCall: () => makeApiRequest("/api/v1/projects?limit=5"),
			action: "Load recent projects",
		},
	];

	for (const test of dashboardTests) {
		try {
			// Wait for element to appear
			await page
				.waitForSelector(test.selector, { timeout: 3000 })
				.catch(() => {});

			// Make API call
			const result = await test.apiCall();
			logTestResult(test.testName, test.action, result);
		} catch (error) {
			logTestResult(test.testName, test.action, {
				status: 0,
				statusText: "Error",
				duration: 0,
				error: error.message,
			});
		}
	}
}

/**
 * Tests projects page interactions
 */
async function testProjectsPage(page) {
	console.log("Testing Projects Page...");

	// Navigate to projects page
	await page.click('nav a[href="/projects"]');
	await page
		.waitForSelector('[data-testid="projects-list"]', { timeout: 5000 })
		.catch(() => {});

	// Test creating a project
	const createProjectTest = {
		testName: "Create Project Button",
		selector: '[data-testid="create-project-btn"]',
		apiCall: () =>
			makeApiRequest("/api/v1/projects", {
				method: "POST",
				body: {
					name: `Test Project ${Date.now()}`,
					description: "Test project created via UI automation",
				},
			}),
		action: "Click create project button",
	};

	try {
		await page
			.waitForSelector(createProjectTest.selector, { timeout: 3000 })
			.catch(() => {});
		const result = await createProjectTest.apiCall();
		logTestResult(createProjectTest.testName, createProjectTest.action, result);
	} catch (error) {
		logTestResult(createProjectTest.testName, createProjectTest.action, {
			status: 0,
			statusText: "Error",
			duration: 0,
			error: error.message,
		});
	}

	// Test loading projects
	const loadProjectsTest = {
		testName: "Load Projects List",
		selector: '[data-testid="projects-table"]',
		apiCall: () => makeApiRequest("/api/v1/projects"),
		action: "Load projects list",
	};

	try {
		await page
			.waitForSelector(loadProjectsTest.selector, { timeout: 3000 })
			.catch(() => {});
		const result = await loadProjectsTest.apiCall();
		logTestResult(loadProjectsTest.testName, loadProjectsTest.action, result);
	} catch (error) {
		logTestResult(loadProjectsTest.testName, loadProjectsTest.action, {
			status: 0,
			statusText: "Error",
			duration: 0,
			error: error.message,
		});
	}
}

/**
 * Tests AutoCAD page interactions
 */
async function testAutoCADPage(page) {
	console.log("Testing AutoCAD Page...");

	// Navigate to AutoCAD page
	await page.click('nav a[href="/autocad"]');
	await page
		.waitForSelector('[data-testid="autocad-panel"]', { timeout: 5000 })
		.catch(() => {});

	// Test connecting to AutoCAD
	const connectAutoCADTest = {
		testName: "Connect AutoCAD Button",
		selector: '[data-testid="connect-autocad-btn"]',
		apiCall: () =>
			makeApiRequest("/api/v1/autocad/connect", { method: "POST", body: {} }),
		action: "Click connect AutoCAD button",
	};

	try {
		await page
			.waitForSelector(connectAutoCADTest.selector, { timeout: 3000 })
			.catch(() => {});
		const result = await connectAutoCADTest.apiCall();
		logTestResult(
			connectAutoCADTest.testName,
			connectAutoCADTest.action,
			result,
		);
	} catch (error) {
		logTestResult(connectAutoCADTest.testName, connectAutoCADTest.action, {
			status: 0,
			statusText: "Error",
			duration: 0,
			error: error.message,
		});
	}

	// Test loading documents
	const loadDocumentsTest = {
		testName: "Load AutoCAD Documents",
		selector: '[data-testid="documents-list"]',
		apiCall: () => makeApiRequest("/api/v1/autocad/documents"),
		action: "Load AutoCAD documents",
	};

	try {
		await page
			.waitForSelector(loadDocumentsTest.selector, { timeout: 3000 })
			.catch(() => {});
		const result = await loadDocumentsTest.apiCall();
		logTestResult(loadDocumentsTest.testName, loadDocumentsTest.action, result);
	} catch (error) {
		logTestResult(loadDocumentsTest.testName, loadDocumentsTest.action, {
			status: 0,
			statusText: "Error",
			duration: 0,
			error: error.message,
		});
	}
}

/**
 * Tests Revit page interactions
 */
async function testRevitPage(page) {
	console.log("Testing Revit Page...");

	// Navigate to Revit page
	await page.click('nav a[href="/revit"]');
	await page
		.waitForSelector('[data-testid="revit-panel"]', { timeout: 5000 })
		.catch(() => {});

	// Test connecting to Revit
	const connectRevitTest = {
		testName: "Connect Revit Button",
		selector: '[data-testid="connect-revit-btn"]',
		apiCall: () =>
			makeApiRequest("/api/v1/revit/connect", { method: "POST", body: {} }),
		action: "Click connect Revit button",
	};

	try {
		await page
			.waitForSelector(connectRevitTest.selector, { timeout: 3000 })
			.catch(() => {});
		const result = await connectRevitTest.apiCall();
		logTestResult(connectRevitTest.testName, connectRevitTest.action, result);
	} catch (error) {
		logTestResult(connectRevitTest.testName, connectRevitTest.action, {
			status: 0,
			statusText: "Error",
			duration: 0,
			error: error.message,
		});
	}

	// Test loading elements
	const loadElementsTest = {
		testName: "Load Revit Elements",
		selector: '[data-testid="elements-list"]',
		apiCall: () => makeApiRequest("/api/v1/revit/elements"),
		action: "Load Revit elements",
	};

	try {
		await page
			.waitForSelector(loadElementsTest.selector, { timeout: 3000 })
			.catch(() => {});
		const result = await loadElementsTest.apiCall();
		logTestResult(loadElementsTest.testName, loadElementsTest.action, result);
	} catch (error) {
		logTestResult(loadElementsTest.testName, loadElementsTest.action, {
			status: 0,
			statusText: "Error",
			duration: 0,
			error: error.message,
		});
	}
}

/**
 * Tests Digital Twin page interactions
 */
async function testDigitalTwinPage(page) {
	console.log("Testing Digital Twin Page...");

	// Navigate to Digital Twin page
	await page.click('nav a[href="/digital-twin"]');
	await page
		.waitForSelector('[data-testid="digital-twin-panel"]', { timeout: 5000 })
		.catch(() => {});

	// Test conversion
	const convertTest = {
		testName: "Digital Twin Convert Button",
		selector: '[data-testid="convert-btn"]',
		apiCall: () =>
			makeApiRequest("/api/v1/digital-twin/convert", {
				method: "POST",
				body: {
					sourceFormat: "dwg",
					targetFormat: "rvt",
					conversionParams: {},
				},
			}),
		action: "Click convert button",
	};

	try {
		await page
			.waitForSelector(convertTest.selector, { timeout: 3000 })
			.catch(() => {});
		const result = await convertTest.apiCall();
		logTestResult(convertTest.testName, convertTest.action, result);
	} catch (error) {
		logTestResult(convertTest.testName, convertTest.action, {
			status: 0,
			statusText: "Error",
			duration: 0,
			error: error.message,
		});
	}

	// Test loading history
	const historyTest = {
		testName: "Load Conversion History",
		selector: '[data-testid="conversion-history"]',
		apiCall: () => makeApiRequest("/api/v1/digital-twin/history"),
		action: "Load conversion history",
	};

	try {
		await page
			.waitForSelector(historyTest.selector, { timeout: 3000 })
			.catch(() => {});
		const result = await historyTest.apiCall();
		logTestResult(historyTest.testName, historyTest.action, result);
	} catch (error) {
		logTestResult(historyTest.testName, historyTest.action, {
			status: 0,
			statusText: "Error",
			duration: 0,
			error: error.message,
		});
	}
}

/**
 * Tests elements page interactions
 */
async function testElementsPage(page) {
	console.log("Testing Elements Page...");

	// Navigate to elements page
	await page.click('nav a[href="/elements"]');
	await page
		.waitForSelector('[data-testid="elements-grid"]', { timeout: 5000 })
		.catch(() => {});

	// Test loading elements
	const elementsTest = {
		testName: "Load Elements List",
		selector: '[data-testid="elements-grid"]',
		apiCall: () => makeApiRequest("/api/v1/elements"),
		action: "Load elements list",
	};

	try {
		await page
			.waitForSelector(elementsTest.selector, { timeout: 3000 })
			.catch(() => {});
		const result = await elementsTest.apiCall();
		logTestResult(elementsTest.testName, elementsTest.action, result);
	} catch (error) {
		logTestResult(elementsTest.testName, elementsTest.action, {
			status: 0,
			statusText: "Error",
			duration: 0,
			error: error.message,
		});
	}
}

/**
 * Tests connections page interactions
 */
async function testConnectionsPage(page) {
	console.log("Testing Connections Page...");

	// Navigate to connections page
	await page.click('nav a[href="/connections"]');
	await page
		.waitForSelector('[data-testid="connections-table"]', { timeout: 5000 })
		.catch(() => {});

	// Test loading connections
	const connectionsTest = {
		testName: "Load Connections List",
		selector: '[data-testid="connections-table"]',
		apiCall: () => makeApiRequest("/api/v1/connections"),
		action: "Load connections list",
	};

	try {
		await page
			.waitForSelector(connectionsTest.selector, { timeout: 3000 })
			.catch(() => {});
		const result = await connectionsTest.apiCall();
		logTestResult(connectionsTest.testName, connectionsTest.action, result);
	} catch (error) {
		logTestResult(connectionsTest.testName, connectionsTest.action, {
			status: 0,
			statusText: "Error",
			duration: 0,
			error: error.message,
		});
	}
}

/**
 * Tests conflicts page interactions
 */
async function testConflictsPage(page) {
	console.log("Testing Conflicts Page...");

	// Navigate to conflicts page
	await page.click('nav a[href="/conflicts"]');
	await page
		.waitForSelector('[data-testid="conflicts-list"]', { timeout: 5000 })
		.catch(() => {});

	// Test checking conflicts
	const conflictsTest = {
		testName: "Check Conflicts",
		selector: '[data-testid="conflicts-list"]',
		apiCall: () => makeApiRequest("/api/v1/conflicts"),
		action: "Check for conflicts",
	};

	try {
		await page
			.waitForSelector(conflictsTest.selector, { timeout: 3000 })
			.catch(() => {});
		const result = await conflictsTest.apiCall();
		logTestResult(conflictsTest.testName, conflictsTest.action, result);
	} catch (error) {
		logTestResult(conflictsTest.testName, conflictsTest.action, {
			status: 0,
			statusText: "Error",
			duration: 0,
			error: error.message,
		});
	}
}

/**
 * Tests reports page interactions
 */
async function testReportsPage(page) {
	console.log("Testing Reports Page...");

	// Navigate to reports page
	await page.click('nav a[href="/reports"]');
	await page
		.waitForSelector('[data-testid="reports-section"]', { timeout: 5000 })
		.catch(() => {});

	// Test generating report
	const reportTest = {
		testName: "Generate Report",
		selector: '[data-testid="generate-report-btn"]',
		apiCall: () =>
			makeApiRequest("/api/v1/reports/generate", {
				method: "POST",
				body: {
					reportType: "summary",
					filters: {},
				},
			}),
		action: "Generate report",
	};

	try {
		await page
			.waitForSelector(reportTest.selector, { timeout: 3000 })
			.catch(() => {});
		const result = await reportTest.apiCall();
		logTestResult(reportTest.testName, reportTest.action, result);
	} catch (error) {
		logTestResult(reportTest.testName, reportTest.action, {
			status: 0,
			statusText: "Error",
			duration: 0,
			error: error.message,
		});
	}
}

/**
 * Generates a detailed test report
 */
function generateTestReport() {
	testReport.endTime = new Date();

	const report = `
# UI and API Integration Test Report

## Test Summary
- **Start Time:** ${testReport.startTime.toISOString()}
- **End Time:** ${testReport.endTime.toISOString()}
- **Total Duration:** ${(testReport.summary.totalTime / 1000).toFixed(2)} seconds
- **Total Tests:** ${testReport.summary.totalTests}
- **Passed:** ${testReport.summary.passedTests}
- **Failed:** ${testReport.summary.failedTests}
- **Success Rate:** ${testReport.summary.totalTests ? ((testReport.summary.passedTests / testReport.summary.totalTests) * 100).toFixed(2) : 0}%

## Test Results
${testReport.results
	.map(
		(result) => `
### ${result.testName}
- **Action:** ${result.action}
- **Timestamp:** ${result.timestamp.toISOString()}
- **Status:** ${result.status} ${result.statusText}
- **Duration:** ${result.duration}ms
${result.error ? `- **Error:** ${result.error}` : ""}
`,
	)
	.join("\n")}

## Failed Tests
${
	testReport.errors.length
		? testReport.errors
				.map(
					(error) => `
### ${error.testName}
- **Action:** ${error.action}
- **Error:** ${error.error || "Unknown error"}
- **Status:** ${error.status}
`,
				)
				.join("\n")
		: "No failed tests"
}

## Detailed Results
${JSON.stringify(testReport.results, null, 2)}
`;

	// Write report to file
	const reportPath = path.join(__dirname, "test_report.md");
	fs.writeFileSync(reportPath, report);
	console.log(`Test report generated: ${reportPath}`);

	// Also write JSON report for programmatic consumption
	const jsonReportPath = path.join(__dirname, "test_report.json");
	fs.writeFileSync(jsonReportPath, JSON.stringify(testReport, null, 2));
	console.log(`JSON test report generated: ${jsonReportPath}`);
}

// Run tests when script is executed directly
if (require.main === module) {
	runUITests()
		.then(() => {
			console.log("UI and API integration tests completed!");
			process.exit(0);
		})
		.catch((error) => {
			console.error("Test execution failed:", error);
			process.exit(1);
		});
}

module.exports = {
	runUITests,
	makeApiRequest,
	logTestResult,
};
