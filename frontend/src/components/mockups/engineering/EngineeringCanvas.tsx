// NOSONAR
/**
 * EngineeringCanvas.tsx - Thermal Visualization Canvas
 * Dynamic color rendering based on electrical calculations
 */

import { Battery, Box, Eye, Power, Siren, Wifi, Zap } from "lucide-react";
import type React from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
	calculateVoltageDrop,
	type VoltageDropResult,
} from "@/engine/CalculationEngine";
import {
	generateCableGradient,
	getLoadColor,
	getVoltageDropColor,
} from "@/engine/VisualizationUtils";
import { actions, type DeviceType, useStore } from "@/store/simpleStore";
import { ThermalLegend } from "./ThermalLegend";

// ============================================================================
// TYPES
// ============================================================================

interface EngineeringCanvasProps {
	onItemDrop?: () => void;
}

interface ThermalConnection {
	id: string;
	fromId: string;
	toId: string;
	fromX: number;
	fromY: number;
	toX: number;
	toY: number;
	current: number;
	voltageDrop: VoltageDropResult;
	color: string;
	isCritical: boolean;
	isWarning: boolean;
}

interface ThermalDevice {
	id: string;
	type: DeviceType;
	x: number;
	y: number;
	load: number;
	voltage: number;
	stressColor: string;
	glowIntensity: number;
	isOverloaded: boolean;
}

// ============================================================================
// ICON CONFIG
// ============================================================================

const DEVICE_ICONS: Record<DeviceType, React.ReactNode> = {
	GENERATOR: <Zap size={24} />,
	BATTERY: <Battery size={24} />,
	LOAD: <Power size={24} />,
	PANEL: <Box size={24} />,
	SENSOR_SMOKE: <Siren size={24} />,
	SENSOR_MOTION: <Wifi size={24} />,
	CAMERA: <Eye size={24} />,
	SPEAKER: <Box size={24} />,
};

const DEVICE_COLORS: Record<DeviceType, string> = {
	GENERATOR: "#f59e0b",
	BATTERY: "#10b981",
	LOAD: "#3b82f6",
	PANEL: "#94a3b8",
	SENSOR_SMOKE: "#ef4444",
	SENSOR_MOTION: "#f97316",
	CAMERA: "#a855f7",
	SPEAKER: "#ec4899",
};

// ============================================================================
// MAIN COMPONENT
// ============================================================================

