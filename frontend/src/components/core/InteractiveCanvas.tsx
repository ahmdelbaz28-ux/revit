import type React from "react";
import { useRef, useState } from "react";
import { actions, type CanvasElement, useStore } from "@/store/simpleStore";

export function InteractiveCanvas() {
	const canvasElements = useStore((s) => s.canvasElements);
	const selectedElementId = useStore((s) => s.selectedElementId);
	const [drawingFrom, setDrawingFrom] = useState<string | null>(null);
	const [mousePos, setMousePos] = useState({ x: 0, y: 0 });
	const canvasRef = useRef<SVGSVGElement>(null);

	const handleCanvasClick = (e: React.MouseEvent<SVGSVGElement>) => {
		if (drawingFrom) {
			setDrawingFrom(null);
			return;
		}
		actions.setSelectedElement(null);
	};

	const handleCanvasMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
		if (drawingFrom && canvasRef.current) {
			const rect = canvasRef.current.getBoundingClientRect();
			setMousePos({
				x: e.clientX - rect.left,
				y: e.clientY - rect.top,
			});
		}
	};

	const handleDeviceMouseDown = (e: React.MouseEvent, id: string) => {
		e.stopPropagation();
		setDrawingFrom(id);
	};

	const handleDeviceMouseUp = (e: React.MouseEvent, id: string) => {
		e.stopPropagation();
		if (drawingFrom && drawingFrom !== id) {
			// Check if connection already exists
			const exists = canvasElements.some(
				(el) =>
					el.type === "cable" &&
					((el.from === drawingFrom && el.to === id) ||
						(el.from === id && el.to === drawingFrom)),
			);

			if (!exists) {
				const newCable: CanvasElement = {
					id: `cable-${Date.now()}`,
					type: "cable",
					from: drawingFrom,
					to: id,
					x: 0,
					y: 0, // Not used for lines directly but required by interface
				};
				actions.addElement(newCable);

				// Validation: If connecting incompatible voltages (simulated)
				const fromEl = canvasElements.find((el) => el.id === drawingFrom);
				const toEl = canvasElements.find((el) => el.id === id);
				if (fromEl && toEl && fromEl.voltage !== toEl.voltage) {
					actions.pushError(
						`Voltage mismatch between ${fromEl.type} (${fromEl.voltage}V) and ${toEl.type} (${toEl.voltage}V)!`,
					);
				}
			}
		}
		setDrawingFrom(null);
	};

	const handleDeviceClick = (e: React.MouseEvent, id: string) => {
		e.stopPropagation();
		actions.setSelectedElement(id);
	};

	const handleDrop = (e: React.DragEvent<SVGSVGElement>) => {
		e.preventDefault();
		const type = e.dataTransfer.getData("elementType") as CanvasElement["type"];
		if (type && canvasRef.current) {
			const rect = canvasRef.current.getBoundingClientRect();
			const x = e.clientX - rect.left;
			const y = e.clientY - rect.top;

			const newElement: CanvasElement = {
				id: `${type}-${Date.now()}`,
				type,
				x,
				y,
				voltage: type === "generator" ? 11000 : 220, // Example voltages
				load: type === "panel" ? 50 : 0,
			};
			actions.addElement(newElement);
		}
	};

	const handleDragOver = (e: React.DragEvent<SVGSVGElement>) => {
		e.preventDefault();
	};

	const getElementById = (id: string) =>
		canvasElements.find((el) => el.id === id);

	return (
		<div className="w-full h-full bg-[#0f1115] border rounded-lg overflow-hidden relative">
			<svg
				ref={canvasRef}
				className="w-full h-full cursor-crosshair"
				onClick={handleCanvasClick}
				onMouseMove={handleCanvasMouseMove}
				onDrop={handleDrop}
				onDragOver={handleDragOver}
				style={{
					backgroundImage: "radial-gradient(#1e293b 1px, transparent 1px)",
					backgroundSize: "20px 20px",
				}}
			>
				{/* Render Cables */}
				{canvasElements
					.filter((el) => el.type === "cable")
					.map((cable) => {
						const fromEl = getElementById(cable.from!);
						const toEl = getElementById(cable.to!);
						if (!fromEl || !toEl) return null;

						const isSelected = selectedElementId === cable.id;

						return (
							<g key={cable.id} onClick={(e) => handleDeviceClick(e, cable.id)}>
								<line
									x1={fromEl.x}
									y1={fromEl.y}
									x2={toEl.x}
									y2={toEl.y}
									stroke={isSelected ? "#3b82f6" : "#10b981"}
									strokeWidth={isSelected ? "4" : "3"}
									className="cursor-pointer hover:stroke-primary transition-colors"
								/>
							</g>
						);
					})}

				{/* Render Drawing Line */}
				{drawingFrom &&
					(() => {
						const fromEl = getElementById(drawingFrom);
						if (!fromEl) return null;
						return (
							<line
								x1={fromEl.x}
								y1={fromEl.y}
								x2={mousePos.x}
								y2={mousePos.y}
								stroke="#3b82f6"
								strokeWidth="2"
								strokeDasharray="5,5"
							/>
						);
					})()}

				{/* Render Devices */}
				{canvasElements
					.filter((el) => el.type !== "cable")
					.map((dev) => {
						const isSelected = selectedElementId === dev.id;
						return (
							<g
								key={dev.id}
								transform={`translate(${dev.x - 20}, ${dev.y - 20})`}
								onMouseDown={(e) => handleDeviceMouseDown(e, dev.id)}
								onMouseUp={(e) => handleDeviceMouseUp(e, dev.id)}
								onClick={(e) => handleDeviceClick(e, dev.id)}
								className="cursor-pointer group"
							>
								<rect
									width="40"
									height="40"
									fill="#1e293b"
									stroke={isSelected ? "#3b82f6" : "#475569"}
									strokeWidth={isSelected ? "3" : "2"}
									rx="4"
									className="group-hover:stroke-primary transition-colors"
								/>
								<text
									x="20"
									y="25"
									fill="#f8fafc"
									fontSize="10"
									fontWeight="bold"
									textAnchor="middle"
								>
									{dev.type.toUpperCase().substring(0, 4)}
								</text>
							</g>
						);
					})}
			</svg>
		</div>
	);
}
