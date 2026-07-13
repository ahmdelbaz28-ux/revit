/**
 * CoverageEngine.test.ts — Unit tests for the NFPA 72 coverage calculation engine.
 *
 * V244: Safety-critical module — calculates detector coverage per NFPA 72.
 */
import { describe, expect, it } from "vitest";
import {
        calculateCoverage,
        calculateRoomCoverage,
        generateCoverageReport,
        validateDetectorPlacement,
} from "@/engine/CoverageEngine";

// ── Test Fixtures ──────────────────────────────────────────────────────────

const room = {
        id: "room-1",
        name: "Office",
        width: 10,
        length: 10,
        height: 3.0,
        ceilingType: "flat" as const,
        occupancy: "ordinary",
};

const detector = {
        id: "det-1",
        roomId: "room-1",
        type: "smoke" as const,
        x: 5,
        y: 5,
        coverageRadius: 6.3, // 0.7 × 9.14m (NFPA 72 spacing)
        sensitivity: "standard" as const,
};

// ── Tests ──────────────────────────────────────────────────────────────────

describe("CoverageEngine", () => {
        describe("calculateRoomCoverage", () => {
                it("should calculate 100% coverage for a single detector in a small room", () => {
                        const smallRoom = { ...room, width: 5, length: 5 };
                        const result = calculateRoomCoverage(smallRoom, [detector]);
                        expect(result.coveragePercentage).toBeGreaterThan(90);
                        expect(result.pass).toBe(true);
                        expect(result.detectorCount).toBe(1);
                        expect(result.roomId).toBe("room-1");
                });

                it("should return 0% coverage for a room with no detectors", () => {
                        const result = calculateRoomCoverage(room, []);
                        expect(result.coveragePercentage).toBe(0);
                        expect(result.pass).toBe(false);
                        expect(result.detectorCount).toBe(0);
                        expect(result.uncoveredAreas.length).toBeGreaterThan(0);
                });

                it("should include NFPA reference in the result", () => {
                        const result = calculateRoomCoverage(room, [detector]);
                        expect(result.nfpaReference).toContain("NFPA 72");
                        expect(result.nfpaReference).toContain("§17.7.4.2.3.1"); // 0.7S Rule reference
                });

                it("should calculate partial coverage when detector doesn't cover entire room", () => {
                        const largeRoom = { ...room, width: 50, length: 50 };
                        const smallDetector = { ...detector, coverageRadius: 3.0 };
                        const result = calculateRoomCoverage(largeRoom, [smallDetector]);
                        expect(result.coveragePercentage).toBeLessThan(50);
                        expect(result.uncoveredAreas.length).toBeGreaterThan(0);
                });
        });

        describe("calculateCoverage", () => {
                it("should calculate coverage across multiple rooms", () => {
                        const room2 = { ...room, id: "room-2", name: "Hallway" };
                        const det2 = { ...detector, id: "det-2", roomId: "room-2" };
                        const result = calculateCoverage([room, room2], [detector, det2]);
                        expect(result.summary.totalRooms).toBe(2);
                        expect(result.summary.totalDetectors).toBe(2);
                        expect(result.summary.passedRooms).toBe(2);
                        expect(result.summary.failedRooms).toBe(0);
                        expect(result.roomResults).toHaveLength(2);
                });

                it("should handle a room with no detectors (fail)", () => {
                        const emptyRoom = { ...room, id: "empty", name: "Storage" };
                        const result = calculateCoverage([room, emptyRoom], [detector]);
                        expect(result.summary.totalRooms).toBe(2);
                        expect(result.summary.failedRooms).toBe(1);
                        expect(result.summary.passedRooms).toBe(1);
                });

                it("should handle empty rooms list gracefully", () => {
                        const result = calculateCoverage([], []);
                        expect(result.summary.totalRooms).toBe(0);
                        expect(result.roomResults).toEqual([]);
                });
        });

        describe("generateCoverageReport", () => {
                it("should generate a readable text report", () => {
                        const calc = calculateCoverage([room], [detector]);
                        const report = generateCoverageReport(calc);
                        expect(report).toContain("NFPA 72 COVERAGE ANALYSIS REPORT");
                        expect(report).toContain("SUMMARY");
                        expect(report).toContain("ROOM-BY-ROOM BREAKDOWN");
                        expect(report).toContain("COMPLIANCE NOTES");
                        expect(report).toContain(room.name);
                });

                it("should include coverage percentage in the report", () => {
                        const calc = calculateCoverage([room], [detector]);
                        const report = generateCoverageReport(calc);
                        expect(report).toContain("Coverage:");
                        expect(report).toContain("%");
                });
        });

        describe("validateDetectorPlacement", () => {
                it("should pass for a detector placed well within room bounds", () => {
                        const result = validateDetectorPlacement(room, [detector]);
                        expect(result.compliant).toBe(true);
                        expect(result.errors).toEqual([]);
                });

                it("should error when detector is outside room boundaries", () => {
                        const outOfBounds = { ...detector, x: 15, y: 15 };
                        const result = validateDetectorPlacement(room, [outOfBounds]);
                        expect(result.compliant).toBe(false);
                        expect(result.errors).toContainEqual(
                                expect.stringContaining("outside room boundaries"),
                        );
                });

                it("should warn when detector is too close to wall (< 0.5m)", () => {
                        const nearWall = { ...detector, x: 0.3, y: 0.3 };
                        const result = validateDetectorPlacement(room, [nearWall]);
                        expect(result.warnings).toContainEqual(
                                expect.stringContaining("close to wall"),
                        );
                });

                it("should warn for smoke detectors on ceilings > 3.0m", () => {
                        const tallRoom = { ...room, height: 4.0 };
                        const result = validateDetectorPlacement(tallRoom, [detector]);
                        expect(result.warnings).toContainEqual(
                                expect.stringContaining("verify spacing per Table 17.6.3.1.1"),
                        );
                });

                it("should handle empty detector list", () => {
                        const result = validateDetectorPlacement(room, []);
                        expect(result.compliant).toBe(true);
                        expect(result.errors).toEqual([]);
                        expect(result.warnings).toEqual([]);
                });
        });
});
