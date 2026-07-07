/**
 * CoverageEngine.ts - NFPA 72 Coverage Calculation Engine
 * Calculates detector coverage per NFPA 72 requirements
 */

interface Room {
	id: string;
	name: string;
	width: number;
	length: number;
	height: number;
	ceilingType: "flat" | "sloped" | "coffered";
	occupancy: string;
}

interface Detector {
	id: string;
	roomId: string;
	type: "smoke" | "heat" | "rate-of-rise" | "flame-detector";
	x: number;
	y: number;
	coverageRadius: number;
	sensitivity: "high" | "standard" | "low";
}

interface CoverageResult {
	roomId: string;
	roomName: string;
	detectorCount: number;
	coveragePercentage: number;
	pass: boolean;
	uncoveredAreas: { x: number; y: number; area: number }[];
	nfpaReference: string;
}

interface CoverageCalculation {
	summary: {
		totalRooms: number;
		totalDetectors: number;
		coveragePercentage: number;
		passedRooms: number;
		failedRooms: number;
	};
	roomResults: CoverageResult[];
}

/**
 * Get NFPA 72 reference based on detector type and ceiling height
 */
function getNFPASpacingReference(room: Room, detectors: Detector[]): string {
	// Check if heat detectors are present
	const hasHeatDetector = detectors.some((d) => d.type === "heat");

	if (hasHeatDetector) {
		return "NFPA 72 §17.7.5"; // Heat detector spacing
	}

	// Smoke detectors - reference ceiling height table
	if (room.height <= 3.0) {
		return "NFPA 72 Table 17.6.3.1.1 (h≤3.0m)"; // ≤10 ft
	} else if (room.height <= 3.7) {
		return "NFPA 72 Table 17.6.3.1.1 (3.0m<h≤3.7m)"; // 10-12 ft
	} else if (room.height <= 4.3) {
		return "NFPA 72 Table 17.6.3.1.1 (3.7m<h≤4.3m)"; // 12-14 ft
	} else if (room.height <= 6.1) {
		return "NFPA 72 Table 17.6.3.1.1 (4.3m<h≤6.1m)"; // 14-20 ft
	} else {
		return "NFPA 72 §17.7.4.2.3.1"; // For heights >20 ft, AHJ approval required
	}
}

/**
 * Get 0.7S Rule reference
 */
function get0_7SRuleReference(): string {
	return "NFPA 72 §17.7.4.2.3.1"; // R = 0.7 × S Rule
}

/**
 * Get occupancy coverage requirement
 */
function getOccupancyRequirement(occupancy: string): {
	minCoverage: number;
	reference: string;
} {
	const occ = occupancy.toLowerCase();

	if (occ.includes("high") || occ.includes("hazard")) {
		return { minCoverage: 90, reference: "NFPA 72 §17.7.5.2.2" };
	} else if (occ.includes("ordinary") || occ.includes("business")) {
		return { minCoverage: 70, reference: "NFPA 72 §17.7.5.2.2" };
	} else {
		return { minCoverage: 70, reference: "NFPA 72 §17.7.5.2.2" };
	}
}

/**
 * Calculate coverage for a single room
 */
export function calculateRoomCoverage(
	room: Room,
	detectors: Detector[],
): CoverageResult {
	// Create grid for coverage calculation
	const gridSize = 0.5;
	const cols = Math.ceil(room.width / gridSize);
	const rows = Math.ceil(room.length / gridSize);

	const grid: boolean[][] = Array(rows)  // NOSONAR - typescript:S7723
		.fill(null)
		.map(() => Array(cols).fill(false));  // NOSONAR - typescript:S7723

	// Mark covered areas
	detectors.forEach((detector) => {
		const centerX = detector.x / gridSize;
		const centerY = detector.y / gridSize;
		const radiusInGrid = detector.coverageRadius / gridSize;
		const radiusSquared = radiusInGrid * radiusInGrid;

		for (let row = 0; row < rows; row++) {
			for (let col = 0; col < cols; col++) {
				const dx = col - centerX;
				const dy = row - centerY;
				const distanceSquared = dx * dx + dy * dy;

				if (distanceSquared <= radiusSquared) {
					grid[row][col] = true;
				}
			}
		}
	});

	// Count coverage
	let coveredCells = 0;
	const uncoveredAreas: { x: number; y: number; area: number }[] = [];

	for (let row = 0; row < rows; row++) {
		for (let col = 0; col < cols; col++) {
			if (grid[row][col]) {
				coveredCells++;
			} else {
				uncoveredAreas.push({
					x: col * gridSize,
					y: row * gridSize,
					area: gridSize * gridSize,
				});
			}
		}
	}

	const totalCells = rows * cols;
	const coveragePercentage =
		totalCells > 0 ? (coveredCells / totalCells) * 100 : 0;

	// Check compliance
	const { minCoverage, reference } = getOccupancyRequirement(room.occupancy);
	const pass = coveragePercentage >= minCoverage;

	// Get appropriate NFPA reference
	const spacingReference = getNFPASpacingReference(room, detectors);
	const ruleReference = get0_7SRuleReference();

	// Combine references
	const nfpaReference = `${spacingReference}; ${ruleReference}; ${reference}`;

	return {
		roomId: room.id,
		roomName: room.name,
		detectorCount: detectors.length,
		coveragePercentage: parseFloat(coveragePercentage.toFixed(2)),  // NOSONAR - typescript:S7773
		pass,
		uncoveredAreas,
		nfpaReference,
	};
}

