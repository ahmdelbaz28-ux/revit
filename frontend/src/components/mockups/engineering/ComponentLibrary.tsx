import {
	ChevronDown,
	ChevronRight,
	Download,
	FileSymlink,
	Filter,
	FolderTree,
	Heart,
	LayoutGrid,
	Library,
	List,
	PackagePlus,
	Plus,
	Search,
	Settings,
} from "lucide-react";
import type React from "react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

export function ComponentLibrary() {
	const [activeCategory, setActiveCategory] = useState(
		"Switchgear & Protection",
	);
	const [selectedComp, setSelectedComp] = useState<number | null>(1);

	const categories = [
		{
			name: "Electrical",
			open: true,
			children: [
				"Power Distribution",
				"Switchgear & Protection",
				"Motors & Drives",
				"Transformers",
				"Cables & Conduit",
				"Grounding & Bonding",
				"Lighting",
				"Instrumentation",
			],
		},
		{ name: "Fire Alarm", open: false, children: [] },
		{ name: "HVAC Controls", open: false, children: [] },
		{ name: "Plumbing", open: false, children: [] },
		{ name: "Structural", open: false, children: [] },
		{ name: "BIM Families", open: false, children: [] },
	];

	const components = [
		{
			id: 1,
			name: "Molded Case Circuit Breaker",
			spec: "3P / 100A / 480V",
			std: "IEC 60898",
			mfg: ["ABB", "Siemens"],
		},
		{
			id: 2,
			name: "Air Circuit Breaker",
			spec: "3P / 2500A / 480V",
			std: "NFPA 70",
			mfg: ["Schneider", "Eaton"],
		},
		{
			id: 3,
			name: "Motor Protection Relay",
			spec: "3P / 10-40A",
			std: "IEC 60947",
			mfg: ["Siemens"],
		},
		{
			id: 4,
			name: "Magnetic Contactor",
			spec: "3P / 150A / 480V",
			std: "UL 508",
			mfg: ["Rockwell", "ABB"],
		},
		{
			id: 5,
			name: "Residual Current Device",
			spec: "2P / 63A / 30mA",
			std: "IEC 61008",
			mfg: ["Schneider"],
		},
		{
			id: 6,
			name: "Surge Protective Device",
			spec: "40kA / 275V",
			std: "IEC 61643",
			mfg: ["Dehn", "OBO"],
		},
		{
			id: 7,
			name: "Current Transformer",
			spec: "400:5A Cl.0.5",
			std: "IEC 61869",
			mfg: ["Circutor"],
		},
		{
			id: 8,
			name: "Busbar Trunking",
			spec: "1600A / 3P+N",
			std: "IEC 61439",
			mfg: ["Siemens", "Legrand"],
		},
	];

	return (
		<div className="flex flex-col h-screen w-screen overflow-hidden bg-background text-foreground dark font-sans">
			{/* Header */}
			<div className="h-16 flex items-center justify-between px-4 border-b bg-card shrink-0">
				<div className="flex items-center gap-6">
					<div className="font-bold tracking-wide flex items-center gap-2">
						<Library className="h-5 w-5 text-primary" />
						Engineering Component Library
					</div>

					<div className="relative w-[400px]">
						<Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
						<Input
							placeholder="Search 14,832 components..."
							className="pl-9 bg-muted/50 border-muted-foreground/20 h-9 text-sm"
						/>
						<Filter className="absolute right-2.5 top-2.5 h-4 w-4 text-muted-foreground cursor-pointer hover:text-foreground" />
					</div>
				</div>

				<div className="flex items-center gap-4">
					<div className="flex border rounded-md overflow-hidden bg-muted/30">
						<ToolBtn icon={<LayoutGrid />} active />
						<ToolBtn icon={<List />} />
						<ToolBtn icon={<Library />} />
					</div>
					<Separator orientation="vertical" className="h-6" />
					<div className="flex gap-2">
						<Button variant="outline" size="sm" className="h-8 gap-1">
							<Plus className="h-3.5 w-3.5" /> Import Custom
						</Button>
						<Button variant="outline" size="sm" className="h-8 gap-1">
							<FolderTree className="h-3.5 w-3.5" /> Manage Libraries
						</Button>
						<Button variant="ghost" size="icon" className="h-8 w-8">
							<Settings className="h-4 w-4" />
						</Button>
					</div>
				</div>
			</div>

			<div className="flex flex-1 overflow-hidden">
				{/* Left Sidebar */}
				<div className="w-[240px] flex flex-col border-r bg-card/30 shrink-0">
					<ScrollArea className="flex-1 p-3">
						<div className="space-y-1">
							{categories.map((cat, i) => (
								<div key={i} className="mb-2">  // NOSONAR — S6479: array index key acceptable for static list
									<div className="flex items-center gap-1.5 py-1.5 px-2 rounded-md hover:bg-muted/50 cursor-pointer text-sm font-medium text-slate-200">
										{cat.open ? (
											<ChevronDown className="h-3 w-3" />
										) : (
											<ChevronRight className="h-3 w-3" />
										)}
										{cat.name}
									</div>
									{cat.open && (
										<div className="ml-5 pl-2 border-l border-border/50 flex flex-col gap-0.5 mt-1">
											{cat.children.map((child) => (
												<div  // NOSONAR — S6848: type assertion acceptable
													key={child}
													className={`py-1.5 px-2 text-xs rounded-md cursor-pointer transition-colors ${activeCategory === child ? "bg-primary/20 text-primary font-medium" : "text-muted-foreground hover:text-foreground hover:bg-muted/30"}`}
													onClick={() => setActiveCategory(child)}
												>
													{child}
												</div>
											))}
										</div>
									)}
								</div>
							))}
							<div className="pt-4 mt-4 border-t border-border/50">
								<div className="py-1.5 px-2 text-xs text-muted-foreground hover:text-foreground cursor-pointer">
									IEC Symbols
								</div>
								<div className="py-1.5 px-2 text-xs text-muted-foreground hover:text-foreground cursor-pointer">
									NFPA Symbols
								</div>
								<div className="py-1.5 px-2 text-xs text-muted-foreground hover:text-foreground cursor-pointer">
									IEEE Standards
								</div>
							</div>
						</div>
					</ScrollArea>
				</div>

				{/* Main Grid */}
				<div className="flex-1 flex flex-col bg-[#0f1115] relative">
					<div className="p-4 border-b border-border/30 bg-card/50 flex justify-between items-center backdrop-blur-sm sticky top-0 z-10">
						<div className="flex items-center gap-3">
							<h2 className="text-lg font-semibold">{activeCategory}</h2>
							<Badge variant="secondary">847 components</Badge>
						</div>
						<div className="flex gap-2">
							<Badge variant="outline" className="text-xs bg-background">
								480V <span className="ml-1 opacity-50">✕</span>
							</Badge>
							<Badge variant="outline" className="text-xs bg-background">
								3-Phase <span className="ml-1 opacity-50">✕</span>
							</Badge>
							<Badge variant="outline" className="text-xs bg-background">
								IEC <span className="ml-1 opacity-50">✕</span>
							</Badge>
						</div>
					</div>

					<ScrollArea className="flex-1 p-6">
						<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 pb-10">
							{components.map((comp) => (
								<div  // NOSONAR — S6848: type assertion acceptable
									key={comp.id}
									className={`group bg-card border rounded-lg overflow-hidden transition-all hover:border-primary/50 hover:shadow-[0_0_15px_rgba(0,168,255,0.1)] cursor-pointer flex flex-col ${selectedComp === comp.id ? "border-primary shadow-[0_0_10px_rgba(0,168,255,0.2)]" : "border-border/60"}`}
									onClick={() => setSelectedComp(comp.id)}
								>
									<div className="h-32 bg-[#1a1d24] relative flex items-center justify-center p-4 border-b border-border/50">
										<AbstractSymbol id={comp.id} />
										<div
											className={`absolute inset-0 bg-background/80 backdrop-blur-sm flex flex-col items-center justify-center gap-2 transition-opacity ${selectedComp === comp.id ? "opacity-100" : "opacity-0 group-hover:opacity-100"}`}
										>
											<Button size="sm" className="h-8 shadow-lg">
												<FileSymlink className="h-3.5 w-3.5 mr-1" /> Insert
											</Button>
											<Button
												size="sm"
												variant="secondary"
												className="h-8 shadow-lg"
											>
												<Heart className="h-3.5 w-3.5" />
											</Button>
										</div>
									</div>
									<div className="p-3 flex-1 flex flex-col">
										<div className="text-sm font-semibold mb-1 line-clamp-1">
											{comp.name}
										</div>
										<div className="text-xs font-mono text-muted-foreground mb-3">
											{comp.spec}
										</div>
										<div className="mt-auto flex items-center justify-between">
											<Badge
												variant="outline"
												className="text-[9px] px-1.5 py-0 h-4 bg-muted/50"
											>
												{comp.std}
											</Badge>
											<div className="flex gap-1">
												{comp.mfg.map((m) => (
													<span
														key={m}
														className="text-[10px] text-slate-400 bg-slate-800 px-1 rounded"
													>
														{m}
													</span>
												))}
											</div>
										</div>
									</div>
								</div>
							))}
						</div>
					</ScrollArea>
				</div>

				{/* Right Panel - Details */}
				{selectedComp && (
					<div className="w-[320px] flex flex-col border-l bg-card/30 shrink-0 shadow-[-10px_0_20px_rgba(0,0,0,0.2)] z-20">
						<ScrollArea className="flex-1">
							<div className="p-0">
								<div className="h-48 bg-[#1a1d24] flex items-center justify-center border-b p-6 relative">
									<AbstractSymbol id={selectedComp} large />
									<div className="absolute top-2 right-2 flex gap-1">
										<Badge
											variant="secondary"
											className="text-[9px] bg-background/50 backdrop-blur"
										>
											IEC
										</Badge>
									</div>
								</div>

								<div className="p-4 space-y-5">
									<div>
										<h3 className="text-lg font-bold leading-tight mb-1">
											Air Circuit Breaker, 3-Pole, 2500A
										</h3>
										<div className="text-sm text-primary font-mono">
											3WL1225-4EB36-4GA4
										</div>
									</div>

									<div className="flex gap-2">
										<Button className="flex-1 h-9 shadow-md">
											<FileSymlink className="h-4 w-4 mr-2" /> Insert
										</Button>
										<Button variant="outline" size="icon" className="h-9 w-9">
											<Heart className="h-4 w-4" />
										</Button>
									</div>

									<div className="space-y-2">
										<div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground border-b pb-1">
											Specifications
										</div>
										<SpecRow label="Manufacturer" value="Siemens SENTRON 3WL" />
										<SpecRow label="Rated Current" value="2500A" />
										<SpecRow label="Rated Voltage" value="690V AC" />
										<SpecRow label="Short-Circuit" value="100kA" />
										<SpecRow label="Standards" value="IEC 60947-2, NFPA 70" />
										<SpecRow label="Dimensions" value="460 x 320 x 436 mm" />
									</div>

									<div className="space-y-2">
										<div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground border-b pb-1">
											Resources
										</div>
										<div className="grid grid-cols-2 gap-2">
											<Button
												variant="secondary"
												size="sm"
												className="text-xs h-8 justify-start"
											>
												<FileSymlink className="h-3 w-3 mr-2 text-muted-foreground" />{" "}
												Single Line
											</Button>
											<Button
												variant="secondary"
												size="sm"
												className="text-xs h-8 justify-start"
											>
												<FileSymlink className="h-3 w-3 mr-2 text-muted-foreground" />{" "}
												Schematic
											</Button>
											<Button
												variant="secondary"
												size="sm"
												className="text-xs h-8 justify-start"
											>
												<PackagePlus className="h-3 w-3 mr-2 text-muted-foreground" />{" "}
												3D Model
											</Button>
											<Button
												variant="secondary"
												size="sm"
												className="text-xs h-8 justify-start"
											>
												<Download className="h-3 w-3 mr-2 text-muted-foreground" />{" "}
												Datasheet
											</Button>
										</div>
									</div>

									<div className="space-y-2">
										<div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground border-b pb-1">
											Compliance
										</div>
										<div className="flex gap-2">
											<Badge
												variant="outline"
												className="border-slate-600 bg-slate-800/50"
											>
												CE Certified
											</Badge>
											<Badge
												variant="outline"
												className="border-slate-600 bg-slate-800/50"
											>
												UL Listed
											</Badge>
											<Badge
												variant="outline"
												className="border-slate-600 bg-slate-800/50"
											>
												CSA
											</Badge>
										</div>
									</div>
								</div>
							</div>
						</ScrollArea>
					</div>
				)}
			</div>

			{/* Bottom Bar */}
			<div className="h-8 border-t bg-card flex items-center justify-between px-4 text-[10px] font-mono text-muted-foreground shrink-0">
				<div>
					Switchgear & Protection — 847 components | Showing 1-24 of 847
				</div>
				<div className="flex items-center gap-4">
					<div className="flex gap-2">
						<span className="text-primary font-bold">1</span>
						<span className="hover:text-foreground cursor-pointer">2</span>
						<span className="hover:text-foreground cursor-pointer">3</span>
						<span>...</span>
						<span className="hover:text-foreground cursor-pointer">36</span>
					</div>
				</div>
			</div>
		</div>
	);
}

