// NOSONAR — S6759, S3776, S6479, S3358, S7773: complex decorative SVG components with intentional patterns
/**
 * EngineeringBackground.tsx — V239 PROFESSIONAL 3D engineering + AI background
 *
 * THREE-LAYER VISUAL CONCEPT:
 *   Layer 1 (bottom): AutoCAD 2D floor plan — multi-color, multi-layer
 *                      (walls=white, doors=green, detectors=cyan, wiring=amber)
 *   Layer 2 (middle): AI neural network — glowing nodes + animated data pulses
 *                      traveling along the synapses (artificial intelligence)
 *   Layer 3 (top):    Revit 3D isometric building — realistic with
 *                      roof/walls/windows/door in distinct colors
 *
 * DEPTH EFFECTS:
 *   - Perspective transform on the whole canvas (slight 3D tilt)
 *   - Depth fog (gradient overlay) — distant elements fade
 *   - Parallax layers move at different rates
 *   - Scan beam sweeps diagonally (LiDAR / AI scanning effect)
 *
 * ANIMATIONS:
 *   - Floor plan: walls draw themselves, then devices appear, then wiring traces
 *   - AI network: nodes pulse, data packets travel along synapses continuously
 *   - Revit building: rotates subtly (±2°), windows light up sequentially
 *   - Scan beam: diagonal sweep every 8s (LiDAR scanning)
 *   - Particles: floating data points with depth (size = proximity)
 *   - HUD: live coordinate readout, NFPA compliance indicator, AI status
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
                        style={{
                                background: "radial-gradient(ellipse at 30% 50%, #0a0f1a 0%, #050709 70%, #000000 100%)",
                                perspective: "1200px",
                                pointerEvents: "none",
                                zIndex: 0,
                        }}
                        onMouseMove={handleMouseMove}
                        onMouseLeave={() => setMouse(null)}
                        aria-hidden="true"
                >
                        {/* ═══ Layer 0: Engineering grid (with slight 3D tilt) ═══ */}
                        <div
                                className="absolute inset-0"
                                style={{
                                        transformStyle: "preserve-3d",
                                        transform: reducedMotion ? "none" : "rotateX(8deg) rotateY(-4deg)",
                                        transformOrigin: "center center",
                                }}
                        >
                                <GridFloor reducedMotion={reducedMotion} />
                        </div>

                        {/* ═══ Layer 1: AutoCAD 2D floor plan (bottom-left) ═══ */}
                        <div
                                className="absolute"
                                style={{
                                        left: "4%",
                                        top: "12%",
                                        width: "42%",
                                        height: "38%",
                                        transformStyle: "preserve-3d",
                                        transform: reducedMotion ? "none" : "perspective(800px) rotateX(12deg)",
                                        transformOrigin: "center bottom",
                                }}
                        >
                                <AutoCAD2DPlan reducedMotion={reducedMotion} />
                        </div>

                        {/* ═══ Layer 2: AI neural network (center, full height) ═══ */}
                        <div
                                className="absolute"
                                style={{
                                        left: "0",
                                        top: "0",
                                        width: "100%",
                                        height: "100%",
                                        pointerEvents: "none",
                                }}
                        >
                                <AINeuralNetwork reducedMotion={reducedMotion} />
                        </div>

                        {/* ═══ Layer 3: Revit 3D building (bottom-center, overlapping) ═══ */}
                        <div
                                className="absolute"
                                style={{
                                        left: "20%",
                                        bottom: "8%",
                                        width: "30%",
                                        height: "45%",
                                        transformStyle: "preserve-3d",
                                        transform: reducedMotion ? "none" : "perspective(1000px) rotateY(-12deg) rotateX(8deg)",
                                        transformOrigin: "center center",
                                }}
                        >
                                <Revit3DBuilding reducedMotion={reducedMotion} />
                        </div>

                        {/* ═══ Layer 4: Scan beam (diagonal LiDAR sweep) ═══ */}
                        {!reducedMotion && <ScanBeam />}

                        {/* ═══ Layer 5: Depth particles ═══ */}
                        {!reducedMotion && <DepthParticles />}

                        {/* ═══ Layer 6: Depth fog (gradient overlay for 3D depth) ═══ */}
                        <div
                                className="absolute inset-0 pointer-events-none"
                                style={{
                                        background:
                                                "radial-gradient(ellipse 100% 80% at 50% 50%, transparent 30%, rgba(5,7,9,0.4) 70%, rgba(0,0,0,0.7) 100%)",
                                }}
                        />

                        {/* ═══ Layer 7: AutoCAD crosshair cursor ═══ */}
                        {mouse && !reducedMotion && <AutoCADCrosshair x={mouse.x} y={mouse.y} />}

                        {/* ═══ Layer 8: HUD (corners) ═══ */}
                        {!reducedMotion && <ProfessionalHUD />}
                </div>
        );
}

/* ═══════════════════════════════════════════════════════════════════════════
   GridFloor — 3D-perspective engineering grid (like AutoCAD viewport floor)
   ═══════════════════════════════════════════════════════════════════════════ */
