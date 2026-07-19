/**
 * BatteryCalculator.test.ts — Unit tests for the NFPA 72 battery calculator.
 *
 * V244: Safety-critical module — calculates battery capacity per NFPA 72 §27.6.2.
 */
import { describe, expect, it } from "vitest";
import {
        calculateBatteryRequirements,
        generateBatteryReport,
        getNFPA27_6_2Requirements,
        validateBatteryCompliance,
} from "@/engine/BatteryCalculator";

// ── Test Fixtures ──────────────────────────────────────────────────────────

const validInput = {
        devices: [
                { type: "smoke", standbyCurrent: 0.05, alarmCurrent: 85, count: 24 },
                { type: "heat", standbyCurrent: 0.03, alarmCurrent: 50, count: 8 },
                { type: "pull", standbyCurrent: 0.01, alarmCurrent: 100, count: 12 },
                { type: "horn", standbyCurrent: 0.02, alarmCurrent: 150, count: 16 },
        ],
        standbyHours: 24,
        alarmMinutes: 5,
        safetyFactor: 1.2,
};

// ── Tests ──────────────────────────────────────────────────────────────────

describe("BatteryCalculator", () => {
        describe("calculateBatteryRequirements", () => {
                it("should calculate total standby current correctly (mA → A) (F-15 FIX)", () => {
                        const result = calculateBatteryRequirements(validInput);
                        // F-15 FIX (Engineering Review): the previous assertion was
                        // `toBeGreaterThanOrEqual(0)` — trivially true for any non-negative
                        // number, including the wrong answer. The correct expected value is
                        // computed from the input:
                        //   standby_total_mA = (0.05×24) + (0.03×8) + (0.01×12) + (0.02×16)
                        //                    = 1.20 + 0.24 + 0.12 + 0.32 = 1.88 mA
                        //   standby_total_A  = 1.88 / 1000 = 0.00188 A
                        // The test now asserts the EXACT expected value (to 4 decimal places)
                        // so a regression in the formula (e.g., forgetting the /1000 conversion)
                        // would be caught.
                        const expectedStandbyA =
                                (0.05 * 24 + 0.03 * 8 + 0.01 * 12 + 0.02 * 16) / 1000;
                        expect(result.totalStandbyCurrent).toBeCloseTo(expectedStandbyA, 4);
                        expect(result.totalStandbyCurrent).toBeLessThan(1); // Should be small (mA range)
                });

                it("should calculate total alarm current correctly (mA → A)", () => {
                        const result = calculateBatteryRequirements(validInput);
                        // (85×24 + 50×8 + 100×12 + 150×16) / 1000 = (2040+400+1200+2400)/1000 = 6.04 A
                        expect(result.totalAlarmCurrent).toBeCloseTo(6.04, 1);
                });

                it("should apply the safety factor to the required capacity", () => {
                        const inputNoSafety = { ...validInput, safetyFactor: 1.0 };
                        const inputWithSafety = { ...validInput, safetyFactor: 1.2 };
                        const noSafety = calculateBatteryRequirements(inputNoSafety);
                        const withSafety = calculateBatteryRequirements(inputWithSafety);
                        expect(withSafety.requiredCapacity).toBeCloseTo(
                                noSafety.requiredCapacity * 1.2,
                                1,
                        );
                });

                it("should recommend a 12V battery for small capacities (<20 Ah)", () => {
                        const smallInput = {
                                ...validInput,
                                devices: [{ type: "smoke", standbyCurrent: 0.01, alarmCurrent: 10, count: 1 }],
                                standbyHours: 24,
                                alarmMinutes: 5,
                                safetyFactor: 1.2,
                        };
                        const result = calculateBatteryRequirements(smallInput);
                        expect(result.recommendedBattery.voltage).toBe(12);
                        expect(result.recommendedBattery.capacity).toBeGreaterThanOrEqual(1);
                });

                it("should recommend a 24V battery for large capacities (>100 Ah)", () => {
                        const largeInput = {
                                devices: [
                                        { type: "horn", standbyCurrent: 100, alarmCurrent: 500, count: 50 },
                                ],
                                standbyHours: 24,
                                alarmMinutes: 10,
                                safetyFactor: 1.2,
                        };
                        const result = calculateBatteryRequirements(largeInput);
                        expect(result.requiredCapacity).toBeGreaterThan(100);
                        expect(result.recommendedBattery.voltage).toBe(24);
                });

                it("should mark compliance as meeting NFPA 72 §27.6.2", () => {
                        const result = calculateBatteryRequirements(validInput);
                        expect(result.compliance.meetsNFPA27_6_2).toBe(true);
                        expect(result.compliance.standbyDuration).toBe(24);
                        expect(result.compliance.alarmDuration).toBe(5);
                        expect(result.compliance.safetyFactor).toBe(1.2);
                });

                it("should mark meetsNFPA27_6_2 as false if standbyHours < 24", () => {
                        const result = calculateBatteryRequirements({
                                ...validInput,
                                standbyHours: 12,
                        });
                        expect(result.compliance.meetsNFPA27_6_2).toBe(false);
                });

                it("should mark meetsNFPA27_6_2 as false if alarmMinutes < 5", () => {
                        const result = calculateBatteryRequirements({
                                ...validInput,
                                alarmMinutes: 3,
                        });
                        expect(result.compliance.meetsNFPA27_6_2).toBe(false);
                });

                it("should handle empty device list", () => {
                        const result = calculateBatteryRequirements({
                                devices: [],
                                standbyHours: 24,
                                alarmMinutes: 5,
                                safetyFactor: 1.2,
                        });
                        expect(result.totalStandbyCurrent).toBe(0);
                        expect(result.totalAlarmCurrent).toBe(0);
                        expect(result.requiredCapacity).toBe(0);
                });
        });

        describe("validateBatteryCompliance", () => {
                it("should pass for standard NFPA 72 compliant values (24h, 5min, 1.2x)", () => {
                        const result = calculateBatteryRequirements(validInput);
                        const compliance = validateBatteryCompliance(result);
                        expect(compliance.compliant).toBe(true);
                        expect(compliance.violations).toEqual([]);
                });

                it("should flag standby duration < 24 hours as a violation", () => {
                        const result = calculateBatteryRequirements({
                                ...validInput,
                                standbyHours: 12,
                        });
                        const compliance = validateBatteryCompliance(result);
                        expect(compliance.compliant).toBe(false);
                        expect(compliance.violations).toContainEqual(
                                expect.stringContaining("does not meet minimum 24 hours"),
                        );
                });

                it("should flag alarm duration < 5 minutes as a violation", () => {
                        const result = calculateBatteryRequirements({
                                ...validInput,
                                alarmMinutes: 3,
                        });
                        const compliance = validateBatteryCompliance(result);
                        expect(compliance.compliant).toBe(false);
                        expect(compliance.violations).toContainEqual(
                                expect.stringContaining("does not meet minimum 5 minutes"),
                        );
                });

                it("should warn when safety factor < 1.2", () => {
                        const result = calculateBatteryRequirements({
                                ...validInput,
                                safetyFactor: 1.0,
                        });
                        const compliance = validateBatteryCompliance(result);
                        expect(compliance.warnings).toContainEqual(
                                expect.stringContaining("less than recommended 1.2x"),
                        );
                });

                it("should pass at exact minimum thresholds (24h, 5min, 1.2x)", () => {
                        const result = calculateBatteryRequirements({
                                ...validInput,
                                standbyHours: 24,
                                alarmMinutes: 5,
                                safetyFactor: 1.2,
                        });
                        const compliance = validateBatteryCompliance(result);
                        expect(compliance.compliant).toBe(true);
                        expect(compliance.violations).toEqual([]);
                });
        });

        describe("generateBatteryReport", () => {
                it("should generate a readable text report", () => {
                        const result = calculateBatteryRequirements(validInput);
                        const report = generateBatteryReport(result);
                        expect(report).toContain("NFPA 72 BATTERY CALCULATION REPORT");
                        expect(report).toContain("DEVICE BREAKDOWN");
                        expect(report).toContain("CALCULATION");
                        expect(report).toContain("RESULT");
                        expect(report).toContain("COMPLIANCE");
                });

                it("should include the required capacity in the report", () => {
                        const result = calculateBatteryRequirements(validInput);
                        const report = generateBatteryReport(result);
                        expect(report).toContain("Required Capacity:");
                        expect(report).toContain("Ah");
                });

                it("should show PASS for compliant calculations", () => {
                        const result = calculateBatteryRequirements(validInput);
                        const report = generateBatteryReport(result);
                        expect(report).toContain("PASSED");
                });
        });

        describe("getNFPA27_6_2Requirements", () => {
                it("should return a list of NFPA 72 §27.6.2 requirements", () => {
                        const reqs = getNFPA27_6_2Requirements();
                        expect(reqs.length).toBeGreaterThan(5);
                        expect(reqs).toContain(
                                "Minimum 24 hours of standby operation",
                        );
                        expect(reqs).toContain(
                                "Minimum 5 minutes of alarm operation",
                        );
                });

                it("should include the safety factor recommendation", () => {
                        const reqs = getNFPA27_6_2Requirements();
                        expect(reqs).toContainEqual(
                                expect.stringContaining("20% safety factor"),
                        );
                });

                it("should reference NFPA 72 §27.6.2", () => {
                        const reqs = getNFPA27_6_2Requirements();
                        expect(reqs).toContainEqual(
                                expect.stringContaining("NFPA 72 §27.6.2"),
                        );
                });
        });
});
