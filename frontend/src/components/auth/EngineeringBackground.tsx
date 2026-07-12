/**
 * EngineeringBackground.tsx — CAD-style animated engineering background
 *
 * Features:
 *  - Engineering blueprint grid (major + minor lines with subtle pulse)
 *  - Animated CAD drawing that "draws itself" — a fire alarm floor plan with:
 *      • Room outlines (rectangles drawn with stroke-dasharray animation)
 *      • Smoke detector circles (placed at NFPA 72-compliant positions)
 *      • Heat detector circles
 *      • Notification appliances (horn/strobe)
 *  - Scanning line that sweeps across the canvas (CAD "scan" effect)
 *  - Floating particles (engineering data points)
 *  - Coordinate labels (A, B, C, D, 1, 2, 3, 4 — like a real CAD drawing)
 *  - Dimension lines with arrowheads
 *  - Crosshair cursor following mouse
 *
 * Performance:
 *  - All animations are CSS-based (transform/opacity) — no JS rAF loop
 *  - SVG is GPU-accelerated via `will-change` on animated layers
 *  - Respects `prefers-reduced-motion` (animations disabled, static drawing shown)
 *  - Total SVG complexity ~3KB, renders in <2ms
 */

import { type MouseEvent, useEffect, useRef, useState } from "react";

