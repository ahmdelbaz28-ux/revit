import {
	Camera,
	ChevronDown,
	ChevronRight,
	Lock,
	Search,
	Settings,
	Shield,
	UserCheck,
	Video,
} from "lucide-react";
import type React from "react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

export function SecuritySystems() {
	const [_activeCam, _setActiveCam] = useState("CAM-EXT-01");  // NOSONAR - typescript:S6754

	return (
		<div className="flex flex-col h-screen w-screen overflow-hidden bg-slate-900 text-slate-100 font-sans">
			{/* Top Toolbar */}
			<div className="h-14 flex items-center justify-between px-4 border-b border-slate-700 bg-slate-800 shrink-0">
				<div className="flex items-center gap-4">
					<div className="flex items-center gap-2 text-indigo-400 font-bold tracking-wide">
						<Shield className="h-5 w-5" />
						<span>Security Systems — CCTV & Access</span>
					</div>
					<Separator orientation="vertical" className="h-6 bg-slate-600" />
					<div className="flex space-x-1">
						<TabBtn label="CCTV Design" active />
						<TabBtn label="Access Control" />
						<TabBtn label="Intrusion" />
						<TabBtn label="Intercom" />
						<TabBtn label="Reports" />
					</div>
				</div>
				<div className="flex items-center gap-3">
					<Button
						size="sm"
						className="h-8 text-xs bg-indigo-600 hover:bg-indigo-700 text-white border-none"
					>
						<Video className="w-3 h-3 mr-2" /> Live Monitor
					</Button>
					<Button
						size="sm"
						variant="outline"
						className="h-8 text-xs border-slate-600 text-slate-300"
					>
						Coverage Analysis
					</Button>
					<Button
						size="icon"
						variant="ghost"
						className="h-8 w-8 text-slate-400"
					>
						<Settings className="w-4 h-4" />
					</Button>
				</div>
			</div>

			<div className="flex flex-1 overflow-hidden">
				{/* Left Tree */}
				<div className="w-[240px] flex flex-col border-r border-slate-700 bg-slate-800 shrink-0">
					<div className="p-3 text-xs font-semibold uppercase tracking-wider text-slate-400 border-b border-slate-700 bg-slate-900/50 flex justify-between">
						<span>System Tree</span>
						<Search className="h-3 w-3" />
					</div>
					<ScrollArea className="flex-1 p-2">
						<NavNode title="Tower-B Security" expanded>
							<NavNode title="CCTV System" expanded>
								<NavNode title="NVR-1 (32-ch, L1)" expanded>
									<NavNode title="Zone A: Exterior (8)" active />
									<NavNode title="Zone B: Lobby (12)" />
									<NavNode title="Zone C: Floors (6)" />
									<NavNode title="Zone D: Parking (6)" />
								</NavNode>
								<NavNode title="NVR-2 (Future)" />
							</NavNode>
							<NavNode title="Access Control">
								<NavNode title="ACS Controller-1" />
								<NavNode title="ACS Controller-2" />
							</NavNode>
							<NavNode title="Intrusion Detection">
								<NavNode title="IDS Panel-1" />
							</NavNode>
							<NavNode title="Intercom" />
						</NavNode>
					</ScrollArea>
				</div>

				{/* Central Canvas */}
				<div
					className="flex-1 bg-[#050914] relative overflow-hidden flex flex-col"
					style={{
						backgroundImage:
							"linear-gradient(#1e293b 1px, transparent 1px), linear-gradient(90deg, #1e293b 1px, transparent 1px)",
						backgroundSize: "40px 40px",
					}}
				>
					<div className="absolute top-4 left-4 z-10 bg-slate-900 border border-slate-700 px-3 py-1.5 rounded flex items-center gap-2 backdrop-blur">
						<span className="w-2 h-2 rounded-full bg-indigo-500 animate-pulse"></span>
						<span className="text-xs font-mono text-indigo-400">
							Coverage: 93.4%
						</span>
						<Separator
							orientation="vertical"
							className="h-3 bg-slate-600 mx-1"
						/>
						<span className="text-[10px] text-slate-400 uppercase">
							Ground Floor / Exterior
						</span>
					</div>

					<div className="absolute inset-0 flex items-center justify-center">
						{/* SVG Floor Plan */}
						<div className="relative w-full max-w-4xl aspect-[16/9] border-2 border-slate-800 bg-slate-900/40 rounded-sm">
							{/* Building Outline */}
							<div className="absolute top-[20%] left-[20%] w-[60%] h-[60%] border border-slate-600 bg-slate-800/30 backdrop-blur-sm"></div>
							{/* Entrances */}
							<div className="absolute bottom-[20%] left-[45%] w-[10%] h-2 bg-slate-500"></div>

							<svg className="absolute inset-0 w-full h-full pointer-events-none">
								{/* FOV Cones - SVG Arcs */}
								{/* PTZ Main Entrance */}
								<circle
									cx="50%"
									cy="80%"
									r="60"
									fill="rgba(99, 102, 241, 0.1)"
									stroke="rgba(99, 102, 241, 0.3)"
									strokeDasharray="4 2"
								/>

								{/* Corner Dome 1 */}
								<path
									d="M 20% 80% L 10% 95% A 120 120 0 0 0 5% 70% Z"
									fill="rgba(99, 102, 241, 0.15)"
									stroke="rgba(99, 102, 241, 0.4)"
									strokeWidth="1"
								/>

								{/* Corner Dome 2 */}
								<path
									d="M 80% 80% L 90% 95% A 120 120 0 0 1 95% 70% Z"
									fill="rgba(99, 102, 241, 0.15)"
									stroke="rgba(99, 102, 241, 0.4)"
									strokeWidth="1"
								/>

								{/* ANPR Parking */}
								<path
									d="M 25% 20% L 20% 5% L 30% 5% Z"
									fill="rgba(99, 102, 241, 0.2)"
									stroke="rgba(99, 102, 241, 0.5)"
								/>

								{/* Blind spot (red area) */}
								<circle
									cx="35%"
									cy="85%"
									r="15"
									fill="rgba(239, 68, 68, 0.15)"
									stroke="rgba(239, 68, 68, 0.3)"
									strokeDasharray="2 2"
								/>
								<text
									x="35%"
									y="85%"
									fill="#ef4444"
									fontSize="8"
									textAnchor="middle"
									dy="3"
								>
									GAP
								</text>
							</svg>

							{/* Camera Symbols */}
							<CamSymbol
								x="50%"
								y="80%"
								label="CAM-EXT-01"
								type="ptz"
								selected
							/>
							<CamSymbol x="20%" y="80%" label="EXT-02" type="dome" dir="sw" />
							<CamSymbol x="80%" y="80%" label="EXT-03" type="dome" dir="se" />
							<CamSymbol
								x="25%"
								y="20%"
								label="EXT-04 (ANPR)"
								type="bullet"
								dir="n"
							/>
						</div>
					</div>
				</div>

				{/* Right Panel */}
				<div className="w-[300px] bg-slate-800 border-l border-slate-700 flex flex-col shrink-0">
					<div className="p-3 border-b border-slate-700 flex justify-between items-center bg-slate-900/50">
						<div className="flex items-center gap-2">
							<Camera className="h-4 w-4 text-indigo-400" />
							<span className="font-bold text-slate-200">CAM-EXT-01</span>
						</div>
						<Badge className="bg-indigo-500/20 text-indigo-400 border border-indigo-500/30 hover:bg-indigo-500/20">
							PTZ ONLINE
						</Badge>
					</div>

					<ScrollArea className="flex-1">
						<div className="p-3 space-y-5">
							{/* Live Feed Placeholder */}
							<div className="rounded overflow-hidden border border-slate-700 bg-black relative aspect-video shadow-inner">
								<div
									className="absolute inset-0"
									style={{
										backgroundImage:
											"linear-gradient(rgba(255,255,255,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.05) 1px, transparent 1px)",
										backgroundSize: "10px 10px",
									}}
								></div>
								<div className="absolute top-2 right-2 flex items-center gap-1 bg-black/60 px-1.5 py-0.5 rounded text-[8px] font-mono text-white border border-slate-800 backdrop-blur-md">
									<div className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse"></div>{" "}
									LIVE
								</div>
								<div className="absolute bottom-2 left-2 text-[8px] font-mono text-white/70 bg-black/60 px-1 rounded backdrop-blur-md">
									4K / 25FPS / H.265
								</div>

								{/* PTZ Controls overlay */}
								<div className="absolute bottom-2 right-2 grid grid-cols-3 gap-0.5 opacity-50 hover:opacity-100 transition-opacity">
									<div></div>
									<div className="w-4 h-4 bg-slate-800 border border-slate-600 rounded flex items-center justify-center text-[8px] cursor-pointer text-white">
										▲
									</div>
									<div></div>
									<div className="w-4 h-4 bg-slate-800 border border-slate-600 rounded flex items-center justify-center text-[8px] cursor-pointer text-white">
										◀
									</div>
									<div className="w-4 h-4 bg-slate-800 border border-slate-600 rounded flex items-center justify-center text-[8px] cursor-pointer text-indigo-400 font-bold">
										H
									</div>
									<div className="w-4 h-4 bg-slate-800 border border-slate-600 rounded flex items-center justify-center text-[8px] cursor-pointer text-white">
										▶
									</div>
									<div></div>
									<div className="w-4 h-4 bg-slate-800 border border-slate-600 rounded flex items-center justify-center text-[8px] cursor-pointer text-white">
										▼
									</div>
									<div></div>
								</div>
							</div>

							{/* Specs */}
							<div>
								<h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
									Camera Specs
								</h3>
								<div className="space-y-1 bg-slate-900/50 p-2 rounded border border-slate-700/50">
									<PropRow label="Type" value="IP PTZ Dome" />
									<PropRow label="Resolution" value="4K (8MP)" />
									<PropRow label="Optical Zoom" value="30x" />
									<PropRow label="IR Range" value="100m" />
									<PropRow label="IP / IK Rating" value="IP67 / IK10" />
									<PropRow label="Manufacturer" value="Hikvision DS-2DE" />
									<PropRow label="NVR Assign" value="NVR-1, Ch 1" />
								</div>
							</div>

							{/* Installation */}
							<div>
								<h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
									Installation
								</h3>
								<div className="space-y-1 bg-slate-900/50 p-2 rounded border border-slate-700/50">
									<PropRow label="Mounting" value="Pole mount, 5.5m" />
									<PropRow label="Cable" value="Cat6A + PoE++" />
									<PropRow label="PoE Switch" value="SW-EXT-01, Pt 1" />
								</div>
							</div>

							{/* Related Access Control */}
							<div>
								<h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2 flex items-center gap-1">
									<Lock className="w-3 h-3" /> Linked Access Point
								</h3>
								<div className="bg-slate-900 border border-slate-700 p-2 rounded">
									<div className="flex justify-between items-center mb-2">
										<span className="text-xs text-slate-300 font-medium">
											Main Entrance Door
										</span>
										<Badge className="bg-green-500/20 text-green-400 border border-green-500/30 text-[9px] px-1 py-0 h-4">
											SECURE
										</Badge>
									</div>
									<div className="text-[10px] text-slate-400 mb-2">
										Suprema BioEntry W2 (Bio/Card)
									</div>
									<div className="flex items-center gap-2 p-1.5 bg-slate-800 rounded text-xs border border-slate-700">
										<UserCheck className="w-3 h-3 text-indigo-400" />
										<div className="flex flex-col">
											<span className="text-slate-300">
												Access granted: Ahmed A.
											</span>
											<span className="text-[9px] font-mono text-slate-500">
												14:43:07 today
											</span>
										</div>
									</div>
								</div>
							</div>
						</div>
					</ScrollArea>
				</div>
			</div>

			{/* Bottom Bar */}
			<div className="h-8 bg-slate-900 border-t border-slate-700 flex items-center justify-between px-4 text-[10px] font-mono shrink-0">
				<div className="flex items-center gap-4 text-slate-400">
					<span>CCTV: 32 active | 0 offline</span>
					<Separator orientation="vertical" className="h-4 bg-slate-700" />
					<span className="text-indigo-400">Storage: 14.2TB / 48TB (30%)</span>
					<Separator orientation="vertical" className="h-4 bg-slate-700" />
					<span>
						ACS: 24 readers |{" "}
						<span className="text-orange-400">3 door warnings</span>
					</span>
					<Separator orientation="vertical" className="h-4 bg-slate-700" />
					<span className="text-green-400 flex items-center gap-1">
						<Shield className="w-3 h-3" /> IDS: ARMED
					</span>
				</div>
				<div className="flex items-center gap-3">
					<Button
						variant="ghost"
						size="sm"
						className="h-6 text-[10px] text-indigo-400 hover:text-indigo-300 px-2"
					>
						Export to AutoCAD
					</Button>
					<Button
						variant="ghost"
						size="sm"
						className="h-6 text-[10px] text-indigo-400 hover:text-indigo-300 px-2"
					>
						Incident Log
					</Button>
				</div>
			</div>
		</div>
	);
}

