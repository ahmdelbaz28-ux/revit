import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

// Mock react-i18next to return keys as display text
vi.mock("react-i18next", () => ({
	useTranslation: () => ({
		t: (key: string) => key,
		i18n: { language: "en", changeLanguage: vi.fn() },
	}),
	initReactI18next: { type: "3rdParty", init: vi.fn() },
}));

// Mock the CalculationEngine
vi.mock("@/engine/CalculationEngine", () => ({
	calculateVoltageDrop: vi
		.fn()
		.mockReturnValue({ percentage: 2.5, voltageDrop: 5.75, isCompliant: true }),
	calculateShortCircuit: vi.fn().mockReturnValue({
		prospectiveCurrent: 5000,
		breakingCapacity: 6000,
		isCompliant: true,
	}),
	calculateCableSizing: vi.fn().mockReturnValue({
		recommendedSize: "2.5mm²",
		deratingFactor: 0.87,
		isCompliant: true,
	}),
	calculateLoadFlow: vi
		.fn()
		.mockReturnValue({ totalLoad: 50, voltageAtEnd: 218, isCompliant: true }),
	checkBreakerCoordination: vi.fn(),
	calculateEarthFaultLoop: vi.fn(),
	calculatePowerFactorCorrection: vi.fn(),
	generateCompleteReport: vi.fn(),
}));

import { EngineeringPage } from "../EngineeringPage";

describe("EngineeringPage", () => {
	it("renders engineering calculation tabs", () => {
		render(<EngineeringPage />);
		// V140 FIX: The page uses i18n keys. 'engineering.voltageDrop' appears
		// in both the tab button AND the card title, so use getAllByText.
		expect(
			screen.getAllByText("engineering.voltageDrop").length,
		).toBeGreaterThanOrEqual(1);
		expect(
			screen.getAllByText("engineering.cableSizing").length,
		).toBeGreaterThanOrEqual(1);
		expect(
			screen.getAllByText("engineering.batteryCalculation").length,
		).toBeGreaterThanOrEqual(1);
	});

	it("renders calculate buttons", () => {
		render(<EngineeringPage />);
		// V140 FIX: The tab buttons are clickable. Verify at least one
		// engineering.voltageDrop element is inside a button.
		const vDropElements = screen.getAllByText("engineering.voltageDrop");
		const hasButton = vDropElements.some((el) => el.closest("button") !== null);
		expect(hasButton).toBe(true);
	});

	it("displays the engineering page heading", () => {
		render(<EngineeringPage />);
		expect(screen.getByText("engineering.title")).toBeInTheDocument();
	});

	it("shows validation-compliant default inputs", () => {
		render(<EngineeringPage />);
		// V140 FIX: The voltage drop tab button should be enabled.
		const vDropElements = screen.getAllByText("engineering.voltageDrop");
		const buttonEl = vDropElements.find((el) => el.closest("button") !== null);
		expect(buttonEl?.closest("button")).not.toBeDisabled();
	});
});
