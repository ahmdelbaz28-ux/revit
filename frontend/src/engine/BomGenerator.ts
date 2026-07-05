/**
 * BomGenerator.ts - Automated Bill of Materials Generation
 * Generates dynamic tables based on canvas elements
 * NO MOCK DATA - All calculations from real coordinates and elements
 */

import type { CanvasElement, Connection, Device } from "@/store/simpleStore";

// ============================================================================
// TYPES & INTERFACES
// ============================================================================

export type CableType = "power" | "control" | "signal" | "fire_alarm" | "data";

export interface CableScheduleItem {
	id: string;
	from: string;
	to: string;
	length: number; // meters
	crossSection: number; // mm²
	material: "Cu" | "Al";
	type: CableType;
	estimatedWeight: number; // kg
	cost: number; // EUR
	destination: string;
}

export interface ConduitScheduleItem {
	id: string;
	size: string;
	fillRatio: number; // percentage
	cables: string[];
	totalCrossSection: number;
	recommendedSize: string;
}

export interface DeviceCountItem {
	type: string;
	category: string;
	count: number;
	avgPower: number; // W
	totalPower: number; // W
	mounting: string;
}

export interface BomSummary {
	totalCables: number;
	totalCableLength: number;
	totalConduits: number;
	totalDevices: number;
	estimatedWeight: number;
	estimatedCost: number;
	generatedAt: number;
}

// ============================================================================
// CONSTANTS
// ============================================================================

const PIXELS_TO_METERS = 0.01; // 1 pixel = 10mm = 0.01m
const SAFETY_MARGIN = 1.1; // 10% extra for bends and termination
const CABLE_WEIGHT_PER_MM2_KG = 0.009; // kg per meter per mm² (Cu)
const CABLE_COST_PER_METER = 0.15; // EUR per meter base cost

const CONDUIT_SIZES = [
	"16",
	"20",
	"25",
	"32",
	"40",
	"50",
	"63",
	"75",
	"90",
	"110",
];
const CONDUIT_AREAS: Record<string, number> = {
	"16": 78,
	"20": 133,
	"25": 230,
	"32": 387,
	"40": 582,
	"50": 862,
	"63": 1376,
	"75": 1970,
	"90": 2880,
	"110": 4210,
};
const MAX_FILL_RATIO = 0.4; // 40% fill per IEC/NEC

// ============================================================================
// CABLE LENGTH CALCULATION
// ============================================================================

/**
 * Calculate exact cable length from canvas coordinates
 * @param from - Starting device
 * @param to - Ending device
 * @returns Length in meters with safety margin
 */
export function calculateCableLength(
	fromX: number,
	fromY: number,
	toX: number,
	toY: number,
): number {
	// Euclidean distance in pixels
	const dx = toX - fromX;
	const dy = toY - fromY;
	const distancePx = Math.sqrt(dx * dx + dy * dy);

	// Convert to meters
	const lengthMeters = distancePx * PIXELS_TO_METERS;

	// Apply safety margin for termination and bends
	return Math.ceil(lengthMeters * SAFETY_MARGIN * 100) / 100;
}

// ============================================================================
// CABLE SCHEDULE GENERATION
// ============================================================================

/**
 * Generate complete cable schedule from canvas elements
 */
export function generateCableSchedule(
	canvasElements: CanvasElement[],
	devices: Device[],
	connections: Connection[],
	scale: number = PIXELS_TO_METERS,
): CableScheduleItem[] {
	const schedule: CableScheduleItem[] = [];

	// Process all connections as cables
	connections.forEach((conn, index) => {
		const fromDevice = devices.find((d) => d.id === conn.fromId);
		const toDevice = devices.find((d) => d.id === conn.toId);

		if (!fromDevice || !toDevice) return;

		const length = calculateCableLength(
			fromDevice.x,
			fromDevice.y,
			toDevice.x,
			toDevice.y,
		);

		// Determine cable type based on device types
		let cableType: CableType = "power";
		if (
			fromDevice.type.includes("SENSOR") ||
			toDevice.type.includes("SENSOR")
		) {
			cableType = "signal";
		}
		if (fromDevice.type.includes("SMOKE") || toDevice.type.includes("SMOKE")) {
			cableType = "fire_alarm";
		}

		// Calculate cross-section based on load current
		const crossSection = determineCrossSection(conn.current);

		// Calculate weight and cost
		const weight = length * crossSection * CABLE_WEIGHT_PER_MM2_KG;
		const cost = length * CABLE_COST_PER_METER * (crossSection / 2.5);

		schedule.push({
			id: `CBL-${String(index + 1).padStart(3, "0")}`,
			from: `${fromDevice.type}-${fromDevice.id.slice(-4)}`,
			to: `${toDevice.type}-${toDevice.id.slice(-4)}`,
			length,
			crossSection,
			material: "Cu",
			type: cableType,
			estimatedWeight: Math.round(weight * 100) / 100,
			cost: Math.round(cost * 100) / 100,
			destination: `Panel ${fromDevice.id.slice(-2)} to Panel ${toDevice.id.slice(-2)}`,
		});
	});

	// Sort by type and length
	return schedule.sort((a, b) => {
		if (a.type !== b.type) return a.type.localeCompare(b.type);
		return a.length - b.length;
	});
}

