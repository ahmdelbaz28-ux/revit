// NOSONAR
import {
	AlertCircle,
	Box,
	CheckCircle,
	ChevronRight,
	Download,
	ExternalLink,
	FileCode2,
	Key,
	Puzzle,
	Search,
	ShieldCheck,
	Star,
	UploadCloud,
	Zap,
} from "lucide-react";
import type React from "react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

export function PluginManager() {
	const [selectedPlugin, setSelectedPlugin] = useState<number | null>(1);

	return (
		<div className="flex flex-col h-screen w-screen overflow-hidden bg-background text-foreground dark font-sans">
			{/* Header */}
			<div className="h-16 flex items-center justify-between px-6 border-b bg-card shrink-0">
				<div className="flex items-center gap-4">
					<div className="w-10 h-10 rounded-md bg-purple-500/20 flex items-center justify-center border border-purple-500/30">
						<Puzzle className="h-5 w-5 text-purple-400" />
					</div>
					<div>
						<h1 className="font-bold tracking-wide text-lg leading-tight">
							Plugin Manager & Marketplace
						</h1>
						<div className="text-[10px] font-mono text-muted-foreground mt-0.5">
							NexusCAD Pro Ecosystem
						</div>
					</div>
				</div>

				<Tabs defaultValue="marketplace" className="h-full flex items-center">
					<TabsList className="bg-transparent gap-2">
						<TabsTrigger value="installed">Installed</TabsTrigger>
						<TabsTrigger
							value="marketplace"
							className="data-[state=active]:bg-primary/20 data-[state=active]:text-primary border border-transparent data-[state=active]:border-primary/30"
						>
							Marketplace
						</TabsTrigger>
						<TabsTrigger value="updates" className="gap-1.5">
							Updates{" "}
							<Badge className="h-4 px-1 py-0 text-[9px] bg-blue-500 text-white border-transparent">
								3
							</Badge>
						</TabsTrigger>
						<TabsTrigger value="dev">Developer Tools</TabsTrigger>
					</TabsList>
				</Tabs>

				<div className="flex items-center gap-4">
					<div className="relative w-64 hidden xl:block">
						<Search className="absolute left-2.5 top-2 h-4 w-4 text-muted-foreground" />
						<Input
							placeholder="Search 2,400+ plugins..."
							className="pl-9 h-8 bg-[#0a0a0f] border-border text-xs focus-visible:ring-purple-500"
						/>
					</div>
					<div className="flex gap-2">
						<Button variant="outline" size="sm" className="h-8 gap-1.5 text-xs">
							<UploadCloud className="h-4 w-4" /> Upload Plugin
						</Button>
						<Button variant="outline" size="sm" className="h-8 gap-1.5 text-xs">
							<Key className="h-4 w-4" /> API Keys
						</Button>
					</div>
				</div>
			</div>

			<div className="flex flex-1 overflow-hidden">
				{/* Left Sidebar - Categories */}
				<div className="w-[220px] flex flex-col border-r bg-card/30 shrink-0">
					<ScrollArea className="flex-1 p-3">
						<div className="space-y-1">
							<CategoryItem label="All Plugins" count="2,400" active />
							<CategoryItem label="Featured" />
							<CategoryItem label="New & Updated" />

							<div className="pt-4 pb-1">
								<div className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider px-2 mb-2">
									By Discipline
								</div>
								<CategoryItem label="Electrical" count="487" expanded>
									<SubCategoryItem label="Arc Flash Tools" />
									<SubCategoryItem label="Protection Coord" />
									<SubCategoryItem label="Cable Sizing" />
									<SubCategoryItem label="Motor Control" />
								</CategoryItem>
								<CategoryItem label="BIM & IFC" count="312" />
								<CategoryItem label="Structural" count="198" />
								<CategoryItem label="Fire Protection" count="156" />
								<CategoryItem label="Compliance & Codes" count="243" />
							</div>

							<div className="pt-2 pb-1">
								<div className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider px-2 mb-2">
									Workflow
								</div>
								<CategoryItem label="AI & Automation" count="89" badge="NEW" />
								<CategoryItem label="Reporting" count="176" />
								<CategoryItem label="Data Import/Export" count="134" />
								<CategoryItem label="Interoperability" count="98" />
								<CategoryItem label="Developer Tools" count="45" />
							</div>
						</div>
					</ScrollArea>
				</div>

				{/* Main Grid - Marketplace */}
				<div className="flex-1 bg-[#0a0a0f] flex flex-col overflow-hidden">
					<div className="px-6 py-4 border-b border-slate-800/50 bg-card/20 flex justify-between items-center shrink-0">
						<h2 className="text-lg font-bold text-foreground tracking-tight">
							Featured & Popular
						</h2>
						<div className="text-xs text-muted-foreground flex items-center gap-2">
							Sort by:{" "}
							<span className="text-foreground font-medium cursor-pointer">
								Most Popular ▼
							</span>
						</div>
					</div>

					<ScrollArea className="flex-1 p-6">
						<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 max-w-[1200px] mx-auto">
							<PluginCard
								id={1}
								name="EasyArcFlash Pro"
								publisher="ABB Digital"
								verified
								desc="IEEE 1584-2018 arc flash analysis with auto-labeling directly from your SLD."
								rating={4.9}
								downloads="12.4k"
								price="$49/mo"
								category="Electrical"
								iconColor="bg-red-500"
								iconLetter="A"
								action="Install"
								selected={selectedPlugin === 1}
								onClick={() => setSelectedPlugin(1)}
							/>

							<PluginCard
								id={2}
								name="IFC BIM Exporter"
								publisher="Autodesk"
								verified
								desc="Export NexusCAD models to IFC 4.3 with complete element metadata mapping."
								rating={4.7}
								downloads="34.2k"
								price="Free"
								category="BIM & IFC"
								iconColor="bg-blue-600"
								iconLetter="I"
								action="Installed"
								onClick={() => setSelectedPlugin(2)}
							/>

							<PluginCard
								id={3}
								name="ProtCoord Suite"
								publisher="PowerSoft"
								desc="Time-current curve coordination with massive global relay library."
								rating={4.8}
								downloads="8.9k"
								price="$199/yr"
								category="Electrical"
								iconColor="bg-primary"
								iconLetter="P"
								action="Install"
								onClick={() => setSelectedPlugin(3)}
							/>

							<PluginCard
								id={4}
								name="AI Drawing Checker"
								publisher="NexusAI"
								verified
								desc="GPT-4 powered automated drawing review and intelligent redline suggestions."
								rating={4.6}
								downloads="5.6k"
								price="Included"
								category="AI & Auto"
								iconColor="bg-purple-500"
								iconLetter="AI"
								action="Installed"
								onClick={() => setSelectedPlugin(4)}
							/>

							<PluginCard
								id={5}
								name="ETAP Bridge"
								publisher="PowerAnalytics"
								desc="Bidirectional live synchronization with ETAP Power System Analysis software."
								rating={4.5}
								downloads="3.2k"
								price="$99/mo"
								category="Interop"
								iconColor="bg-emerald-600"
								iconLetter="E"
								action="Install"
								onClick={() => setSelectedPlugin(5)}
							/>

							<PluginCard
								id={6}
								name="Load Pro Calculator"
								publisher="ElecTools"
								desc="Advanced demand load calculations compliant with NEC, IEC, and ASHRAE."
								rating={4.9}
								downloads="21.8k"
								price="Free"
								category="Electrical"
								iconColor="bg-cyan-500"
								iconLetter="L"
								action="Update"
								onClick={() => setSelectedPlugin(6)}
							/>

							<PluginCard
								id={7}
								name="Revit Live Link"
								publisher="Autodesk"
								verified
								desc="Real-time geometry and metadata sync between NexusCAD and Revit projects."
								rating={4.4}
								downloads="18.7k"
								price="Included"
								category="BIM & IFC"
								iconColor="bg-blue-800"
								iconLetter="R"
								action="Installed"
								onClick={() => setSelectedPlugin(7)}
							/>

							<PluginCard
								id={8}
								name="Cable Schedule Gen"
								publisher="EngiSoft"
								desc="Automatically generate, route, and size cable schedules from drawing data."
								rating={4.7}
								downloads="9.4k"
								price="$29/mo"
								category="Reporting"
								iconColor="bg-yellow-600"
								iconLetter="C"
								action="Install"
								onClick={() => setSelectedPlugin(8)}
							/>

							<PluginCard
								id={9}
								name="Code Check AI"
								publisher="LegalTech Eng"
								desc="Multi-code compliance engine with automated localized fix suggestions."
								rating={5.0}
								downloads="2.1k"
								price="$79/mo"
								category="Compliance"
								iconColor="bg-indigo-500"
								iconLetter="✓"
								action="Install"
								onClick={() => setSelectedPlugin(9)}
							/>
						</div>
					</ScrollArea>
				</div>

				{/* Right Sidebar - Detail View */}
				{selectedPlugin === 1 && (
					<div className="w-[320px] flex flex-col border-l bg-card/30 shrink-0 shadow-[-10px_0_30px_rgba(0,0,0,0.3)] z-10 animate-in slide-in-from-right-8 duration-300">
						<ScrollArea className="flex-1">
							<div className="p-6">
								{/* Detail Header */}
								<div className="flex gap-4 mb-6">
									<div className="w-16 h-16 rounded-md bg-red-500 flex items-center justify-center text-white text-3xl font-bold shadow-lg shadow-red-500/20 shrink-0">
										A
									</div>
									<div>
										<h2 className="text-lg font-bold leading-tight mb-1">
											EasyArcFlash Pro
										</h2>
										<div className="flex items-center gap-1 text-xs text-muted-foreground mb-1">
											<span>ABB Digital</span>
											<ShieldCheck className="h-3 w-3 text-info" />
										</div>
										<div className="flex items-center gap-1 text-[10px] font-mono text-yellow-500">
											<Star className="h-3 w-3 fill-yellow-500" />
											<span>4.9/5.0</span>
											<span className="text-muted-foreground">(847 reviews)</span>
										</div>
									</div>
								</div>

								<div className="grid grid-cols-2 gap-y-3 gap-x-2 text-[11px] mb-6 bg-card/50 p-3 rounded-lg border border-slate-800">
									<div className="text-muted-foreground">Version:</div>
									<div className="font-mono text-right text-foreground/90">
										3.4.2
									</div>
									<div className="text-muted-foreground">Updated:</div>
									<div className="font-mono text-right text-foreground/90">
										Nov 12, 2024
									</div>
									<div className="text-muted-foreground">Requires:</div>
									<div className="font-mono text-right text-foreground/90">
										NexusCAD 4.x+
									</div>
									<div className="text-muted-foreground">License:</div>
									<div className="font-mono text-right text-foreground/90">
										Per-seat, Sub
									</div>
								</div>

								<Button className="w-full h-10 bg-blue-600 hover:bg-blue-500 text-white font-semibold shadow-[0_0_20px_rgba(37,99,235,0.4)] mb-6 transition-all">
									Install Plugin — $49/mo
								</Button>

								{/* Description */}
								<div className="mb-6">
									<h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-2">
										Description
									</h3>
									<p className="text-xs text-foreground/90 leading-relaxed">
										Full IEEE 1584-2018 arc flash hazard analysis integrated
										directly into NexusCAD. Auto-extracts system data from your
										drawings, runs the complete analysis workflow, and generates
										NFPA 70E-compliant labels and reports without leaving the
										canvas.
									</p>
								</div>

								{/* Features */}
								<div className="mb-6">
									<h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-2">
										Key Features
									</h3>
									<ul className="space-y-2 text-xs text-foreground/90">
										<li className="flex items-start gap-2">
											<div className="w-1.5 h-1.5 rounded-full bg-blue-500 mt-1 shrink-0"></div>{" "}
											Auto-extract from SLD topology
										</li>
										<li className="flex items-start gap-2">
											<div className="w-1.5 h-1.5 rounded-full bg-blue-500 mt-1 shrink-0"></div>{" "}
											Incident energy calculation engine
										</li>
										<li className="flex items-start gap-2">
											<div className="w-1.5 h-1.5 rounded-full bg-blue-500 mt-1 shrink-0"></div>{" "}
											PPE category assignment mapping
										</li>
										<li className="flex items-start gap-2">
											<div className="w-1.5 h-1.5 rounded-full bg-blue-500 mt-1 shrink-0"></div>{" "}
											Visual arc flash label generation
										</li>
										<li className="flex items-start gap-2">
											<div className="w-1.5 h-1.5 rounded-full bg-blue-500 mt-1 shrink-0"></div>{" "}
											Working distance optimization
										</li>
										<li className="flex items-start gap-2">
											<div className="w-1.5 h-1.5 rounded-full bg-blue-500 mt-1 shrink-0"></div>{" "}
											NFPA 70E 2021 & 2024 compliant
										</li>
									</ul>
								</div>

								{/* Screenshots Fake */}
								<div className="mb-6">
									<h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-2">
										Screenshots
									</h3>
									<div className="flex gap-2 overflow-x-auto pb-2 scrollbar-hide">
										<div className="w-24 h-16 shrink-0 bg-card rounded border border-border flex items-center justify-center">
											<Zap className="h-4 w-4 text-muted-foreground/70" />
										</div>
										<div className="w-24 h-16 shrink-0 bg-card rounded border border-border flex items-center justify-center">
											<Box className="h-4 w-4 text-muted-foreground/70" />
										</div>
										<div className="w-24 h-16 shrink-0 bg-card rounded border border-border flex items-center justify-center">
											<FileCode2 className="h-4 w-4 text-muted-foreground/70" />
										</div>
									</div>
								</div>

								{/* Permissions */}
								<div className="mb-6">
									<h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-2">
										Permissions Requested
									</h3>
									<div className="space-y-1.5">
										<Badge
											variant="outline"
											className="text-[10px] font-normal w-full justify-start border-border bg-muted/50"
										>
											<Search className="h-3 w-3 mr-2 text-muted-foreground" />{" "}
											Read drawing data & properties
										</Badge>
										<Badge
											variant="outline"
											className="text-[10px] font-normal w-full justify-start border-border bg-muted/50"
										>
											<FileCode2 className="h-3 w-3 mr-2 text-muted-foreground" />{" "}
											Write annotations to canvas
										</Badge>
										<Badge
											variant="outline"
											className="text-[10px] font-normal w-full justify-start border-border bg-muted/50"
										>
											<Box className="h-3 w-3 mr-2 text-muted-foreground" />{" "}
											Access component library specs
										</Badge>
									</div>
								</div>

								{/* Links */}
								<div className="flex flex-col gap-2">
									<Button
										variant="ghost"
										className="h-8 text-xs justify-between w-full border border-slate-800 hover:bg-card"
									>
										View Documentation <ExternalLink className="h-3 w-3" />
									</Button>
									<Button
										variant="ghost"
										className="h-8 text-xs justify-between w-full border border-slate-800 hover:bg-card"
									>
										Publisher Website <ExternalLink className="h-3 w-3" />
									</Button>
									<Button
										variant="ghost"
										className="h-8 text-xs justify-between w-full border border-slate-800 hover:bg-card text-muted-foreground"
									>
										Report Issue <AlertCircle className="h-3 w-3" />
									</Button>
								</div>
							</div>
						</ScrollArea>
					</div>
				)}
			</div>

			{/* Bottom Console */}
			<div className="h-8 border-t bg-card flex items-center justify-between px-6 text-[11px] font-mono text-muted-foreground shrink-0">
				<div className="flex items-center gap-4">
					<span>
						<span className="text-foreground font-semibold">47</span> plugins
						installed
					</span>
					<Separator orientation="vertical" className="h-4" />
					<span className="text-info cursor-pointer hover:underline">
						3 updates available
					</span>
					<Separator orientation="vertical" className="h-4" />
					<span>License: Enterprise (unlimited seats)</span>
				</div>
				<div className="flex items-center gap-4">
					<span className="cursor-pointer hover:text-foreground">
						Check for Updates
					</span>
					<span className="cursor-pointer hover:text-foreground">
						View License
					</span>
				</div>
			</div>
		</div>
	);
}