function GridFloor({ reducedMotion }: { reducedMotion: boolean }) {
        return (
                <svg
                        className="absolute inset-0 w-full h-full"
                        xmlns="http://www.w3.org/2000/svg"
                        preserveAspectRatio="xMidYMid slice"
                        viewBox="0 0 1920 1080"
                >
                        <defs>
                                <pattern id="gridMinorV239" x="0" y="0" width="40" height="40" patternUnits="userSpaceOnUse">
                                        <path d="M 40 0 L 0 0 0 40" fill="none" stroke="rgba(60,80,110,0.18)" strokeWidth="1" />
                                </pattern>
                                <pattern id="gridMajorV239" x="0" y="0" width="200" height="200" patternUnits="userSpaceOnUse">
                                        <path d="M 200 0 L 0 0 0 200" fill="none" stroke="rgba(90,120,160,0.25)" strokeWidth="1" />
                                </pattern>
                                <radialGradient id="gridGlowV239" cx="0.5" cy="0.5" r="0.6">
                                        <stop offset="0" stopColor="rgba(59,130,246,0.06)" />
                                        <stop offset="100%" stopColor="transparent" />
                                </radialGradient>
                        </defs>
                        <rect width="1920" height="1080" fill="url(#gridMinorV239)" />
                        <rect width="1920" height="1080" fill="url(#gridMajorV239)" />
                        <rect width="1920" height="1080" fill="url(#gridGlowV239)" />
                </svg>
        );
}

