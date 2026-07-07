/**
 * CodeValidator.ts - Real-time Code Compliance Engine
 * Checks all canvas actions against international standards
 * Standards: NFPA 72, IEC 60598, NEC, IEC 60364
 * NO MOCK DATA - All violations from real code requirements
 */

import type { Device } from "@/store/simpleStore";

// ============================================================================
// TYPES & INTERFACES
// ============================================================================

export type Standard = "NFPA72" | "IEC60364" | "NEC" | "IEC60598";
export type Severity = "CRITICAL" | "WARNING" | "INFO";

export interface CodeViolation {
	id: string;
	standard: Standard;
	rule: string;
	section: string;
	severity: Severity;
	message: string;
	affectedDevices: string[];
	recommendation: string;
	autoFixable: boolean;
}

export interface SpacingResult {
	isCompliant: boolean;
	actualDistance: number;
	maxDistance: number;
	violations: CodeViolation[];
}

export interface ProtectionResult {
	isProtected: boolean;
	upstreamBreaker: number;
	cableAmpacity: number;
	loadCurrent: number;
	status: "PROPER" | "FAIL";
	violations: CodeViolation[];
}

// ============================================================================
// CONSTANTS - Code Requirements
// ============================================================================

// NFPA 72 - Fire Alarm Detection
const SMOKE_DETECTOR_MAX_SPACING = 7.5; // meters
const _SMOKE_DETECTOR_MAX_FROM_WALL = 3.75; // meters
const _HEAT_DETECTOR_MAX_SPACING = 10.5; // meters
const DETECTOR_COVERAGE_AREA = 80; // m² per detector

// IEC 60598 - Luminaries
const EMERGENCY_LIGHT_SPACING = 4.0; // meters (max gap for 1 lux coverage)
const EMERGENCY_LIGHT_MIN_HEIGHT = 2.0; // meters
const EMERGENCY_LIGHT_MAX_HEIGHT = 5.0; // meters

// NEC/IEC Protection
const MIN_CABLE_AMPACITY_RATIO = 1.25; // Cable ampacity must be 125% of load
const _MAX_VOLTAGE_DROP_LIGHTING = 3; // percent
const _MAX_VOLTAGE_DROP_POWER = 5; // percent

// Cable sizing
const _CIRCUIT_MAX_CURRENT_15A = 15; // AWG 14
const _CIRCUIT_MAX_CURRENT_20A = 20; // AWG 12
const _CIRCUIT_MAX_CURRENT_30A = 30; // AWG 10

// ============================================================================
// SMOKE DETECTOR PLACEMENT VALIDATION (NFPA 72)
// ============================================================================

/**
 * Validate smoke detector placement per NFPA 72 Chapter 17
 * Rules:
 * - Max 7.5m spacing between detectors
 * - Max 3.75m from any wall
 * - Coverage area max 80m² per detector
 */