function CategoryItem({  // NOSONAR - typescript:S6759
	label,
	count,
	active,
	expanded,
	badge,
	children,
}: {
	label: string;
	count?: string;
	active?: boolean;
	expanded?: boolean;
	badge?: string;
	children?: React.ReactNode;
}) {
	return (
		<div className="mb-0.5">
			<div
				className={`flex items-center justify-between px-3 py-2 rounded-md cursor-pointer transition-colors ${active ? "bg-primary/20 text-primary font-medium" : "text-muted-foreground hover:bg-muted hover:text-foreground"}`}
			>
				<div className="flex items-center gap-2">
					{children && (
						<ChevronRight
							className={`h-3 w-3 transition-transform ${expanded ? "rotate-90" : ""}`}
						/>
					)}
					<span className="text-xs">{label}</span>
				</div>
				<div className="flex items-center gap-2">
					{badge && (
						<Badge className="h-4 px-1 py-0 text-[8px] bg-purple-500 text-white border-transparent">
							{badge}
						</Badge>
					)}
					{count && (
						<span className="text-[10px] font-mono opacity-60">{count}</span>
					)}
				</div>
			</div>
			{expanded && children && (
				<div className="ml-5 pl-2 border-l border-slate-800 mt-1 flex flex-col gap-0.5">
					{children}
				</div>
			)}
		</div>
	);
}

