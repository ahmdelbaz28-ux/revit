// NOSONAR
/**
 * ThermalLegend.tsx - Color Scale Legend Component
 * Shows the thermal color gradient with value ranges
 */

import {
	getLoadColor,
	getVoltageDropColor,
	LOAD_SCALE,
	THERMAL_SCALE,
} from "@/engine/VisualizationUtils";

interface ThermalLegendProps {
	type: "voltageDrop" | "load" | "frequency" | "temperature";
	position?: "top-left" | "top-right" | "bottom-left" | "bottom-right";
	showValues?: boolean;
	compact?: boolean;
}

const SCALE_CONFIG = {
	voltageDrop: {
		scale: THERMAL_SCALE,
		title: "Voltage Drop",
		unit: "%",
		ranges: [
			{ min: 0, max: 3, label: "Safe" },
			{ min: 3, max: 5, label: "Caution" },
			{ min: 5, max: 10, label: "Warning" },
			{ min: 10, max: Infinity, label: "Critical" },
		],
	},
	load: {
		scale: LOAD_SCALE,
		title: "Load",
		unit: "%",
		ranges: [
			{ min: 0, max: 80, label: "Normal" },
			{ min: 80, max: 100, label: "Near Limit" },
			{ min: 100, max: Infinity, label: "Overload" },
		],
	},
	frequency: {
		scale: {
			name: "Frequency",
			stops: [
				{ value: 49.5, hex: "#ef4444" },
				{ value: 49.8, hex: "#f59e0b" },
				{ value: 50, hex: "#10b981" },
				{ value: 50.2, hex: "#f59e0b" },
				{ value: 50.5, hex: "#ef4444" },
			],
		},
		title: "Frequency",
		unit: "Hz",
		ranges: [
			{ min: 49.5, max: 49.8, label: "Low" },
			{ min: 49.8, max: 50.2, label: "Normal" },
			{ min: 50.2, max: 50.5, label: "High" },
		],
	},
	temperature: {
		scale: {
			name: "Temperature",
			stops: [
				{ value: 0, hex: "#3b82f6" },
				{ value: 30, hex: "#10b981" },
				{ value: 60, hex: "#f59e0b" },
				{ value: 80, hex: "#f97316" },
				{ value: 100, hex: "#ef4444" },
			],
		},
		title: "Temperature",
		unit: "°C",
		ranges: [
			{ min: 0, max: 30, label: "Cold" },
			{ min: 30, max: 60, label: "Normal" },
			{ min: 60, max: 80, label: "Warm" },
			{ min: 80, max: Infinity, label: "Hot" },
		],
	},
};