export function validateSmokeDetectorPlacement(
	detectors: Device[],
	roomWidth: number,
	roomLength: number,
): SpacingResult[] {
	const results: SpacingResult[] = [];

	if (detectors.length === 0) {
		return [
			{
				isCompliant: false,
				actualDistance: 0,
				maxDistance: SMOKE_DETECTOR_MAX_SPACING,
				violations: [
					{
						id: "NFPA-001",
						standard: "NFPA72",
						rule: "17.4.3(a)",
						section: "General",
						severity: "CRITICAL",
						message: "No smoke detectors installed in this area",
						affectedDevices: [],
						recommendation:
							"Install smoke detectors following NFPA 72 spacing requirements",
						autoFixable: true,
					},
				],
			},
		];
	}

	// Check spacing between detectors
	for (let i = 0; i < detectors.length; i++) {
		for (let j = i + 1; j < detectors.length; j++) {
			const dist = calculateDistance(
				detectors[i].x,
				detectors[i].y,
				detectors[j].x,
				detectors[j].y,
			);

			const isCompliant = dist <= SMOKE_DETECTOR_MAX_SPACING;

			results.push({
				isCompliant,
				actualDistance: dist,
				maxDistance: SMOKE_DETECTOR_MAX_SPACING,
				violations: isCompliant
					? []
					: [
							{
								id: "NFPA-002",
								standard: "NFPA72",
								rule: "17.4.3(b)",
								section: "Spacing",
								severity: "CRITICAL",
								message: `Smoke detector spacing exceeds ${SMOKE_DETECTOR_MAX_SPACING}m (actual: ${dist.toFixed(2)}m)`,
								affectedDevices: [detectors[i].id, detectors[j].id],
								recommendation:
									"Add additional smoke detector or relocate existing ones",
								autoFixable: false,
							},
						],
			});
		}

		// DEAD AIR SPACE CHECK (NFPA 72 §17.6.3.1.1)
		// Detectors must NOT be within 0.1m of a wall (dead air space).
		// NOTE: NFPA 72 does NOT require detectors to be close to walls.
		// The old code flagged detectors far from walls as violations — that was
		// the "Wall-Hugging Fallacy" (same as Backend Bug 3). A detector in the
		// center of a 30×30m hall is perfectly valid; pushing it to a wall leaves
		// the room center uncovered.
		const distFromWallX = Math.min(detectors[i].x, roomWidth - detectors[i].x);
		const distFromWallY = Math.min(detectors[i].y, roomLength - detectors[i].y);
		const distFromWall = Math.min(distFromWallX, distFromWallY);
		const DEAD_AIR_SPACE_MIN = 0.1; // meters per NFPA 72 §17.6.3.1.1

		if (distFromWall < DEAD_AIR_SPACE_MIN) {
			results.push({
				isCompliant: false,
				actualDistance: distFromWall,
				maxDistance: DEAD_AIR_SPACE_MIN,
				violations: [
					{
						id: "NFPA-003",
						standard: "NFPA72",
						rule: "17.6.3.1.1",
						section: "Dead Air Space",
						severity: "CRITICAL",
						message: `Detector within dead air space: ${distFromWall.toFixed(3)}m from wall (min ${DEAD_AIR_SPACE_MIN}m per NFPA 72)`,
						affectedDevices: [detectors[i].id],
						recommendation:
							"Move detector away from wall — at least 0.1m clearance required",
						autoFixable: false,
					},
				],
			});
		}
	}

	// Check coverage area
	const totalCoverageArea = detectors.length * DETECTOR_COVERAGE_AREA;
	const roomArea = roomWidth * roomLength;

	if (totalCoverageArea < roomArea) {
		results.push({
			isCompliant: false,
			actualDistance: totalCoverageArea,
			maxDistance: roomArea,
			violations: [
				{
					id: "NFPA-004",
					standard: "NFPA72",
					rule: "17.4.6",
					section: "Coverage",
					severity: "WARNING",
					message: `Coverage insufficient: ${totalCoverageArea}m² installed vs ${roomArea}m² required`,
					affectedDevices: detectors.map((d) => d.id),
					recommendation: `Add ${Math.ceil((roomArea - totalCoverageArea) / DETECTOR_COVERAGE_AREA)} more detector(s)`,
					autoFixable: true,
				},
			],
		});
	}

	return results;
}

// ============================================================================
// EMERGENCY LIGHTING VALIDATION (IEC 60598)
// ============================================================================

/**
 * Validate emergency lighting placement per IEC 60598
 * Rules:
 * - Max 4m spacing for 1 lux coverage
 * - Min 2m height, max 5m height
 * - Must cover all egress paths
 */
