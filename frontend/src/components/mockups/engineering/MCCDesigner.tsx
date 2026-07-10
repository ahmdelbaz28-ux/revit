
import { AlertCircle, Download, FileText, Plus, Settings } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

export function MCCDesigner() {
	return (
		<div className="flex flex-col h-screen w-screen overflow-hidden bg-background text-foreground dark font-sans">
			{/* Top Toolbar */}
			<div className="h-14 flex items-center justify-between px-4 border-b bg-card shrink-0">
				<div className="flex items-center gap-4">
					<div className="font-bold tracking-wider text-sm">
						Motor Control Center Designer — MCC-1
					</div>
					<Separator orientation="vertical" className="h-5" />
					<div className="flex space-x-1 text-xs">
						<button className="px-3 py-1 rounded bg-blue-500/10 text-info font-medium border border-blue-500/20">
							MCC-1
						</button>
						<button className="px-3 py-1 rounded text-muted-foreground hover:bg-muted">
							MCC-2
						</button>
						<button className="px-3 py-1 rounded text-muted-foreground hover:bg-muted">
							MCC-3
						</button>
						<button className="px-3 py-1 rounded text-muted-foreground hover:bg-muted flex items-center">
							<Plus className="h-3 w-3 mr-1" /> Add
						</button>
					</div>
				</div>
				<div className="flex items-center gap-2">
					<Button
						variant="outline"
						size="sm"
						className="h-8 text-xs border-border hover:bg-card"
					>
						<Plus className="h-4 w-4 mr-1" /> Add Section
					</Button>
					<Button
						variant="outline"
						size="sm"
						className="h-8 text-xs border-border hover:bg-card"
					>
						<Plus className="h-4 w-4 mr-1" /> Add Bucket
					</Button>
					<Button
						variant="outline"
						size="sm"
						className="h-8 text-xs border-border hover:bg-card"
					>
						<Settings className="h-4 w-4 mr-1" /> Validate
					</Button>
					<Button
						variant="outline"
						size="sm"
						className="h-8 text-xs border-border hover:bg-card"
					>
						<FileText className="h-4 w-4 mr-1" /> Generate Schedule
					</Button>
					<Button
						size="sm"
						className="h-8 text-xs bg-blue-600 hover:bg-blue-500 text-white"
					>
						<Download className="h-4 w-4 mr-1" /> Export to DWG
					</Button>
				</div>
			</div>

			<div className="flex flex-1 overflow-hidden">
				{/* Left Panel - Palette */}
				<div className="w-[260px] flex flex-col border-r bg-card/30 shrink-0">
					<div className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground border-b flex justify-between items-center bg-card/40">
						<span>Component Palette</span>
					</div>
					<ScrollArea className="flex-1">
						<div className="p-3 space-y-5">
							<div>
								<div className="text-[10px] font-bold text-muted-foreground uppercase mb-2">
									Starters
								</div>
								<div className="grid grid-cols-2 gap-2">
									<PaletteItem label="FVNR Starter" size="2U-6U" />
									<PaletteItem label="FVR Starter" size="3U-8U" />
									<PaletteItem
										label="VFD Drive"
										size="4U-12U"
										bg="bg-blue-500/10 border-blue-500/30"
									/>
									<PaletteItem label="Soft Starter" size="4U-10U" />
								</div>
							</div>

							<div>
								<div className="text-[10px] font-bold text-muted-foreground uppercase mb-2">
									Protection
								</div>
								<div className="grid grid-cols-2 gap-2">
									<PaletteItem label="Feeder CB" size="2U-4U" />
									<PaletteItem label="Fusible Disc." size="2U-6U" />
									<PaletteItem
										label="Main Inc."
										size="6U-12U"
										bg="bg-emerald-500/10 border-success/30"
									/>
									<PaletteItem label="Bus Plug" size="2U" />
								</div>
							</div>

							<div>
								<div className="text-[10px] font-bold text-muted-foreground uppercase mb-2">
									Monitoring & Misc
								</div>
								<div className="grid grid-cols-2 gap-2">
									<PaletteItem label="Power Meter" size="2U-4U" />
									<PaletteItem label="PLC I/O" size="4U" />
									<PaletteItem
										label="Space"
										size="Any"
										border="border-dashed border-border"
									/>
									<PaletteItem
										label="Spare"
										size="Any"
										border="border-dashed border-border"
									/>
								</div>
							</div>
						</div>
					</ScrollArea>
				</div>

				{/* Center - Visual */}
				<div className="flex-1 relative bg-[#111827] overflow-y-auto flex justify-center p-8">
					{/* MCC Panel Container */}
					<div className="flex gap-1 h-[800px] p-2 bg-card border-2 border-border shadow-2xl rounded-sm">
						{/* Section 1 */}
						<div className="w-[200px] h-full flex flex-col gap-1 border-r border-slate-900 pr-1">
							<div className="h-6 bg-card flex justify-center items-center text-[10px] text-muted-foreground font-mono">
								SEC 1
							</div>
							<Bucket
								title="MAIN — 800A — 3Φ 480V"
								units={8}
								color="bg-card border-emerald-500/50"
								text="text-success"
							/>
							<div className="h-[40px] flex items-center justify-center bg-muted/50 border border-border">
								<div className="w-full h-2 bg-primary/20 flex justify-between px-2">
									<div className="h-full w-1/4 bg-primary/50"></div>
								</div>
							</div>
							<Bucket title="PM-1, ION9000" units={4} />
							<div className="flex-1 border-2 border-dashed border-border bg-card/30 flex justify-center items-center">
								<span className="text-muted-foreground/70 text-xs font-mono">SPACE</span>
							</div>
						</div>

						{/* Section 2 */}
						<div className="w-[200px] h-full flex flex-col gap-1 border-r border-slate-900 pr-1 px-1">
							<div className="h-6 bg-card flex justify-center items-center text-[10px] text-muted-foreground font-mono">
								SEC 2
							</div>
							<Bucket
								title="F2-01: Chiller Pump-1"
								sub="75HP • 96A"
								status="green"
								units={4}
							/>
							<Bucket
								title="F2-02: Chiller Pump-2"
								sub="75HP • 96A"
								status="yellow"
								units={4}
							/>
							<Bucket
								title="F2-03: AHU-1 Supply Fan"
								sub="50HP • 65A"
								status="green"
								units={4}
							/>
							<Bucket
								title="F2-04: AHU-2 Supply Fan"
								sub="50HP • 65A"
								status="green"
								units={4}
							/>
							<Bucket
								title="F2-05: Cooling Tower"
								sub="30HP • 40A"
								status="green"
								units={3}
							/>

							{/* Highlighted Fault Bucket */}
							<div className="h-[120px] bg-card border-2 border-blue-500 relative flex flex-col p-2 shadow-[0_0_15px_rgba(59,130,246,0.3)]">
								<div className="absolute top-2 right-2 w-2 h-2 rounded-full bg-slate-500 animate-pulse shadow-[0_0_5px_red]"></div>
								<div className="text-xs font-bold text-white mb-1">
									F2-06: Condenser Water
								</div>
								<div className="text-[10px] text-muted-foreground font-mono">
									20HP • 27A
								</div>
								<div className="mt-auto flex gap-2">
									<div className="w-4 h-4 bg-slate-500/20 border border-slate-500 rounded-sm"></div>
									<div className="w-4 h-4 bg-card border border-border rounded-sm"></div>
								</div>
							</div>

							<div className="h-[90px] border-2 border-dashed border-border bg-card/30 flex justify-center items-center flex-col">
								<span className="text-muted-foreground text-xs font-mono">F2-07</span>
								<span className="text-muted-foreground/70 text-xs font-mono">SPARE</span>
							</div>
							<div className="flex-1 border-2 border-dashed border-border bg-card/30 flex justify-center items-center">
								<span className="text-muted-foreground/70 text-xs font-mono">SPACE</span>
							</div>
						</div>

						{/* Section 3 */}
						<div className="w-[200px] h-full flex flex-col gap-1 pl-1">
							<div className="h-6 bg-card flex justify-center items-center text-[10px] text-muted-foreground font-mono">
								SEC 3
							</div>
							<Bucket
								title="F3-01: Fire Pump"
								sub="100HP • 128A"
								status="green"
								units={6}
							/>
							<Bucket
								title="F3-02: Jockey Pump"
								sub="10HP • 14A"
								status="green"
								units={2}
							/>
							<Bucket
								title="F3-03: Elevator-1"
								sub="40HP • 52A"
								status="green"
								units={3}
							/>
							<Bucket
								title="F3-04: Elevator-2"
								sub="40HP • 52A"
								status="green"
								units={3}
							/>
							<Bucket
								title="F3-05: Booster Pump"
								sub="25HP • 33A"
								status="yellow"
								units={3}
							/>
							<Bucket
								title="F3-06: VFD"
								sub="60HP • 78A"
								status="green"
								units={8}
								color="bg-blue-900/20 border-blue-800"
								text="text-blue-100"
							/>
							<div className="flex-1 border-2 border-dashed border-border bg-card/30 flex justify-center items-center flex-col">
								<span className="text-muted-foreground text-xs font-mono">
									SPARE x2
								</span>
							</div>
						</div>
					</div>
				</div>

				{/* Right Panel - Properties */}
				<div className="w-[300px] flex flex-col border-l bg-card/30 shrink-0">
					<div className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-foreground border-b flex justify-between items-center bg-card/40">
						<span>Bucket Properties</span>
					</div>
					<ScrollArea className="flex-1">
						<div className="p-4 space-y-6">
							{/* Header */}
							<div>
								<div className="flex items-center gap-2 mb-2">
									<Badge
										variant="outline"
										className="bg-blue-500/10 text-info border-blue-500/30 text-xs"
									>
										F2-06
									</Badge>
									<Badge variant="destructive" className="animate-pulse">
										FAULT
									</Badge>
								</div>
								<h3 className="font-bold text-base leading-tight">
									Condenser Water Pump
								</h3>
								<div className="text-xs text-muted-foreground mt-1">
									Section 2, Position 6 • 4U (144mm)
								</div>
							</div>

							{/* Fault Details */}
							<div className="border border-slate-500/50 bg-slate-500/10 rounded-md p-3 space-y-2">
								<div className="flex items-center gap-2 text-danger font-bold text-xs uppercase">
									<AlertCircle className="h-4 w-4" /> Fault Detected
								</div>
								<div className="text-xs text-foreground/90">
									<span className="text-muted-foreground">Code:</span> OL-01 (Overload
									Trip)
								</div>
								<div className="text-xs text-foreground/90">
									<span className="text-muted-foreground">Trip Current:</span> 34.2A
									(125% FLA)
								</div>
								<div className="text-xs text-foreground/90">
									<span className="text-muted-foreground">Time:</span> 14:23:07
								</div>
								<div className="flex gap-2 mt-2 pt-2 border-t border-slate-500/20">
									<Button
										size="sm"
										variant="destructive"
										className="h-7 text-[10px] w-full bg-danger"
									>
										Reset Fault
									</Button>
									<Button
										size="sm"
										variant="outline"
										className="h-7 text-[10px] w-full border-danger/30 text-danger bg-transparent"
									>
										History
									</Button>
								</div>
							</div>

							{/* Details */}
							<div className="space-y-4">
								<div>
									<div className="text-[10px] font-bold text-muted-foreground uppercase border-b border-border/50 pb-1 mb-2">
										Motor Details
									</div>
									<div className="space-y-1">
										<PropRow label="Power" value="20HP / 14.9kW" />
										<PropRow label="Voltage" value="480V, 3Φ" />
										<PropRow label="FLA" value="27.4A" />
										<PropRow label="LRC" value="165A (6x)" />
										<PropRow label="Service Factor" value="1.15" />
									</div>
								</div>

								<div>
									<div className="text-[10px] font-bold text-muted-foreground uppercase border-b border-border/50 pb-1 mb-2">
										Starter Details
									</div>
									<div className="space-y-1">
										<PropRow label="Type" value="FVNR" />
										<PropRow label="Contactor" value="30A, IEC AC3" />
										<PropRow label="Overload Relay" value="24–32A" />
										<PropRow label="Protection" value="100A MCCB, 65kA" />
									</div>
								</div>

								<div>
									<div className="text-[10px] font-bold text-muted-foreground uppercase border-b border-border/50 pb-1 mb-2">
										Wiring
									</div>
									<div className="space-y-1">
										<PropRow label="Control Volts" value="120V AC" />
										<PropRow label="Diagram Ref" value="DWG-E-MCC-2.4" link />
									</div>
								</div>
							</div>
						</div>
					</ScrollArea>
				</div>
			</div>

			{/* Bottom Console */}
			<div className="h-12 border-t bg-card flex items-center justify-between px-4 text-[11px] shrink-0">
				<div className="flex items-center gap-4 text-foreground/90">
					<span className="font-semibold text-white">MCC-1 Summary:</span>
					<span>15 feeders</span>
					<Separator orientation="vertical" className="h-4" />
					<span className="text-success">12 running</span>
					<span className="text-danger">1 fault</span>
					<span className="text-muted-foreground">2 spare</span>
				</div>

				<div className="flex items-center gap-4">
					<div className="flex flex-col items-end">
						<div className="flex gap-2">
							<span className="text-muted-foreground">Connected: 440kW</span>
							<span className="text-info">Demand: 374kW (85%)</span>
						</div>
						<div className="flex items-center gap-2 mt-0.5">
							<span className="text-muted-foreground">Bus: 800A</span>
							<div className="w-32 h-1.5 bg-card rounded-full overflow-hidden">
								<div
									className="bg-emerald-500 h-full"
									style={{ width: "76.5%" }}
								></div>
							</div>
							<span className="text-success font-mono">612A</span>
						</div>
					</div>
				</div>
			</div>
		</div>
	);
}