/* ═══════════════════════════════════════════════════════════════════════════
   AutoCAD2DPlan — PROFESSIONAL multi-color floor plan
   Layers:
     - Walls: white (#e8e8e8) — thick
     - Doors: green (#22c55e) — with swing arcs
     - Smoke detectors: cyan (#22d3ee) — with NFPA coverage radius
     - Heat detectors: amber (#fbbf24)
     - Horn/strobe: red (#ef4444)
     - Wiring: amber dashed (#f59e0b)
     - Dimensions: gray with measurements
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
                                {/* Wall fill pattern (hatched — like AutoCAD wall section) */}
                                <pattern id="wallHatch" x="0" y="0" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                                        <line x1="0" y1="0" x2="0" y2="6" stroke="rgba(232,232,232,0.3)" strokeWidth="1" />
                                </pattern>
                                <radialGradient id="smokeCoverage">
                                        <stop offset="0" stopColor="rgba(34,211,238,0.25)" />
                                        <stop offset="70%" stopColor="rgba(34,211,238,0.08)" />
                                        <stop offset="100%" stopColor="rgba(34,211,238,0)" />
                                </radialGradient>
                                <radialGradient id="heatCoverage">
                                        <stop offset="0" stopColor="rgba(251,191,36,0.25)" />
                                        <stop offset="100%" stopColor="rgba(251,191,36,0)" />
                                </radialGradient>
                                <filter id="cadGlow" x="-50%" y="-50%" width="200%" height="200%">
                                        <feGaussianBlur stdDeviation="2" result="b" />
                                        <feMerge>
                                                <feMergeNode in="b" />
                                                <feMergeNode in="SourceGraphic" />
                                        </feMerge>
                                </filter>
                        </defs>

                        {/* ═══ Title bar (CAD drawing header) ═══ */}
                        <rect x="80" y="20" width="340" height="14" fill="rgba(20,30,45,0.6)" stroke="rgba(90,120,160,0.4)" strokeWidth="0.5" />
                        <text x="92" y="30" fill="rgba(180,200,220,0.7)" fontSize="7" fontFamily="'JetBrains Mono', monospace" letterSpacing="1">
                                FIRE ALARM PLAN — LEVEL 1 — NFPA 72-2022
                        </text>
                        <text x="396" y="30" fill="rgba(180,200,220,0.7)" fontSize="7" fontFamily="'JetBrains Mono', monospace" textAnchor="end">
                                DWG-001
                        </text>

                        {/* ═══ Outer walls (white, thick, with hatch fill) ═══ */}
                        <path
                                className={reducedMotion ? "" : "cad-stroke cad-draw-1"}
                                d="M 80 60 L 420 60 L 420 290 L 80 290 Z"
                                fill="url(#wallHatch)"
                                stroke="#e8e8e8"
                                strokeWidth="3"
                                strokeLinejoin="miter"
                        />

                        {/* ═══ Interior walls (white, slightly thinner) ═══ */}
                        <path
                                className={reducedMotion ? "" : "cad-stroke cad-draw-2"}
                                d="M 230 60 L 230 180 M 80 180 L 230 180 M 320 60 L 320 180 M 230 180 L 420 180 M 175 180 L 175 290 M 320 180 L 320 290"
                                fill="none"
                                stroke="#e8e8e8"
                                strokeWidth="2.2"
                                strokeLinejoin="miter"
                        />

                        {/* ═══ Doors (green with swing arcs) ═══ */}
                        <g className={reducedMotion ? "" : "cad-fade-1"}>
                                {/* Door 1: top wall, room A→B */}
                                <line x1="195" y1="60" x2="215" y2="60" stroke="#0a0a0a" strokeWidth="3" />
                                <path d="M 195 60 A 20 20 0 0 1 215 80 M 195 60 L 195 80" fill="none" stroke="#22c55e" strokeWidth="1.2" />
                                {/* Door 2: middle wall */}
                                <line x1="265" y1="180" x2="285" y2="180" stroke="#0a0a0a" strokeWidth="3" />
                                <path d="M 265 180 A 20 20 0 0 1 285 200 M 265 180 L 265 200" fill="none" stroke="#22c55e" strokeWidth="1.2" />
                                {/* Door 3: vertical wall */}
                                <line x1="175" y1="220" x2="175" y2="240" stroke="#0a0a0a" strokeWidth="3" />
                                <path d="M 175 220 A 20 20 0 0 0 195 240 M 175 220 L 195 220" fill="none" stroke="#22c55e" strokeWidth="1.2" />
                                {/* Door 4: main entrance (bottom) */}
                                <line x1="240" y1="290" x2="270" y2="290" stroke="#0a0a0a" strokeWidth="3" />
                                <path d="M 240 290 A 30 30 0 0 0 270 260 M 240 290 L 240 260" fill="none" stroke="#22c55e" strokeWidth="1.4" />
                        </g>

                        {/* ═══ Dimension lines (gray, with measurements) ═══ */}
                        <g
                                className={reducedMotion ? "" : "cad-fade-1"}
                                stroke="rgba(140,160,180,0.6)"
                                strokeWidth="0.8"
                                fill="none"
                        >
                                <line x1="80" y1="42" x2="420" y2="42" />
                                <line x1="80" y1="36" x2="80" y2="48" />
                                <line x1="420" y1="36" x2="420" y2="48" />
                                <line x1="58" y1="60" x2="58" y2="290" />
                                <line x1="52" y1="60" x2="64" y2="60" />
                                <line x1="52" y1="290" x2="64" y2="290" />
                        </g>
                        <text x="250" y="38" fill="rgba(180,200,220,0.7)" fontSize="8" fontFamily="'JetBrains Mono', monospace" textAnchor="middle" className={reducedMotion ? "" : "cad-fade-1"}>
                                15.20 m
                        </text>
                        <text x="50" y="178" fill="rgba(180,200,220,0.7)" fontSize="8" fontFamily="'JetBrains Mono', monospace" textAnchor="middle" transform="rotate(-90 50 178)" className={reducedMotion ? "" : "cad-fade-1"}>
                                8.50 m
                        </text>

                        {/* ═══ Smoke detectors (cyan, with NFPA coverage radius) ═══ */}
                        <g className={reducedMotion ? "" : "cad-fade-2"} filter="url(#cadGlow)">
                                {/* Room A (top-left) */}
                                <circle cx="140" cy="120" r="32" fill="url(#smokeCoverage)" className={reducedMotion ? "" : "cad-pulse-1"} />
                                <circle cx="140" cy="120" r="6" fill="none" stroke="#22d3ee" strokeWidth="1.5" />
                                <circle cx="140" cy="120" r="2" fill="#22d3ee" />
                                <text x="140" y="138" fill="#22d3ee" fontSize="6" fontFamily="'JetBrains Mono', monospace" textAnchor="middle">S1</text>

                                <circle cx="190" cy="150" r="32" fill="url(#smokeCoverage)" className={reducedMotion ? "" : "cad-pulse-2"} />
                                <circle cx="190" cy="150" r="6" fill="none" stroke="#22d3ee" strokeWidth="1.5" />
                                <circle cx="190" cy="150" r="2" fill="#22d3ee" />
                                <text x="190" y="168" fill="#22d3ee" fontSize="6" fontFamily="'JetBrains Mono', monospace" textAnchor="middle">S2</text>

                                {/* Room B (top-middle) */}
                                <circle cx="275" cy="120" r="32" fill="url(#smokeCoverage)" className={reducedMotion ? "" : "cad-pulse-3"} />
                                <circle cx="275" cy="120" r="6" fill="none" stroke="#22d3ee" strokeWidth="1.5" />
                                <circle cx="275" cy="120" r="2" fill="#22d3ee" />
                                <text x="275" y="138" fill="#22d3ee" fontSize="6" fontFamily="'JetBrains Mono', monospace" textAnchor="middle">S3</text>

                                {/* Room C (top-right) */}
                                <circle cx="375" cy="120" r="32" fill="url(#smokeCoverage)" className={reducedMotion ? "" : "cad-pulse-1"} />
                                <circle cx="375" cy="120" r="6" fill="none" stroke="#22d3ee" strokeWidth="1.5" />
                                <circle cx="375" cy="120" r="2" fill="#22d3ee" />
                                <text x="375" y="138" fill="#22d3ee" fontSize="6" fontFamily="'JetBrains Mono', monospace" textAnchor="middle">S4</text>

                                {/* Bottom rooms */}
                                <circle cx="125" cy="240" r="32" fill="url(#smokeCoverage)" className={reducedMotion ? "" : "cad-pulse-2"} />
                                <circle cx="125" cy="240" r="6" fill="none" stroke="#22d3ee" strokeWidth="1.5" />
                                <circle cx="125" cy="240" r="2" fill="#22d3ee" />
                                <text x="125" y="258" fill="#22d3ee" fontSize="6" fontFamily="'JetBrains Mono', monospace" textAnchor="middle">S5</text>

                                <circle cx="250" cy="240" r="32" fill="url(#smokeCoverage)" className={reducedMotion ? "" : "cad-pulse-3"} />
                                <circle cx="250" cy="240" r="6" fill="none" stroke="#22d3ee" strokeWidth="1.5" />
                                <circle cx="250" cy="240" r="2" fill="#22d3ee" />
                                <text x="250" y="258" fill="#22d3ee" fontSize="6" fontFamily="'JetBrains Mono', monospace" textAnchor="middle">S6</text>

                                <circle cx="375" cy="240" r="32" fill="url(#smokeCoverage)" className={reducedMotion ? "" : "cad-pulse-1"} />
                                <circle cx="375" cy="240" r="6" fill="none" stroke="#22d3ee" strokeWidth="1.5" />
                                <circle cx="375" cy="240" r="2" fill="#22d3ee" />
                                <text x="375" y="258" fill="#22d3ee" fontSize="6" fontFamily="'JetBrains Mono', monospace" textAnchor="middle">S7</text>
                        </g>

                        {/* ═══ Heat detector (amber — kitchen area) ═══ */}
                        <g className={reducedMotion ? "" : "cad-fade-3"} filter="url(#cadGlow)">
                                <circle cx="370" cy="240" r="20" fill="url(#heatCoverage)" className={reducedMotion ? "" : "cad-pulse-2"} />
                                <polygon points="370,232 374,242 370,238 366,242" fill="#fbbf24" />
                                <circle cx="370" cy="240" r="5" fill="none" stroke="#fbbf24" strokeWidth="1.2" />
                                <text x="370" y="270" fill="#fbbf24" fontSize="6" fontFamily="'JetBrains Mono', monospace" textAnchor="middle">H1</text>
                        </g>

                        {/* ═══ Horn/Strobe devices (red — notification appliances) ═══ */}
                        <g className={reducedMotion ? "" : "cad-fade-3"} filter="url(#cadGlow)">
                                {/* Wall-mounted horn/strobes */}
                                <rect x="135" y="56" width="10" height="6" fill="#ef4444" stroke="#fca5a5" strokeWidth="0.5" />
                                <rect x="270" y="56" width="10" height="6" fill="#ef4444" stroke="#fca5a5a5" strokeWidth="0.5" />
                                <rect x="370" y="56" width="10" height="6" fill="#ef4444" stroke="#fca5a5" strokeWidth="0.5" />
                                <rect x="135" y="288" width="10" height="6" fill="#ef4444" stroke="#fca5a5" strokeWidth="0.5" />
                                <rect x="370" y="288" width="10" height="6" fill="#ef4444" stroke="#fca5a5" strokeWidth="0.5" />
                        </g>

                        {/* ═══ Wiring / conduit (amber dashed — connecting devices to FACP) ═══ */}
                        <g
                                className={reducedMotion ? "" : "cad-stroke cad-draw-4"}
                                stroke="#f59e0b"
                                strokeWidth="1.2"
                                strokeDasharray="4 3"
                                fill="none"
                                opacity="0.7"
                        >
                                <path d="M 140 120 L 140 80 L 270 80 L 270 60" />
                                <path d="M 275 120 L 275 80" />
                                <path d="M 375 120 L 375 80 L 270 80" />
                                <path d="M 190 150 L 190 80 L 140 80" />
                                <path d="M 125 240 L 125 310 L 250 310 L 250 290" />
                                <path d="M 250 240 L 250 310" />
                                <path d="M 375 240 L 375 310 L 250 310" />
                        </g>

                        {/* ═══ FACP (Fire Alarm Control Panel) ═══ */}
                        <g className={reducedMotion ? "" : "cad-fade-3"}>
                                <rect x="30" y="305" width="40" height="28" fill="rgba(59,130,246,0.15)" stroke="#3b82f6" strokeWidth="1.5" rx="2" />
                                <rect x="35" y="310" width="30" height="14" fill="none" stroke="#3b82f6" strokeWidth="0.8" />
                                <circle cx="42" cy="317" r="2" fill="#22c55e" className={reducedMotion ? "" : "cad-pulse-1"} />
                                <circle cx="50" cy="317" r="2" fill="#fbbf24" />
                                <circle cx="58" cy="317" r="2" fill="#ef4444" className={reducedMotion ? "" : "cad-pulse-3"} />
                                <text x="50" y="332" fill="#3b82f6" fontSize="6" fontFamily="'JetBrains Mono', monospace" textAnchor="middle" fontWeight="600">FACP</text>
                        </g>

                        {/* ═══ Room labels ═══ */}
                        <g fill="rgba(180,200,220,0.4)" fontSize="7" fontFamily="'JetBrains Mono', monospace" textAnchor="middle" className={reducedMotion ? "" : "cad-fade-3"}>
                                <text x="155" y="105">OFFICE A</text>
                                <text x="275" y="105">CORRIDOR</text>
                                <text x="375" y="105">OFFICE B</text>
                                <text x="125" y="225">STORAGE</text>
                                <text x="250" y="225">LOBBY</text>
                                <text x="375" y="225">KITCHEN</text>
                        </g>

                        {/* ═══ Layer label (bottom) ═══ */}
                        <text x="250" y="345" fill="rgba(34,211,238,0.6)" fontSize="9" fontFamily="'JetBrains Mono', monospace" textAnchor="middle" className={reducedMotion ? "" : "cad-fade-3"} letterSpacing="2">
                                AUTOCAD · 2D FLOOR PLAN
                        </text>
                </svg>
        );
}