function TabBtn({  // NOSONAR - typescript:S6759
	label,
	active = false,
}: {
	label: string;
	active?: boolean;
}) {
	return (
		<button
			className={`px-3 py-1.5 text-xs font-medium rounded-t-sm transition-colors ${active ? "bg-slate-900 text-indigo-400 border-t-2 border-indigo-500" : "text-slate-400 hover:bg-slate-700/50 hover:text-slate-200"}`}
		>
			{label}
		</button>
	);
}

function NavNode({  // NOSONAR - typescript:S6759
	title,
	expanded = false,
	active = false,
	children,
}: {
	title: string;
	expanded?: boolean;
	active?: boolean;
	children?: React.ReactNode;
}) {
	return (
		<div className="select-none">
			<div
				className={`flex items-center gap-1.5 py-1 px-2 rounded cursor-pointer hover:bg-slate-700/50 ${active ? "bg-indigo-500/20 text-indigo-400 font-medium" : "text-slate-300"}`}
			>
				<div className="w-4 h-4 flex items-center justify-center">
					{children ? (
						expanded ? (  // NOSONAR — S3358: nested ternary acceptable in this localized context
							<ChevronDown className="h-3 w-3 text-slate-500" />
						) : (
							<ChevronRight className="h-3 w-3 text-slate-500" />
						)
					) : (
						<div className="w-1 h-1" />
					)}
				</div>
				<span className="text-xs truncate">{title}</span>
			</div>
			{expanded && children && (
				<div className="ml-3 pl-2 border-l border-slate-700 flex flex-col gap-0.5 mt-0.5">
					{children}
				</div>
			)}
		</div>
	);
}

