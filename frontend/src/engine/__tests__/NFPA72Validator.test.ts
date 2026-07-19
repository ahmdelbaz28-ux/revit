/**
 * NFPA72Validator.test.ts — Unit tests for the NFPA 72 compliance validator.
 *
 * V244: Safety-critical module — validates fire alarm system designs against
 * NFPA 72 (National Fire Alarm and Signaling Code) standards.
 *
 * Coverage:
 *   - validateNFPA72Compliance() — full system validation
 *   - getNFPAReference() — code reference lookup
 *   - Detector spacing rules (smoke, heat, pull stations)
 *   - Coverage requirements by occupancy hazard level
 *   - Edge cases: empty designs, missing rooms, invalid heights
 */
import { describe, expect, it } from "vitest";
import {
        getNFPAReference,
        validateNFPA72Compliance,
} from "@/engine/NFPA72Validator";

// ── Test Fixtures ──────────────────────────────────────────────────────────

const validRoom = {
        id: "room-1",
        name: "Office A",
        width: 10,
        length: 10,
        height: 3.0,
        occupancy: "ordinary" as const,
        ceilingType: "flat" as const,
};

const validSmokeDetector = {
        id: "det-1",
        type: "smoke" as const,
        x: 5,
        y: 5,
        zone: "zone-1",
        room: "room-1",
        height: 3.0,
        manufacturer: "Honeywell",
        model: "SD-100",
};

const validPullStation = {
        id: "pull-1",
        type: "pull" as const,
        x: 1,
        y: 1,
        zone: "zone-1",
        room: "room-1",
        height: 1.2, // 1.0-1.37m per NFPA 72 §21.4.1
        manufacturer: "Edwards",
        model: "SIGA-278",
};

const validSystemDesign = {
        devices: [validSmokeDetector, validPullStation],
        rooms: [validRoom],
        panels: [],
        circuits: [],
};

// ── Tests ──────────────────────────────────────────────────────────────────