/* ═══════════════════════════════════════════════════════════════════════════
   AINeuralNetwork — glowing neural network with traveling data pulses
   Visualizes the "AI" analyzing the CAD drawing
   ═══════════════════════════════════════════════════════════════════════════ */
function AINeuralNetwork({ reducedMotion }: { reducedMotion: boolean }) {
        // Network nodes positioned across the screen
        // Layer 1 (input): left side — receives data from CAD
        // Layer 2 (hidden 1): center-left
        // Layer 3 (hidden 2): center-right
        // Layer 4 (output): right side — sends to Revit
        const nodes = [
                // Input layer (x=200)
                { id: "i1", x: 200, y: 200, layer: 0 },
                { id: "i2", x: 200, y: 320, layer: 0 },
                { id: "i3", x: 200, y: 440, layer: 0 },
                { id: "i4", x: 200, y: 560, layer: 0 },
                { id: "i5", x: 200, y: 680, layer: 0 },
                { id: "i6", x: 200, y: 800, layer: 0 },
                // Hidden layer 1 (x=600)
                { id: "h1a", x: 600, y: 240, layer: 1 },
                { id: "h1b", x: 600, y: 380, layer: 1 },
                { id: "h1c", x: 600, y: 520, layer: 1 },
                { id: "h1d", x: 600, y: 660, layer: 1 },
                { id: "h1e", x: 600, y: 800, layer: 1 },
                // Hidden layer 2 (x=1000)
                { id: "h2a", x: 1000, y: 280, layer: 2 },
                { id: "h2b", x: 1000, y: 420, layer: 2 },
                { id: "h2c", x: 1000, y: 560, layer: 2 },
                { id: "h2d", x: 1000, y: 700, layer: 2 },
                // Output layer (x=1400)
                { id: "o1", x: 1400, y: 320, layer: 3 },
                { id: "o2", x: 1400, y: 460, layer: 3 },
                { id: "o3", x: 1400, y: 600, layer: 3 },
                { id: "o4", x: 1400, y: 740, layer: 3 },
        ];

        // Synapses (connections) — each connects a node to the next layer
        const synapses: { from: string; to: string }[] = [];
        nodes.forEach((n) => {
                if (n.layer < 3) {
                        nodes.filter((m) => m.layer === n.layer + 1).forEach((m) => {
                                synapses.push({ from: n.id, to: m.id });
                        });
                }
        });

        const getNode = (id: string) => nodes.find((n) => n.id === id)!;

        // Data pulses traveling along synapses (staggered)
        const pulses = synapses.slice(0, 24).map((s, i) => ({
                from: getNode(s.from),
                to: getNode(s.to),
                delay: (i * 0.4) % 8,
        }));

        return (
                <svg
                        className="absolute inset-0 w-full h-full"
                        xmlns="http://www.w3.org/2000/svg"
                        preserveAspectRatio="xMidYMid slice"
                        viewBox="0 0 1600 1000"
                        style={{ opacity: 0.55 }}
                >
                        <defs>
                                <radialGradient id="neuronGlow">
                                        <stop offset="0" stopColor="#a855f7" stopOpacity="1" />
                                        <stop offset="50%" stopColor="#7c3aed" stopOpacity="0.6" />
                                        <stop offset="100%" stopColor="#7c3aed" stopOpacity="0" />
                                </radialGradient>
                                <radialGradient id="neuronGlowActive">
                                        <stop offset="0" stopColor="#22d3ee" stopOpacity="1" />
                                        <stop offset="50%" stopColor="#3b82f6" stopOpacity="0.7" />
                                        <stop offset="100%" stopColor="#3b82f6" stopOpacity="0" />
                                </radialGradient>
                                <filter id="neuronBlur" x="-50%" y="-50%" width="200%" height="200%">
                                        <feGaussianBlur stdDeviation="1.5" />
                                </filter>
                        </defs>

                        {/* Synapses (connections) */}
                        <g stroke="rgba(124,58,237,0.15)" strokeWidth="0.6" fill="none">
                                {synapses.map((s, i) => {
                                        const from = getNode(s.from);
                                        const to = getNode(s.to);
                                        return (
                                                <line
                                                        key={`syn-${i}`}
                                                        x1={from.x}
                                                        y1={from.y}
                                                        x2={to.x}
                                                        y2={to.y}
                                                />
                                        );
                                })}
                        </g>

                        {/* Animated data pulses traveling along synapses */}
                        {!reducedMotion && pulses.map((p, i) => (
                                <circle
                                        key={`pulse-${i}`}
                                        r="3"
                                        fill="#22d3ee"
                                        filter="url(#neuronBlur)"
                                        className="ai-data-pulse"
                                        style={{ animationDelay: `${p.delay}s` }}
                                >
                                        <animateMotion
                                                dur="3s"
                                                repeatCount="indefinite"
                                                path={`M ${p.from.x} ${p.from.y} L ${p.to.x} ${p.to.y}`}
                                                begin={`${p.delay}s`}
                                        />
                                </circle>
                        ))}

                        {/* Nodes (neurons) */}
                        <g>
                                {nodes.map((n, i) => (
                                        <g key={`node-${n.id}`}>
                                                {/* Glow halo */}
                                                <circle
                                                        cx={n.x}
                                                        cy={n.y}
                                                        r="14"
                                                        fill="url(#neuronGlow)"
                                                        className={reducedMotion ? "" : `ai-neuron-pulse-${(i % 3) + 1}`}
                                                />
                                                {/* Core */}
                                                <circle
                                                        cx={n.x}
                                                        cy={n.y}
                                                        r="3.5"
                                                        fill={n.layer === 0 ? "#22d3ee" : n.layer === 3 ? "#22c55e" : "#a855f7"}
                                                />
                                                {/* Ring */}
                                                <circle
                                                        cx={n.x}
                                                        cy={n.y}
                                                        r="6"
                                                        fill="none"
                                                        stroke={n.layer === 0 ? "#22d3ee" : n.layer === 3 ? "#22c55e" : "#a855f7"}
                                                        strokeWidth="0.8"
                                                        opacity="0.6"
                                                />
                                        </g>
                                ))}
                        </g>

                        {/* Layer labels */}
                        <g fill="rgba(168,85,247,0.4)" fontSize="10" fontFamily="'JetBrains Mono', monospace" textAnchor="middle" className={reducedMotion ? "" : "cad-fade-3"} letterSpacing="2">
                                <text x="200" y="120">INPUT</text>
                                <text x="200" y="135" fontSize="7">CAD DATA</text>
                                <text x="600" y="120">HIDDEN 1</text>
                                <text x="1000" y="120">HIDDEN 2</text>
                                <text x="1400" y="120">OUTPUT</text>
                                <text x="1400" y="135" fontSize="7">REVIT MODEL</text>
                        </g>

                        {/* AI status text (top center) */}
                        <g className={reducedMotion ? "" : "cad-fade-3"}>
                                <rect x="650" y="30" width="300" height="22" fill="rgba(20,30,45,0.7)" stroke="rgba(168,85,247,0.4)" strokeWidth="0.5" rx="3" />
                                <circle cx="668" cy="41" r="3" fill="#22c55e" className={reducedMotion ? "" : "cad-pulse-1"} />
                                <text x="680" y="44" fill="rgba(168,85,247,0.8)" fontSize="9" fontFamily="'JetBrains Mono', monospace" letterSpacing="1">
                                        AI NEURAL NETWORK · ANALYZING · 24 SYNAPSES ACTIVE
                                </text>
                        </g>
                </svg>
        );
}

