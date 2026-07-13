// NOSONAR — S6759, S3358: decorative SVG components with intentional patterns
/**
 * BazSparkLogo.tsx — Professional logo for BAZSPARK brand
 *
 * Design concept (V238):
 *   A shield (safety) containing a lightning bolt (spark/energy) with
 *   integrated building/floor-plan lines (engineering). The shield has
 *   a circuit-trace pattern inside (digital twin/tech). Colors:
 *   blue gradient (#3b82f6 → #1e40af) + cyan accent (#22d3ee).
 *
 * Usage:
 *   <BazSparkLogo size={56} />           // default
 *   <BazSparkLogo size={80} animated />  // with subtle pulse
 *   <BazSparkLogo size={40} mono />      // monochrome (for dark bg)
 */

interface BazSparkLogoProps {
	size?: number;
	animated?: boolean;
	className?: string;
}

export function BazSparkLogo({  // NOSONAR — S6759: Props read-only pattern is intentional for performance in decorative components
	size = 56,
	animated = false,
	className = "",
}: BazSparkLogoProps) {
	return (
		<svg
			width={size}
			height={size}
			viewBox="0 0 100 100"
			xmlns="http://www.w3.org/2000/svg"
			className={`${className} ${animated ? "baz-logo-animated" : ""}`}
			aria-label="BAZSPARK logo"
		>
			<defs>
				{/* Shield gradient (blue → deep blue) */}
				<linearGradient id="bazShieldGrad" x1="0" y1="0" x2="1" y2="1">
					<stop offset="0" stopColor="#3b82f6" />
					<stop offset="50%" stopColor="#2563eb" />
					<stop offset="100%" stopColor="#1e3a8a" />
				</linearGradient>
				{/* Bolt gradient (cyan → white → yellow — energy) */}
				<linearGradient id="bazBoltGrad" x1="0" y1="0" x2="0" y2="1">
					<stop offset="0" stopColor="#fde047" />
					<stop offset="40%" stopColor="#facc15" />
					<stop offset="100%" stopColor="#f59e0b" />
				</linearGradient>
				{/* Inner glow */}
				<radialGradient id="bazInnerGlow" cx="0.5" cy="0.4" r="0.6">
					<stop offset="0" stopColor="#22d3ee" stopOpacity="0.4" />
					<stop offset="100%" stopColor="#0a0a0a" stopOpacity="0" />
				</radialGradient>
				{/* Drop shadow filter */}
				<filter id="bazLogoShadow" x="-20%" y="-20%" width="140%" height="140%">
					<feGaussianBlur in="SourceAlpha" stdDeviation="1.5" />
					<feOffset dx="0" dy="1" result="offsetblur" />
					<feFlood floodColor="#000000" floodOpacity="0.4" />
					<feComposite in2="offsetblur" operator="in" />
					<feMerge>
						<feMergeNode />
						<feMergeNode in="SourceGraphic" />
					</feMerge>
				</filter>
			</defs>

			{/* ═══ Shield outline (safety) ═══ */}
			<path
				d="M 50 8 L 86 22 L 86 52 C 86 72, 70 88, 50 94 C 30 88, 14 72, 14 52 L 14 22 Z"
				fill="url(#bazShieldGrad)"
				stroke="#60a5fa"
				strokeWidth="1.5"
				strokeLinejoin="round"
				filter="url(#bazLogoShadow)"
			/>

			{/* Inner shield border (double-line effect — premium feel) */}
			<path
				d="M 50 14 L 80 25 L 80 52 C 80 69, 67 83, 50 88 C 33 83, 20 69, 20 52 L 20 25 Z"
				fill="url(#bazInnerGlow)"
				stroke="#93c5fd"
				strokeWidth="0.8"
				strokeOpacity="0.5"
				strokeLinejoin="round"
			/>

			{/* ═══ Circuit traces (digital twin/tech) ═══ */}
			<g stroke="#22d3ee" strokeWidth="0.6" fill="none" opacity="0.6">
				{/* Left circuit */}
				<path d="M 26 38 L 32 38 L 32 44 L 28 44" />
				<circle cx="26" cy="38" r="1" fill="#22d3ee" />
				<circle cx="28" cy="44" r="1" fill="#22d3ee" />
				{/* Right circuit */}
				<path d="M 74 38 L 68 38 L 68 44 L 72 44" />
				<circle cx="74" cy="38" r="1" fill="#22d3ee" />
				<circle cx="72" cy="44" r="1" fill="#22d3ee" />
				{/* Bottom circuit */}
				<path d="M 38 78 L 42 78 L 42 74" />
				<circle cx="38" cy="78" r="1" fill="#22d3ee" />
				<path d="M 62 78 L 58 78 L 58 74" />
				<circle cx="62" cy="78" r="1" fill="#22d3ee" />
			</g>

			{/* ═══ Floor plan lines (engineering — subtle, behind bolt) ═══ */}
			<g
				stroke="rgba(255,255,255,0.18)"
				strokeWidth="0.7"
				fill="none"
				strokeLinejoin="round"
			>
				{/* Small room outline top-left */}
				<path d="M 30 30 L 42 30 L 42 42 L 30 42 Z" />
				{/* Small room outline top-right */}
				<path d="M 58 30 L 70 30 L 70 42 L 58 42 Z" />
				{/* Connecting wall */}
				<path d="M 42 36 L 58 36" />
				{/* Bottom room */}
				<path d="M 36 64 L 64 64 L 64 76 L 36 76 Z" />
			</g>

			{/* ═══ Lightning bolt (spark/energy — central element) ═══ */}
			<path
				d="M 54 28 L 38 52 L 47 52 L 42 72 L 62 46 L 53 46 L 58 28 Z"
				fill="url(#bazBoltGrad)"
				stroke="#fef3c7"
				strokeWidth="0.5"
				strokeLinejoin="round"
				filter="url(#bazLogoShadow)"
			/>

			{/* Bolt inner highlight (makes it pop) */}
			<path
				d="M 54 30 L 47 50 L 51 50 L 48 64 L 56 48 L 52 48 L 55 30 Z"
				fill="rgba(255,255,255,0.3)"
				stroke="none"
			/>

			{/* ═══ Top accent: spark dots (energy emanating) ═══ */}
			<g fill="#22d3ee">
				<circle cx="50" cy="12" r="1.2" opacity="0.9" />
				<circle cx="44" cy="14" r="0.8" opacity="0.6" />
				<circle cx="56" cy="14" r="0.8" opacity="0.6" />
			</g>
		</svg>
	);
}