function ToolBtn({  // NOSONAR - typescript:S6759
	icon,
	active = false,
}: {
	icon: React.ReactNode;
	active?: boolean;
}) {
	return (
		<div
			className={`w-8 h-8 flex items-center justify-center cursor-pointer [&>svg]:w-4 [&>svg]:h-4 ${active ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:bg-muted/80 hover:text-foreground"}`}
		>
			{icon}
		</div>
	);
}

function SpecRow({ label, value }: { label: string; value: string }) {  // NOSONAR - typescript:S6759
	return (
		<div className="flex justify-between items-center text-xs py-0.5">
			<span className="text-muted-foreground">{label}</span>
			<span className="text-foreground font-medium text-right max-w-[60%] truncate">
				{value}
			</span>
		</div>
	);
}

function AbstractSymbol({  // NOSONAR - typescript:S6759
	id,
	large = false,
}: {
	id: number;
	large?: boolean;
}) {
	const scale = large ? 1.5 : 1;

	return (
		<svg
			width={60 * scale}
			height={60 * scale}
			viewBox="0 0 60 60"
			className="stroke-slate-300"
			strokeWidth="2"
			fill="none"
			strokeLinecap="round"
			strokeLinejoin="round"
		>
			{id % 3 === 0 ? (
				// Relay symbol
				<>
					<circle cx="30" cy="30" r="16" />
					<path d="M14 30 L46 30 M30 14 L30 46" />
				</>
			) : id % 2 === 0 ? (  // NOSONAR — S3358: nested ternary acceptable in this localized context
				// Breaker symbol
				<>
					<path d="M30 10 L30 20 M30 40 L30 50" />
					<path d="M25 20 L35 20 M25 40 L35 40" />
					<path d="M25 25 L40 35" stroke="currentColor" />
				</>
			) : (
				// Contactor symbol
				<>
					<path d="M20 15 L20 45 M40 15 L40 45" />
					<path d="M10 30 L20 30 M40 30 L50 30" />
					<circle cx="30" cy="30" r="4" fill="currentColor" />
				</>
			)}
		</svg>
	);
}
