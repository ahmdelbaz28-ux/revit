
import {
	Activity,
	ActivitySquare,
	AlertTriangle,
	Box,
	Crosshair,
	Eye,
	GitCommit,
	Grid,
	Layers,
	Maximize,
	MousePointer2,
	Power,
	Search,
	Settings,
	Triangle,
	Zap,
} from "lucide-react";
import React from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

export function SLDEditor() {
	return (
		<div className="flex flex-col h-screen w-screen overflow-hidden bg-background text-foreground dark font-sans">
			{/* Top Ribbon */}
			<div className="flex flex-col border-b bg-card shrink-0">
				<div className="h-8 flex items-center px-4 border-b border-border/50 text-[11px] font-medium text-muted-foreground gap-4 bg-[#0f1115]">
					<span className="text-foreground hover:bg-muted px-2 py-0.5 rounded cursor-pointer">
						File
					</span>
					<span className="hover:bg-muted px-2 py-0.5 rounded cursor-pointer">
						Edit
					</span>
					<span className="hover:bg-muted px-2 py-0.5 rounded cursor-pointer">
						View
					</span>
					<span className="hover:bg-muted px-2 py-0.5 rounded cursor-pointer">
						Insert
					</span>
					<span className="hover:bg-muted px-2 py-0.5 rounded cursor-pointer">
						Analyze
					</span>
				</div>
				<div className="h-16 flex items-center px-2 space-x-4">
					<RibbonGroup title="Draw">
						<RibbonBtn icon={<MousePointer2 />} label="Select" active />
						<RibbonBtn icon={<GitCommit />} label="Wire" />
						<RibbonBtn icon={<Box />} label="Bus Bar" />
					</RibbonGroup>
					<Separator orientation="vertical" className="h-10" />

					<RibbonGroup title="Power Source">
						<RibbonBtn icon={<Power />} label="Utility" />
						<RibbonBtn icon={<Zap />} label="Transformer" />
						<RibbonBtn icon={<Activity />} label="Generator" />
					</RibbonGroup>
					<Separator orientation="vertical" className="h-10" />

					<RibbonGroup title="Protection">
						<RibbonBtn
							icon={<Box className="text-danger" />}
							label="Circuit Breaker"
						/>
						<RibbonBtn
							icon={<Box className="text-primary" />}
							label="Fuse"
						/>
						<RibbonBtn icon={<Crosshair />} label="Relay" />
					</RibbonGroup>
					<Separator orientation="vertical" className="h-10" />

					<RibbonGroup title="Load">
						<RibbonBtn icon={<ActivitySquare />} label="Motor" />
						<RibbonBtn icon={<Layers />} label="Panel" />
					</RibbonGroup>
					<Separator orientation="vertical" className="h-10" />

					<RibbonGroup title="View">
						<RibbonBtn icon={<Maximize />} label="Zoom Fit" />
						<RibbonBtn icon={<Grid />} label="Grid" />
						<RibbonBtn icon={<Eye />} label="Layers" />
					</RibbonGroup>
				</div>
			</div>

			<div className="flex flex-1 overflow-hidden">
				{/* Left Panel - Navigator */}
				<div className="w-[240px] flex flex-col border-r bg-card/30 shrink-0">
					<div className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground border-b flex justify-between items-center bg-card/40">
						<span>SLD Navigator</span>
						<Search className="h-3 w-3" />
					</div>
					<ScrollArea className="flex-1">
						<div className="p-2 space-y-1">
							<TreeFolder
								title="Utility Source (11kV)"
								icon={<Power className="h-4 w-4 text-info" />}
								defaultOpen
							>
								<TreeFolder
									title="Main Transformer T1 (11kV/480V)"
									icon={<Zap className="h-4 w-4 text-info" />}
									defaultOpen
								>
									<TreeFolder
										title="Main Switchboard MSB-1"
										icon={<Box className="h-4 w-4 text-muted-foreground" />}
										defaultOpen
									>
										<TreeFolder
											title="Feeder 1 → MDB-A"
											icon={
												<GitCommit className="h-4 w-4 text-muted-foreground" />
											}
											defaultOpen
										>
											<TreeItem title="Panel LP-1 (400A)" />
											<TreeItem title="Panel LP-2 (400A)" />
											<TreeItem title="MCC-1 (800A)" />
										</TreeFolder>
										<TreeFolder
											title="Feeder 2 → MDB-B"
											icon={
												<GitCommit className="h-4 w-4 text-muted-foreground" />
											}
											defaultOpen
										>
											<TreeItem title="Panel LP-3A (400A)" error />
											<TreeItem title="Panel LP-4 (200A)" />
										</TreeFolder>
										<TreeFolder
											title="Emergency Feeder"
											icon={
												<GitCommit className="h-4 w-4 text-primary" />
											}
										>
											<TreeItem title="ATS-1" />
											<TreeItem title="Generator G1" />
										</TreeFolder>
									</TreeFolder>
								</TreeFolder>
							</TreeFolder>
						</div>
					</ScrollArea>
				</div>

				{/* Center - Canvas */}
				<div
					className="flex-1 bg-[#0a0a0f] relative overflow-hidden flex justify-center items-center"
					style={{
						backgroundImage:
							"radial-gradient(rgba(255,255,255,0.05) 1px, transparent 1px)",
						backgroundSize: "20px 20px",
					}}
				>
					{/* SLD Drawing Area (SVG) */}
					<div className="relative w-[800px] h-[800px]">
						<svg width="100%" height="100%" xmlns="http://www.w3.org/2000/svg">
							{/* Utility Supply */}
							<g transform="translate(400, 50)">
								<line
									x1="-15"
									y1="0"
									x2="-15"
									y2="40"
									stroke="#60a5fa"
									strokeWidth="2"
								/>
								<line
									x1="0"
									y1="0"
									x2="0"
									y2="40"
									stroke="#60a5fa"
									strokeWidth="2"
								/>
								<line
									x1="15"
									y1="0"
									x2="15"
									y2="40"
									stroke="#60a5fa"
									strokeWidth="2"
								/>
								<line
									x1="0"
									y1="40"
									x2="0"
									y2="80"
									stroke="#60a5fa"
									strokeWidth="2"
								/>
								<text
									x="30"
									y="20"
									fill="#94a3b8"
									fontSize="11"
									fontFamily="monospace"
								>
									11kV Utility Supply, 3Φ, 60Hz
								</text>
							</g>

							{/* Main Breaker 52-M */}
							<g transform="translate(400, 130)">
								<rect
									x="-10"
									y="0"
									width="20"
									height="20"
									fill="transparent"
									stroke="#94a3b8"
									strokeWidth="2"
								/>
								<line
									x1="-10"
									y1="0"
									x2="10"
									y2="20"
									stroke="#94a3b8"
									strokeWidth="2"
								/>
								<line
									x1="0"
									y1="20"
									x2="0"
									y2="60"
									stroke="#94a3b8"
									strokeWidth="2"
								/>
								<text
									x="25"
									y="15"
									fill="#e2e8f0"
									fontSize="12"
									fontWeight="bold"
								>
									52-M Main CB
								</text>
								<text
									x="25"
									y="30"
									fill="#94a3b8"
									fontSize="10"
									fontFamily="monospace"
								>
									1200A, 65kA
								</text>
								{/* Relay symbol */}
								<circle
									cx="-25"
									cy="10"
									r="8"
									fill="transparent"
									stroke="#fbbf24"
									strokeWidth="1.5"
								/>
								<text
									x="-29"
									y="14"
									fill="#fbbf24"
									fontSize="10"
									fontFamily="monospace"
								>
									R
								</text>
								<line
									x1="-17"
									y1="10"
									x2="-10"
									y2="10"
									stroke="#fbbf24"
									strokeWidth="1"
									strokeDasharray="2,2"
								/>
							</g>

							{/* Transformer T-1 */}
							<g transform="translate(400, 190)">
								<circle
									cx="0"
									cy="15"
									r="15"
									fill="transparent"
									stroke="#60a5fa"
									strokeWidth="2"
								/>
								<circle
									cx="0"
									cy="35"
									r="15"
									fill="transparent"
									stroke="#60a5fa"
									strokeWidth="2"
								/>
								<line
									x1="0"
									y1="50"
									x2="0"
									y2="90"
									stroke="#94a3b8"
									strokeWidth="2"
								/>
								<text
									x="30"
									y="25"
									fill="#e2e8f0"
									fontSize="12"
									fontWeight="bold"
								>
									T-1
								</text>
								<text
									x="30"
									y="40"
									fill="#94a3b8"
									fontSize="10"
									fontFamily="monospace"
								>
									11kV/480V, 2500kVA, Dyn11, Z=5.75%
								</text>
							</g>

							{/* Main Bus */}
							<g transform="translate(200, 280)">
								<line
									x1="0"
									y1="0"
									x2="450"
									y2="0"
									stroke="#f8fafc"
									strokeWidth="6"
									strokeLinecap="round"
								/>
								<text
									x="465"
									y="5"
									fill="#f8fafc"
									fontSize="12"
									fontWeight="bold"
								>
									Main Bus MSB-1
								</text>
								<text
									x="465"
									y="20"
									fill="#94a3b8"
									fontSize="10"
									fontFamily="monospace"
								>
									480V, 3Φ, 4W, 3000A
								</text>
							</g>

							{/* Feeder 1 */}
							<g transform="translate(250, 280)">
								<line
									x1="0"
									y1="0"
									x2="0"
									y2="40"
									stroke="#94a3b8"
									strokeWidth="2"
								/>
								{/* CT Symbol */}
								<circle
									cx="0"
									cy="20"
									r="5"
									fill="transparent"
									stroke="#94a3b8"
									strokeWidth="1.5"
								/>
								<line
									x1="-5"
									y1="15"
									x2="5"
									y2="25"
									stroke="#94a3b8"
									strokeWidth="1"
								/>

								{/* Breaker */}
								<rect
									x="-8"
									y="40"
									width="16"
									height="16"
									fill="transparent"
									stroke="#94a3b8"
									strokeWidth="2"
								/>
								<line
									x1="-8"
									y1="40"
									x2="8"
									y2="56"
									stroke="#94a3b8"
									strokeWidth="2"
								/>
								<text
									x="-45"
									y="52"
									fill="#e2e8f0"
									fontSize="11"
									fontFamily="monospace"
								>
									52-F1
								</text>
								<text
									x="-45"
									y="65"
									fill="#94a3b8"
									fontSize="9"
									fontFamily="monospace"
								>
									1600A
								</text>

								{/* Down line to MDB-A */}
								<line
									x1="0"
									y1="56"
									x2="0"
									y2="120"
									stroke="#94a3b8"
									strokeWidth="2"
								/>
								<rect
									x="-30"
									y="120"
									width="60"
									height="40"
									fill="#1e293b"
									stroke="#64748b"
									strokeWidth="2"
									rx="4"
								/>
								<text
									x="0"
									y="145"
									fill="#e2e8f0"
									fontSize="12"
									fontWeight="bold"
									textAnchor="middle"
								>
									MDB-A
								</text>
							</g>

							{/* Feeder 2 - HIGHLIGHTED */}
							<g transform="translate(400, 280)">
								<line
									x1="0"
									y1="0"
									x2="0"
									y2="40"
									stroke="#94a3b8"
									strokeWidth="2"
								/>
								<circle
									cx="0"
									cy="20"
									r="5"
									fill="transparent"
									stroke="#94a3b8"
									strokeWidth="1.5"
								/>
								<line
									x1="-5"
									y1="15"
									x2="5"
									y2="25"
									stroke="#94a3b8"
									strokeWidth="1"
								/>

								{/* Selected Breaker */}
								<rect
									x="-14"
									y="34"
									width="28"
									height="28"
									fill="rgba(59, 130, 246, 0.1)"
									stroke="#3b82f6"
									strokeWidth="2"
								/>
								<rect
									x="-8"
									y="40"
									width="16"
									height="16"
									fill="transparent"
									stroke="#94a3b8"
									strokeWidth="2"
								/>
								<line
									x1="-8"
									y1="40"
									x2="8"
									y2="56"
									stroke="#94a3b8"
									strokeWidth="2"
								/>
								{/* Handles */}
								<rect x="-16" y="32" width="4" height="4" fill="#3b82f6" />
								<rect x="12" y="32" width="4" height="4" fill="#3b82f6" />
								<rect x="-16" y="60" width="4" height="4" fill="#3b82f6" />
								<rect x="12" y="60" width="4" height="4" fill="#3b82f6" />

								<text
									x="25"
									y="52"
									fill="#3b82f6"
									fontSize="11"
									fontFamily="monospace"
									fontWeight="bold"
								>
									52-F2
								</text>
								<text
									x="25"
									y="65"
									fill="#94a3b8"
									fontSize="9"
									fontFamily="monospace"
								>
									1600A
								</text>

								{/* Dimension Arrow */}
								<line
									x1="15"
									y1="80"
									x2="15"
									y2="150"
									stroke="#10b981"
									strokeWidth="1"
									strokeDasharray="4,4"
								/>
								<polygon points="12,145 15,150 18,145" fill="#10b981" />
								<polygon points="12,85 15,80 18,85" fill="#10b981" />
								<rect x="10" y="105" width="80" height="16" fill="#0a0a0f" />
								<text
									x="15"
									y="117"
									fill="#10b981"
									fontSize="10"
									fontFamily="monospace"
								>
									Length: 4.2m
								</text>

								{/* Down line to MDB-B with Error */}
								<line
									x1="0"
									y1="62"
									x2="0"
									y2="150"
									stroke="#94a3b8"
									strokeWidth="2"
								/>
								<rect
									x="-30"
									y="150"
									width="60"
									height="40"
									fill="#1e293b"
									stroke="#64748b"
									strokeWidth="2"
									rx="4"
								/>
								<text
									x="0"
									y="175"
									fill="#e2e8f0"
									fontSize="12"
									fontWeight="bold"
									textAnchor="middle"
								>
									MDB-B
								</text>
								<circle cx="30" cy="150" r="8" fill="#64748b" />
								<text
									x="30"
									y="153"
									fill="white"
									fontSize="10"
									fontWeight="bold"
									textAnchor="middle"
								>
									!
								</text>
							</g>

							{/* Emergency Feeder */}
							<g transform="translate(600, 280)">
								<line
									x1="0"
									y1="0"
									x2="0"
									y2="40"
									stroke="#94a3b8"
									strokeWidth="2"
								/>
								<rect
									x="-8"
									y="40"
									width="16"
									height="16"
									fill="transparent"
									stroke="#94a3b8"
									strokeWidth="2"
								/>
								<line
									x1="-8"
									y1="40"
									x2="8"
									y2="56"
									stroke="#94a3b8"
									strokeWidth="2"
								/>
								<text
									x="15"
									y="52"
									fill="#e2e8f0"
									fontSize="11"
									fontFamily="monospace"
								>
									52-E (800A)
								</text>

								<line
									x1="0"
									y1="56"
									x2="0"
									y2="100"
									stroke="#94a3b8"
									strokeWidth="2"
								/>

								{/* ATS Box */}
								<rect
									x="-20"
									y="100"
									width="40"
									height="30"
									fill="transparent"
									stroke="#fbbf24"
									strokeWidth="2"
									rx="2"
								/>
								<text
									x="0"
									y="118"
									fill="#fbbf24"
									fontSize="11"
									fontWeight="bold"
									textAnchor="middle"
								>
									ATS-1
								</text>

								{/* Gen feed into ATS */}
								<line
									x1="20"
									y1="115"
									x2="60"
									y2="115"
									stroke="#94a3b8"
									strokeWidth="2"
								/>
								<circle
									cx="75"
									cy="115"
									r="15"
									fill="transparent"
									stroke="#f8fafc"
									strokeWidth="2"
								/>
								<text
									x="75"
									y="119"
									fill="#f8fafc"
									fontSize="12"
									fontWeight="bold"
									textAnchor="middle"
								>
									G
								</text>
								<text
									x="65"
									y="145"
									fill="#e2e8f0"
									fontSize="10"
									fontFamily="monospace"
								>
									G1, 500kW
								</text>
							</g>
						</svg>
					</div>
				</div>

				{/* Right Panel - Properties */}
				<div className="w-[300px] flex flex-col border-l bg-card/30 shrink-0 shadow-xl z-10">
					<div className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-foreground border-b bg-card/40 flex justify-between items-center">
						<span>Element Properties</span>
						<Settings className="h-4 w-4 text-muted-foreground" />
					</div>

					<ScrollArea className="flex-1">
						<div className="p-4 space-y-6">
							<div>
								<div className="flex items-center gap-3 mb-4">
									<div className="w-10 h-10 bg-blue-500/10 border border-blue-500/30 rounded flex items-center justify-center">
										<Box className="h-5 w-5 text-info" />
									</div>
									<div>
										<h3 className="font-bold text-base leading-tight">
											Circuit Breaker
										</h3>
										<div className="text-xs font-mono text-muted-foreground">
											ID: 52-F2
										</div>
									</div>
								</div>

								<div className="flex gap-2 mb-4">
									<Badge className="bg-emerald-500/10 text-success border-success/30 hover:bg-emerald-500/20">
										CLOSED
									</Badge>
									<Badge variant="outline" className="text-xs">
										Main Bus → MDB-B
									</Badge>
								</div>
							</div>

							<div className="space-y-3">
								<div className="text-xs font-bold text-muted-foreground uppercase border-b pb-1 mb-2">
									Specifications
								</div>
								<PropRow label="Type" value="Air Circuit Breaker" />
								<PropRow label="Rating" value="1600A" />
								<PropRow label="Interrupting" value="65kA @ 480V" />
								<PropRow label="Relay Type" value="Overcurrent + EF" />
							</div>

							<div className="space-y-3">
								<div className="text-xs font-bold text-muted-foreground uppercase border-b pb-1 mb-2">
									Protection Settings
								</div>
								<PropRow label="Long-time (L)" value="1.0x (1600A)" />
								<PropRow label="Short-time (S)" value="8x / 0.3s" />
								<PropRow label="Instantaneous (I)" value="15x (24kA)" />
								<PropRow label="Ground (G)" value="0.2x / 0.1s" />
								<Button
									variant="outline"
									size="sm"
									className="w-full h-7 text-xs mt-2 bg-background"
								>
									View TCC Curve
								</Button>
							</div>

							<div className="p-3 border border-primary/30 bg-primary/10 rounded-md">
								<div className="flex items-center gap-2 text-primary font-semibold text-xs mb-1">
									<AlertTriangle className="h-4 w-4" /> Compliance Warning
								</div>
								<p className="text-[11px] text-muted-foreground">
									Downstream feeder to Panel LP-3A exceeds 3% voltage drop limit
									(calculated 3.4%).
								</p>
								<Button
									size="sm"
									variant="outline"
									className="h-6 text-[10px] mt-2 border-primary/30 text-primary bg-background hover:bg-primary/10"
								>
									View Issue
								</Button>
							</div>

							<div className="flex flex-col gap-2 pt-2">
								<Button className="w-full text-xs h-8 bg-blue-600 hover:bg-blue-500">
									Edit Properties
								</Button>
								<div className="flex gap-2">
									<Button variant="outline" className="flex-1 text-xs h-8">
										View Datasheet
									</Button>
									<Button variant="outline" className="flex-1 text-xs h-8">
										Coordination
									</Button>
								</div>
							</div>
						</div>
					</ScrollArea>

					{/* Mini-map / controls */}
					<div className="h-40 border-t bg-card/50 p-3 flex flex-col">
						<div className="text-[10px] font-bold text-muted-foreground uppercase mb-2">
							Grid & Snap
						</div>
						<div className="grid grid-cols-2 gap-2 text-xs">
							<div className="bg-background border px-2 py-1.5 rounded flex justify-between items-center">
								<span className="text-muted-foreground">Grid</span>
								<span className="font-mono">10mm</span>
							</div>
							<div className="bg-background border px-2 py-1.5 rounded flex justify-between items-center">
								<span className="text-muted-foreground">Snap</span>
								<span className="text-success font-semibold">ON</span>
							</div>
						</div>
						<div className="mt-auto h-16 bg-[#0a0a0f] border border-border rounded relative overflow-hidden flex items-center justify-center">
							{/* Fake minimap */}
							<div className="w-12 h-10 border-2 border-blue-500/50 absolute"></div>
							<div className="w-20 h-0.5 bg-slate-600"></div>
						</div>
					</div>
				</div>
			</div>

			{/* Bottom Console */}
			<div className="h-8 border-t bg-card flex items-center justify-between px-4 text-[10px] font-mono text-muted-foreground shrink-0">
				<div className="flex items-center gap-4">
					<span className="text-primary flex items-center gap-1">
						<AlertTriangle className="h-3 w-3" /> 2 issues in diagram
					</span>
					<Separator orientation="vertical" className="h-4" />
					<span>NEC Check: 1 warning</span>
					<Separator orientation="vertical" className="h-4" />
					<span className="text-info cursor-pointer hover:underline">
						Short circuit: Run needed
					</span>
				</div>
				<div className="flex items-center gap-4">
					<span>Scale: 1:1</span>
					<Separator orientation="vertical" className="h-4" />
					<span>Auto-number: ON</span>
					<Separator orientation="vertical" className="h-4" />
					<span>Standards: IEEE/ANSI</span>
				</div>
			</div>
		</div>
	);
}

