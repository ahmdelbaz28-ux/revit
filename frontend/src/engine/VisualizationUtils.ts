/**
 * VisualizationUtils.ts - Color Mapping for Thermal Visualization
 * Maps electrical values to color gradients based on IEC/NEC thresholds
 */

// ============================================================================
// TYPES & INTERFACES
// ============================================================================

export interface ColorStop {
	value: number;
	hex: string;
	label?: string;
}

export interface ColorScale {
	name: string;
	stops: ColorStop[];
}

export interface GradientConfig {
	min: number;
	max: number;
	scale: ColorScale;
	unit: string;
}

// ============================================================================
// THRESHOLD DEFAULTS (IEC/NEC Compliant)
// ============================================================================

export const VOLTAGE_DROP_THRESHOLDS = {
	GREEN_MAX: 3, // IEC: 3% max for lighting
	YELLOW_MAX: 5, // IEC: 5% max for power
	ORANGE_MAX: 10, // Warning threshold
	RED_START: 10, // Critical
};

export const LOAD_THRESHOLDS = {
	GREEN_MAX: 80, // Normal operation
	YELLOW_MAX: 100, // At limit
	RED_START: 100, // Overload
};

export const SHORT_CIRCUIT_THRESHOLDS = {
	GREEN_MAX: 50, // 50% of breaking capacity
	YELLOW_MAX: 80, // Warning
	RED_START: 80, // Critical
};

export const POWER_FACTOR_THRESHOLDS = {
	GREEN_MIN: 0.95, // Excellent PF
	YELLOW_MIN: 0.85, // Acceptable
	RED_START: 0.85, // Poor
};

// ============================================================================
// COLOR PALETTES
// ============================================================================

export const THERMAL_SCALE: ColorScale = {
	name: "Thermal",
	stops: [
		{ value: 0, hex: "#10b981", label: "Safe" }, // Emerald Green
		{ value: 3, hex: "#84cc16", label: "Low" }, // Lime
		{ value: 5, hex: "#f59e0b", label: "Warning" }, // Amber
		{ value: 7, hex: "#f97316", label: "High" }, // Orange
		{ value: 10, hex: "#ef4444", label: "Critical" }, // Red
	],
};

export const LOAD_SCALE: ColorScale = {
	name: "Load",
	stops: [
		{ value: 0, hex: "#10b981", label: "0%" },
		{ value: 50, hex: "#84cc16", label: "50%" },
		{ value: 80, hex: "#facc15", label: "80%" },
		{ value: 100, hex: "#ef4444", label: "100%" },
	],
};

export const FREQUENCY_SCALE: ColorScale = {
	name: "Frequency",
	stops: [
		{ value: 49.5, hex: "#ef4444", label: "49.5Hz" },
		{ value: 49.8, hex: "#f59e0b", label: "49.8Hz" },
		{ value: 50.0, hex: "#10b981", label: "50Hz" },
		{ value: 50.2, hex: "#f59e0b", label: "50.2Hz" },
		{ value: 50.5, hex: "#ef4444", label: "50.5Hz" },
	],
};

export const HEAT_SCALE: ColorScale = {
	name: "Heat",
	stops: [
		{ value: 0, hex: "#3b82f6", label: "Cold" }, // Blue
		{ value: 30, hex: "#10b981", label: "Normal" }, // Green
		{ value: 60, hex: "#f59e0b", label: "Warm" }, // Yellow
		{ value: 80, hex: "#f97316", label: "Hot" }, // Orange
		{ value: 100, hex: "#ef4444", label: "Overheating" }, // Red
	],
};

// ============================================================================
// CORE COLOR INTERPOLATION
// ============================================================================

/**
 * Interpolate between two hex colors
 * @param color1 - Starting hex color
 * @param color2 - Ending hex color
 * @param factor - Interpolation factor (0-1)
 * @returns Interpolated hex color
 */
export function interpolateColor(
	color1: string,
	color2: string,
	factor: number,
): string {
	const rgb1 = hexToRgb(color1);
	const rgb2 = hexToRgb(color2);

	const r = Math.round(rgb1.r + (rgb2.r - rgb1.r) * factor);
	const g = Math.round(rgb1.g + (rgb2.g - rgb1.g) * factor);
	const b = Math.round(rgb1.b + (rgb2.b - rgb1.b) * factor);

	return rgbToHex(r, g, b);
}

/**
 * Get color for a value based on a color scale
 * @param value - The value to map
 * @param scale - The color scale with stops
 * @returns Interpolated hex color
 */