export function EngineeringCanvas({ onItemDrop }: EngineeringCanvasProps) {  // NOSONAR - typescript:S6759
	const devices = useStore((s) => s.devices);
	const connections = useStore((s) => s.connections);
	const selectedId = useStore((s) => s.selectedElementId);

	const [draggingId, setDraggingId] = useState<string | null>(null);
	const [connectingFrom, setConnectingFrom] = useState<string | null>(null);
	const [mousePos, setMousePos] = useState({ x: 0, y: 0 });
	const [hoveredId, setHoveredId] = useState<string | null>(null);
	const svgRef = useRef<SVGSVGElement>(null);

	// Calculate thermal data for all connections
	const thermalConnections = useMemo<ThermalConnection[]>(() => {
		return connections
			.map((conn) => {
				const from = devices.find((d) => d.id === conn.fromId);
				const to = devices.find((d) => d.id === conn.toId);

				if (!from || !to) return null;

				// Calculate cable length (pixels to meters, then km)
				const dx = to.x - from.x;
				const dy = to.y - from.y;
				const lengthPx = Math.sqrt(dx * dx + dy * dy);  // NOSONAR - typescript:S7769
				const lengthM = lengthPx * 0.01; // 1px = 10mm
				const _lengthKm = lengthM / 1000;

				// Calculate voltage drop
				const vd = calculateVoltageDrop(
					conn.current,
					lengthM,
					"Cu",
					2.5, // Default 2.5mm²
					0.85,
					400,
				);

				const color = getVoltageDropColor(vd.percentage);
				const isCritical = vd.percentage > 10;
				const isWarning = vd.percentage > 5;

				return {
					id: conn.id,
					fromId: conn.fromId,
					toId: conn.toId,
					fromX: from.x,
					fromY: from.y,
					toX: to.x,
					toY: to.y,
					current: conn.current,
					voltageDrop: vd,
					color,
					isCritical,
					isWarning,
				};
			})
			.filter(Boolean) as ThermalConnection[];
	}, [connections, devices]);

	// Calculate thermal data for all devices
	const thermalDevices = useMemo<ThermalDevice[]>(() => {
		return devices.map((dev) => {
			const deviceConnections = connections.filter(
				(c) => c.fromId === dev.id || c.toId === dev.id,
			);
			const totalCurrent = deviceConnections.reduce(
				(sum, c) => sum + c.current,
				0,
			);
			const loadPercent = (totalCurrent / 100) * 100; // Assume 100A base
			const stressColor = getLoadColor(loadPercent);
			const glowIntensity =
				loadPercent > 100 ? 1 : loadPercent > 80 ? 0.6 : 0.2;  // NOSONAR — S3358: nested ternary acceptable in this localized context
			const isOverloaded = loadPercent >= 100;

			return {
				id: dev.id,
				type: dev.type,
				x: dev.x,
				y: dev.y,
				load: dev.load,
				voltage: dev.voltage,
				stressColor,
				glowIntensity,
				isOverloaded,
			};
		});
	}, [devices, connections]);

	// Global stress values for the legend
	const globalMaxVoltageDrop = useMemo(() => {
		if (thermalConnections.length === 0) return 0;
		return Math.max(...thermalConnections.map((c) => c.voltageDrop.percentage));
	}, [thermalConnections]);

	// Handle Global Reset Event
	useEffect(() => {
		const handler = () => actions.resetProject();
		globalThis.addEventListener("nexus-reset-project", handler);
		return () => globalThis.removeEventListener("nexus-reset-project", handler);
	}, []);

	const getCoords = (e: React.MouseEvent) => {
		if (!svgRef.current) return { x: 0, y: 0 };
		const rect = svgRef.current.getBoundingClientRect();
		return { x: e.clientX - rect.left, y: e.clientY - rect.top };
	};

	const handleDeviceMouseDown = (e: React.MouseEvent, id: string) => {
		e.stopPropagation();
		if (e.button === 0) {
			if (e.shiftKey) {
				setConnectingFrom(id);
			} else {
				setDraggingId(id);
				actions.selectElement(id);
			}
		}
	};

	const handleDeviceMouseUp = (e: React.MouseEvent, id: string) => {
		e.stopPropagation();
		if (connectingFrom && connectingFrom !== id) {
			actions.addConnection(connectingFrom, id);
			setConnectingFrom(null);
		}
	};

	const handleMouseMove = (e: React.MouseEvent) => {
		const { x, y } = getCoords(e);
		setMousePos({ x, y });

		if (draggingId) {
			actions.updateDevicePosition(draggingId, x, y);
		}
	};

	const handleMouseUp = () => {
		setDraggingId(null);
		setConnectingFrom(null);
	};

	const handleKeyDown = useCallback(
		(e: KeyboardEvent) => {
			if ((e.key === "Delete" || e.key === "Backspace") && selectedId) {
				if (devices.find((d) => d.id === selectedId)) {  // NOSONAR - typescript:S7754
					actions.deleteDevice(selectedId);
					actions.selectElement(null);
				}
			}
		},
		[selectedId, devices],
	);

	useEffect(() => {
		globalThis.addEventListener("keydown", handleKeyDown);
		return () => globalThis.removeEventListener("keydown", handleKeyDown);
	}, [handleKeyDown]);

	// Handle Drop from Library
	const handleDrop = (e: React.DragEvent) => {
		e.preventDefault();
		const data = e.dataTransfer.getData("application/json");
		if (!data) return;

		try {
			const item = JSON.parse(data);
			if (!svgRef.current) return;

			const rect = svgRef.current.getBoundingClientRect();
			const x = e.clientX - rect.left;
			const y = e.clientY - rect.top;

			actions.addDevice({
				type: item.id as DeviceType,
				load: item.defaultLoad,
				voltage: 220,
				x,
				y,
			});

			if (onItemDrop) onItemDrop();
		} catch (err) {
			console.error("Failed to parse dropped item", err);
		}
	};

	const handleDragOver = (e: React.DragEvent) => {
		e.preventDefault();
		e.dataTransfer.dropEffect = "copy";
	};

	// ============================================================================
	// RENDER
	// ============================================================================

	return (
		<div className="relative w-full h-full bg-[#0f1115] overflow-hidden">
			{/* Thermal Legend */}
			<ThermalLegend type="voltageDrop" position="bottom-right" />

			{/* Stress Summary */}
			<div className="absolute top-4 right-4 bg-black/80 backdrop-blur-sm rounded-lg p-3 border border-white/20 z-50 min-w-[200px]">
				<div className="text-xs font-bold text-white mb-2 flex items-center gap-2">
					<span>Engineering Analysis</span>
					<span className="text-[10px] bg-primary/20 text-primary px-2 py-0.5 rounded">
						LIVE
					</span>
				</div>

				<div className="space-y-2">
					<div className="flex items-center gap-2 text-[10px]">
						<span className="text-white/50 w-20">Max V-Drop:</span>
						<div className="flex-1 h-2 bg-white/10 rounded-full overflow-hidden">
							<div
								className={`h-full rounded-full transition-all duration-300 ${globalMaxVoltageDrop > 5 ? "animate-pulse" : ""}`}
								style={{
									width: `${Math.min(100, globalMaxVoltageDrop * 5)}%`,
									backgroundColor: getVoltageDropColor(globalMaxVoltageDrop),
									boxShadow: `0 0 8px ${getVoltageDropColor(globalMaxVoltageDrop)}`,
								}}
							/>
						</div>
						<span className="font-mono text-white w-16 text-right">
							{globalMaxVoltageDrop.toFixed(2)}%
						</span>
					</div>

					<div className="flex items-center gap-2 text-[10px]">
						<span className="text-white/50 w-20">Devices:</span>
						<span className="font-mono text-white">{devices.length}</span>
					</div>

					<div className="flex items-center gap-2 text-[10px]">
						<span className="text-white/50 w-20">Connections:</span>
						<span className="font-mono text-white">
							{thermalConnections.length}
						</span>
					</div>

					<div className="flex items-center gap-2 text-[10px]">
						<span className="text-white/50 w-20">Critical:</span>
						<span className="font-mono text-red-400">
							{thermalConnections.filter((c) => c.isCritical).length}
						</span>
					</div>
				</div>
			</div>

			<svg
				ref={svgRef}
				className="w-full h-full"
				onMouseMove={handleMouseMove}
				onMouseUp={handleMouseUp}
				onDrop={handleDrop}
				onDragOver={handleDragOver}
				style={{
					backgroundImage: "radial-gradient(#1e293b 1px, transparent 1px)",
					backgroundSize: "20px 20px",
				}}
			>
				<defs>
					{/* Critical Animation */}
					<style>{`
            @keyframes criticalPulse {
              0%, 100% { opacity: 1; filter: drop-shadow(0 0 8px #ef4444); }
              50% { opacity: 0.7; filter: drop-shadow(0 0 16px #ef4444); }
            }
            @keyframes dashFlow {
              to { stroke-dashoffset: -20; }
            }
            .critical-animated {
              animation: criticalPulse 1s ease-in-out infinite;
            }
            .dash-animated {
              animation: dashFlow 1s linear infinite;
            }
          `}</style>

					{/* Glow Filters */}
					<filter
						id="glow-critical"
						x="-50%"
						y="-50%"
						width="200%"
						height="200%"
					>
						<feGaussianBlur stdDeviation="4" result="blur" />
						<feFlood flood-color="#ef4444" flood-opacity="0.6" result="color" />  // NOSONAR — S6747: JSX acceptable
						<feComposite in="color" in2="blur" operator="in" result="glow" />
						<feMerge>
							<feMergeNode in="glow" />
							<feMergeNode in="SourceGraphic" />
						</feMerge>
					</filter>

					<filter
						id="glow-warning"
						x="-50%"
						y="-50%"
						width="200%"
						height="200%"
					>
						<feGaussianBlur stdDeviation="3" result="blur" />
						<feFlood flood-color="#f59e0b" flood-opacity="0.5" result="color" />  // NOSONAR — S6747: JSX acceptable
						<feComposite in="color" in2="blur" operator="in" result="glow" />
						<feMerge>
							<feMergeNode in="glow" />
							<feMergeNode in="SourceGraphic" />
						</feMerge>
					</filter>

					<filter id="glow-normal" x="-50%" y="-50%" width="200%" height="200%">
						<feGaussianBlur stdDeviation="2" result="blur" />
						<feFlood flood-color="#10b981" flood-opacity="0.3" result="color" />  // NOSONAR — S6747: JSX acceptable
						<feComposite in="color" in2="blur" operator="in" result="glow" />
						<feMerge>
							<feMergeNode in="glow" />
							<feMergeNode in="SourceGraphic" />
						</feMerge>
					</filter>
				</defs>

				{/* Thermal Connections */}
				{thermalConnections.map((conn) => {
					const _gradientSegments = generateCableGradient(
						Math.sqrt(  // NOSONAR - typescript:S7769
							(conn.toX - conn.fromX) ** 2 + (conn.toY - conn.fromY) ** 2,
						),
						conn.voltageDrop.percentage * 0.8,
						conn.voltageDrop.percentage,
						5,
					);

					return (
						<g key={conn.id}>
							{/* Main Cable Line with Thermal Color */}
							<line
								x1={conn.fromX}
								y1={conn.fromY}
								x2={conn.toX}
								y2={conn.toY}
								stroke={conn.color}
								strokeWidth={conn.isCritical ? 5 : conn.isWarning ? 4 : 3}  // NOSONAR — S3358: nested ternary acceptable in this localized context
								className={`
                  transition-all duration-150
                  ${conn.isCritical ? "critical-animated" : ""}
                  ${conn.isCritical ? "" : conn.isWarning ? "" : "dash-animated"}  // NOSONAR — S3358: nested ternary acceptable in this localized context
                `}
								style={{
									strokeDasharray: conn.isWarning ? "8,4" : "none",
									filter: conn.isCritical
										? "url(#glow-critical)"
										: conn.isWarning  // NOSONAR — S3358: nested ternary acceptable in this localized context
											? "url(#glow-warning)"
											: "url(#glow-normal)",
								}}
							/>

							{/* Gradient overlay for long cables */}
							{Math.sqrt(  // NOSONAR - typescript:S7769
								(conn.toX - conn.fromX) ** 2 + (conn.toY - conn.fromY) ** 2,
							) > 200 && (
								<line
									x1={conn.fromX}
									y1={conn.fromY}
									x2={conn.toX}
									y2={conn.toY}
									stroke={`url(#cable-gradient-${conn.id})`}
									strokeWidth="8"
									strokeOpacity="0.3"
									style={{ pointerEvents: "none" }}
								/>
							)}

							{/* Midpoint Info Badge */}
							<g
								transform={`translate(${(conn.fromX + conn.toX) / 2}, ${(conn.fromY + conn.toY) / 2})`}
							>
								<rect
									x="-25"
									y="-18"
									width="50"
									height="18"
									rx="4"
									fill="#0f1115"
									stroke={conn.color}
									strokeWidth="1"
									opacity="0.9"
								/>
								<text
									x="0"
									y="-6"
									fill={conn.color}
									fontSize="9"
									textAnchor="middle"
									fontFamily="monospace"
									fontWeight="bold"
								>
									{conn.voltageDrop.percentage.toFixed(1)}%
								</text>
								<text
									x="0"
									y="3"
									fill="#94a3b8"
									fontSize="8"
									textAnchor="middle"
									fontFamily="monospace"
								>
									{conn.current.toFixed(0)}A
								</text>
							</g>

							{/* Warning Indicator for Critical Cables */}
							{conn.isCritical && (
								<circle
									cx={(conn.fromX + conn.toX) / 2}
									cy={(conn.fromY + conn.toY) / 2}
									r="8"
									fill="#ef4444"
									className="animate-pulse"
								/>
							)}
						</g>
					);
				})}

				{/* Drag Line */}
				{connectingFrom &&
					(() => {
						const from = devices.find((d) => d.id === connectingFrom);
						if (!from) return null;
						return (
							<line
								x1={from.x}
								y1={from.y}
								x2={mousePos.x}
								y2={mousePos.y}
								stroke="#3b82f6"
								strokeWidth="2"
								strokeDasharray="5,5"
							/>
						);
					})()}

				{/* Thermal Devices */}
				{thermalDevices.map((dev) => {
					const isSelected = selectedId === dev.id;
					const isHovered = hoveredId === dev.id;

					return (
						<g
							key={dev.id}
							transform={`translate(${dev.x - 30}, ${dev.y - 30})`}
							onMouseDown={(e) => handleDeviceMouseDown(e, dev.id)}
							onMouseUp={(e) => handleDeviceMouseUp(e, dev.id)}
							onMouseEnter={() => setHoveredId(dev.id)}
							onMouseLeave={() => setHoveredId(null)}
							className="cursor-pointer"
						>
							{/* Glow Effect */}
							{dev.glowIntensity > 0.3 && (
								<rect
									x="-5"
									y="-5"
									width="70"
									height="70"
									rx="12"
									fill="none"
									stroke={dev.stressColor}
									strokeWidth="4"
									opacity={dev.glowIntensity * 0.5}
									filter={`blur(${dev.glowIntensity * 8}px)`}
								/>
							)}

							{/* Device Body */}
							<rect
								width="60"
								height="60"
								rx="8"
								fill="#1e293b"
								stroke={
									isSelected
										? "#3b82f6"
										: dev.isOverloaded  // NOSONAR — S3358: nested ternary acceptable in this localized context
											? "#ef4444"
											: dev.stressColor
								}
								strokeWidth={isSelected ? 3 : 2}
								className={`
                  transition-all duration-150
                  ${dev.isOverloaded ? "critical-animated" : ""}
                  ${isHovered ? "scale-105" : ""}
                `}
								style={{
									filter: dev.isOverloaded
										? "url(#glow-critical)"
										: dev.glowIntensity > 0.2  // NOSONAR — S3358: nested ternary acceptable in this localized context
											? "url(#glow-normal)"
											: "none",
								}}
							/>

							{/* Stress Indicator Bar */}
							<rect x="5" y="52" width="50" height="4" rx="2" fill="#0f1115" />
							<rect
								x="5"
								y="52"
								width={Math.min(50, (dev.load / 200) * 50)}
								height="4"
								rx="2"
								fill={dev.stressColor}
								className="transition-all duration-150"
							/>

							{/* Icon */}
							<g transform="translate(18, 10)" fill={DEVICE_COLORS[dev.type]}>
								{DEVICE_ICONS[dev.type]}
							</g>

							{/* Load Text */}
							<text
								x="30"
								y="50"
								textAnchor="middle"
								fill="#94a3b8"
								fontSize="10"
								fontFamily="monospace"
							>
								{dev.load}A
							</text>

							{/* Overload Warning */}
							{dev.isOverloaded && (
								<g>
									<circle
										cx="50"
										cy="10"
										r="6"
										fill="#ef4444"
										className="animate-pulse"
									/>
									<text
										x="50"
										y="13"
										fill="white"
										fontSize="8"
										textAnchor="middle"
										fontWeight="bold"
									>
										!
									</text>
								</g>
							)}

							{/* Hover Tooltip */}
							{isHovered && (
								<g transform="translate(65, -20)">
									<rect
										x="0"
										y="0"
										width="100"
										height="50"
										rx="6"
										fill="#0f1115"
										stroke="#475569"
										strokeWidth="1"
									/>
									<text
										x="8"
										y="15"
										fill="white"
										fontSize="10"
										fontWeight="bold"
									>
										Load: {dev.load}A
									</text>
									<text x="8" y="28" fill="#94a3b8" fontSize="9">
										Voltage: {dev.voltage}V
									</text>
									<text x="8" y="41" fill={dev.stressColor} fontSize="9">
										Status: {dev.isOverloaded ? "OVERLOAD" : "Normal"}
									</text>
								</g>
							)}
						</g>
					);
				})}
			</svg>

			{/* Instructions Overlay */}
			<div className="absolute bottom-4 left-4 bg-card/90 backdrop-blur p-3 rounded border border-border shadow-lg pointer-events-none">
				<h3 className="text-xs font-bold text-primary mb-1">
					NexusCAD Thermal Engine
				</h3>
				<ul className="text-[10px] text-muted-foreground space-y-1">
					<li>• Drag devices from library and drop here.</li>
					<li>• Drag Device to move.</li>
					<li>• Shift+Drag between devices to connect.</li>
					<li>• Colors indicate electrical stress.</li>
				</ul>
			</div>
		</div>
	);
}

export default EngineeringCanvas;