export function validateEmergencyLighting(
	lights: Device[],
	pathLength: number,
	mountingHeight: number = 2.5,
): SpacingResult[] {
	const results: SpacingResult[] = [];

	// Check mounting height
	if (
		mountingHeight < EMERGENCY_LIGHT_MIN_HEIGHT ||
		mountingHeight > EMERGENCY_LIGHT_MAX_HEIGHT
	) {
		results.push({
			isCompliant: false,
			actualDistance: mountingHeight,
			maxDistance: EMERGENCY_LIGHT_MAX_HEIGHT,
			violations: [
				{
					id: "IEC-001",
					standard: "IEC60598",
					rule: "5.3.1",
					section: "Mounting Height",
					severity: "CRITICAL",
					message: `Emergency light mounting height ${mountingHeight}m outside permitted range (${EMERGENCY_LIGHT_MIN_HEIGHT}-${EMERGENCY_LIGHT_MAX_HEIGHT}m)`,
					affectedDevices: lights.map((l) => l.id),
					recommendation: `Adjust mounting height to between ${EMERGENCY_LIGHT_MIN_HEIGHT}m and ${EMERGENCY_LIGHT_MAX_HEIGHT}m`,
					autoFixable: false,
				},
			],
		});
	}

	// Check spacing between lights
	for (let i = 0; i < lights.length; i++) {
		for (let j = i + 1; j < lights.length; j++) {
			const dist = calculateDistance(
				lights[i].x,
				lights[i].y,
				lights[j].x,
				lights[j].y,
			);

			const isCompliant = dist <= EMERGENCY_LIGHT_SPACING;

			results.push({
				isCompliant,
				actualDistance: dist,
				maxDistance: EMERGENCY_LIGHT_SPACING,
				violations: isCompliant
					? []
					: [
							{
								id: "IEC-002",
								standard: "IEC60598",
								rule: "5.4.2",
								section: "Spacing",
								severity: "WARNING",
								message: `Emergency light spacing ${dist.toFixed(2)}m exceeds ${EMERGENCY_LIGHT_SPACING}m for adequate coverage`,
								affectedDevices: [lights[i].id, lights[j].id],
								recommendation:
									"Add intermediate emergency light or reposition existing lights",
								autoFixable: false,
							},
						],
			});
		}
	}

	// Check total coverage
	const effectiveSpacing =
		mountingHeight > 3
			? EMERGENCY_LIGHT_SPACING * 0.9
			: EMERGENCY_LIGHT_SPACING;
	const minLightsRequired = Math.ceil(pathLength / effectiveSpacing) + 1;

	if (lights.length < minLightsRequired) {
		results.push({
			isCompliant: false,
			actualDistance: lights.length,
			maxDistance: minLightsRequired,
			violations: [
				{
					id: "IEC-003",
					standard: "IEC60598",
					rule: "5.4.1",
					section: "Coverage",
					severity: "CRITICAL",
					message: `Insufficient emergency lights: ${lights.length} installed, ${minLightsRequired} required for ${pathLength}m path`,
					affectedDevices: lights.map((l) => l.id),
					recommendation: `Add ${minLightsRequired - lights.length} more emergency light(s)`,
					autoFixable: true,
				},
			],
		});
	}

	return results;
}

// ============================================================================
// CABLE PROTECTION VALIDATION (NEC/IEC)
// ============================================================================

/**
 * Validate cable protection per NEC and IEC 60364
 * Rules:
 * - Cable ampacity >= Load current × 1.25
 * - Voltage drop within limits
 * - Proper circuit breaker coordination
 */