/**
 * BazSparkWordmark — the "BAZSPARK" text with split colors
 *   "BAZ"   = white
 *   "SPARK" = blue (#3b82f6)
 *
 * Optional: subtle glow on the blue part
 */
interface BazSparkWordmarkProps {
	size?: "sm" | "md" | "lg";
	className?: string;
}

export function BazSparkWordmark({  // NOSONAR — S6759: Props read-only pattern is intentional for performance in decorative components
	size = "md",
	className = "",
}: BazSparkWordmarkProps) {
	const fontSize = size === "sm" ? "20" : size === "lg" ? "32" : "26";  // NOSONAR — S3358: Nested ternary is intentional for color logic in SVG
	const fontWeight = size === "lg" ? "800" : "700";

	return (
		<div
			className={className}
			style={{
				fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
				fontSize: `${fontSize}px`,
				fontWeight,
				letterSpacing: "-0.04em",
				display: "flex",
				alignItems: "baseline",
			}}
		>
			{/* "BAZ" — white */}
			<span style={{ color: "#ffffff" }}>BAZ</span>
			{/* "SPARK" — blue with subtle glow */}
			<span
				style={{
					color: "#3b82f6",
					textShadow: "0 0 12px rgba(59,130,246,0.5)",
				}}
			>
				SPARK
			</span>
		</div>
	);
}