// ============================================================================
// CROSS SECTION DETERMINATION
// ============================================================================

/**
 * Automatically determine minimum cross-section based on current
 * Based on IEC 60364 and common practice
 */
function determineCrossSection(current: number): number {
	const crossSections = [1.5, 2.5, 4, 6, 10, 16, 25, 35, 50, 70, 95, 120];
	const ampacity = {
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

	// CRITICAL FIX: NEC/IEC requires cable ampacity >= load current × 1.25 (125% rule).
	// Previous code used `current * 0.8` which selected cables rated for only 80% of load —
	// an undersizing bug that could cause cable overheating and fire.
	// Correct: ampacity >= current * 1.25
	const minRequiredAmpacity = current * 1.25;

	for (const section of crossSections) {
		if (ampacity[section as keyof typeof ampacity] >= minRequiredAmpacity) {
			return section;
		}
	}

	return 120; // Maximum standard size
}

// ============================================================================
// CONDUIT SIZING
// ============================================================================

/**
 * Calculate required conduit size based on cable fill
 * Based on NEC Chapter 9 Table 4 (40% fill for 3+ cables)
 */
export function calculateConduitSize(
	cables: { crossSection: number; quantity: number }[],
): ConduitScheduleItem {
	// Calculate total cross-section of all cables
	let totalArea = 0;
	const cableIds: string[] = [];

	cables.forEach((cable, i) => {
		const cableArea =
			(Math.PI / 4) *
			(Math.sqrt(cable.crossSection / Math.PI) * 2 * 1.13 * 10) ** 2;
		totalArea += cableArea * cable.quantity;
		cableIds.push(`CBL-${String(i + 1).padStart(3, "0")}`);
	});

	// Convert to mm²
	const totalAreaMM2 = totalArea;

	// Find minimum conduit that allows 40% fill
	let recommendedSize = CONDUIT_SIZES[0];
	for (const size of CONDUIT_SIZES) {
		const conduitArea = CONDUIT_AREAS[size];
		if (conduitArea * MAX_FILL_RATIO >= totalAreaMM2) {
			recommendedSize = size;
			break;
		}
	}

	const actualConduitArea = CONDUIT_AREAS[recommendedSize];
	const fillRatio = (totalAreaMM2 / actualConduitArea) * 100;

	return {
		id: `COND-${String(cables.length).padStart(3, "0")}`,
		size: recommendedSize,
		fillRatio: Math.round(fillRatio * 10) / 10,
		cables: cableIds,
		totalCrossSection: Math.round(totalAreaMM2),
		recommendedSize: `MT ${recommendedSize}`,
	};
}

// ============================================================================
// DEVICE COUNTING
// ============================================================================

/**
 * Count and categorize all devices on canvas
 */
export function generateDeviceCount(devices: Device[]): DeviceCountItem[] {
	const typeGroups: Record<string, Device[]> = {};

	// Group devices by type
	devices.forEach((device) => {
		if (!typeGroups[device.type]) {
			typeGroups[device.type] = [];
		}
		typeGroups[device.type].push(device);
	});

	// Generate counts
	const counts: DeviceCountItem[] = [];

	Object.entries(typeGroups).forEach(([type, devs]) => {
		const category = categorizeDevice(type);
		const avgPower = getAveragePower(type);

		counts.push({
			type: formatDeviceType(type),
			category,
			count: devs.length,
			avgPower,
			totalPower: Math.round(devs.length * avgPower),
			mounting: getMountingType(type),
		});
	});

	return counts.sort((a, b) => b.count - a.count);
}

// ============================================================================
// DEVICE HELPERS
// ============================================================================

function categorizeDevice(type: string): string {
	if (type.includes("SENSOR") || type.includes("DETECTOR")) return "Detection";
	if (type.includes("BATTERY") || type.includes("GENERATOR")) return "Power";
	if (type.includes("PANEL") || type.includes("BOARD")) return "Distribution";
	if (type.includes("CAMERA")) return "CCTV";
	if (type.includes("SPEAKER") || type.includes("HORN")) return "Audio";
	return "Other";
}

function formatDeviceType(type: string): string {
	return type.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase());
}

function getAveragePower(type: string): number {
	const powers: Record<string, number> = {
		SENSOR_MOTION: 2,
		SENSOR_SMOKE: 5,
		CAMERA: 15,
		SPEAKER: 10,
		GENERATOR: 5000,
		BATTERY: 0,
		PANEL: 100,
	};
	return powers[type] || 10;
}

function getMountingType(type: string): string {
	if (type.includes("SMOKE") || type.includes("DETECTOR")) return "Ceiling";
	if (type.includes("PANEL") || type.includes("BOARD")) return "Wall";
	if (type.includes("CAMERA")) return "Pendent/Wall";
	return "Wall/Ceiling";
}