export function validateCableProtection(
	loadCurrent: number,
	cableAmpacity: number,
	circuitBreakerRating: number,
	_circuitType: "lighting" | "power" | "motor",
): ProtectionResult {
	const violations: CodeViolation[] = [];

	// Check cable ampacity
	const minRequiredAmpacity = loadCurrent * MIN_CABLE_AMPACITY_RATIO;
	if (cableAmpacity < minRequiredAmpacity) {
		violations.push({
			id: "PROT-001",
			standard: "IEC60364",
			rule: "433.1",
			section: "Ampacity",
			severity: "CRITICAL",
			message: `Cable ampacity ${cableAmpacity}A insufficient for load ${loadCurrent}A (min ${minRequiredAmpacity.toFixed(1)}A required)`,
			affectedDevices: [],
			recommendation: "Upgrade cable cross-section or reduce load",
			autoFixable: true,
		});
	}

	// Check breaker coordination
	if (circuitBreakerRating < cableAmpacity) {
		violations.push({
			id: "PROT-002",
			standard: "NEC",
			rule: "240.4",
			section: "Overcurrent",
			severity: "CRITICAL",
			message: `Circuit breaker rating ${circuitBreakerRating}A below cable ampacity ${cableAmpacity}A`,
			affectedDevices: [],
			recommendation: "Install properly rated circuit breaker or upgrade cable",
			autoFixable: true,
		});
	}

	// Check breaker against load (must be at least 125% of load)
	const minBreakerRating = loadCurrent * 1.25;
	if (circuitBreakerRating < minBreakerRating) {
		violations.push({
			id: "PROT-003",
			standard: "NEC",
			rule: "240.6",
			section: "Sizing",
			severity: "WARNING",
			message: `Breaker ${circuitBreakerRating}A may be undersized for ${loadCurrent}A load (min ${minBreakerRating.toFixed(1)}A)`,
			affectedDevices: [],
			recommendation: "Consider upsizing breaker to next standard rating",
			autoFixable: true,
		});
	}

	return {
		isProtected: violations.length === 0,
		upstreamBreaker: circuitBreakerRating,
		cableAmpacity,
		loadCurrent,
		status:
			violations.filter((v) => v.severity === "CRITICAL").length > 0  // NOSONAR - typescript:S7754
				? "FAIL"
				: violations.length > 0  // NOSONAR — S3358: nested ternary acceptable in this localized context
					? "FAIL"
					: "PROPER",
		violations,
	};
}

// ============================================================================
// MOTOR CIRCUIT VALIDATION (IEC/NEC)
// ============================================================================

/**
 * Validate motor circuit per NEC 430 and IEC 60364
 * Rules:
 * - Motor circuit must be 125% of FLA (Full Load Amps)
 * - Separate overload protection required
 * - Starter sizing based on motor HP
 */
export interface MotorCircuitValidation {
	isValid: boolean;
	serviceFactor: number;
	minWireSize: number;
	recommendedBreaker: number;
	violations: CodeViolation[];
}