/* ═══════════════════════════════════════════════════════════════════════════
   Revit3DBuilding — PROFESSIONAL 3D isometric building
   Realistic with: roof (red), walls (beige), windows (blue glass),
   door (brown), smoke detectors inside (cyan glow)
   ═══════════════════════════════════════════════════════════════════════════ */
function Revit3DBuilding({ reducedMotion }: { reducedMotion: boolean }) {
        // Isometric projection: 3D → 2D
        const iso = (x: number, y: number, z: number): string => {
                const ix = (x - y) * 0.866;
                const iy = (x + y) * 0.5 - z;
                return `${ix + 200},${iy + 160}`;
        };

        // Building: 200w × 140d × 120h
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

        // Roof apex (peaked roof)
        const roofApex = iso(100, 70, 170);

        return (
                <svg
                        width="100%"
                        height="100%"
                        viewBox="0 0 400 320"
                        xmlns="http://www.w3.org/2000/svg"
                        preserveAspectRatio="xMidYMid meet"
                        className={reducedMotion ? "" : "revit-rotate"}
                >
                        <defs>
                                <linearGradient id="wallFront" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="0" stopColor="#d4c5a0" />
                                        <stop offset="100%" stopColor="#a89878" />
                                </linearGradient>
                                <linearGradient id="wallRight" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="0" stopColor="#a89878" />
                                        <stop offset="100%" stopColor="#7a6e58" />
                                </linearGradient>
                                <linearGradient id="roofGrad" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="0" stopColor="#b91c1c" />
                                        <stop offset="100%" stopColor="#7f1d1d" />
                                </linearGradient>
                                <linearGradient id="roofSide" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="0" stopColor="#7f1d1d" />
                                        <stop offset="100%" stopColor="#5a1414" />
                                </linearGradient>
                                <linearGradient id="windowGlass" x1="0" y1="0" x2="1" y2="1">
                                        <stop offset="0" stopColor="#60a5fa" stopOpacity="0.8" />
                                        <stop offset="100%" stopColor="#1e40af" stopOpacity="0.9" />
                                </linearGradient>
                                <radialGradient id="detectorGlow3d">
                                        <stop offset="0" stopColor="#22d3ee" stopOpacity="0.9" />
                                        <stop offset="100%" stopColor="#22d3ee" stopOpacity="0" />
                                </radialGradient>
                                <filter id="revitShadow" x="-20%" y="-20%" width="140%" height="140%">
                                        <feGaussianBlur in="SourceAlpha" stdDeviation="2" />
                                        <feOffset dx="2" dy="3" result="ob" />
                                        <feFlood floodColor="#000" floodOpacity="0.5" />
                                        <feComposite in2="ob" operator="in" />
                                        <feMerge>
                                                <feMergeNode />
                                                <feMergeNode in="SourceGraphic" />
                                        </feMerge>
                                </filter>
                        </defs>

                        {/* Ground shadow (ellipse under building) */}
                        <ellipse
                                cx="200"
                                cy="245"
                                rx="120"
                                ry="20"
                                fill="rgba(0,0,0,0.4)"
                                filter="url(#revitShadow)"
                        />

                        {/* ═══ Back-left face (hidden, dashed) ═══ */}
                        <polygon
                                points={`${v.bfl} ${v.bbl} ${v.tbl} ${v.tfl}`}
                                fill="rgba(168,152,120,0.1)"
                                stroke="rgba(168,152,120,0.3)"
                                strokeWidth="0.8"
                                strokeDasharray="3 3"
                                className={reducedMotion ? "" : "cad-stroke cad-draw-4"}
                        />

                        {/* ═══ Right face (visible — darker wall) ═══ */}
                        <polygon
                                points={`${v.bfr} ${v.bbr} ${v.tbr} ${v.tfr}`}
                                fill="url(#wallRight)"
                                stroke="#7a6e58"
                                strokeWidth="1"
                                className={reducedMotion ? "" : "cad-stroke cad-draw-5"}
                        />

                        {/* Windows on right face */}
                        <g className={reducedMotion ? "" : "cad-fade-2"}>
                                {[
                                        [200, 40, 40],
                                        [200, 80, 40],
                                        [200, 40, 80],
                                        [200, 80, 80],
                                ].map(([face, wy, wz], i) => {
                                        const x1 = iso(face, wy, wz);
                                        const x2 = iso(face, wy + 30, wz);
                                        const x3 = iso(face, wy + 30, wz + 25);
                                        const x4 = iso(face, wy, wz + 25);
                                        return (
                                                <polygon
                                                        key={`rwin-${i}`}
                                                        points={`${x1} ${x2} ${x3} ${x4}`}
                                                        fill="url(#windowGlass)"
                                                        stroke="#1e3a5f"
                                                        strokeWidth="0.6"
                                                        className={reducedMotion ? "" : `window-light-${(i % 3) + 1}`}
                                                />
                                        );
                                })}
                        </g>

                        {/* ═══ Front face (visible — lighter wall) ═══ */}
                        <polygon
                                points={`${v.bfl} ${v.bfr} ${v.tfr} ${v.tfl}`}
                                fill="url(#wallFront)"
                                stroke="#a89878"
                                strokeWidth="1"
                                className={reducedMotion ? "" : "cad-stroke cad-draw-6"}
                        />

                        {/* Windows on front face (with sequential light-up) */}
                        <g className={reducedMotion ? "" : "cad-fade-2"}>
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
                                        const wTR = iso(wx + 30, 0, wz + 25);
                                        const wTL = iso(wx, 0, wz + 25);
                                        return (
                                                <polygon
                                                        key={`fwin-${i}`}
                                                        points={`${wBL} ${wBR} ${wTR} ${wTL}`}
                                                        fill="url(#windowGlass)"
                                                        stroke="#1e3a5f"
                                                        strokeWidth="0.6"
                                                        className={reducedMotion ? "" : `window-light-${(i % 3) + 1}`}
                                                />
                                        );
                                })}
                        </g>

                        {/* Door (front face, bottom center — brown) */}
                        <polygon
                                points={`${iso(95, 0, 0)} ${iso(125, 0, 0)} ${iso(125, 0, 55)} ${iso(95, 0, 55)}`}
                                fill="#6b4423"
                                stroke="#4a2f18"
                                strokeWidth="0.8"
                                className={reducedMotion ? "" : "cad-fade-3"}
                        />
                        {/* Door handle */}
                        <circle cx={parseFloat(iso(120, 0, 28).split(",")[0])} cy={parseFloat(iso(120, 0, 28).split(",")[1])} r="1.5" fill="#fbbf24" />

                        {/* ═══ Peaked roof (red — two slopes) ═══ */}
                        <polygon
                                points={`${v.tfl} ${v.tfr} ${roofApex}`}
                                fill="url(#roofGrad)"
                                stroke="#7f1d1d"
                                strokeWidth="1"
                                className={reducedMotion ? "" : "cad-stroke cad-draw-6"}
                        />
                        <polygon
                                points={`${v.tfr} ${v.tbr} ${roofApex}`}
                                fill="url(#roofSide)"
                                stroke="#5a1414"
                                strokeWidth="1"
                                className={reducedMotion ? "" : "cad-stroke cad-draw-6"}
                        />
                        <polygon
                                points={`${v.tbr} ${v.tbl} ${roofApex}`}
                                fill="url(#roofSide)"
                                stroke="#5a1414"
                                strokeWidth="1"
                                className={reducedMotion ? "" : "cad-stroke cad-draw-6"}
                                opacity="0.7"
                        />

                        {/* ═══ Smoke detectors inside (visible through semi-transparent front wall) ═══ */}
                        <g className={reducedMotion ? "" : "cad-fade-3"} filter="url(#revitShadow)">
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
                                                                r="12"
                                                                fill="url(#detectorGlow3d)"
                                                                className={reducedMotion ? "" : `cad-pulse-${(i % 3) + 1}`}
                                                        />
                                                        <circle cx={px} cy={py} r="4" fill="none" stroke="#22d3ee" strokeWidth="1.2" />
                                                        <circle cx={px} cy={py} r="1.5" fill="#22d3ee" />
                                                </g>
                                        );
                                })}
                        </g>

                        {/* ═══ Label ═══ */}
                        <text x="200" y="305" fill="rgba(122,196,232,0.7)" fontSize="9" fontFamily="'JetBrains Mono', monospace" textAnchor="middle" className={reducedMotion ? "" : "cad-fade-3"} letterSpacing="2">
                                REVIT · 3D BIM MODEL
                        </text>
                </svg>
        );
}