function PropRow({ label, value }: { label: string; value: string }) {  // NOSONAR - typescript:S6759
	return (
		<div className="flex justify-between py-0.5 text-xs">
			<span className="text-slate-400">{label}</span>
			<span className="text-slate-200 font-mono text-[10px]">{value}</span>
		</div>
	);
}

function CamSymbol({  // NOSONAR - typescript:S6759
	x,
	y,
	label,
	type,
	dir = "n",
	selected = false,
}: {
	x: string;
	y: string;
	label: string;
	type: "ptz" | "dome" | "bullet";
	dir?: string;
	selected?: boolean;
}) {
	return (
		<div
			className="absolute flex flex-col items-center"
			style={{ left: x, top: y, transform: "translate(-50%, -50%)" }}
		>
			<div
				className={`w-5 h-5 rounded-full border-2 bg-slate-800 flex items-center justify-center z-10 ${selected ? "border-indigo-400 shadow-[0_0_10px_rgba(99,102,241,0.5)]" : "border-slate-400"}`}
			>
				<Camera
					className={`w-2.5 h-2.5 ${selected ? "text-indigo-400" : "text-slate-400"}`}
				/>
			</div>
			<div
				className={`mt-0.5 text-[8px] font-mono whitespace-nowrap bg-slate-900 px-1 py-0.5 rounded border ${selected ? "border-indigo-500 text-indigo-300" : "border-slate-700 text-slate-400"}`}
			>
				{label}
			</div>
		</div>
	);
}
