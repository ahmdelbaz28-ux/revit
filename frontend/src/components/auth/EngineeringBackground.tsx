/**
 * EngineeringBackground.tsx — CAD/Revit split-screen animated background
 *
 * DESIGN (V237 — complete redesign per user feedback):
 *   ┌────────────────────────┬────────────────────────┐
 *   │                        │                        │
 *   │   AutoCAD 2D Plan     │                        │
 *   │   (draws itself)      │   Login Card           │
 *   │                        │   (rendered by parent) │
 *   ├──── ← AutoCAD ↔ Revit → ────┤                        │
 *   │                        │                        │
 *   │   Revit 3D Building   │                        │
 *   │   (isometric wireframe)│                        │
 *   │                        │                        │
 *   └────────────────────────┴────────────────────────┘
 *
 * FEATURES:
 *   - Pure black background (#0a0a0a) — no dirty gradients
 *   - AutoCAD-style grid (light gray, subtle — like real AutoCAD)
 *   - Left half: animation
 *       • Top: AutoCAD 2D floor plan (walls draw themselves via stroke-dashoffset)
 *       • Middle: bidirectional arrow showing AutoCAD ↔ Revit conversion
 *       • Bottom: Revit 3D isometric building (wireframe)
 *   - Right half: empty grid (login card rendered on top by parent)
 *   - AutoCAD crosshair cursor (+) with live X/Y coordinates
 *
 * PERFORMANCE:
 *   - All CSS animations (no rAF loop)
 *   - Respects prefers-reduced-motion
 */

import { type MouseEvent, useEffect, useState } from "react";

export function EngineeringBackground() {
	const [mouse, setMouse] = useState<{ x: number; y: number } | null>(null);
	const [reducedMotion, setReducedMotion] = useState(false);

	useEffect(() => {
		const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
		setReducedMotion(mq.matches);
		const handler = () => setReducedMotion(mq.matches);
		mq.addEventListener("change", handler);
		return () => mq.removeEventListener("change", handler);
	}, []);

	const handleMouseMove = (e: MouseEvent<HTMLDivElement>) => {
		if (reducedMotion) return;
		const rect = e.currentTarget.getBoundingClientRect();
		setMouse({ x: e.clientX - rect.left, y: e.clientY - rect.top });
	};

	return (
		<div
			className="absolute inset-0 overflow-hidden"
			style={{ backgroundColor: "#0a0a0a" }}
			onMouseMove={handleMouseMove}
			onMouseLeave={() => setMouse(null)}
			aria-hidden="true"
		>
			{/* ═════════════════════════════════════════════════════════════════
			    Layer 1: AutoCAD grid (light gray, subtle — like real AutoCAD)
			   ═════════════════════════════════════════════════════════════════ */}
			<svg
				className="absolute inset-0 w-full h-full"
				xmlns="http://www.w3.org/2000/svg"
				preserveAspectRatio="xMidYMid slice"
				viewBox="0 0 1920 1080"
			>
				<defs>
					<pattern
						id="cadGridMinor"
						x="0"
						y="0"
						width="40"
						height="40"
						patternUnits="userSpaceOnUse"
					>
						<path
							d="M 40 0 L 0 0 0 40"
							fill="none"
							stroke="rgba(90,90,90,0.15)"
							strokeWidth="1"
						/>
					</pattern>
					<pattern
						id="cadGridMajor"
						x="0"
						y="0"
						width="200"
						height="200"
						patternUnits="userSpaceOnUse"
					>
						<path
							d="M 200 0 L 0 0 0 200"
							fill="none"
							stroke="rgba(120,120,120,0.22)"
							strokeWidth="1"
						/>
					</pattern>
				</defs>
				<rect width="1920" height="1080" fill="url(#cadGridMinor)" />
				<rect width="1920" height="1080" fill="url(#cadGridMajor)" />
			</svg>

			{/* ═════════════════════════════════════════════════════════════════
			    Layer 2: Left half — animation (AutoCAD 2D + Revit 3D)
			   ═════════════════════════════════════════════════════════════════ */}
			<div className="absolute left-0 top-0 h-full flex flex-col" style={{ width: "50%" }}>
				<div className="flex-1 relative flex items-center justify-center min-h-0">
					<AutoCAD2DPlan reducedMotion={reducedMotion} />
				</div>

				<div className="relative flex items-center justify-center" style={{ height: "70px" }}>
					<BidirectionalArrow reducedMotion={reducedMotion} />
				</div>

				<div className="flex-1 relative flex items-center justify-center min-h-0">
					<Revit3DView reducedMotion={reducedMotion} />
				</div>
			</div>

			{/* ═════════════════════════════════════════════════════════════════
			    Layer 3: Center divider line (subtle)
			   ═════════════════════════════════════════════════════════════════ */}
			<div
				className="absolute top-0 h-full"
				style={{
					left: "50%",
					width: "1px",
					backgroundColor: "rgba(120,120,120,0.2)",
				}}
			/>

			{/* ═════════════════════════════════════════════════════════════════
			    Layer 4: AutoCAD crosshair cursor (+) with coordinates
			   ═════════════════════════════════════════════════════════════════ */}
			{mouse && !reducedMotion && <AutoCADCrosshair x={mouse.x} y={mouse.y} />}
		</div>
	);
}