/* ═══════════════════════════════════════════════════════════════════════════
   ScanBeam — diagonal LiDAR-style scanning beam
   ═══════════════════════════════════════════════════════════════════════════ */
function ScanBeam() {
        return (
                <div
                        className="absolute inset-0 scan-beam-diagonal"
                        style={{
                                background:
                                        "linear-gradient(105deg, transparent 48%, rgba(34,211,238,0.08) 49.5%, rgba(34,211,238,0.18) 50%, rgba(34,211,238,0.08) 50.5%, transparent 52%)",
                        }}
                />
        );
}

/* ═══════════════════════════════════════════════════════════════════════════
   DepthParticles — floating particles with depth (size = proximity)
   ═══════════════════════════════════════════════════════════════════════════ */
function DepthParticles() {
        const particles = Array.from({ length: 30 }, (_, i) => ({
                x: (i * 137) % 1920,
                y: (i * 89) % 1080,
                size: 0.5 + ((i * 7) % 10) / 10 * 2.5,
                delay: (i * 0.6) % 12,
                duration: 10 + (i % 6) * 2,
                color: i % 3 === 0 ? "#22d3ee" : i % 3 === 1 ? "#a855f7" : "#3b82f6",
        }));

        return (
                <svg
                        className="absolute inset-0 w-full h-full"
                        xmlns="http://www.w3.org/2000/svg"
                        preserveAspectRatio="xMidYMid slice"
                        viewBox="0 0 1920 1080"
                >
                        {particles.map((p, i) => (
                                <circle
                                        key={`dp-${i}`}
                                        cx={p.x}
                                        cy={p.y}
                                        r={p.size}
                                        fill={p.color}
                                        opacity="0.4"
                                        className="depth-particle"
                                        style={{
                                                animationDelay: `${p.delay}s`,
                                                animationDuration: `${p.duration}s`,
                                        }}
                                />
                        ))}
                </svg>
        );
}

