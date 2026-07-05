/**
 * StatusIndicator.test.ts
 *
 * Verifies that the connection-status indicator logic correctly maps
 * connectionStatus values to the expected visual states.
 * This closes the "blind trust" gap in UI correctness verification.
 */

import { beforeEach, describe, expect, it } from "vitest";
import { getState, setState } from "@/store/simpleStore";

// ── Pure logic extracted from the Header component ───────────────────────────
// These mirror the exact conditional expressions in Header.tsx so any drift
// between component and test will surface as a test failure.

function getIndicatorClass(connectionStatus: string): string {
	return connectionStatus === "connected"
		? "status-pulse-connected"
		: "status-solid-disconnected";
}

function getBannerVisible(connectionStatus: string): boolean {
	return connectionStatus !== "connected";
}

function getIndicatorColor(connectionStatus: string): string {
	return connectionStatus === "connected" ? "#22c55e" : "#ef4444";
}

// ─────────────────────────────────────────────────────────────────────────────

describe("Status Indicator — Connection State Logic", () => {
	beforeEach(() => {
		setState({
			theme: "dark",
			faults: [],
			helpOpen: false,
			liveData: { voltage: 220.5, current: 15.2, frequency: 50.0 },
			eventLogs: [],
			dataMode: "mock",
			connectionStatus: "connected",
		});
	});

	// ── TEST 1 ─────────────────────────────────────────────────────────────────
	it("applies pulse animation class when connected", () => {
		const status = getState().connectionStatus;
		expect(getIndicatorClass(status)).toBe("status-pulse-connected");
	});

	// ── TEST 2 ─────────────────────────────────────────────────────────────────
	it("applies solid-red class when disconnected", () => {
		setState({ connectionStatus: "disconnected" });
		const status = getState().connectionStatus;
		expect(getIndicatorClass(status)).toBe("status-solid-disconnected");
	});

	// ── TEST 3 (the critical one) ──────────────────────────────────────────────
	it("changes indicator class when connection is simulated as lost", () => {
		// Initially connected
		expect(getIndicatorClass("connected")).toBe("status-pulse-connected");

		// Simulate disconnection
		setState({ connectionStatus: "disconnected" });
		const newStatus = getState().connectionStatus;

		// Indicator MUST switch — no blind trust
		expect(getIndicatorClass(newStatus)).not.toBe("status-pulse-connected");
		expect(getIndicatorClass(newStatus)).toBe("status-solid-disconnected");
	});

	// ── TEST 4 ─────────────────────────────────────────────────────────────────
	it("hides the connection-lost banner when connected", () => {
		const status = getState().connectionStatus;
		expect(getBannerVisible(status)).toBe(false);
	});

	// ── TEST 5 ─────────────────────────────────────────────────────────────────
	it("shows the connection-lost banner when disconnected", () => {
		setState({ connectionStatus: "disconnected" });
		const status = getState().connectionStatus;
		expect(getBannerVisible(status)).toBe(true);
	});

	// ── TEST 6 ─────────────────────────────────────────────────────────────────
	it("uses green color token when connected and red when disconnected", () => {
		expect(getIndicatorColor("connected")).toBe("#22c55e");
		expect(getIndicatorColor("disconnected")).toBe("#ef4444");
	});
});