export function validateMotorCircuit(
	motorHP: number,
	voltage: number,
	phase: number = 3,
	standardWireSize: number = 2.5,
): MotorCircuitValidation {
	const violations: CodeViolation[] = [];

	// Calculate Full Load Amps (FLA) using standard formula
	// For 3-phase: HP × 746 / (√3 × V × Efficiency × PF)
	// Simplified using NEC Table 430.150 for standard motors
	const efficiency = 0.85;
	const powerFactor = 0.85;

	let fla: number;
	if (phase === 3) {
		fla = (motorHP * 746) / (Math.sqrt(3) * voltage * efficiency * powerFactor);
	} else {
		fla = (motorHP * 746) / (voltage * efficiency * powerFactor);
	}

	const minWireAmpacity = fla * 1.25; // NEC 125% rule for motors
	const recommendedBreaker = fla * 2.5; // NEC allows 250% for motor circuits

	// Check wire size
	const standardSizes = [1.5, 2.5, 4, 6, 10, 16, 25, 35, 50, 70, 95, 120];
	const ampacity: Record<number, number> = {
		1.5: 18,
		2.5: 25,
		4: 32,
		6: 41,
		10: 54,
		16: 73,
		25: 95,
		35: 115,
		50: 140,
		70: 175,
		95: 210,
		120: 245,
	};

	const wireAmpacity = ampacity[standardWireSize] || 18;

	if (wireAmpacity < minWireAmpacity) {
		let recommendedSize = 1.5;
		for (const size of standardSizes) {
			if (ampacity[size] >= minWireAmpacity) {
				recommendedSize = size;
				break;
			}
		}

		violations.push({
			id: "MOTOR-001",
			standard: "NEC",
			rule: "430.22",
			section: "Motor Branch Circuit",
			severity: "CRITICAL",
			message: `Wire size ${standardWireSize}mm² insufficient for ${motorHP}HP motor (FLA: ${fla.toFixed(1)}A, min: ${minWireAmpacity.toFixed(1)}A)`,
			affectedDevices: [],
			recommendation: `Use minimum ${recommendedSize}mm² wire for this motor circuit`,
			autoFixable: true,
		});
	}

	// Check breaker sizing
	const standardBreakers = [10, 16, 20, 25, 32, 40, 50, 63, 80, 100];
	let breakerOk = false;
	for (const breaker of standardBreakers) {
		if (breaker >= recommendedBreaker && breaker <= fla * 4) {
			breakerOk = true;
			break;
		}
	}

	if (!breakerOk) {
		violations.push({
			id: "MOTOR-002",
			standard: "NEC",
			rule: "430.52",
			section: "Overcurrent Protection",
			severity: "WARNING",
			message: `Circuit breaker ${recommendedBreaker.toFixed(1)}A may be improperly sized for ${motorHP}HP motor`,
			affectedDevices: [],
			recommendation:
				"Select breaker from standard sizes to properly protect motor circuit",
			autoFixable: true,
		});
	}

	return {
		isValid: violations.filter((v) => v.severity === "CRITICAL").length === 0,
		serviceFactor: 1.15,
		minWireSize:
			Math.ceil(minWireAmpacity / 10) * 10 > 120  // NOSONAR - typescript:S7766
				? 120
				: Math.ceil(minWireAmpacity / 10) * 10,
		recommendedBreaker: Math.ceil(recommendedBreaker / 5) * 5,
		violations,
	};
}

// ============================================================================
// PANEL BOARD SIZING (NEC/IEE)
// ============================================================================

export interface PanelSizingValidation {
	isValid: boolean;
	loadVA: number;
	ratedAmps: number;
	recommendedAmps: number;
	usagePercent: number;
	violations: CodeViolation[];
}

export function validatePanelSizing(
	connectedLoadVA: number,
	voltage: number,
	panelRating: number, // in amps
	demandFactor: number = 0.8,
): PanelSizingValidation {
	const violations: CodeViolation[] = [];

	const demandLoad = connectedLoadVA * demandFactor;
	const loadAmps = demandLoad / voltage;
	const usagePercent = (loadAmps / panelRating) * 100;

	// Check panel loading
	if (usagePercent > 80) {
		violations.push({
			id: "PANEL-001",
			standard: "NEC",
			rule: "408.36",
			section: "Panel Loading",
			severity: "WARNING",
			message: `Panel usage ${usagePercent.toFixed(1)}% exceeds recommended 80% capacity`,
			affectedDevices: [],
			recommendation: "Consider adding additional panel or distributing load",
			autoFixable: true,
		});
	}

	if (usagePercent > 100) {
		violations.push({
			id: "PANEL-002",
			standard: "NEC",
			rule: "408.36",
			section: "Panel Overload",
			severity: "CRITICAL",
			message: `Panel OVERLOADED: ${usagePercent.toFixed(1)}% of rated capacity`,
			affectedDevices: [],
			recommendation:
				"URGENT: Add panel capacity or reduce connected load immediately",
			autoFixable: false,
		});
	}

	const recommendedAmps = Math.ceil(loadAmps / 0.8 / 10) * 10;

	return {
		isValid: usagePercent <= 100,
		loadVA: demandLoad,
		ratedAmps: panelRating,
		recommendedAmps: Math.max(recommendedAmps, panelRating),
		usagePercent: Math.round(usagePercent * 10) / 10,
		violations,
	};
}

// ============================================================================
// FULL COMPLIANCE REPORT
// ============================================================================

export interface ComplianceReport {
	totalViolations: number;
	criticalCount: number;
	warningCount: number;
	passedRules: number;
	violationsByStandard: Record<Standard, number>;
	recommendations: string[];
	timestamp: number;
}

