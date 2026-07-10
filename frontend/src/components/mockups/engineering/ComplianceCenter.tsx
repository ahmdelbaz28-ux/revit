// NOSONAR
import {
	AlertOctagon,
	AlertTriangle,
	ChevronRight,
	FileText,
	History,
	Play,
	Search,
	Settings,
	ShieldCheck,
	Target,
	Zap,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export function ComplianceCenter() {
	return (
		<div className="flex flex-col h-screen w-screen overflow-hidden bg-background text-foreground dark font-sans">
			{/* Header */}
			<div className="h-16 flex items-center justify-between px-4 border-b bg-card shrink-0">
				<div className="flex items-center gap-4">
					<div className="w-10 h-10 rounded-md bg-emerald-500/20 flex items-center justify-center border border-success/30">
						<ShieldCheck className="h-5 w-5 text-success" />
					</div>
					<div>
						<h1 className="font-bold tracking-wide text-lg leading-tight">
							Code Compliance Center
						</h1>
						<div className="text-[10px] font-mono text-muted-foreground flex items-center gap-2">
							<span>
								Status: <span className="text-warning">Action Required</span>
							</span>
							<span>•</span>
							<span>Last check: 14:47 today</span>
						</div>
					</div>
				</div>

				<div className="flex items-center gap-4">
					<div className="flex gap-2">
						<Button variant="outline" size="sm" className="h-8 gap-1">
							<History className="h-4 w-4" /> History
						</Button>
						<Button variant="outline" size="sm" className="h-8 gap-1">
							<Settings className="h-4 w-4" /> Configure Standards
						</Button>
						<Button variant="outline" size="sm" className="h-8 gap-1">
							<FileText className="h-4 w-4" /> Generate Report
						</Button>
						<Button
							size="sm"
							className="h-8 gap-1 shadow-[0_0_15px_rgba(0,168,255,0.4)]"
						>
							<Play className="h-4 w-4" /> Run Full Check
						</Button>
					</div>
				</div>
			</div>

			{/* Status Banner */}
			<div className="h-8 bg-card/80 border-b flex items-center px-4 gap-4 text-xs font-medium shrink-0">
				<div className="flex-1 h-1.5 rounded-full overflow-hidden flex">
					<div className="bg-red-500 w-[2%]" title="Critical (3)"></div>
					<div className="bg-orange-400 w-[5%]" title="Warnings (8)"></div>
					<div className="bg-emerald-500 w-[93%]" title="Passed (127)"></div>
				</div>
				<div className="flex gap-4 font-mono">
					<span className="text-danger">3 Critical</span>
					<span className="text-primary">8 Warnings</span>
					<span className="text-success">127 Passed</span>
				</div>
			</div>

			<div className="flex flex-1 overflow-hidden">
				{/* Left Panel - Standards Library */}
				<div className="w-[260px] flex flex-col border-r bg-card/30 shrink-0">
					<div className="p-3 border-b bg-card/50 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
						Active Standards
					</div>
					<ScrollArea className="flex-1">
						<div className="p-3 space-y-4">
							<StandardGroup
								title="Electrical"
								items={[
									{ name: "NFPA 70", version: "NEC 2023", active: true },
									{
										name: "NFPA 72",
										version: "Fire Alarm",
										active: true,
										update: true,
									},
									{ name: "IEEE 1584", version: "Arc Flash", active: true },
									{ name: "IEC 60364", version: "L.V. Install", active: true },
								]}
							/>

							<StandardGroup
								title="Mechanical"
								items={[
									{ name: "ASHRAE 90.1", version: "Energy", active: true },
									{ name: "SMACNA", version: "Duct Const.", active: true },
								]}
							/>

							<StandardGroup
								title="Structural"
								items={[
									{ name: "ASCE 7-22", version: "Loads", active: true },
									{ name: "ACI 318-19", version: "Concrete", active: false },
								]}
							/>

							<StandardGroup
								title="Building"
								items={[
									{ name: "IBC 2021", version: "Building", active: true },
									{ name: "ADA 2010", version: "Accessibility", active: true },
								]}
							/>
						</div>
					</ScrollArea>
				</div>

				{/* Center Panel - Results */}
				<div className="flex-1 flex flex-col bg-[#0f1115]">
					<Tabs defaultValue="critical" className="flex flex-col h-full">
						<div className="px-4 py-2 border-b bg-card/80 flex items-center justify-between">
							<TabsList className="h-8 bg-background">
								<TabsTrigger value="all" className="text-xs px-3">
									All Results
								</TabsTrigger>
								<TabsTrigger
									value="critical"
									className="text-xs px-3 data-[state=active]:bg-red-500/20 data-[state=active]:text-danger"
								>
									Critical{" "}
									<Badge
										variant="secondary"
										className="ml-1 text-[9px] px-1 py-0 h-4 bg-red-500 text-white"
									>
										3
									</Badge>
								</TabsTrigger>
								<TabsTrigger
									value="warnings"
									className="text-xs px-3 data-[state=active]:bg-primary/20 data-[state=active]:text-primary"
								>
									Warnings{" "}
									<Badge
										variant="secondary"
										className="ml-1 text-[9px] px-1 py-0 h-4 bg-primary text-white"
									>
										8
									</Badge>
								</TabsTrigger>
								<TabsTrigger
									value="passed"
									className="text-xs px-3 data-[state=active]:bg-emerald-500/20 data-[state=active]:text-success"
								>
									Passed{" "}
									<Badge
										variant="secondary"
										className="ml-1 text-[9px] px-1 py-0 h-4 bg-emerald-500 text-white"
									>
										127
									</Badge>
								</TabsTrigger>
								<TabsTrigger value="suppressed" className="text-xs px-3">
									Suppressed
								</TabsTrigger>
							</TabsList>

							<div className="relative w-48">
								<Search className="absolute left-2 top-1.5 h-4 w-4 text-muted-foreground" />
								<Input
									placeholder="Search issues..."
									className="h-7 text-xs pl-7 bg-background border-muted"
								/>
							</div>
						</div>

						<ScrollArea className="flex-1 p-4">
							<TabsContent value="critical" className="m-0 space-y-3">
								<IssueCard
									active
									severity="Critical"
									std="NFPA 72 § 17.7.3"
									title="Smoke detector SD-047 coverage area exceeds 84m²"
									desc="Maximum 84m² per AHJ. Actual coverage calculated: 97.2m² in open office area."
									actions={["View Element", "Add Detector", "Suppress"]}
								/>
								<IssueCard
									severity="Critical"
									std="NEC 2023 § 230.70"
									title="Service disconnecting means not accessible from grade level"
									desc="Panel MDP-1 located at height 4.2m. Maximum permitted operating height is 1.98m."
									actions={["View Element", "Auto-Fix", "Suppress"]}
								/>
								<IssueCard
									severity="Critical"
									std="IEEE 1584"
									title="Arc flash PPE category 4 required at Panel LP-3A"
									desc="Incident energy calculated at 52.4 cal/cm². Warning label is not present on the equipment."
									actions={["View Element", "Generate Label", "Suppress"]}
								/>
							</TabsContent>

							<TabsContent value="warnings" className="m-0 space-y-3">
								<IssueCard
									severity="Warning"
									std="NEC § 210.8"
									title="GFCI protection required within 1.8m of sink"
									desc="Receptacle REC-22 in room 204-B is 1.2m from sink edge but lacks GFCI designation."
									actions={["View Element", "Change Type", "Suppress"]}
								/>
								<IssueCard
									severity="Warning"
									std="NEC § 110.26"
									title="Working clearance at Panel LP-5 may be insufficient"
									desc="Verify 914mm minimum depth. Adjacent water pipe limits clearance to 850mm."
									actions={["View Element", "Suppress"]}
								/>
								<IssueCard
									severity="Warning"
									std="NFPA 72 § 10.15"
									title="Battery backup calculation not found for FACP-1"
									desc="System requires 24h standby + 5min alarm capacity documentation attached."
									actions={["Attach Calc", "Suppress"]}
								/>
								<IssueCard
									severity="Warning"
									std="ADA 2010 § 308"
									title="Electrical receptacles exceed reach range"
									desc="Receptacles in conference room 305 mounted at 1250mm. Max high forward reach is 1220mm."
									actions={["View Element", "Auto-Fix", "Suppress"]}
								/>
							</TabsContent>
						</ScrollArea>
					</Tabs>
				</div>

				{/* Right Panel - Issue Detail */}
				<div className="w-[320px] flex flex-col border-l bg-card/30 shrink-0 shadow-[-10px_0_20px_rgba(0,0,0,0.2)] z-20">
					<div className="p-4 border-b bg-card/50">
						<div className="flex items-center justify-between mb-2">
							<span className="font-mono text-xs font-bold text-muted-foreground">
								CMP-084
							</span>
							<Badge
								variant="outline"
								className="bg-red-500/20 text-danger border-danger/30"
							>
								Critical
							</Badge>
						</div>
						<h3 className="font-semibold text-sm leading-tight mb-2">
							Smoke detector SD-047 coverage area exceeds 84m²
						</h3>
						<div className="flex items-center gap-2 text-xs font-mono text-muted-foreground">
							<span className="text-primary font-bold">NFPA 72 § 17.7.3</span>
							<span>•</span>
							<span>Level 3, Room 312-A</span>
						</div>
					</div>

					<ScrollArea className="flex-1">
						<div className="p-4 space-y-6">
							<div>
								<div className="text-xs font-semibold uppercase text-muted-foreground mb-2">
									Code Text
								</div>
								<div className="p-3 bg-[#0f1115] border border-border rounded-md font-mono text-[10px] text-foreground/90 leading-relaxed">
									"For smooth ceilings, all points on the ceiling shall have a
									detector within a distance equal to 0.7 times the selected
									spacing (0.7S). This equates to a maximum coverage area of 900
									ft² (84m²) per detector."
								</div>
							</div>

							<div>
								<div className="text-xs font-semibold uppercase text-muted-foreground mb-2">
									Element Info
								</div>
								<div className="grid grid-cols-2 gap-2 text-xs">
									<div className="text-muted-foreground">Device:</div>
									<div className="font-mono text-right">
										SD-047 (Photoelectric)
									</div>
									<div className="text-muted-foreground">Actual Area:</div>
									<div className="font-mono text-right text-danger">
										97.2 m²
									</div>
									<div className="text-muted-foreground">Max Allowed:</div>
									<div className="font-mono text-right">84.0 m²</div>
									<div className="text-muted-foreground">Grid Loc:</div>
									<div className="font-mono text-right">X:12.5, Y:8.6</div>
								</div>
							</div>

							<div>
								<div className="p-3 border border-primary/40 bg-primary/5 rounded-md relative overflow-hidden">
									<div className="absolute top-0 left-0 w-1 h-full bg-primary"></div>
									<div className="flex items-center gap-2 text-primary font-semibold text-xs mb-2">
										<Zap className="h-4 w-4 fill-primary/20" /> AI
										Resolution
									</div>
									<p className="text-xs text-muted-foreground mb-4">
										Install 1 additional smoke detector at grid coordinate
										X:16.2, Y:8.6 to split the zone. This reduces coverage area
										to 51.4m² per detector.
									</p>
									<Button
										size="sm"
										className="w-full text-xs h-8 shadow-[0_0_10px_rgba(0,168,255,0.3)]"
									>
										Accept AI Fix
									</Button>
								</div>
							</div>

							<div className="flex flex-col gap-2">
								<Button
									variant="outline"
									size="sm"
									className="text-xs h-8 justify-start"
								>
									<Target className="h-4 w-4 mr-2" /> View in Drawing
								</Button>
								<Button
									variant="outline"
									size="sm"
									className="text-xs h-8 justify-start"
								>
									<AlertOctagon className="h-4 w-4 mr-2" /> Suppress with
									Reason
								</Button>
							</div>
						</div>
					</ScrollArea>
				</div>
			</div>

			{/* Bottom Bar */}
			<div className="h-8 border-t bg-card flex items-center justify-between px-4 text-[10px] font-mono text-muted-foreground shrink-0">
				<div className="flex items-center gap-4">
					<span>Project: Tower-B</span>
					<Separator orientation="vertical" className="h-4" />
					<span>Profile: Commercial Office v2.1</span>
				</div>
				<div className="flex items-center gap-4 text-success font-bold">
					Compliance Score: 94.7%
				</div>
			</div>
		</div>
	);
}

function StandardGroup({ title, items }: { title: string; items: any[] }) {  // NOSONAR - typescript:S6759
	return (
		<div className="mb-4">
			<div className="text-xs font-semibold text-foreground mb-2 flex items-center">
				<ChevronRight className="h-3 w-3 mr-1 opacity-50" /> {title}
			</div>
			<div className="space-y-1 pl-4 border-l border-border/30 ml-1.5">
				{items.map((item, i) => (
					<div
						key={i}  // NOSONAR — S6479: array index key acceptable for static list
						className="flex items-center justify-between py-1 px-2 hover:bg-muted/50 rounded-md"
					>
						<div className="flex items-center gap-2">
							<Switch
								checked={item.active}
								className="scale-[0.6] origin-left"
							/>
							<span
								className={`text-xs ${item.active ? "text-foreground" : "text-muted-foreground"}`}
							>
								{item.name}
							</span>
						</div>
						<div className="flex items-center gap-2">
							{item.update && (
								<div
									className="w-1.5 h-1.5 rounded-full bg-blue-500"
									title="Update Available"
								></div>
							)}
							<span className="text-[9px] font-mono text-muted-foreground">
								{item.version}
							</span>
						</div>
					</div>
				))}
			</div>
		</div>
	);
}

function IssueCard({ active, severity, std, title, desc, actions }: any) {
	const isCrit = severity === "Critical";
	const borderColor = isCrit ? "border-l-red-500" : "border-l-orange-500";
	const iconColor = isCrit ? "text-danger" : "text-primary";
	const Icon = isCrit ? AlertOctagon : AlertTriangle;

	return (
		<div
			className={`p-3 bg-card border border-border/50 border-l-4 ${borderColor} rounded-r-md cursor-pointer transition-colors ${active ? "bg-muted shadow-md" : "hover:bg-muted/50"}`}
		>
			<div className="flex items-start gap-3">
				<Icon className={`h-4 w-4 shrink-0 mt-0.5 ${iconColor}`} />
				<div className="flex-1">
					<div className="flex items-center gap-2 mb-1">
						<Badge
							variant="outline"
							className={`text-[9px] px-1 py-0 h-4 border-muted-foreground/30 ${isCrit ? "text-danger bg-red-500/10" : "text-primary bg-primary/10"}`}
						>
							{severity}
						</Badge>
						<span className="text-[10px] font-mono text-muted-foreground">
							{std}
						</span>
					</div>
					<h4 className="text-sm font-semibold mb-1 leading-tight">{title}</h4>
					<p className="text-xs text-muted-foreground mb-3">{desc}</p>
					<div className="flex gap-2">
						{actions.map((act: string, i: number) => (
							<Button
								key={i}  // NOSONAR — S6479: array index key acceptable for static list
								variant={i === 0 ? "secondary" : "outline"}
								size="sm"
								className="h-6 text-[10px] px-2 bg-background border-muted"
							>
								{act}
							</Button>
						))}
					</div>
				</div>
			</div>
		</div>
	);
}