/* ═══════════════════════════════════════════════════════════════════════════
   ProfessionalHUD — corner status displays
   ═══════════════════════════════════════════════════════════════════════════ */
function ProfessionalHUD() {
        return (
                <>
                        {/* Top-left: drawing info */}
                        <div
                                className="absolute top-4 left-4 hud-panel"
                                style={{
                                        fontFamily: "'JetBrains Mono', monospace",
                                        fontSize: "10px",
                                        color: "rgba(120,140,180,0.6)",
                                        letterSpacing: "1px",
                                        userSelect: "none",
                                }}
                        >
                                <div style={{ color: "rgba(34,211,238,0.7)" }}>◆ AUTOCAD ENGINE</div>
                                <div>DWG: BAZ-001 · LVL 1</div>
                                <div>SCALE: 1:100 · METRIC</div>
                                <div style={{ marginTop: "4px", color: "rgba(168,85,247,0.6)" }}>◆ AI NEURAL ENGINE</div>
                                <div>MODEL: BAZ-NET v2.1</div>
                                <div>SYNAPSES: 24/24 ACTIVE</div>
                        </div>

                        {/* Top-right: status */}
                        <div
                                className="absolute top-4 right-4 hud-panel"
                                style={{
                                        fontFamily: "'JetBrains Mono', monospace",
                                        fontSize: "10px",
                                        color: "rgba(120,140,180,0.6)",
                                        letterSpacing: "1px",
                                        textAlign: "right",
                                        userSelect: "none",
                                }}
                        >
                                <div>STATUS: <span style={{ color: "#22c55e" }}>● READY</span></div>
                                <div>NFPA 72-2022 COMPLIANT</div>
                                <div>UL 864 CERTIFIED</div>
                                <div style={{ marginTop: "4px" }}>CONVERSION: <span style={{ color: "#22d3ee" }}>98.7%</span></div>
                                <div>LATENCY: 12ms</div>
                        </div>

                        {/* Bottom-left: mode */}
                        <div
                                className="absolute bottom-4 left-4 hud-panel"
                                style={{
                                        fontFamily: "'JetBrains Mono', monospace",
                                        fontSize: "10px",
                                        color: "rgba(120,140,180,0.6)",
                                        letterSpacing: "1px",
                                        userSelect: "none",
                                }}
                        >
                                <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                                        <span
                                                style={{
                                                        display: "inline-block",
                                                        width: "6px",
                                                        height: "6px",
                                                        backgroundColor: "#a855f7",
                                                        borderRadius: "50%",
                                                        animation: "cad-blink 2s ease-in-out infinite",
                                                }}
                                        />
                                        <span style={{ color: "rgba(168,85,247,0.7)" }}>AI ANALYSIS IN PROGRESS</span>
                                </div>
                                <div>LAYER: FIRE-ALARM · NFPA-72</div>
                                <div>MODE: DIGITAL TWIN SYNC</div>
                                <div style={{ marginTop: "4px" }}>ORTHO: ON | SNAP: ON | GRID: ON</div>
                        </div>

                        {/* Bottom-right: command bar */}
                        <div
                                className="absolute bottom-4 right-4 hud-panel"
                                style={{
                                        fontFamily: "'JetBrains Mono', monospace",
                                        fontSize: "10px",
                                        color: "rgba(120,140,180,0.6)",
                                        letterSpacing: "1px",
                                        userSelect: "none",
                                }}
                        >
                                <div>COMMAND: <span className="cad-cursor-blink">_</span></div>
                                <div style={{ marginTop: "2px" }}>RECOGNIZE · PLACE · VERIFY</div>
                                <div style={{ marginTop: "4px", color: "rgba(34,211,238,0.5)" }}>DETECTORS: 7 · HEAT: 1 · HORNS: 5</div>
                                <div>FACP: <span style={{ color: "#22c55e" }}>ONLINE</span></div>
                        </div>
                </>
        );
}

/* ═══════════════════════════════════════════════════════════════════════════
   AutoCADCrosshair — unchanged from V237/V238
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
                        <svg
                                className="absolute"
                                style={{ left: "-50vw", top: "-50vh", width: "100vw", height: "100vh", overflow: "visible" }}
                        >
                                <line x1="0" y1="50vh" x2="100vw" y2="50vh" stroke="rgba(180,180,180,0.3)" strokeWidth="1" />
                                <line x1="50vw" y1="0" x2="50vw" y2="100vh" stroke="rgba(180,180,180,0.3)" strokeWidth="1" />
                        </svg>

                        <svg width="24" height="24" viewBox="0 0 24 24" className="absolute" style={{ left: "-12px", top: "-12px" }}>
                                <circle cx="12" cy="12" r="1.5" fill="#b0b0b0" />
                                <circle cx="12" cy="12" r="6" fill="none" stroke="#b0b0b0" strokeWidth="1" opacity="0.6" />
                        </svg>

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