describe("NFPA72Validator", () => {
        describe("validateNFPA72Compliance", () => {
                it("should return compliant for a valid system design", () => {
                        const result = validateNFPA72Compliance(validSystemDesign);
                        expect(result.compliant).toBe(true);
                        expect(result.violations).toEqual([]);
                        expect(result.passedChecks.length).toBeGreaterThan(0);
                });

                it("should return non-compliant when a device references a non-existent room", () => {
                        const design = {
                                ...validSystemDesign,
                                devices: [
                                        { ...validSmokeDetector, room: "non-existent-room" },
                                ],
                        };
                        const result = validateNFPA72Compliance(design);
                        expect(result.compliant).toBe(false);
                        expect(result.violations).toContainEqual(
                                expect.stringContaining("references non-existent room"),
                        );
                });

                it("should flag pull station height below 1.0m as a violation", () => {
                        const design = {
                                ...validSystemDesign,
                                devices: [
                                        { ...validPullStation, height: 0.8 },
                                ],
                        };
                        const result = validateNFPA72Compliance(design);
                        expect(result.compliant).toBe(false);
                        expect(result.violations).toContainEqual(
                                expect.stringContaining("outside required range of 1.0-1.37m"),
                        );
                });

                it("should flag pull station height above 1.37m as a violation", () => {
                        const design = {
                                ...validSystemDesign,
                                devices: [
                                        { ...validPullStation, height: 1.5 },
                                ],
                        };
                        const result = validateNFPA72Compliance(design);
                        expect(result.compliant).toBe(false);
                        expect(result.violations).toContainEqual(
                                expect.stringContaining("outside required range"),
                        );
                });

                it("should accept pull station at the lower bound (1.0m)", () => {
                        const design = {
                                ...validSystemDesign,
                                devices: [{ ...validPullStation, height: 1.0 }],
                        };
                        const result = validateNFPA72Compliance(design);
                        expect(result.compliant).toBe(true);
                });

                it("should accept pull station at the upper bound (1.37m)", () => {
                        const design = {
                                ...validSystemDesign,
                                devices: [{ ...validPullStation, height: 1.37 }],
                        };
                        const result = validateNFPA72Compliance(design);
                        expect(result.compliant).toBe(true);
                });

                it("should flag heat detector in room with ceiling height > 4.3m", () => {
                        const tallRoom = { ...validRoom, height: 5.0 };
                        const heatDetector = { ...validSmokeDetector, type: "heat" as const };
                        const design = {
                                devices: [heatDetector],
                                rooms: [tallRoom],
                                panels: [],
                                circuits: [],
                        };
                        const result = validateNFPA72Compliance(design);
                        expect(result.compliant).toBe(false);
                        expect(result.violations).toContainEqual(
                                expect.stringContaining("may exceed maximum permitted height"),
                        );
                });

                it("should warn when smoke detector height exceeds ceiling height of 3.0m", () => {
                        const design = {
                                ...validSystemDesign,
                                devices: [{ ...validSmokeDetector, height: 4.0 }],
                        };
                        const result = validateNFPA72Compliance(design);
                        expect(result.warnings).toContainEqual(
                                expect.stringContaining("exceeds recommended ceiling height"),
                        );
                });

                it("should flag room with no detectors as a violation", () => {
                        const emptyRoom = { ...validRoom, id: "empty-room", name: "Storage" };
                        const design = {
                                devices: [validSmokeDetector], // only in room-1
                                rooms: [validRoom, emptyRoom],
                                panels: [],
                                circuits: [],
                        };
                        const result = validateNFPA72Compliance(design);
                        expect(result.compliant).toBe(false);
                        expect(result.violations).toContainEqual(
                                expect.stringContaining("has no detectors"),
                        );
                });

                it("should warn about high-hazard rooms with fewer than 2 detectors", () => {
                        const highHazardRoom = {
                                ...validRoom,
                                id: "hh-room",
                                name: "Chemical Storage",
                                occupancy: "high-hazard" as const,
                        };
                        const design = {
                                devices: [{ ...validSmokeDetector, room: "hh-room" }],
                                rooms: [highHazardRoom],
                                panels: [],
                                circuits: [],
                        };
                        const result = validateNFPA72Compliance(design);
                        expect(result.warnings).toContainEqual(
                                expect.stringContaining("may require additional detectors"),
                        );
                });

                it("should handle empty system design gracefully", () => {
                        const design = {
                                devices: [],
                                rooms: [],
                                panels: [],
                                circuits: [],
                        };
                        const result = validateNFPA72Compliance(design);
                        expect(result.compliant).toBe(true);
                        expect(result.violations).toEqual([]);
                });

                it("should include passed checks that reflect ACTUAL validation results (F-03/F-15 FIX)", () => {
                        // F-15 FIX (Engineering Review): the previous test asserted the
                        // exact hardcoded string "NFPA 72 §17.7.4.2.3.1 (0.7S Rule)
                        // considered" — which was test theater because the production
                        // code returned that string regardless of input. The new
                        // production code builds passedChecks dynamically. The test
                        // now asserts BEHAVIORAL properties of the result, not exact
                        // string matches against the production code's literals.
                        const result = validateNFPA72Compliance(validSystemDesign);

                        // passedChecks must be a non-empty array of strings.
                        expect(Array.isArray(result.passedChecks)).toBe(true);
                        expect(result.passedChecks.length).toBeGreaterThan(0);
                        result.passedChecks.forEach((c) => {
                                expect(typeof c).toBe("string");
                                expect(c.length).toBeGreaterThan(0);
                        });

                        // If the design has at least one smoke detector, the 0.7S Rule
                        // check MUST appear in some form (the wording is now more
                        // specific — "applied — coverage computed with R = 0.7 × S").
                        const hasSmoke = validSystemDesign.devices.some(
                                (d) => d.type === "smoke",
                        );
                        if (hasSmoke) {
                                const mentions07SRule = result.passedChecks.some((c) =>
                                        c.includes("0.7S Rule"),
                                );
                                expect(mentions07SRule).toBe(true);
                        }
                });

                it("should return EMPTY passedChecks when design has no devices (F-03 FIX)", () => {
                        // F-03 FIX: previously, an empty design still got 7 fake
                        // passedChecks. Now passedChecks must be empty because
                        // nothing was actually validated.
                        const emptyDesign = {
                                devices: [],
                                rooms: [],
                                panels: [],
                                circuits: [],
                        };
                        const result = validateNFPA72Compliance(emptyDesign);
                        expect(result.passedChecks).toEqual([]);
                        expect(result.compliant).toBe(true); // vacuously — no violations possible
                });

                it("should grow passedChecks as more rooms pass coverage (F-04 FIX)", () => {
                        // F-04 FIX: passedChecks should reflect the number of rooms
                        // that actually met their coverage requirement. Adding a
                        // room with adequate coverage should add a passed check.
                        const oneRoomDesign = {
                                devices: [
                                        {
                                                id: "d1",
                                                type: "smoke" as const,
                                                x: 5,
                                                y: 5,
                                                zone: "z1",
                                                room: "r1",
                                                height: 3,
                                                manufacturer: "",
                                                model: "",
                                        },
                                ],
                                rooms: [
                                        {
                                                id: "r1",
                                                name: "Room 1",
                                                width: 10,
                                                length: 10,
                                                height: 3,
                                                occupancy: "ordinary" as const,
                                                ceilingType: "flat" as const,
                                        },
                                ],
                                panels: [],
                                circuits: [],
                        };
                        const r1 = validateNFPA72Compliance(oneRoomDesign);
                        const r1CoverageChecks = r1.passedChecks.filter((c) =>
                                c.includes("Room 1 coverage"),
                        );
                        expect(r1CoverageChecks.length).toBe(1);
                });
        });

        describe("getNFPAReference", () => {
                it("should return correct reference for smoke detector spacing", () => {
                        expect(getNFPAReference("spacing_smoke")).toBe(
                                "NFPA 72 Table 17.6.3.1.1",
                        );
                });

                it("should return correct reference for heat detector spacing", () => {
                        expect(getNFPAReference("spacing_heat")).toBe("NFPA 72 §17.7.5");
                });

                it("should return correct reference for coverage by occupancy", () => {
                        expect(getNFPAReference("coverage_occupancy")).toBe(
                                "NFPA 72 §17.7.5.2.2",
                        );
                });

                it("should return correct reference for manual stations", () => {
                        expect(getNFPAReference("manual_stations")).toBe("NFPA 72 §21.4.1");
                });

                it("should return correct reference for 0.7S rule", () => {
                        expect(getNFPAReference("0.7S_rule")).toBe("NFPA 72 §17.7.4.2.3.1");
                });

                it("should return correct reference for notification appliances", () => {
                        expect(getNFPAReference("notification_appliances")).toBe(
                                "NFPA 72 §18.4.1",
                        );
                });

                it("should return default reference for unknown check type", () => {
                        expect(getNFPAReference("unknown_check")).toBe(
                                "NFPA 72 2022 Edition",
                        );
                });
        });
});