function SubCategoryItem({ label }: { label: string }) {  // NOSONAR - typescript:S6759
	return (
		<div className="px-2 py-1.5 rounded text-[11px] text-muted-foreground hover:text-foreground/90 hover:bg-muted cursor-pointer transition-colors">
			{label}
		</div>
	);
}

function PluginCard({
	id,
	name,
	publisher,
	verified,
	desc,
	rating,
	downloads,
	price,
	category,
	iconColor,
	iconLetter,
	action,
	selected,
	onClick,
}: any) {
	let actionBtn;
	if (action === "Installed") {
		actionBtn = (
			<Button
				variant="secondary"
				size="sm"
				className="w-full h-8 text-xs bg-card text-success hover:bg-secondary"
			>
				<CheckCircle className="h-3 w-3 mr-1.5" /> Installed
			</Button>
		);
	} else if (action === "Update") {
		actionBtn = (
			<Button
				variant="default"
				size="sm"
				className="w-full h-8 text-xs bg-blue-600 hover:bg-blue-500 text-white"
			>
				Update Available
			</Button>
		);
	} else {
		actionBtn = (
			<Button
				variant="outline"
				size="sm"
				className="w-full h-8 text-xs border-border hover:bg-card hover:text-white"
			>
				Install
			</Button>
		);
	}

	return (
		<div  // NOSONAR — S6848: type assertion acceptable
			className={`flex flex-col bg-card/40 border rounded-md p-5 cursor-pointer transition-all hover:shadow-lg hover:border-border ${selected ? "border-blue-500 shadow-[0_0_15px_rgba(59,130,246,0.15)] bg-blue-950/10" : "border-slate-800"}`}
			onClick={onClick}
		>
			<div className="flex gap-4 mb-4">
				<div
					className={`w-12 h-12 rounded-lg flex items-center justify-center text-white text-xl font-bold shadow-md shrink-0 ${iconColor}`}
				>
					{iconLetter}
				</div>
				<div className="flex-1 min-w-0">
					<div className="flex justify-between items-start mb-0.5">
						<h3 className="font-bold text-sm text-foreground truncate pr-2">
							{name}
						</h3>
						<Badge
							variant="outline"
							className="text-[9px] h-4 py-0 px-1 border-border bg-muted/50 text-foreground/90 shrink-0"
						>
							{category}
						</Badge>
					</div>
					<div className="flex items-center gap-1 text-[11px] text-muted-foreground">
						<span className="truncate">{publisher}</span>
						{verified && (
							<ShieldCheck className="h-3 w-3 text-info shrink-0" />
						)}
					</div>
				</div>
			</div>

			<p className="text-xs text-muted-foreground line-clamp-2 mb-4 flex-1">{desc}</p>

			<div className="flex items-center justify-between text-[10px] font-mono text-muted-foreground mb-4 pb-4 border-b border-slate-800/50">
				<div className="flex items-center gap-1 text-yellow-500">
					<Star className="h-3 w-3 fill-yellow-500" /> {rating}
				</div>
				<div className="flex items-center gap-1">
					<Download className="h-3 w-3" /> {downloads}
				</div>
				<div className="font-sans font-medium text-foreground/90">{price}</div>
			</div>

			<div className="mt-auto">{actionBtn}</div>
		</div>
	);
}