/* ═══════════════════════════════════════════════════════════════════════════
   Component 1: AutoCAD 2D Floor Plan
   ═══════════════════════════════════════════════════════════════════════════ */
function AutoCAD2DPlan({ reducedMotion }: { reducedMotion: boolean }) {
	return (
		<svg
			width="100%"
			height="100%"
			viewBox="0 0 500 350"
			xmlns="http://www.w3.org/2000/svg"
			preserveAspectRatio="xMidYMid meet"
		>
			<defs>
				<linearGradient id="cadLineGrad2d" x1="0" y1="0" x2="1" y2="0">
					<stop offset="0" stopColor="#5b9bd5" stopOpacity="0.9" />
					<stop offset="100%" stopColor="#a0c4e8" stopOpacity="0.8" />
				</linearGradient>
				<radialGradient id="smokeDetGrad2d">
					<stop offset="0" stopColor="#5b9bd5" stopOpacity="0.9" />
					<stop offset="100%" stopColor="#3a6ea5" stopOpacity="0" />
				</radialGradient>
			</defs>

			{/* Outer wall */}
			<path
				className={reducedMotion ? "" : "cad-stroke cad-draw-1"}
				d="M 80 60 L 420 60 L 420 290 L 80 290 Z"
				fill="none"
				stroke="url(#cadLineGrad2d)"
				strokeWidth="2.5"
				strokeLinejoin="round"
			/>

			{/* Interior walls */}
			<path
				className={reducedMotion ? "" : "cad-stroke cad-draw-2"}
				d="M 230 60 L 230 180 M 230 180 L 80 180 M 320 60 L 320 180 M 320 180 L 230 180 M 320 180 L 420 180"
				fill="none"
				stroke="url(#cadLineGrad2d)"
				strokeWidth="1.8"
			/>

			{/* Door swings */}
			<path
				className={reducedMotion ? "" : "cad-stroke cad-draw-3"}
				d="M 180 180 A 30 30 0 0 1 210 210 M 180 180 L 180 210 M 280 180 A 30 30 0 0 1 310 210 M 280 180 L 280 210"
				fill="none"
				stroke="rgba(160,160,160,0.6)"
				strokeWidth="1.2"
			/>

			{/* Dimension lines */}
			<g
				className={reducedMotion ? "" : "cad-fade-1"}
				stroke="rgba(140,140,140,0.5)"
				strokeWidth="1"
				fill="none"
			>
				<line x1="80" y1="35" x2="420" y2="35" />
				<line x1="80" y1="28" x2="80" y2="42" />
				<line x1="420" y1="28" x2="420" y2="42" />
				<line x1="50" y1="60" x2="50" y2="290" />
				<line x1="43" y1="60" x2="57" y2="60" />
				<line x1="43" y1="290" x2="57" y2="290" />
			</g>
			<text
				x="250"
				y="30"
				fill="rgba(160,160,160,0.7)"
				fontSize="10"
				fontFamily="'JetBrains Mono', monospace"
				textAnchor="middle"
				className={reducedMotion ? "" : "cad-fade-1"}
			>
				15.20 m
			</text>
			<text
				x="42"
				y="178"
				fill="rgba(160,160,160,0.7)"
				fontSize="10"
				fontFamily="'JetBrains Mono', monospace"
				textAnchor="middle"
				transform="rotate(-90 42 178)"
				className={reducedMotion ? "" : "cad-fade-1"}
			>
				8.50 m
			</text>

			{/* Smoke detectors */}
			<g className={reducedMotion ? "" : "cad-fade-2"}>
				{[
					[140, 120],
					[180, 150],
					[275, 120],
					[370, 120],
					[370, 240],
					[180, 240],
					[275, 240],
				].map(([cx, cy], i) => (
					<g key={`det-2d-${i}`}>
						<circle
							cx={cx}
							cy={cy}
							r="14"
							fill="url(#smokeDetGrad2d)"
							className={reducedMotion ? "" : `cad-pulse-${(i % 3) + 1}`}
						/>
						<circle
							cx={cx}
							cy={cy}
							r="7"
							fill="none"
							stroke="#5b9bd5"
							strokeWidth="1.5"
						/>
						<circle cx={cx} cy={cy} r="2" fill="#5b9bd5" />
					</g>
				))}
			</g>

			{/* Label */}
			<text
				x="250"
				y="335"
				fill="rgba(160,160,160,0.6)"
				fontSize="11"
				fontFamily="'JetBrains Mono', monospace"
				textAnchor="middle"
				className={reducedMotion ? "" : "cad-fade-3"}
				letterSpacing="2"
			>
				AUTOCAD · 2D FLOOR PLAN
			</text>
		</svg>
	);
}