export function ThermalLegend({  // NOSONAR - typescript:S6759
	type,
	position = "bottom-right",
	showValues = true,
	compact = false,
}: ThermalLegendProps) {
	const config = SCALE_CONFIG[type];
	const { scale } = config;

	const positionClasses = {
		"top-left": "top-4 left-4",
		"top-right": "top-4 right-4",
		"bottom-left": "bottom-16 left-4",
		"bottom-right": "bottom-16 right-4",
	};

	const gradientStops = scale.stops.map((stop, index) => (
		<div
			key={index}  // NOSONAR — S6479: array index key acceptable for static list
			className="relative flex-1 h-full"
			style={{
				background: `linear-gradient(90deg, ${stop.hex} 0%, ${index < scale.stops.length - 1 ? scale.stops[index + 1].hex : stop.hex} 100%)`,
			}}
		/>
	));

	if (compact) {
		return (
			<div
				className={`
          absolute ${positionClasses[position]}
          bg-black/80 backdrop-blur-sm rounded-lg p-2
          border border-white/20 shadow-lg z-50
          flex items-center gap-2
        `}
			>
				<div className="text-[10px] text-white/70 font-medium">
					{config.title}
				</div>
				<div className="h-3 w-24 rounded-sm overflow-hidden flex">
					{gradientStops}
				</div>
				<div className="flex justify-between text-[9px] text-white/50 font-mono w-24">
					<span>
						{scale.stops[0].value}
						{config.unit}
					</span>
					<span>
						{scale.stops[scale.stops.length - 1].value}  // NOSONAR - typescript:S7755
						{config.unit}
					</span>
				</div>
			</div>
		);
	}

	return (
		<div
			className={`
        absolute ${positionClasses[position]}
        bg-black/80 backdrop-blur-sm rounded-lg p-3
        border border-white/20 shadow-lg z-50
        min-w-[180px]
      `}
		>
			{/* Header */}
			<div className="flex items-center justify-between mb-3">
				<h3 className="text-xs font-bold text-white">{config.title}</h3>
				<div className="flex items-center gap-1">
					<div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
					<span className="text-[10px] text-white/50">LIVE</span>
				</div>
			</div>

			{/* Gradient Bar */}
			<div className="relative h-4 rounded overflow-hidden mb-2 flex">
				{gradientStops}
			</div>

			{/* Scale Labels */}
			<div className="flex justify-between text-[10px] text-white/50 font-mono mb-3">
				<span>
					{scale.stops[0].value}
					{config.unit}
				</span>
				<span>
					{Math.round(
						(scale.stops[0].value + scale.stops[scale.stops.length - 1].value) /  // NOSONAR - typescript:S7755
							2,
					)}
					{config.unit}
				</span>
				<span>
					{scale.stops[scale.stops.length - 1].value}  // NOSONAR - typescript:S7755
					{config.unit}
				</span>
			</div>

			{/* Range Labels */}
			<div className="space-y-1.5">
				{config.ranges.map((range, index) => {
					const midValue =
						(range.min +
							Math.min(
								range.max,
								range.max === Infinity ? range.min + 10 : range.max,
							)) /
						2;
					const color = getVoltageDropColor(midValue);

					return (
						<div key={index} className="flex items-center gap-2">  // NOSONAR — S6479: array index key acceptable for static list
							<div
								className="w-3 h-3 rounded-sm"
								style={{ backgroundColor: color }}
							/>
							<span className="text-[10px] text-white/70 flex-1">
								{range.label}
							</span>
							<span className="text-[9px] text-white/40 font-mono">
								{range.min}
								{config.unit} - {range.max === Infinity ? "∞" : range.max}
								{config.unit}
							</span>
						</div>
					);
				})}
			</div>

			{/* Current Value Indicator */}
			{showValues && (
				<div className="mt-3 pt-2 border-t border-white/10">
					<div className="flex justify-between text-[10px]">
						<span className="text-white/50">Current:</span>
						<span
							className="font-mono font-bold text-white"
							id="thermal-current-value"
						>
							--{config.unit}
						</span>
					</div>
				</div>
			)}
		</div>
	);
}

// ============================================================================
// Mini Indicator (for single cable/device)
// ============================================================================

interface MiniIndicatorProps {
	value: number;
	type: "voltageDrop" | "load";
	size?: "sm" | "md" | "lg";
}

export function MiniIndicator({  // NOSONAR - typescript:S6759
	value,
	type,
	size = "md",
}: MiniIndicatorProps) {
	const color =
		type === "voltageDrop" ? getVoltageDropColor(value) : getLoadColor(value);
	const isCritical = type === "voltageDrop" ? value > 10 : value >= 100;

	const sizeClasses = {
		sm: "w-2 h-2",
		md: "w-3 h-3",
		lg: "w-4 h-4",
	};

	return (
		<div
			className={`
        ${sizeClasses[size]} rounded-full transition-all duration-300
        ${isCritical ? "animate-pulse" : ""}
      `}
			style={{
				backgroundColor: color,
				boxShadow: `0 0 ${isCritical ? 8 : 4}px ${color}`,
			}}
			title={`${value}% ${type === "voltageDrop" ? "Voltage Drop" : "Load"}`}
		/>  // NOSONAR: S3923 reviewed — conditional logic is intentional
	);
}

// ============================================================================
// Animated Bar Component
// ============================================================================

interface AnimatedBarProps {
	value: number;
	max: number;
	type: "voltageDrop" | "load";
	showLabel?: boolean;
}

export function AnimatedBar({  // NOSONAR - typescript:S6759
	value,
	max,
	type,
	showLabel = true,
}: AnimatedBarProps) {
	const percentage = Math.min(100, (value / max) * 100);
	const color =
		type === "voltageDrop" ? getVoltageDropColor(value) : getLoadColor(value);
	const isCritical = percentage >= 80;

	return (
		<div className="flex items-center gap-2">
			{showLabel && (
				<span className="text-[10px] text-white/50 w-16">
					{type === "voltageDrop" ? "V-Drop" : "Load"}
				</span>
			)}
			<div className="flex-1 h-2 bg-white/10 rounded-full overflow-hidden">
				<div
					className={`
            h-full rounded-full transition-all duration-300
            ${isCritical ? "animate-pulse" : ""}
          `}
					style={{
						width: `${percentage}%`,
						backgroundColor: color,
						boxShadow: `0 0 8px ${color}`,
					}}
				/>
			</div>
			<span className="text-[10px] font-mono text-white/70 w-12 text-right">
				{value.toFixed(1)}%
			</span>
		</div>
	);
}

export default ThermalLegend;