export function getColorForValue(value: number, scale: ColorScale): string {
	const { stops } = scale;

	// Value is below minimum
	if (value <= stops[0].value) {
		return stops[0].hex;
	}

	// Value is above maximum
	if (value >= stops[stops.length - 1].value) {
		return stops[stops.length - 1].hex;
	}

	// Find the two stops the value falls between
	for (let i = 0; i < stops.length - 1; i++) {
		const current = stops[i];
		const next = stops[i + 1];

		if (value >= current.value && value <= next.value) {
			const range = next.value - current.value;
			const position = value - current.value;
			const factor = range > 0 ? position / range : 0;

			return interpolateColor(current.hex, next.hex, factor);
		}
	}

	// Fallback
	return stops[0].hex;
}

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

/**
 * Convert hex to RGB
 */
export function hexToRgb(hex: string): { r: number; g: number; b: number } {
	const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
	return result
		? {
				r: parseInt(result[1], 16),
				g: parseInt(result[2], 16),
				b: parseInt(result[3], 16),
			}
		: { r: 0, g: 0, b: 0 };
}

/**
 * Convert RGB to hex
 */
export function rgbToHex(r: number, g: number, b: number): string {
	return (
		"#" +
		[r, g, b]
			.map((x) => {
				const hex = Math.max(0, Math.min(255, x)).toString(16);
				return hex.length === 1 ? "0" + hex : hex;
			})
			.join("")
	);
}

/**
 * Calculate relative position within a range
 */
export function normalizeValue(
	value: number,
	min: number,
	max: number,
): number {
	if (max === min) return 0;
	return Math.max(0, Math.min(1, (value - min) / (max - min)));
}

/**
 * Get color for value with custom range
 */
export function getColorInRange(
	value: number,
	min: number,
	max: number,
	colorStops: { value: number; hex: string }[],
): string {
	const normalized = normalizeValue(value, min, max);
	const scaledValue = min + normalized * (max - min);
	return getColorForValue(scaledValue, { name: "custom", stops: colorStops });
}

// ============================================================================
// SPECIFIC VALUE MAPPERS
// ============================================================================

/**
 * Get color for voltage drop percentage
 * Based on IEC 60364 standards
 */
export function getVoltageDropColor(percentage: number): string {
	return getColorForValue(percentage, THERMAL_SCALE);
}

/**
 * Get color for load percentage
 */
export function getLoadColor(percentage: number): string {
	return getColorForValue(percentage, LOAD_SCALE);
}

/**
 * Get color for frequency deviation
 */
export function getFrequencyColor(frequency: number): string {
	return getColorForValue(frequency, FREQUENCY_SCALE);
}

/**
 * Get color for temperature
 */
export function getTemperatureColor(tempCelsius: number): string {
	return getColorForValue(tempCelsius, HEAT_SCALE);
}

/**
 * Get color for short circuit percentage of breaking capacity
 */
export function getShortCircuitColor(percentageOfBreaking: number): string {
	return getColorForValue(percentageOfBreaking, {
		name: "Short Circuit",
		stops: [
			{ value: 0, hex: "#10b981" },
			{ value: 30, hex: "#84cc16" },
			{ value: 50, hex: "#f59e0b" },
			{ value: 80, hex: "#f97316" },
			{ value: 100, hex: "#ef4444" },
		],
	});
}

// ============================================================================
// STATUS HELPERS
// ============================================================================

export type StressLevel = "NORMAL" | "WARNING" | "CRITICAL";

export interface StressResult {
	color: string;
	level: StressLevel;
	percentage: number;
	label: string;
}

/**
 * Calculate stress level for voltage drop
 */
export function calculateVoltageDropStress(percentage: number): StressResult {
	let level: StressLevel = "NORMAL";
	let label = "Safe";

	if (percentage > 10) {
		level = "CRITICAL";
		label = "Critical - exceeds 10%";
	} else if (percentage > 5) {
		level = "WARNING";
		label = "Warning - exceeds 5%";
	} else if (percentage > 3) {
		level = "WARNING";
		label = "Caution - exceeds 3%";
	}

	return {
		color: getVoltageDropColor(percentage),
		level,
		percentage,
		label,
	};
}

/**
 * Calculate stress level for load
 */
export function calculateLoadStress(percentage: number): StressResult {
	let level: StressLevel = "NORMAL";
	let label = "Normal";

	if (percentage >= 100) {
		level = "CRITICAL";
		label = "Overloaded!";
	} else if (percentage >= 80) {
		level = "WARNING";
		label = "Near capacity";
	}

	return {
		color: getLoadColor(percentage),
		level,
		percentage,
		label,
	};
}