function PaletteItem({
	label,
	size,
	bg = "bg-card",
	border = "border border-border",
}: {
	label: string;
	size: string;
	bg?: string;
	border?: string;
}) {
	return (
		<div
			className={`p-2 rounded cursor-grab hover:ring-1 ring-blue-500 transition-all ${bg} ${border}`}
		>
			<div className="text-[10px] font-semibold text-foreground">{label}</div>
			<div className="text-[9px] text-muted-foreground font-mono mt-1">{size}</div>
		</div>
	);
}

function Bucket({
	title,
	sub,
	status,
	units,
	color = "bg-card border-border",
	text = "text-white",
}: {
	title: string;
	sub?: string;
	status?: string;
	units: number;
	color?: string;
	text?: string;
}) {
	const height = Math.max(units * 30, 40); // Rough pixel mapping

	let dot = null;
	if (status === "green") dot = "bg-emerald-500 shadow-[0_0_5px_#10b981]";
	if (status === "yellow") dot = "bg-yellow-400 shadow-[0_0_5px_#facc15]";
	if (status === "red") dot = "bg-slate-500 shadow-[0_0_5px_#64748b]";

	return (
		<div
			className={`${color} border relative flex flex-col p-2 hover:border-border cursor-pointer`}
			style={{ height: `${height}px` }}
		>
			{dot && (
				<div
					className={`absolute top-2 right-2 w-2 h-2 rounded-full ${dot}`}
				></div>
			)}
			<div className={`text-xs font-bold ${text} truncate mb-0.5 w-[90%]`}>
				{title}
			</div>
			{sub && <div className="text-[10px] text-muted-foreground font-mono">{sub}</div>}
			<div className="mt-auto flex gap-1">
				<div className="w-3 h-3 bg-card border border-border rounded-sm"></div>
				<div className="w-3 h-3 bg-card border border-border rounded-sm"></div>
			</div>
		</div>
	);
}

function PropRow({
	label,
	value,
	link = false,
}: {
	label: string;
	value: string;
	link?: boolean;
}) {
	return (
		<div className="flex justify-between items-center text-xs">
			<span className="text-muted-foreground">{label}</span>
			<span
				className={`font-mono ${link ? "text-info hover:underline cursor-pointer" : "text-foreground text-right"}`}
			>
				{value}
			</span>
		</div>
	);
}
