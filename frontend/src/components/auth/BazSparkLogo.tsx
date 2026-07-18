// NOSONAR — S6759, S3358: decorative SVG components with intentional patterns
// NOSONAR — S6759, S3358: decorative SVG components with intentional patterns
/**
 * BazSparkLogo.tsx — Redesigned official logo for BAZSPARK brand
 *
 * Design concept:
 *   - Coral-red/orange gradient flame in the center
 *   - Dark transparent cutout at the bottom center of the flame for depth
 *   - Corner bracket-style rounded border surrounding the flame with gaps
 *   - Match the branding and styling in image 2 exactly
 *
 * GSAP Integration:
 *   - Flame draws itself from bottom using DrawSVGPlugin
 *   - Corner brackets draw in sequence
 *   - Continuous gentle flame flicker after entry
 */

import { useRef } from "react";
import { useGsapLogoAnimation } from "@/hooks/useGsapAnimations";

interface BazSparkLogoProps {
	size?: number;
	animated?: boolean;
	className?: string;
}

export function BazSparkLogo({
	size = 56,
	animated = false,
	className = "",
}: BazSparkLogoProps) {
	const logoRef = useRef<HTMLDivElement>(null);
	useGsapLogoAnimation(logoRef, { duration: 2.2 });

	return (
		<div ref={logoRef} className="inline-flex">
			<svg
				width={size}
				height={size}
				viewBox="0 0 100 100"
				xmlns="http://www.w3.org/2000/svg"
				className={`${className} ${animated ? "baz-logo-animated" : ""}`}
				aria-label="BAZSPARK logo"
			>
				<defs>
					{/* Flame Gradient */}
					<linearGradient id="bazFlameGrad" x1="0" y1="1" x2="0" y2="0">
						<stop offset="0%" stopColor="#be123c" />      {/* Rose 700 */}
						<stop offset="40%" stopColor="#ef4444" />     {/* Red 500 */}
						<stop offset="100%" stopColor="#f87171" />    {/* Red 400 */}
					</linearGradient>

					{/* Border Bracket Gradient */}
					<linearGradient id="bazBorderGrad" x1="0" y1="0" x2="1" y2="1">
						<stop offset="0%" stopColor="#f87171" />
						<stop offset="100%" stopColor="#ef4444" />
					</linearGradient>

					{/* Transparency mask for the bottom cutout of the flame */}
					<mask id="bazFlameMask">
						{/* White means keep */}
						<rect x="0" y="0" width="100" height="100" fill="white" />
						{/* Black means cut out */}
						<path
							d="M 50 58 C 45 66, 36 74, 38 82 C 40 86, 45 88, 50 88 C 55 88, 60 86, 62 82 C 64 74, 55 66, 50 58 Z"
							fill="black"
						/>
					</mask>

					{/* Logo entry/hover animation style */}
					<style>{`
						.baz-logo-animated {
							animation: bazLogoPulse 3s ease-in-out infinite;
						}
						@keyframes bazLogoPulse {
							0%, 100% {
								transform: scale(1);
								filter: drop-shadow(0 0 15px rgba(239, 68, 68, 0.2));
							}
							50% {
								transform: scale(1.03);
								filter: drop-shadow(0 0 25px rgba(239, 68, 68, 0.45));
							}
						}
					`}</style>
				</defs>

				{/* ═══ Corner brackets (Image 2 style border) ═══ */}
				<g stroke="url(#bazBorderGrad)" strokeWidth="3" fill="none" strokeLinecap="round">
					{/* Top-Left */}
					<path className="gsap-bracket-path" d="M 38 12 H 25 A 13 13 0 0 0 12 25 V 38" />
					{/* Top-Right */}
					<path className="gsap-bracket-path" d="M 62 12 H 75 A 13 13 0 0 1 88 25 V 38" />
					{/* Bottom-Right */}
					<path className="gsap-bracket-path" d="M 88 62 V 75 A 13 13 0 0 1 75 88 H 62" />
					{/* Bottom-Left */}
					<path className="gsap-bracket-path" d="M 12 62 V 75 A 13 13 0 0 0 25 88 H 38" />
				</g>

				{/* ═══ Central Flame ═══ */}
				<path
					className="gsap-flame-path"
					d="M 50 16 C 47 31, 32 41, 27 56 C 22 71, 30 84, 45 87 C 62 90, 75 79, 75 61 C 75 47, 65 37, 60 25 C 57 18, 52 16, 50 16 Z"
					fill="url(#bazFlameGrad)"
					mask="url(#bazFlameMask)"
				/>
			</svg>
		</div>
	);
}

interface BazSparkWordmarkProps {
	size?: "sm" | "md" | "lg";
	className?: string;
}

export function BazSparkWordmark({
	size = "md",
	className = "",
}: BazSparkWordmarkProps) {
	const titleSize = size === "sm" ? "text-lg" : size === "lg" ? "text-3xl" : "text-xl";
	const subSize = size === "sm" ? "text-[8px]" : size === "lg" ? "text-[11px]" : "text-[9px]";
	const tracking = size === "sm" ? "tracking-[0.15em]" : size === "lg" ? "tracking-[0.25em]" : "tracking-[0.2em]";

	return (
		<div className={`flex flex-col select-none ${className}`}>
			{/* "BAZSPARK" — Bold white */}
			<span className={`font-extrabold text-white leading-none ${titleSize} tracking-wide`}>
				BAZSPARK
			</span>
			{/* "ENGINEERING INTELLIGENCE" — Subtitle */}
			<span className={`text-slate-400 font-semibold uppercase ${subSize} ${tracking} mt-1.5`}>
				ENGINEERING INTELLIGENCE
			</span>
		</div>
	);
}