// ============================================================================
// BOM SUMMARY GENERATION
// ============================================================================

export function generateBomSummary(
	cableSchedule: CableScheduleItem[],
	conduitSchedule: ConduitScheduleItem[],
	deviceCounts: DeviceCountItem[],
): BomSummary {
	const totalCableLength = cableSchedule.reduce((sum, c) => sum + c.length, 0);
	const totalWeight = cableSchedule.reduce(
		(sum, c) => sum + c.estimatedWeight,
		0,
	);
	const totalCost = cableSchedule.reduce((sum, c) => sum + c.cost, 0);

	// Add conduit cost
	const conduitCost = conduitSchedule.length * 15; // Base cost per conduit
	// Add device cost estimate
	const deviceCost = deviceCounts.reduce((sum, d) => sum + d.count * 50, 0);

	return {
		totalCables: cableSchedule.length,
		totalCableLength: Math.round(totalCableLength * 100) / 100,
		totalConduits: conduitSchedule.length,
		totalDevices: deviceCounts.reduce((sum, d) => sum + d.count, 0),
		estimatedWeight: Math.round(totalWeight * 100) / 100,
		estimatedCost:
			Math.round((totalCost + conduitCost + deviceCost) * 100) / 100,
		generatedAt: Date.now(),
	};
}

// ============================================================================
// GROUPED CABLE SCHEDULE
// ============================================================================

export interface GroupedCableSchedule {
	power: CableScheduleItem[];
	control: CableScheduleItem[];
	signal: CableScheduleItem[];
	fire_alarm: CableScheduleItem[];
	data: CableScheduleItem[];
}

export function groupCablesByType(
	cableSchedule: CableScheduleItem[],
): GroupedCableSchedule {
	return {
		power: cableSchedule.filter((c) => c.type === "power"),
		control: cableSchedule.filter((c) => c.type === "control"),
		signal: cableSchedule.filter((c) => c.type === "signal"),
		fire_alarm: cableSchedule.filter((c) => c.type === "fire_alarm"),
		data: cableSchedule.filter((c) => c.type === "data"),
	};
}

// ============================================================================
// EXPORT FORMATS
// ============================================================================

export interface ExcelRow {
	[key: string]: string | number;
}

export function generateExcelData(
	cableSchedule: CableScheduleItem[],
	deviceCounts: DeviceCountItem[],
	summary: BomSummary,
): { cables: ExcelRow[]; devices: ExcelRow[]; summary: ExcelRow[] } {
	return {
		cables: cableSchedule.map((c) => ({
			"Cable ID": c.id,
			From: c.from,
			To: c.to,
			"Length (m)": c.length,
			"Cross Section (mm²)": c.crossSection,
			Material: c.material,
			Type: c.type,
			"Weight (kg)": c.estimatedWeight,
			"Cost (EUR)": c.cost,
			Route: c.destination,
		})),
		devices: deviceCounts.map((d) => ({
			Type: d.type,
			Category: d.category,
			Quantity: d.count,
			"Avg Power (W)": d.avgPower,
			"Total Power (W)": d.totalPower,
			Mounting: d.mounting,
		})),
		summary: [
			{ "Total Cables": summary.totalCables },
			{ "Total Length (m)": summary.totalCableLength },
			{ "Total Conduits": summary.totalConduits },
			{ "Total Devices": summary.totalDevices },
			{ "Est. Weight (kg)": summary.estimatedWeight },
			{ "Est. Cost (EUR)": summary.estimatedCost },
			{ Generated: new Date(summary.generatedAt).toISOString() },
		],
	};
}

// ============================================================================
// DXF GENERATION HELPERS
// ============================================================================

export interface DxfEntity {
	type: string;
	layer: string;
	color: number;
	data: Record<string, number | string>;
}

export function generateDxfCableEntities(
	cableSchedule: CableScheduleItem[],
	devices: Device[],
): DxfEntity[] {
	const entities: DxfEntity[] = [];

	cableSchedule.forEach((cable) => {
		const fromDevice = devices.find((d) => cable.from.includes(d.id.slice(-4)));
		const toDevice = devices.find((d) => cable.to.includes(d.id.slice(-4)));

		if (fromDevice && toDevice) {
			// LINE entity for cable
			entities.push({
				type: "LINE",
				layer: "CABLES",
				color: 1, // Red
				data: {
					x1: fromDevice.x * 10, // Scale up for mm
					y1: fromDevice.y * 10,
					x2: toDevice.x * 10,
					y2: toDevice.y * 10,
				},
			});
		}
	});

	return entities;
}

export function generateDxfDeviceEntities(devices: Device[]): DxfEntity[] {
	return devices.map((device) => ({
		type: "CIRCLE",
		layer: "DEVICES",
		color: 3, // Green
		data: {
			x: device.x * 10,
			y: device.y * 10,
			radius: 50, // 500mm representation
		},
	}));
}