/**
 * Calculate coverage for multiple rooms
 */
export function calculateCoverage(
	rooms: Room[],
	detectors: Detector[],
): CoverageCalculation {
	const roomResults: CoverageResult[] = [];

	rooms.forEach((room) => {
		const roomDetectors = detectors.filter((d) => d.roomId === room.id);
		const result = calculateRoomCoverage(room, roomDetectors);
		roomResults.push(result);
	});

	const totalRooms = rooms.length;
	const totalDetectors = detectors.length;
	const passedRooms = roomResults.filter((r) => r.pass).length;
	const failedRooms = roomResults.filter((r) => !r.pass).length;
	const overallCoverage =
		roomResults.reduce((sum, r) => sum + r.coveragePercentage, 0) / totalRooms;

	return {
		summary: {
			totalRooms,
			totalDetectors,
			coveragePercentage: parseFloat(overallCoverage.toFixed(2)),  // NOSONAR - typescript:S7773
			passedRooms,
			failedRooms,
		},
		roomResults,
	};
}

/**
 * Generate detailed coverage report
 */
export function generateCoverageReport(
	calculation: CoverageCalculation,
): string {
	let report = "";
	report += "═══════════════════════════════════════════════════\n";
	report += "       NFPA 72 COVERAGE ANALYSIS REPORT\n";
	report += "═══════════════════════════════════════════════════\n\n";

	report += "SUMMARY:\n";
	report += "─────────────────────────────────────────────────\n";
	report += `Total Rooms:          ${calculation.summary.totalRooms}\n`;
	report += `Total Detectors:      ${calculation.summary.totalDetectors}\n`;
	report += `Overall Coverage:     ${calculation.summary.coveragePercentage}%\n`;
	report += `Passed Rooms:         ${calculation.summary.passedRooms}\n`;
	report += `Failed Rooms:         ${calculation.summary.failedRooms}\n\n`;

	report += "ROOM-BY-ROOM BREAKDOWN:\n";
	report += "─────────────────────────────────────────────────\n";

	calculation.roomResults.forEach((result) => {
		report += `\nRoom: ${result.roomName}\n`;
		report += `  Detectors: ${result.detectorCount}\n`;
		report += `  Coverage: ${result.coveragePercentage}%\n`;
		report += `  Status: ${result.pass ? "✅ PASS" : "❌ FAIL"}\n`;
		report += `  NFPA Reference: ${result.nfpaReference}\n`;
		report += `  Uncovered Areas: ${result.uncoveredAreas.length}\n`;
	});

	report += "\nCOMPLIANCE NOTES:\n";
	report += "─────────────────────────────────────────────────\n";
	report += "Per NFPA 72 2022 Edition:\n";
	report += "- Table 17.6.3.1.1: Coverage radius by ceiling height\n";
	report += "- §17.7.4.2.3.1: 0.7S Rule (R = 0.7 × S)\n";
	report += "- §17.7.5: Heat detector spacing requirements\n";
	report += "- §17.7.5.2.2: Coverage requirements by occupancy\n";

	return report;
}

/**
 * Validate detector placement
 */
export function validateDetectorPlacement(
	room: Room,
	detectors: Detector[],
): {
	compliant: boolean;
	warnings: string[];
	errors: string[];
} {
	const warnings: string[] = [];
	const errors: string[] = [];

	detectors.forEach((detector) => {
		// Check bounds
		if (detector.x > room.width || detector.y > room.length) {
			errors.push(`Detector ${detector.id} is outside room boundaries`);
		}

		// Check wall distance
		if (
			detector.x < 0.5 ||
			detector.y < 0.5 ||
			detector.x > room.width - 0.5 ||
			detector.y > room.length - 0.5
		) {
			warnings.push(
				`Detector ${detector.id} is close to wall (less than 0.5m)`,
			);
		}

		// Check coverage radius for ceiling height
		if (detector.type === "smoke" && room.height > 3.0) {
			// Warning for elevated ceilings
			warnings.push(
				`Smoke detector ${detector.id} at ceiling height ${room.height}m - verify spacing per Table 17.6.3.1.1`,
			);
		}
	});

	return {
		compliant: errors.length === 0,
		warnings,
		errors,
	};
}