/* ═══════════════════════════════════════════════════════════════════════════
   Component 2: Bidirectional Arrow (AutoCAD ↔ Revit)
   ═══════════════════════════════════════════════════════════════════════════ */
function BidirectionalArrow({ reducedMotion }: { reducedMotion: boolean }) {
	return (
		<svg width="300" height="60" viewBox="0 0 300 60" xmlns="http://www.w3.org/2000/svg">
			<defs>
				<linearGradient id="arrowGradL" x1="1" y1="0" x2="0" y2="0">
					<stop offset="0" stopColor="#5b9bd5" />
					<stop offset="100%" stopColor="#3a6ea5" stopOpacity="0.3" />
				</linearGradient>
				<linearGradient id="arrowGradR" x1="0" y1="0" x2="1" y2="0">
					<stop offset="0" stopColor="#5b9bd5" />
					<stop offset="100%" stopColor="#3a6ea5" stopOpacity="0.3" />
				</linearGradient>
			</defs>

			<g className={reducedMotion ? "" : "cad-arrow-left"}>
				<line x1="130" y1="30" x2="30" y2="30" stroke="url(#arrowGradL)" strokeWidth="2" />
				<polygon points="30,30 42,24 42,36" fill="#5b9bd5" />
			</g>

			<text
				x="150"
				y="26"
				fill="#5b9bd5"
				fontSize="11"
				fontFamily="'JetBrains Mono', monospace"
				fontWeight="600"
				textAnchor="middle"
				letterSpacing="1"
			>
				DIGITAL TWIN
			</text>
			<text
				x="150"
				y="40"
				fill="rgba(160,160,160,0.6)"
				fontSize="9"
				fontFamily="'JetBrains Mono', monospace"
				textAnchor="middle"
				letterSpacing="1"
			>
				BIDIRECTIONAL SYNC
			</text>

			<g className={reducedMotion ? "" : "cad-arrow-right"}>
				<line x1="170" y1="30" x2="270" y2="30" stroke="url(#arrowGradR)" strokeWidth="2" />
				<polygon points="270,30 258,24 258,36" fill="#5b9bd5" />
			</g>
		</svg>
	);
}

/* ═══════════════════════════════════════════════════════════════════════════
   Component 3: Revit 3D Isometric Building (wireframe)
   ═══════════════════════════════════════════════════════════════════════════ */