// ============================================================================
// GRADIENT SVG GENERATION
// ============================================================================

export interface GradientSegment {
	startX: number;
	endX: number;
	color: string;
}

/**
 * Generate SVG gradient definition for a cable
 * Returns segments with calculated colors
 */
export function generateCableGradient(
	length: number,
	startVoltageDrop: number,
	endVoltageDrop: number,
	segments: number = 10,
): GradientSegment[] {
	const result: GradientSegment[] = [];
	const segmentLength = length / segments;

	for (let i = 0; i < segments; i++) {
		const startPercent =
			startVoltageDrop + (endVoltageDrop - startVoltageDrop) * (i / segments);
		const endPercent =
			startVoltageDrop +
			(endVoltageDrop - startVoltageDrop) * ((i + 1) / segments);

		result.push({
			startX: i * segmentLength,
			endX: (i + 1) * segmentLength,
			color: interpolateColor(
				getVoltageDropColor(startPercent),
				getVoltageDropColor(endPercent),
				0.5,
			),
		});
	}

	return result;
}

/**
 * Create SVG linear gradient definition
 */
export function createSvgLinearGradient(
	id: string,
	stops: { offset: number; color: string }[],
): string {
	const gradientStops = stops
		.map((s) => `<stop offset="${s.offset}%" stop-color="${s.color}"/>`)
		.join("");

	return `<linearGradient id="${id}" x1="0%" y1="0%" x2="100%" y2="0%">${gradientStops}</linearGradient>`;
}

// ============================================================================
// ANIMATION HELPERS
// ============================================================================

export interface PulseConfig {
	enabled: boolean;
	speed: number; // ms per cycle
	minOpacity: number;
	maxOpacity: number;
}

/**
 * Get CSS animation for critical state
 */
export function getCriticalAnimation(): string {
	return `
    @keyframes criticalPulse {
      0%, 100% { 
        opacity: 1;
        filter: drop-shadow(0 0 8px #ef4444);
      }
      50% { 
        opacity: 0.7;
        filter: drop-shadow(0 0 16px #ef4444);
      }
    }
  `;
}

/**
 * Get CSS animation for warning state
 */
export function getWarningAnimation(): string {
	return `
    @keyframes warningPulse {
      0%, 100% { 
        opacity: 1;
        filter: drop-shadow(0 0 4px #f59e0b);
      }
      50% { 
        opacity: 0.8;
        filter: drop-shadow(0 0 8px #f59e0b);
      }
    }
  `;
}

/**
 * Get dash animation for active fault
 */
export function getDashAnimation(speed: number = 1000): string {
	return `
    @keyframes dashFlow {
      to {
        stroke-dashoffset: -20;
      }
    }
  `;
}

// ============================================================================
// GLOW EFFECTS
// ============================================================================

export interface GlowConfig {
	color: string;
	intensity: number; // 0-1
	blur: number;
}

/**
 * Calculate glow intensity based on stress level
 */
export function calculateGlowIntensity(stress: StressResult): GlowConfig {
	switch (stress.level) {
		case "CRITICAL":
			return {
				color: "#ef4444",
				intensity: 1,
				blur: 12,
			};
		case "WARNING":
			return {
				color: "#f59e0b",
				intensity: 0.6,
				blur: 8,
			};
		default:
			return {
				color: "#10b981",
				intensity: 0.2,
				blur: 4,
			};
	}
}

/**
 * Generate SVG filter for glow effect
 */
export function createGlowFilter(id: string, config: GlowConfig): string {
	const { color, blur } = config;
	return `
    <filter id="${id}" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur in="SourceGraphic" stdDeviation="${blur / 2}" result="blur"/>
      <feFlood flood-color="${color}" flood-opacity="0.5" result="color"/>
      <feComposite in="color" in2="blur" operator="in" result="glow"/>
      <feMerge>
        <feMergeNode in="glow"/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>
  `;
}

// ============================================================================
// EXPORT DEFAULT CONFIG
// ============================================================================

export const DEFAULT_VISUALIZATION_CONFIG = {
	voltageDrop: {
		min: 0,
		max: 15,
		scale: THERMAL_SCALE,
		unit: "%",
	},
	load: {
		min: 0,
		max: 150,
		scale: LOAD_SCALE,
		unit: "%",
	},
	frequency: {
		min: 49,
		max: 51,
		scale: FREQUENCY_SCALE,
		unit: "Hz",
	},
	temperature: {
		min: 0,
		max: 100,
		scale: HEAT_SCALE,
		unit: "°C",
	},
};