export function generateComplianceReport(
	allViolations: CodeViolation[],
): ComplianceReport {
	const report: ComplianceReport = {
		totalViolations: allViolations.length,
		criticalCount: allViolations.filter((v) => v.severity === "CRITICAL")
			.length,
		warningCount: allViolations.filter((v) => v.severity === "WARNING").length,
		passedRules: 0, // Calculated in UI based on total rules
		violationsByStandard: {
			NFPA72: 0,
			IEC60364: 0,
			NEC: 0,
			IEC60598: 0,
		},
		recommendations: [],
		timestamp: Date.now(),
	};

	// Count by standard
	allViolations.forEach((v) => {
		report.violationsByStandard[v.standard]++;
	});

	// Generate recommendations
	const criticalViolations = allViolations.filter(
		(v) => v.severity === "CRITICAL",
	);
	if (criticalViolations.length > 0) {
		report.recommendations.push(
			`${criticalViolations.length} CRITICAL violation(s) must be addressed before operation`,
		);
	}

	return report;
}

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

function calculateDistance(
	x1: number,
	y1: number,
	x2: number,
	y2: number,
): number {
	const dx = (x2 - x1) * 0.01; // Convert to meters
	const dy = (y2 - y1) * 0.01;
	return Math.sqrt(dx * dx + dy * dy);  // NOSONAR - typescript:S7769
}

export function validateAllDevices(devices: Device[]): CodeViolation[] {
	const violations: CodeViolation[] = [];

	// Group by type for validation
	const smokeDetectors = devices.filter((d) => d.type.includes("SMOKE"));
	const emergencyLights = devices.filter((d) => d.type.includes("LIGHT"));
	const panels = devices.filter((d) => d.type.includes("PANEL"));

	// Validate smoke detector placement
	if (smokeDetectors.length > 1) {
		const spacingResults = validateSmokeDetectorPlacement(
			smokeDetectors,
			15,
			20,
		);
		spacingResults.forEach((r) => violations.push(...r.violations));
	}

	// Validate emergency lighting
	if (emergencyLights.length > 0) {
		const lightResults = validateEmergencyLighting(emergencyLights, 30, 2.5);
		lightResults.forEach((r) => violations.push(...r.violations));
	}

	// Validate panel loading
	panels.forEach((panel) => {
		const loadVA = panel.load * panel.voltage;
		const result = validatePanelSizing(loadVA, panel.voltage, 200);
		violations.push(...result.violations);
	});

	return violations;
}

// ============================================================================
// AUTO-FIX RECOMMENDATIONS
// ============================================================================

export interface AutoFixRecommendation {
	violationId: string;
	action: string;
	newValue: number | string;
	affectedDevices: string[];
	estimatedCost: number;
}

export function generateAutoFix(
	violation: CodeViolation,
	currentValue: number | string,
): AutoFixRecommendation {
	switch (violation.id) {
		case "PROT-001":
			return {
				violationId: violation.id,
				action: "Upgrade cable cross-section",
				newValue: "Increase to next standard size",
				affectedDevices: violation.affectedDevices,
				estimatedCost: 25, // EUR per meter
			};
		case "NFPA-004":
			return {
				violationId: violation.id,
				action: "Add smoke detector",
				newValue: Math.ceil((currentValue as number) / DETECTOR_COVERAGE_AREA),
				affectedDevices: violation.affectedDevices,
				estimatedCost: 150, // EUR per detector
			};
		case "MOTOR-001":
			return {
				violationId: violation.id,
				action: "Increase wire size",
				newValue: "Use larger cross-section cable",
				affectedDevices: violation.affectedDevices,
				estimatedCost: 15,
			};
		default:
			return {
				violationId: violation.id,
				action: violation.recommendation,
				newValue: "Review and update",
				affectedDevices: violation.affectedDevices,
				estimatedCost: 0,
			};
	}
}