function Revit3DView({ reducedMotion }: { reducedMotion: boolean }) {
	const iso = (x: number, y: number, z: number): string => {
		const ix = (x - y) * 0.866;
		const iy = (x + y) * 0.5 - z;
		return `${ix + 250},${iy + 180}`;
	};

	const v = {
		bfl: iso(0, 0, 0),
		bfr: iso(200, 0, 0),
		bbr: iso(200, 140, 0),
		bbl: iso(0, 140, 0),
		tfl: iso(0, 0, 120),
		tfr: iso(200, 0, 120),
		tbr: iso(200, 140, 120),
		tbl: iso(0, 140, 120),
	};

	return (
		<svg
			width="100%"
			height="100%"
			viewBox="0 0 500 280"
			xmlns="http://www.w3.org/2000/svg"
			preserveAspectRatio="xMidYMid meet"
		>
			<defs>
				<linearGradient id="revitLineGrad" x1="0" y1="0" x2="1" y2="1">
					<stop offset="0" stopColor="#7ac4e8" stopOpacity="0.9" />
					<stop offset="100%" stopColor="#4a90b8" stopOpacity="0.7" />
				</linearGradient>
				<radialGradient id="smokeDetGrad3d">
					<stop offset="0" stopColor="#7ac4e8" stopOpacity="0.9" />
					<stop offset="100%" stopColor="#4a90b8" stopOpacity="0" />
				</radialGradient>
			</defs>

			{/* Ground plane */}
			<polygon
				points={`${v.bfl} ${v.bfr} ${v.bbr} ${v.bbl}`}
				fill="rgba(90,90,90,0.08)"
				stroke="rgba(120,120,120,0.3)"
				strokeWidth="1"
				strokeDasharray="4 3"
				className={reducedMotion ? "" : "cad-fade-1"}
			/>

			{/* Back-left face (hidden, dashed) */}
			<polygon
				points={`${v.bfl} ${v.bbl} ${v.tbl} ${v.tfl}`}
				fill="rgba(122,196,232,0.05)"
				stroke="rgba(122,196,232,0.3)"
				strokeWidth="1"
				strokeDasharray="3 3"
				className={reducedMotion ? "" : "cad-stroke cad-draw-4"}
			/>

			{/* Top face (roof) */}
			<polygon
				points={`${v.tfl} ${v.tfr} ${v.tbr} ${v.tbl}`}
				fill="rgba(122,196,232,0.1)"
				stroke="url(#revitLineGrad)"
				strokeWidth="1.8"
				className={reducedMotion ? "" : "cad-stroke cad-draw-5"}
			/>

			{/* Right face */}
			<polygon
				points={`${v.bfr} ${v.bbr} ${v.tbr} ${v.tfr}`}
				fill="rgba(122,196,232,0.08)"
				stroke="url(#revitLineGrad)"
				strokeWidth="1.8"
				className={reducedMotion ? "" : "cad-stroke cad-draw-5"}
			/>

			{/* Front face (semi-transparent) */}
			<polygon
				points={`${v.bfl} ${v.bfr} ${v.tfr} ${v.tfl}`}
				fill="rgba(122,196,232,0.06)"
				stroke="url(#revitLineGrad)"
				strokeWidth="1.8"
				className={reducedMotion ? "" : "cad-stroke cad-draw-6"}
			/>

			{/* Windows on front face */}
			<g className={reducedMotion ? "" : "cad-fade-2"} stroke="rgba(122,196,232,0.7)" strokeWidth="1.2" fill="rgba(122,196,232,0.12)">
				{[
					[40, 40],
					[90, 40],
					[150, 40],
					[40, 80],
					[90, 80],
					[150, 80],
				].map(([wx, wz], i) => {
					const wBL = iso(wx, 0, wz);
					const wBR = iso(wx + 30, 0, wz);
					const wTR = iso(wx + 30, 0, wz + 30);
					const wTL = iso(wx, 0, wz + 30);
					return (
						<polygon
							key={`win-${i}`}
							points={`${wBL} ${wBR} ${wTR} ${wTL}`}
						/>
					);
				})}
			</g>

			{/* Door on front face */}
			<polygon
				points={`${iso(100, 0, 0)} ${iso(130, 0, 0)} ${iso(130, 0, 50)} ${iso(100, 0, 50)}`}
				fill="rgba(122,196,232,0.2)"
				stroke="rgba(122,196,232,0.8)"
				strokeWidth="1.5"
				className={reducedMotion ? "" : "cad-fade-2"}
			/>

			{/* Smoke detectors inside building */}
			<g className={reducedMotion ? "" : "cad-fade-3"}>
				{[
					[60, 40, 110],
					[100, 70, 110],
					[140, 40, 110],
					[60, 100, 110],
					[140, 100, 110],
				].map(([x, y, z], i) => {
					const pos = iso(x, y, z);
					const [px, py] = pos.split(",").map(Number);
					return (
						<g key={`det-3d-${i}`}>
							<circle
								cx={px}
								cy={py}
								r="10"
								fill="url(#smokeDetGrad3d)"
								className={reducedMotion ? "" : `cad-pulse-${(i % 3) + 1}`}
							/>
							<circle
								cx={px}
								cy={py}
								r="5"
								fill="none"
								stroke="#7ac4e8"
								strokeWidth="1.5"
							/>
							<circle cx={px} cy={py} r="1.5" fill="#7ac4e8" />
						</g>
					);
				})}
			</g>

			{/* Label */}
			<text
				x="250"
				y="265"
				fill="rgba(160,160,160,0.6)"
				fontSize="11"
				fontFamily="'JetBrains Mono', monospace"
				textAnchor="middle"
				className={reducedMotion ? "" : "cad-fade-3"}
				letterSpacing="2"
			>
				REVIT · 3D ISOMETRIC VIEW
			</text>
		</svg>
	);
}