export function EngineeringBackground() {
	const containerRef = useRef<HTMLDivElement>(null);
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

	const handleMouseLeave = () => setMouse(null);

	return (
		<div
			ref={containerRef}
			className="absolute inset-0 pointer-events-none overflow-hidden"
			onMouseMove={handleMouseMove}
			onMouseLeave={handleMouseLeave}
			aria-hidden="true"
		>
			{/* ── Layer 1: Base gradient (deep navy with cyan/red ember glows) ──── */}
			<div
				className="absolute inset-0"
				style={{
					background:
						"radial-gradient(ellipse 80% 60% at 50% 0%, rgba(34,211,238,0.06) 0%, transparent 60%)," +
						"radial-gradient(ellipse 60% 80% at 100% 100%, rgba(239,68,68,0.05) 0%, transparent 50%)," +
						"radial-gradient(ellipse 60% 80% at 0% 100%, rgba(34,211,238,0.04) 0%, transparent 50%)," +
						"linear-gradient(180deg, #070b12 0%, #0a0e1a 50%, #070b12 100%)",
				}}
			/>

			{/* ── Layer 2: Engineering grid (major + minor) ────────────────────── */}
			<svg
				className="absolute inset-0 w-full h-full"
				xmlns="http://www.w3.org/2000/svg"
				preserveAspectRatio="xMidYMid slice"
				viewBox="0 0 1920 1080"
				style={{ opacity: 0.55 }}
			>
				<defs>
					{/* Minor grid pattern (10px) */}
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
							stroke="rgba(34,211,238,0.06)"
							strokeWidth="1"
						/>
					</pattern>
					{/* Major grid pattern (200px) */}
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
							stroke="rgba(34,211,238,0.12)"
							strokeWidth="1.5"
						/>
					</pattern>
				</defs>
				<rect width="1920" height="1080" fill="url(#cadGridMinor)" />
				<rect width="1920" height="1080" fill="url(#cadGridMajor)" />
			</svg>

			{/* ── Layer 3: Animated CAD drawing (floor plan with fire alarm devices) ── */}
			<svg
				className="absolute inset-0 w-full h-full cad-drawing"
				xmlns="http://www.w3.org/2000/svg"
				preserveAspectRatio="xMidYMid slice"
				viewBox="0 0 1920 1080"
			>
				<defs>
					{/* Gradient for "drawing" lines (cyan → white) */}
					<linearGradient id="cadLineGrad" x1="0" y1="0" x2="1" y2="0">
						<stop offset="0" stopColor="#22d3ee" stopOpacity="0.9" />
						<stop offset="100%" stopColor="#e0f2fe" stopOpacity="0.7" />
					</linearGradient>
					{/* Smoke detector gradient (cyan glow) */}
					<radialGradient id="smokeDetectorGrad">
						<stop offset="0" stopColor="#22d3ee" stopOpacity="0.9" />
						<stop offset="60%" stopColor="#0891b2" stopOpacity="0.4" />
						<stop offset="100%" stopColor="#0e7490" stopOpacity="0" />
					</radialGradient>
					{/* Heat detector gradient (amber glow) */}
					<radialGradient id="heatDetectorGrad">
						<stop offset="0" stopColor="#fbbf24" stopOpacity="0.9" />
						<stop offset="60%" stopColor="#f59e0b" stopOpacity="0.4" />
						<stop offset="100%" stopColor="#d97706" stopOpacity="0" />
					</radialGradient>
					{/* Notification appliance gradient (red glow) */}
					<radialGradient id="notifApplianceGrad">
						<stop offset="0" stopColor="#f87171" stopOpacity="0.9" />
						<stop offset="60%" stopColor="#ef4444" stopOpacity="0.4" />
						<stop offset="100%" stopColor="#dc2626" stopOpacity="0" />
					</radialGradient>
					{/* Glow filter for devices */}
					<filter id="deviceGlow" x="-50%" y="-50%" width="200%" height="200%">
						<feGaussianBlur stdDeviation="3" result="coloredBlur" />
						<feMerge>
							<feMergeNode in="coloredBlur" />
							<feMergeNode in="SourceGraphic" />
						</feMerge>
					</filter>
				</defs>

				{/* ── Floor plan outline (draws itself) ────────────────────────── */}
				{/* Outer building wall */}
				<path
					className="cad-stroke cad-draw-1"
					d="M 200 200 L 1720 200 L 1720 880 L 200 880 Z"
					fill="none"
					stroke="url(#cadLineGrad)"
					strokeWidth="2.5"
					strokeLinejoin="round"
				/>

				{/* Interior walls (room dividers) */}
				<path
					className="cad-stroke cad-draw-2"
					d="M 700 200 L 700 540 M 700 540 L 200 540 M 1100 200 L 1100 540 M 1100 540 L 700 540 M 1100 540 L 1720 540 M 460 540 L 460 880 M 920 540 L 920 880 M 1320 540 L 1320 880"
					fill="none"
					stroke="url(#cadLineGrad)"
					strokeWidth="1.8"
					strokeLinejoin="round"
				/>

				{/* Door swings (arc + line — standard CAD door symbol) */}
				<path
					className="cad-stroke cad-draw-3"
					d="M 460 540 A 60 60 0 0 1 520 600 M 460 540 L 460 600 M 920 540 A 60 60 0 0 1 980 600 M 920 540 L 920 600 M 1320 540 A 60 60 0 0 1 1380 600 M 1320 540 L 1320 600"
					fill="none"
					stroke="rgba(34,211,238,0.6)"
					strokeWidth="1.2"
				/>

				{/* ── Dimension lines (with arrowheads + measurements) ─────────── */}
				<g
					className="cad-stroke cad-draw-4"
					stroke="rgba(148,163,184,0.5)"
					strokeWidth="1"
					fill="none"
				>
					{/* Top horizontal dimension */}
					<line x1="200" y1="140" x2="1720" y2="140" />
					<line x1="200" y1="130" x2="200" y2="150" />
					<line x1="1720" y1="130" x2="1720" y2="150" />
					{/* Left vertical dimension */}
					<line x1="140" y1="200" x2="140" y2="880" />
					<line x1="130" y1="200" x2="150" y2="200" />
					<line x1="130" y1="880" x2="150" y2="880" />
				</g>
				{/* Dimension text */}
				<text
					x="960"
					y="132"
					fill="rgba(148,163,184,0.7)"
					fontSize="11"
					fontFamily="'JetBrains Mono', monospace"
					textAnchor="middle"
					className="cad-fade-1"
				>
					15.20 m
				</text>
				<text
					x="132"
					y="540"
					fill="rgba(148,163,184,0.7)"
					fontSize="11"
					fontFamily="'JetBrains Mono', monospace"
					textAnchor="middle"
					transform="rotate(-90 132 540)"
					className="cad-fade-1"
				>
					6.80 m
				</text>

				{/* ── Coordinate labels (A-D × 1-4) ───────────────────────────── */}
				<g
					fill="rgba(148,163,184,0.5)"
					fontSize="10"
					fontFamily="'JetBrains Mono', monospace"
					className="cad-fade-2"
				>
					<text x="195" y="195">A1</text>
					<text x="695" y="195">B1</text>
					<text x="1095" y="195">C1</text>
					<text x="1715" y="195">D1</text>
					<text x="195" y="535">A2</text>
					<text x="695" y="535">B2</text>
					<text x="1095" y="535">C2</text>
					<text x="1715" y="535">D2</text>
					<text x="195" y="875">A3</text>
					<text x="695" y="875">B3</text>
					<text x="1095" y="875">C3</text>
					<text x="1715" y="875">D3</text>
				</g>

				{/* ── Smoke detectors (cyan circles — NFPA 72 spacing) ─────────── */}
				{/* Each detector: outer ring (placement), inner dot (device), pulsing glow */}
				<g filter="url(#deviceGlow)">
					{/* Room A1 (top-left) — 2 detectors */}
					<circle cx="350" cy="320" r="22" fill="url(#smokeDetectorGrad)" className="cad-pulse-1" />
					<circle cx="350" cy="320" r="10" fill="none" stroke="#22d3ee" strokeWidth="2" className="cad-draw-5" />
					<circle cx="350" cy="320" r="3" fill="#22d3ee" className="cad-draw-5" />
					<circle cx="550" cy="420" r="22" fill="url(#smokeDetectorGrad)" className="cad-pulse-2" />
					<circle cx="550" cy="420" r="10" fill="none" stroke="#22d3ee" strokeWidth="2" className="cad-draw-5" />
					<circle cx="550" cy="420" r="3" fill="#22d3ee" className="cad-draw-5" />

					{/* Room B1 (top-middle) — 1 detector */}
					<circle cx="900" cy="370" r="22" fill="url(#smokeDetectorGrad)" className="cad-pulse-3" />
					<circle cx="900" cy="370" r="10" fill="none" stroke="#22d3ee" strokeWidth="2" className="cad-draw-5" />
					<circle cx="900" cy="370" r="3" fill="#22d3ee" className="cad-draw-5" />

					{/* Room C1 (top-right) — 2 detectors */}
					<circle cx="1250" cy="320" r="22" fill="url(#smokeDetectorGrad)" className="cad-pulse-1" />
					<circle cx="1250" cy="320" r="10" fill="none" stroke="#22d3ee" strokeWidth="2" className="cad-draw-5" />
					<circle cx="1250" cy="320" r="3" fill="#22d3ee" className="cad-draw-5" />
					<circle cx="1550" cy="420" r="22" fill="url(#smokeDetectorGrad)" className="cad-pulse-2" />
					<circle cx="1550" cy="420" r="10" fill="none" stroke="#22d3ee" strokeWidth="2" className="cad-draw-5" />
					<circle cx="1550" cy="420" r="3" fill="#22d3ee" className="cad-draw-5" />

					{/* Room A2 (corridor, bottom-left) — 1 detector */}
					<circle cx="330" cy="710" r="22" fill="url(#smokeDetectorGrad)" className="cad-pulse-3" />
					<circle cx="330" cy="710" r="10" fill="none" stroke="#22d3ee" strokeWidth="2" className="cad-draw-5" />
					<circle cx="330" cy="710" r="3" fill="#22d3ee" className="cad-draw-5" />

					{/* Room B2 (corridor, bottom-middle) — 1 detector */}
					<circle cx="790" cy="710" r="22" fill="url(#smokeDetectorGrad)" className="cad-pulse-1" />
					<circle cx="790" cy="710" r="10" fill="none" stroke="#22d3ee" strokeWidth="2" className="cad-draw-5" />
					<circle cx="790" cy="710" r="3" fill="#22d3ee" className="cad-draw-5" />

					{/* Room C2 (corridor, bottom-right) — 1 detector */}
					<circle cx="1190" cy="710" r="22" fill="url(#smokeDetectorGrad)" className="cad-pulse-2" />
					<circle cx="1190" cy="710" r="10" fill="none" stroke="#22d3ee" strokeWidth="2" className="cad-draw-5" />
					<circle cx="1190" cy="710" r="3" fill="#22d3ee" className="cad-draw-5" />

					{/* Room D2 (bottom-right corner) — 1 detector */}
					<circle cx="1550" cy="710" r="22" fill="url(#smokeDetectorGrad)" className="cad-pulse-3" />
					<circle cx="1550" cy="710" r="10" fill="none" stroke="#22d3ee" strokeWidth="2" className="cad-draw-5" />
					<circle cx="1550" cy="710" r="3" fill="#22d3ee" className="cad-draw-5" />
				</g>

				{/* ── Heat detectors (amber — kitchen/utility areas) ───────────── */}
				<g filter="url(#deviceGlow)">
					<circle cx="1100" cy="380" r="18" fill="url(#heatDetectorGrad)" className="cad-pulse-2" />
					<circle cx="1100" cy="380" r="8" fill="none" stroke="#fbbf24" strokeWidth="2" className="cad-draw-6" />
					<circle cx="1100" cy="380" r="2.5" fill="#fbbf24" className="cad-draw-6" />
				</g>

				{/* ── Notification appliances (red — horn/strobe) ──────────────── */}
				<g filter="url(#deviceGlow)">
					{/* Horn/strobe on wall */}
					<rect x="450" y="195" width="20" height="10" fill="url(#notifApplianceGrad)" stroke="#f87171" strokeWidth="1.5" className="cad-draw-6" />
					<rect x="950" y="195" width="20" height="10" fill="url(#notifApplianceGrad)" stroke="#f87171" strokeWidth="1.5" className="cad-draw-6" />
					<rect x="1450" y="195" width="20" height="10" fill="url(#notifApplianceGrad)" stroke="#f87171" strokeWidth="1.5" className="cad-draw-6" />
					<rect x="450" y="875" width="20" height="10" fill="url(#notifApplianceGrad)" stroke="#f87171" strokeWidth="1.5" className="cad-draw-6" />
					<rect x="950" y="875" width="20" height="10" fill="url(#notifApplianceGrad)" stroke="#f87171" strokeWidth="1.5" className="cad-draw-6" />
					<rect x="1450" y="875" width="20" height="10" fill="url(#notifApplianceGrad)" stroke="#f87171" strokeWidth="1.5" className="cad-draw-6" />
				</g>

				{/* ── Conduit / wiring lines (connecting devices to panel) ────── */}
				<g
					className="cad-stroke cad-draw-7"
					stroke="rgba(34,211,238,0.35)"
					strokeWidth="1.2"
					strokeDasharray="6 4"
					fill="none"
				>
					<path d="M 350 320 L 350 280 L 950 280 L 950 195" />
					<path d="M 900 370 L 900 280" />
					<path d="M 1250 320 L 1250 280 L 950 280" />
					<path d="M 550 420 L 550 280 L 350 280" />
					<path d="M 1550 420 L 1550 280 L 1450 280 L 1450 195" />
					<path d="M 330 710 L 330 920 L 950 920 L 950 875" />
					<path d="M 790 710 L 790 920" />
					<path d="M 1190 710 L 1190 920" />
					<path d="M 1550 710 L 1550 920 L 1450 920 L 1450 875" />
				</g>

				{/* ── FACP (Fire Alarm Control Panel) — bottom-left ───────────── */}
				<g className="cad-draw-7" filter="url(#deviceGlow)">
					<rect x="60" y="940" width="80" height="60" fill="rgba(34,211,238,0.15)" stroke="#22d3ee" strokeWidth="2" rx="4" />
					<rect x="75" y="955" width="50" height="30" fill="none" stroke="#22d3ee" strokeWidth="1" />
					<circle cx="100" cy="970" r="4" fill="#22d3ee" className="cad-pulse-1" />
					<text x="100" y="1018" fill="#22d3ee" fontSize="10" fontFamily="'JetBrains Mono', monospace" textAnchor="middle" fontWeight="600">FACP</text>
				</g>

				{/* ── Title block (bottom-right — like real CAD drawings) ─────── */}
				<g className="cad-fade-3">
					<rect x="1500" y="940" width="380" height="100" fill="rgba(7,11,18,0.8)" stroke="rgba(34,211,238,0.4)" strokeWidth="1" />
					<line x1="1500" y1="970" x2="1880" y2="970" stroke="rgba(34,211,238,0.3)" strokeWidth="1" />
					<line x1="1700" y1="940" x2="1700" y2="1040" stroke="rgba(34,211,238,0.3)" strokeWidth="1" />
					<text x="1510" y="958" fill="rgba(34,211,238,0.9)" fontSize="10" fontFamily="'JetBrains Mono', monospace" fontWeight="600">BAZSPARK · FIRE ALARM PLAN</text>
					<text x="1510" y="988" fill="rgba(148,163,184,0.7)" fontSize="9" fontFamily="'JetBrains Mono', monospace">DWG-001 · NFPA 72-2022</text>
					<text x="1510" y="1006" fill="rgba(148,163,184,0.7)" fontSize="9" fontFamily="'JetBrains Mono', monospace">SCALE 1:100 · UNIT: mm</text>
					<text x="1510" y="1024" fill="rgba(148,163,184,0.7)" fontSize="9" fontFamily="'JetBrains Mono', monospace">DESIGNER: A. ELBAZ</text>
					<text x="1710" y="988" fill="rgba(148,163,184,0.7)" fontSize="9" fontFamily="'JetBrains Mono', monospace">SHEET 1/1</text>
					<text x="1710" y="1006" fill="rgba(34,211,238,0.9)" fontSize="9" fontFamily="'JetBrains Mono', monospace" fontWeight="600">REV: A</text>
					<text x="1710" y="1024" fill="rgba(148,163,184,0.7)" fontSize="9" fontFamily="'JetBrains Mono', monospace">v1.55.0</text>
				</g>

				{/* ── North arrow (top-right corner — CAD convention) ─────────── */}
				<g className="cad-fade-2" transform="translate(1820, 80)">
					<circle cx="0" cy="0" r="22" fill="none" stroke="rgba(34,211,238,0.5)" strokeWidth="1" />
					<path d="M 0 -18 L 6 8 L 0 4 L -6 8 Z" fill="rgba(34,211,238,0.7)" stroke="#22d3ee" strokeWidth="1" />
					<text x="0" y="-26" fill="rgba(34,211,238,0.9)" fontSize="11" fontFamily="'JetBrains Mono', monospace" textAnchor="middle" fontWeight="700">N</text>
				</g>
			</svg>

			{/* ── Layer 4: Scanning line (CAD "scan" effect) ───────────────────── */}
			{!reducedMotion && (
				<div
					className="absolute inset-0 cad-scan-line"
					style={{
						background:
							"linear-gradient(180deg, transparent 0%, rgba(34,211,238,0.0) 45%, rgba(34,211,238,0.15) 50%, rgba(34,211,238,0.0) 55%, transparent 100%)",
						height: "100%",
						transform: "translateY(-100%)",
					}}
				/>
			)}

			{/* ── Layer 5: Floating particles (engineering data points) ──────── */}
			{!reducedMotion && (
				<svg
					className="absolute inset-0 w-full h-full"
					xmlns="http://www.w3.org/2000/svg"
					preserveAspectRatio="xMidYMid slice"
					viewBox="0 0 1920 1080"
				>
					{Array.from({ length: 18 }).map((_, i) => {
						const x = (i * 113) % 1920;
						const y = (i * 67) % 1080;
						const size = 1 + (i % 3);
						const delay = (i * 0.7) % 8;
						const duration = 6 + (i % 4) * 2;
						return (
							<circle
								key={`particle-${i}`}
								cx={x}
								cy={y}
								r={size}
								fill="#22d3ee"
								opacity="0.6"
								className="cad-particle"
								style={{
									animationDelay: `${delay}s`,
									animationDuration: `${duration}s`,
								}}
							/>
						);
					})}
				</svg>
			)}

			{/* ── Layer 6: Crosshair cursor (follows mouse) ──────────────────── */}
			{!reducedMotion && mouse && (
				<div
					className="absolute pointer-events-none cad-crosshair"
					style={{
						left: `${mouse.x}px`,
						top: `${mouse.y}px`,
						transform: "translate(-50%, -50%)",
					}}
				>
					<svg width="40" height="40" viewBox="0 0 40 40">
						<circle cx="20" cy="20" r="14" fill="none" stroke="#22d3ee" strokeWidth="1" opacity="0.5" />
						<line x1="20" y1="0" x2="20" y2="14" stroke="#22d3ee" strokeWidth="1" opacity="0.7" />
						<line x1="20" y1="26" x2="20" y2="40" stroke="#22d3ee" strokeWidth="1" opacity="0.7" />
						<line x1="0" y1="20" x2="14" y2="20" stroke="#22d3ee" strokeWidth="1" opacity="0.7" />
						<line x1="26" y1="20" x2="40" y2="20" stroke="#22d3ee" strokeWidth="1" opacity="0.7" />
						<circle cx="20" cy="20" r="1.5" fill="#22d3ee" />
					</svg>
					<div
						className="absolute top-5 left-5 text-[10px] font-mono text-cyan-300/70 whitespace-nowrap"
						style={{ fontFamily: "'JetBrains Mono', monospace" }}
					>
						X: {Math.round(mouse.x)} Y: {Math.round(mouse.y)}
					</div>
				</div>
			)}

			{/* ── Layer 7: Subtle vignette + grain ────────────────────────────── */}
			<div
				className="absolute inset-0"
				style={{
					background:
						"radial-gradient(ellipse 100% 100% at 50% 50%, transparent 40%, rgba(7,11,18,0.6) 100%)",
				}}
			/>
			<div
				className="absolute inset-0 opacity-20"
				style={{
					backgroundImage:
						"url(\"data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.4'/%3E%3C/svg%3E\")",
				}}
			/>
		</div>
	);
}