function RibbonGroup({
	title,
	children,
}: {
	title: string;
	children: React.ReactNode;
}) {
	return (
		<div className="flex flex-col items-center justify-center h-full">
			<div className="flex items-center gap-1 flex-1">{children}</div>
			<div className="text-[9px] text-muted-foreground uppercase tracking-wider mt-1">
				{title}
			</div>
		</div>
	);
}

function RibbonBtn({
	icon,
	label,
	active = false,
}: {
	icon: React.ReactNode;
	label: string;
	active?: boolean;
}) {
	return (
		<div
			className={`flex flex-col items-center justify-center w-14 h-10 rounded cursor-pointer transition-colors group ${active ? "bg-primary/20 text-primary border border-primary/30" : "hover:bg-muted"}`}
		>
			<div
				className={`mb-1 [&>svg]:w-4 [&>svg]:h-4 ${active ? "text-primary" : "text-muted-foreground group-hover:text-foreground"}`}
			>
				{icon}
			</div>
			<span
				className={`text-[8px] text-center leading-tight whitespace-nowrap overflow-hidden text-ellipsis w-full ${active ? "text-primary" : "text-muted-foreground group-hover:text-foreground"}`}
			>
				{label}
			</span>
		</div>
	);
}

function TreeFolder({
	title,
	icon,
	children,
	defaultOpen = false,
}: {
	title: string;
	icon?: React.ReactNode;
	children: React.ReactNode;
	defaultOpen?: boolean;
}) {
	const [open, setOpen] = React.useState(defaultOpen);
	return (
		<div className="mb-0.5">
			<div
				role="button"
				tabIndex={0}
				className="flex items-center gap-1.5 py-1 px-1 hover:bg-muted cursor-pointer rounded transition-colors"
				onClick={() => setOpen(!open)}
				onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpen(!open) } }}
			>
				<Triangle
					className={`h-2.5 w-2.5 text-muted-foreground transition-transform ${open ? "rotate-180" : "rotate-90"}`}
				/>
				{icon}
				<span className="text-[11px] font-medium text-foreground/90 truncate">
					{title}
				</span>
			</div>
			{open && (
				<div className="ml-3 pl-2 border-l border-border flex flex-col gap-0.5 mt-0.5">
					{children}
				</div>
			)}
		</div>
	);
}

function TreeItem({
	title,
	active = false,
	error = false,
}: {
	title: string;
	active?: boolean;
	error?: boolean;
}) {
	return (
		<div
			className={`flex items-center gap-1.5 py-1 px-1 rounded cursor-pointer transition-colors ${active ? "bg-blue-500/20 text-info" : "hover:bg-muted"} ${error ? "text-danger bg-slate-500/10" : ""}`}
		>
			<div
				className={`w-1.5 h-1.5 rounded-full ${error ? "bg-slate-500" : "bg-slate-600"}`}
			></div>
			<span
				className={`text-[10px] truncate ${error ? "font-semibold" : "text-muted-foreground"}`}
			>
				{title}
			</span>
		</div>
	);
}

function PropRow({ label, value }: { label: string; value: string }) {
	return (
		<div className="flex justify-between items-center text-xs">
			<span className="text-muted-foreground">{label}</span>
			<span className="font-mono text-foreground text-right">{value}</span>
		</div>
	);
}
