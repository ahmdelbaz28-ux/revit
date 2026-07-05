/**
 * API Verification Helpers
 *
 * This module provides utilities for verifying backend connections
 * and API call responses during UI testing.
 */

interface ApiResponse {
	status: number;
	statusText: string;
	data: any;
	headers: Record<string, string>;
	ok: boolean;
	duration: number;
}

/**
 * Makes an API request to the backend and captures detailed response
 */
export async function makeApiRequest(
	endpoint: string,
	options: RequestInit = {},
): Promise<ApiResponse> {
	const startTime = Date.now();

	// Default headers for API requests
	const defaultHeaders = {
		"X-API-Key": process.env.API_KEY || "test-api-key",
		"Content-Type": "application/json",
		...options.headers,
	};

	try {
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

		const endTime = Date.now();

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
			duration: endTime - startTime,
		};
	} catch (error) {
		const endTime = Date.now();
		return {
			status: 0,
			statusText: "Network Error",
			data: {},
			headers: {},
			ok: false,
			duration: endTime - startTime,
		};
	}
}

/**
 * Verifies that a specific API endpoint is accessible and returns expected response
 */
export async function verifyEndpoint(
	endpoint: string,
	expectedStatus: number | number[] = [200, 201, 204],
	method: string = "GET",
): Promise<{ success: boolean; response: ApiResponse; message: string }> {
	const response = await makeApiRequest(endpoint, { method });

	const expectedStatusArray = Array.isArray(expectedStatus)
		? expectedStatus
		: [expectedStatus];
	const isSuccess = expectedStatusArray.includes(response.status);

	let message = "";
	if (isSuccess) {
		message = `Endpoint ${endpoint} responded with expected status ${response.status}`;
	} else {
		message = `Endpoint ${endpoint} responded with unexpected status ${response.status} (expected: ${expectedStatusArray.join(", ")})`;
	}

	return {
		success: isSuccess,
		response,
		message,
	};
}

/**
 * Waits for an API endpoint to become available (useful for testing startup)
 */
export async function waitForEndpoint(
	endpoint: string,
	maxAttempts: number = 30,
	interval: number = 1000,
	method: string = "GET",
): Promise<boolean> {
	for (let attempt = 0; attempt < maxAttempts; attempt++) {
		try {
			const response = await makeApiRequest(endpoint, { method });
			if (response.status >= 200 && response.status < 400) {
				return true;
			}
		} catch (error) {
			// Continue waiting if there's a network error
		}

		await new Promise((resolve) => setTimeout(resolve, interval));
	}

	return false;
}

/**
 * Validates the structure of API response data
 */
export async function validateApiResponse(
	endpoint: string,
	validator: (data: any) => boolean,
): Promise<{ success: boolean; response: ApiResponse; message: string }> {
	const response = await makeApiRequest(endpoint);

	if (!response.ok) {
		return {
			success: false,
			response,
			message: `API call to ${endpoint} failed with status ${response.status}`,
		};
	}

	const isValid = validator(response.data);

	return {
		success: isValid,
		response,
		message: isValid
			? `API response from ${endpoint} is valid`
			: `API response from ${endpoint} does not match expected structure`,
	};
}

/**
 * Collects performance metrics for API calls
 */
export async function measureApiPerformance(
	endpoint: string,
	iterations: number = 5,
	method: string = "GET",
): Promise<{
	avgResponseTime: number;
	minResponseTime: number;
	maxResponseTime: number;
	successRate: number;
}> {
	const responseTimes: number[] = [];
	let successCount = 0;

	for (let i = 0; i < iterations; i++) {
		const response = await makeApiRequest(endpoint, { method });
		responseTimes.push(response.duration);

		if (response.status >= 200 && response.status < 300) {
			successCount++;
		}
	}

	const totalResponseTime = responseTimes.reduce((sum, time) => sum + time, 0);
	const avgResponseTime = totalResponseTime / iterations;
	const minResponseTime = Math.min(...responseTimes);
	const maxResponseTime = Math.max(...responseTimes);
	const successRate = (successCount / iterations) * 100;

	return {
		avgResponseTime,
		minResponseTime,
		maxResponseTime,
		successRate,
	};
}

/**
 * Tests multiple endpoints simultaneously to check for concurrent performance
 */
export async function testConcurrentEndpoints(
	endpoints: string[],
	method: string = "GET",
): Promise<
	Array<{ endpoint: string; response: ApiResponse; success: boolean }>
> {
	const promises = endpoints.map((endpoint) =>
		makeApiRequest(endpoint, { method }).then((response) => ({
			endpoint,
			response,
			success: response.status >= 200 && response.status < 300,
		})),
	);

	return Promise.all(promises);
}

/**
 * Verifies authentication headers are properly set
 */
export function verifyAuthHeaders(): boolean {
	const apiKey = process.env.API_KEY;
	return !!apiKey && apiKey !== "test-api-key";
}

/**
 * Gets the base API URL
 */
export function getApiBaseUrl(): string {
	return process.env.API_URL || "http://localhost:8000";
}

/**
 * Formats a test result for logging
 */
export function formatTestResult(
	testName: string,
	success: boolean,
	details?: any,
): string {
	const status = success ? "PASS" : "FAIL";
	const timestamp = new Date().toISOString();

	let result = `[${timestamp}] ${testName}: ${status}`;

	if (details) {
		result += ` - ${JSON.stringify(details)}`;
	}

	return result;
}
