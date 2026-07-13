/**
 * CodeValidator.test.ts — Unit tests for the code compliance engine.
 *
 * V244: Safety-critical module — validates designs against NFPA 72, IEC 60364,
 * NEC, and IEC 60598 standards.
 */
import { describe, expect, it } from "vitest";
import type { Device } from "@/store/simpleStore";
import {
        validateAllDevices,
        validateCableProtection,
        validateEmergencyLighting,
        validateSmokeDetectorPlacement,
} from "@/engine/CodeValidator";

// ── Test Fixtures ──────────────────────────────────────────────────────────

function makeDevice(overrides: Partial<Device> = {}): Device {
        return {
                id: "dev-1",
                type: "SENSOR_SMOKE",
                x: 5,
                y: 5,
                load: 0,
                voltage: 24,
                ...overrides,
        };
}

// ── Tests ──────────────────────────────────────────────────────────────────

describe("CodeValidator", () => {
        describe("validateSmokeDetectorPlacement", () => {
                it("should return a CRITICAL violation when no detectors are provided", () => {
                        const results = validateSmokeDetectorPlacement([], 10, 10);
                        expect(results).toHaveLength(1);
                        expect(results[0].isCompliant).toBe(false);
                        expect(results[0].violations[0].severity).toBe("CRITICAL");
                        expect(results[0].violations[0].message).toContain(
                                "No smoke detectors installed",
                        );
                });

                it("should pass when two detectors are within max spacing (≤7.5m)", () => {
                        const d1 = makeDevice({ id: "d1", x: 0, y: 0 });
                        const d2 = makeDevice({ id: "d2", x: 5, y: 0 });
                        const results = validateSmokeDetectorPlacement([d1, d2], 10, 10);
                        // At least one result should be compliant
                        expect(results.some((r) => r.isCompliant)).toBe(true);
                });

                it("should flag a violation when detectors exceed max spacing (>7.5m)", () => {
                        const d1 = makeDevice({ id: "d1", x: 0, y: 0 });
                        const d2 = makeDevice({ id: "d2", x: 10, y: 0 });
                        const results = validateSmokeDetectorPlacement([d1, d2], 15, 10);
                        expect(results.some((r) => !r.isCompliant)).toBe(true);
                });

                it("should return the actual and max distance in results", () => {
                        const d1 = makeDevice({ id: "d1", x: 0, y: 0 });
                        const d2 = makeDevice({ id: "d2", x: 5, y: 0 });
                        const results = validateSmokeDetectorPlacement([d1, d2], 10, 10);
                        expect(results[0].actualDistance).toBeGreaterThan(0);
                        expect(results[0].maxDistance).toBe(7.5); // SMOKE_DETECTOR_MAX_SPACING
                });
        });

        describe("validateEmergencyLighting", () => {
                it("should flag a CRITICAL violation when mounting height is below 2.0m", () => {
                        const light = makeDevice({ id: "light-1", type: "SPEAKER", x: 0, y: 0 });
                        const results = validateEmergencyLighting([light], 10, 1.5);
                        expect(
                                results.some(
                                        (r) =>
                                                r.violations.some(
                                                        (v) =>
                                                                v.severity === "CRITICAL" &&
                                                                v.message.includes("mounting height"),
                                                ),
                                ),
                        ).toBe(true);
                });

                it("should flag a CRITICAL violation when mounting height is above 5.0m", () => {
                        const light = makeDevice({ id: "light-1", type: "SPEAKER", x: 0, y: 0 });
                        const results = validateEmergencyLighting([light], 10, 6.0);
                        expect(
                                results.some(
                                        (r) =>
                                                r.violations.some(
                                                        (v) =>
                                                                v.severity === "CRITICAL" &&
                                                                v.message.includes("mounting height"),
                                                ),
                                ),
                        ).toBe(true);
                });

                it("should flag a violation when light spacing exceeds 4.0m", () => {
                        const l1 = makeDevice({ id: "l1", type: "SPEAKER", x: 0, y: 0 });
                        const l2 = makeDevice({ id: "l2", type: "SPEAKER", x: 10, y: 0 });
                        const results = validateEmergencyLighting([l1, l2], 15, 2.5);
                        expect(results.some((r) => !r.isCompliant)).toBe(true);
                });

                it("should flag insufficient lights for path length", () => {
                        const light = makeDevice({ id: "l1", type: "SPEAKER", x: 0, y: 0 });
                        const results = validateEmergencyLighting([light], 50, 2.5);
                        // The message says "Insufficient emergency lights: X installed, Y required"
                        expect(
                                results.some(
                                        (r) =>
                                                r.violations.some(
                                                        (v) =>
                                                                v.message.includes("Insufficient") ||
                                                                v.message.includes("required"),
                                                ),
                                ),
                        ).toBe(true);
                });
        });

        describe("validateCableProtection", () => {
                it("should pass when cable ampacity is ≥125% of load current and breaker ≥ ampacity", () => {
                        // loadCurrent=10, cableAmpacity=20, breakerRating=20, circuitType="lighting"
                        // 20 >= 10 * 1.25 = 12.5 → ampacity OK
                        // 20 >= 20 → breaker OK (not below ampacity)
                        // 20 >= 10 * 1.25 = 12.5 → breaker vs load OK
                        const result = validateCableProtection(10, 20, 20, "lighting");
                        expect(result.status).toBe("PROPER");
                        expect(result.isProtected).toBe(true);
                });

                it("should fail when cable ampacity is below 125% of load current", () => {
                        // loadCurrent=10, cableAmpacity=10, breakerRating=15, circuitType="lighting"
                        // 10 < 10 * 1.25 = 12.5 → ampacity FAIL
                        const result = validateCableProtection(10, 10, 15, "lighting");
                        expect(result.status).toBe("FAIL");
                        expect(result.isProtected).toBe(false);
                });

                it("should include the actual values in the result", () => {
                        const result = validateCableProtection(10, 20, 20, "lighting");
                        expect(result.upstreamBreaker).toBe(20);
                        expect(result.cableAmpacity).toBe(20);
                        expect(result.loadCurrent).toBe(10);
                });
        });

        describe("validateAllDevices", () => {
                it("should return an array of violations for a set of devices", () => {
                        const devices = [
                                makeDevice({ id: "d1", type: "SENSOR_SMOKE", x: 0, y: 0 }),
                                makeDevice({ id: "d2", type: "SENSOR_SMOKE", x: 20, y: 20 }),
                        ];
                        const violations = validateAllDevices(devices);
                        expect(Array.isArray(violations)).toBe(true);
                });

                it("should return an empty array for an empty device list", () => {
                        const violations = validateAllDevices([]);
                        expect(violations).toEqual([]);
                });
        });
});