/* ═══════════════════════════════════════════════════════════════════════════
   Component 4: AutoCAD Crosshair Cursor
   ═══════════════════════════════════════════════════════════════════════════ */
function AutoCADCrosshair({ x, y }: { x: number; y: number }) {
	const snappedX = Math.round(x / 10) * 10;
	const snappedY = Math.round(y / 10) * 10;

	return (
		<div
			className="absolute pointer-events-none"
			style={{
				left: `${x}px`,
				top: `${y}px`,
				transform: "translate(-50%, -50%)",
				zIndex: 50,
			}}
		>
			{/* Crosshair lines — full viewport */}
			<svg
				className="absolute"
				style={{
					left: "-50vw",
					top: "-50vh",
					width: "100vw",
					height: "100vh",
					overflow: "visible",
				}}
			>
				<line
					x1="0"
					y1="50vh"
					x2="100vw"
					y2="50vh"
					stroke="rgba(180,180,180,0.3)"
					strokeWidth="1"
				/>
				<line
					x1="50vw"
					y1="0"
					x2="50vw"
					y2="100vh"
					stroke="rgba(180,180,180,0.3)"
					strokeWidth="1"
				/>
			</svg>

			{/* Center + marker */}
			<svg width="24" height="24" viewBox="0 0 24 24" className="absolute" style={{ left: "-12px", top: "-12px" }}>
				<circle cx="12" cy="12" r="1.5" fill="#b0b0b0" />
				<circle cx="12" cy="12" r="6" fill="none" stroke="#b0b0b0" strokeWidth="1" opacity="0.6" />
			</svg>

			{/* Coordinate readout */}
			<div
				className="absolute"
				style={{
					left: "14px",
					top: "14px",
					fontFamily: "'JetBrains Mono', 'Courier New', monospace",
					fontSize: "11px",
					color: "#a0a0a0",
					backgroundColor: "rgba(20,20,20,0.85)",
					padding: "2px 8px",
					border: "1px solid rgba(120,120,120,0.4)",
					whiteSpace: "nowrap",
					userSelect: "none",
				}}
			>
				<span style={{ color: "#7a9ec4" }}>X:</span> {snappedX}{"  "}
				<span style={{ color: "#7a9ec4" }}>Y:</span> {snappedY}{"  "}
				<span style={{ color: "#666" }}>Z:</span> 0
			</div>
		</div>
	);
}
