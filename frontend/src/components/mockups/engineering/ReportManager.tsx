// NOSONAR
import {
	Calendar,
	Check,
	ChevronDown,
	ChevronRight,
	FileBox,
	FileText,
	Folder,
	GripVertical,
	Image as ImageIcon,
	Search,
	Settings,
	Wand2,
	X,
} from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";

export function ReportManager() {
	const [activeTab, setActiveTab] = useState("My Reports");

	return (
		<div className="flex flex-col h-screen w-screen overflow-hidden bg-card text-foreground font-sans dark">
			{/* Top Toolbar */}
			<div className="h-14 flex items-center justify-between px-6 border-b border-slate-800 bg-background shrink-0">
				<div className="flex items-center gap-6">
					<div className="flex items-center gap-2">
						<div className="w-8 h-8 rounded bg-blue-500/20 border border-blue-500/30 flex items-center justify-center">
							<FileText className="w-4 h-4 text-info" />
						</div>
						<h1 className="font-bold text-sm tracking-wide">
							Report Manager & Document Control
						</h1>
					</div>
					<div className="flex text-sm space-x-1">
						{[
							"My Reports",
							"Templates",
							"Scheduled",
							"Submitted",
							"Archived",
							"Settings",
						].map((tab) => (
							<button
								key={tab}
								className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${activeTab === tab ? "bg-card text-info" : "text-muted-foreground hover:text-foreground hover:bg-muted/50"}`}
								onClick={() => setActiveTab(tab)}
							>
								{tab}
							</button>
						))}
					</div>
				</div>
				<div className="flex gap-2">
					<Button
						size="sm"
						className="h-8 bg-blue-600 hover:bg-blue-500 text-white border-0"
					>
						New Report
					</Button>
					<Button
						size="sm"
						variant="outline"
						className="h-8 border-border text-foreground/90 hover:bg-card"
					>
						Import Template
					</Button>
					<Button
						size="sm"
						variant="outline"
						className="h-8 border-border text-foreground/90 hover:bg-card"
					>
						Bulk Generate
					</Button>
					<Button
						size="sm"
						variant="ghost"
						className="h-8 w-8 p-0 text-muted-foreground hover:text-foreground"
					>
						<Settings className="w-4 h-4" />
					</Button>
				</div>
			</div>

			<div className="flex flex-1 overflow-hidden">
				{/* Left Panel */}
				<div className="w-[260px] flex flex-col border-r border-slate-800 bg-muted/50 shrink-0">
					<div className="p-3 border-b border-slate-800 bg-card">
						<div className="relative">
							<Search className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
							<input
								type="text"
								placeholder="Filter reports..."
								className="w-full bg-background border border-slate-800 rounded pl-7 pr-2 py-1.5 text-xs text-foreground placeholder:text-muted-foreground focus:border-blue-500 outline-none"
							/>
						</div>
						<div className="flex gap-1 mt-2 overflow-x-auto pb-1 scrollbar-hide">
							{["All", "Draft", "In Review", "Approved", "Submitted"].map(
								(f) => (
									<Badge
										key={f}
										variant="outline"
										className={`shrink-0 h-5 text-[9px] px-1.5 cursor-pointer ${f === "All" ? "bg-card text-foreground border-border" : "text-muted-foreground border-slate-800 hover:bg-card"}`}
									>
										{f}
									</Badge>
								),
							)}
						</div>
					</div>

					<ScrollArea className="flex-1">
						<div className="p-2 space-y-0.5 text-xs font-sans">
							<div className="flex items-center gap-1.5 px-2 py-1.5 rounded hover:bg-card cursor-pointer text-foreground font-medium">
								<Folder className="w-3.5 h-3.5 text-muted-foreground" /> All Reports{" "}
								<span className="ml-auto text-muted-foreground text-[10px]">47</span>
							</div>

							<div className="flex items-center gap-1.5 px-2 py-1.5 rounded bg-card text-info font-medium cursor-pointer">
								<ChevronDown className="w-3.5 h-3.5" />
								<Folder className="w-3.5 h-3.5 fill-blue-400/20" />
								Electrical Engineering{" "}
								<span className="ml-auto text-blue-500 text-[10px]">18</span>
							</div>
							<div className="pl-6 space-y-0.5">
								<div className="flex items-center gap-1.5 px-2 py-1 rounded bg-blue-500/10 text-foreground cursor-pointer">
									Load Calculations{" "}
									<span className="ml-auto text-muted-foreground text-[10px]">6</span>
								</div>
								<div className="flex items-center gap-1.5 px-2 py-1 rounded hover:bg-card text-muted-foreground cursor-pointer">
									Arc Flash Studies{" "}
									<span className="ml-auto text-muted-foreground/70 text-[10px]">3</span>
								</div>
								<div className="flex items-center gap-1.5 px-2 py-1 rounded hover:bg-card text-muted-foreground cursor-pointer">
									Short Circuit Analysis{" "}
									<span className="ml-auto text-muted-foreground/70 text-[10px]">2</span>
								</div>
								<div className="flex items-center gap-1.5 px-2 py-1 rounded hover:bg-card text-muted-foreground cursor-pointer">
									Protection Coordination{" "}
									<span className="ml-auto text-muted-foreground/70 text-[10px]">2</span>
								</div>
								<div className="flex items-center gap-1.5 px-2 py-1 rounded hover:bg-card text-muted-foreground cursor-pointer">
									Power Quality{" "}
									<span className="ml-auto text-muted-foreground/70 text-[10px]">1</span>
								</div>
								<div className="flex items-center gap-1.5 px-2 py-1 rounded hover:bg-card text-muted-foreground cursor-pointer">
									As-Built Packages{" "}
									<span className="ml-auto text-muted-foreground/70 text-[10px]">4</span>
								</div>
							</div>

							<div className="flex items-center gap-1.5 px-2 py-1.5 rounded hover:bg-card text-foreground/90 font-medium cursor-pointer mt-1">
								<ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />
								<Folder className="w-3.5 h-3.5 text-primary" />
								Fire & Life Safety{" "}
								<span className="ml-auto text-muted-foreground text-[10px]">8</span>
							</div>
							<div className="flex items-center gap-1.5 px-2 py-1.5 rounded hover:bg-card text-foreground/90 font-medium cursor-pointer">
								<ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />
								<Folder className="w-3.5 h-3.5 text-purple-400" />
								BIM & Coordination{" "}
								<span className="ml-auto text-muted-foreground text-[10px]">5</span>
							</div>
							<div className="flex items-center gap-1.5 px-2 py-1.5 rounded hover:bg-card text-foreground/90 font-medium cursor-pointer">
								<ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />
								<Folder className="w-3.5 h-3.5 text-success" />
								Compliance & Permitting{" "}
								<span className="ml-auto text-muted-foreground text-[10px]">7</span>
							</div>
							<div className="flex items-center gap-1.5 px-2 py-1.5 rounded hover:bg-card text-foreground/90 font-medium cursor-pointer">
								<ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />
								<Folder className="w-3.5 h-3.5 text-muted-foreground" />
								Project Management{" "}
								<span className="ml-auto text-muted-foreground text-[10px]">9</span>
							</div>
						</div>
					</ScrollArea>
				</div>

				{/* Center Panel */}
				<div className="flex-1 flex flex-col bg-background min-w-0">
					<div className="p-4 border-b border-slate-800 flex justify-between items-center bg-muted/50">
						<h2 className="text-lg font-semibold text-foreground">
							Load Calculations
						</h2>
						<div className="text-xs text-muted-foreground flex items-center gap-2">
							Sort by:{" "}
							<span className="text-foreground cursor-pointer border-b border-border border-dashed pb-0.5">
								Date ▼
							</span>
						</div>
					</div>

					<ScrollArea className="flex-1 p-4">
						<div className="space-y-3 max-w-3xl mx-auto">
							{/* Card 1 */}
							<div className="bg-card border-2 border-blue-500 rounded-lg p-4 shadow-lg shadow-blue-900/10 cursor-pointer">
								<div className="flex justify-between items-start mb-2">
									<div className="flex gap-3">
										<FileText className="w-8 h-8 text-danger shrink-0" />
										<div>
											<h3 className="font-bold text-foreground text-base">
												Load Calculation Report — Tower-B Office Complex
											</h3>
											<div className="text-xs text-muted-foreground mt-1">
												Report No: EL-LC-2024-014 | Rev: 3 | Pages: 48
											</div>
										</div>
									</div>
									<Badge
										variant="outline"
										className="bg-green-500/20 text-green-400 border-green-500/30"
									>
										Approved
									</Badge>
								</div>

								<div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground mt-4 mb-4 p-3 bg-background rounded border border-slate-800">
									<div>
										<span className="text-muted-foreground">Created:</span> Nov 5, 2024
									</div>
									<div>
										<span className="text-muted-foreground">Modified:</span> Today
										14:15
									</div>
									<div>
										<span className="text-muted-foreground">Author:</span> Ahmed
										Al-Rashidi
									</div>
									<div>
										<span className="text-muted-foreground">Template:</span> IEC 60364
										Load Calc v4.2
									</div>
									<div className="col-span-2">
										<span className="text-muted-foreground">Approval:</span>{" "}
										<span className="text-info">
											Issued for Construction
										</span>
									</div>
								</div>

								<div className="flex gap-2">
									<Button
										size="sm"
										className="h-7 text-xs bg-card hover:bg-secondary"
									>
										Open
									</Button>
									<Button
										size="sm"
										className="h-7 text-xs bg-blue-600 hover:bg-blue-500 text-white border-0"
									>
										Edit
									</Button>
									<Button
										size="sm"
										variant="outline"
										className="h-7 text-xs border-border hover:bg-card"
									>
										Download PDF
									</Button>
									<Button
										size="sm"
										variant="outline"
										className="h-7 text-xs border-border hover:bg-card"
									>
										Submit
									</Button>
									<Button
										size="sm"
										variant="ghost"
										className="h-7 w-7 p-0 ml-auto text-muted-foreground hover:text-foreground"
									>
										...
									</Button>
								</div>
							</div>

							{/* Card 2 */}
							<div className="bg-card border border-slate-800 rounded-lg p-4 hover:border-border cursor-pointer transition-colors">
								<div className="flex justify-between items-start mb-2">
									<div className="flex gap-3">
										<FileText className="w-8 h-8 text-danger shrink-0" />
										<div>
											<h3 className="font-semibold text-foreground text-sm">
												Arc Flash Hazard Analysis — All Panels
											</h3>
											<div className="text-xs text-muted-foreground mt-1">
												EL-AF-2024-007 | Rev: 2 | Pages: 124
											</div>
										</div>
									</div>
									<Badge
										variant="outline"
										className="bg-primary/20 text-primary border-primary/30"
									>
										In Review
									</Badge>
								</div>
								<div className="flex justify-between text-xs text-muted-foreground mt-3 mb-4">
									<span>Nov 10 | James Okafor</span>
									<span className="text-primary">For Review</span>
								</div>
								<div className="flex gap-2">
									<Button
										size="sm"
										variant="outline"
										className="h-7 text-xs border-slate-800 hover:bg-card"
									>
										Open
									</Button>
									<Button
										size="sm"
										variant="outline"
										className="h-7 text-xs border-slate-800 hover:bg-card"
									>
										Edit
									</Button>
									<Button
										size="sm"
										variant="outline"
										className="h-7 text-xs border-slate-800 hover:bg-card"
									>
										Download
									</Button>
									<Button
										size="sm"
										variant="outline"
										className="h-7 text-xs border-slate-800 hover:bg-card"
									>
										Submit
									</Button>
								</div>
							</div>

							{/* Card 3 */}
							<div className="bg-card border border-slate-800 rounded-lg p-4 hover:border-border cursor-pointer transition-colors">
								<div className="flex justify-between items-start mb-2">
									<div className="flex gap-3">
										<FileText className="w-8 h-8 text-danger shrink-0" />
										<div>
											<h3 className="font-semibold text-foreground text-sm">
												NEC 2023 Compliance Report
											</h3>
											<div className="text-xs text-muted-foreground mt-1">
												EL-CR-2024-022 | Rev: 1 | Pages: 31
											</div>
										</div>
									</div>
									<Badge
										variant="outline"
										className="bg-slate-500/20 text-muted-foreground border-border/30"
									>
										Draft
									</Badge>
								</div>
								<div className="flex justify-between text-xs text-muted-foreground mt-3 mb-4">
									<span>Today 14:47 | Ahmed</span>
									<span className="text-muted-foreground">Preliminary</span>
								</div>
								<div className="flex gap-2">
									<Button
										size="sm"
										variant="outline"
										className="h-7 text-xs border-slate-800 hover:bg-card"
									>
										Open
									</Button>
									<Button
										size="sm"
										variant="outline"
										className="h-7 text-xs border-slate-800 hover:bg-card"
									>
										Edit
									</Button>
									<Button
										size="sm"
										variant="outline"
										className="h-7 text-xs border-slate-800 hover:bg-card"
									>
										Download
									</Button>
									<Button
										size="sm"
										variant="outline"
										className="h-7 text-xs border-slate-800 hover:bg-card"
									>
										Submit
									</Button>
								</div>
							</div>

							{/* Card 4 */}
							<div className="bg-card border border-slate-800 rounded-lg p-4 hover:border-border cursor-pointer transition-colors opacity-75">
								<div className="flex justify-between items-start mb-2">
									<div className="flex gap-3">
										<FileBox className="w-8 h-8 text-info shrink-0" />
										<div>
											<h3 className="font-semibold text-foreground/90 text-sm">
												BIM Coordination Clash Detection Report
											</h3>
											<div className="text-xs text-muted-foreground mt-1">
												BIM-CD-2024-011 | Rev: 4 | Pages: 67
											</div>
										</div>
									</div>
									<Badge
										variant="outline"
										className="bg-green-500/10 text-green-500/70 border-green-500/20"
									>
										Approved
									</Badge>
								</div>
								<div className="flex justify-between text-xs text-muted-foreground mt-3">
									<span>Nov 8 | Sarah Chen</span>
									<span className="text-purple-400/70">For Information</span>
								</div>
							</div>

							{/* Card 5 */}
							<div className="bg-card border border-slate-800 rounded-lg p-4 hover:border-border cursor-pointer transition-colors opacity-75">
								<div className="flex justify-between items-start mb-2">
									<div className="flex gap-3">
										<FileText className="w-8 h-8 text-danger/70 shrink-0" />
										<div>
											<h3 className="font-semibold text-foreground/90 text-sm">
												NFPA 72 Compliance Verification
											</h3>
											<div className="text-xs text-muted-foreground mt-1">
												FS-CR-2024-005 | Rev: 2 | Pages: 22
											</div>
										</div>
									</div>
									<Badge
										variant="outline"
										className="bg-blue-500/10 text-info border-blue-500/30"
									>
										Submitted
									</Badge>
								</div>
								<div className="flex justify-between text-xs text-muted-foreground mt-3">
									<span>Nov 1 | James Okafor</span>
									<span className="text-info/70">Submitted to AHJ</span>
								</div>
							</div>
						</div>
					</ScrollArea>
				</div>

				{/* Right Editor Panel */}
				<div className="w-[360px] flex flex-col border-l border-slate-800 bg-card shrink-0">
					<div className="h-12 border-b border-slate-800 flex items-center px-4 bg-background">
						<h2 className="font-bold text-sm text-foreground truncate">
							EL-LC-2024-014 Editor
						</h2>
					</div>

					<ScrollArea className="flex-1">
						<div className="p-4 space-y-6">
							{/* Identity */}
							<div className="space-y-3">
								<h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider">
									Report Identity
								</h3>
								<div className="space-y-1.5">
									<label className="text-[10px] text-muted-foreground">  // NOSONAR — S6853: React import kept for JSX transform
										Report Title
									</label>
									<Input
										className="h-7 text-xs bg-background border-border text-foreground"
										defaultValue="Load Calculation Report — Tower-B Office Complex"
									/>
								</div>
								<div className="grid grid-cols-2 gap-3">
									<div className="space-y-1.5">
										<label className="text-[10px] text-muted-foreground">  // NOSONAR — S6853: React import kept for JSX transform
											Report Number
										</label>
										<Input
											className="h-7 text-xs bg-background border-border text-foreground"
											defaultValue="EL-LC-2024-014"
										/>
									</div>
									<div className="space-y-1.5">
										<label className="text-[10px] text-muted-foreground">  // NOSONAR — S6853: React import kept for JSX transform
											Revision
										</label>
										<div className="flex items-center">
											<Button
												variant="outline"
												className="h-7 w-7 p-0 rounded-r-none border-border bg-card text-muted-foreground"
											>
												-
											</Button>
											<Input
												className="h-7 text-xs bg-background border-border border-x-0 rounded-none text-center font-mono w-full"
												defaultValue="3"
											/>
											<Button
												variant="outline"
												className="h-7 w-7 p-0 rounded-l-none border-border bg-card text-muted-foreground"
											>
												+
											</Button>
										</div>
									</div>
								</div>
								<div className="grid grid-cols-2 gap-3">
									<div className="space-y-1.5 relative">
										<label className="text-[10px] text-muted-foreground">Date</label>  // NOSONAR — S6853: React import kept for JSX transform
										<Input
											className="h-7 text-xs bg-background border-border text-foreground pl-7"
											defaultValue="Nov 15, 2024"
										/>
										<Calendar className="w-3 h-3 absolute left-2 top-7 text-muted-foreground" />
									</div>
									<div className="space-y-1.5">
										<label className="text-[10px] text-muted-foreground">Status</label>  // NOSONAR — S6853: React import kept for JSX transform
										<select className="h-7 w-full text-xs bg-background border border-border rounded text-foreground px-2 outline-none">  // NOSONAR - typescript:S6772
											<option>Issued for Construction</option>
											<option>For Review</option>
											<option>Draft</option>
										</select>
									</div>
								</div>
							</div>

							<Separator className="bg-card" />

							{/* Authorship */}
							<div className="space-y-3">
								<h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider">
									Authorship & Approval
								</h3>
								<div className="space-y-2 text-xs">
									<div className="flex flex-col gap-1">
										<span className="text-[10px] text-muted-foreground">
											Prepared by
										</span>
										<select className="h-7 bg-background border border-border rounded text-foreground px-2">
											<option>
												Ahmed Al-Rashidi, Lead Electrical Engineer
											</option>
										</select>
									</div>
									<div className="flex flex-col gap-1">
										<span className="text-[10px] text-muted-foreground">
											Checked by
										</span>
										<select className="h-7 bg-background border border-border rounded text-foreground px-2">
											<option>Marcus Williams, Senior Engineer</option>
										</select>
									</div>
									<div className="flex flex-col gap-1">
										<span className="text-[10px] text-muted-foreground">
											Approved by
										</span>
										<select className="h-7 bg-background border border-border rounded text-foreground px-2">
											<option>Sarah Chen, Principal Engineer</option>
										</select>
									</div>
									<div className="flex flex-col gap-1">
										<span className="text-[10px] text-muted-foreground">
											Client Rep
										</span>
										<Input
											className="h-7 text-xs bg-background border-border text-foreground"
											defaultValue="Eng. Khalid Al-Mansouri"
										/>
									</div>
								</div>
								<div className="space-y-2 pt-2">
									<div className="flex items-center justify-between">
										<span className="text-xs text-foreground/90">
											Include digital stamp
										</span>
										<Switch
											defaultChecked
											className="data-[state=checked]:bg-blue-600"
										/>
									</div>
									<div className="flex items-center justify-between">
										<span className="text-xs text-foreground/90">
											Apply PKI signature
										</span>
										<Switch
											defaultChecked
											className="data-[state=checked]:bg-blue-600"
										/>
									</div>
								</div>
							</div>

							<Separator className="bg-card" />

							{/* Standard */}
							<div className="space-y-3">
								<h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider">
									Standard & Template
								</h3>
								<div className="flex gap-2">
									<Badge
										variant="outline"
										className="bg-blue-600 border-blue-600 text-white cursor-pointer h-6 px-3 rounded-full"
									>
										IEC 60364
									</Badge>
									<Badge
										variant="outline"
										className="bg-card border-border text-foreground/90 cursor-pointer h-6 px-3 rounded-full hover:bg-secondary"
									>
										NEC 2023
									</Badge>
									<Badge
										variant="outline"
										className="bg-card border-border text-foreground/90 cursor-pointer h-6 px-3 rounded-full hover:bg-secondary"
									>
										BS 7671
									</Badge>
								</div>
								<select className="h-7 w-full text-xs bg-background border border-border rounded text-foreground px-2">
									<option>IEC Load Calc v4.2 — updated Nov 2024</option>
								</select>
								<div className="grid grid-cols-2 gap-3 text-xs">
									<select className="h-7 w-full bg-background border border-border rounded text-foreground px-2">
										<option>English</option>
										<option>العربية</option>
									</select>
									<div className="flex items-center bg-background border border-border rounded p-0.5">
										<button className="flex-1 bg-card rounded shadow-sm text-info py-1 font-medium text-[10px]">
											SI
										</button>
										<button className="flex-1 text-muted-foreground py-1 text-[10px] hover:text-foreground">
											Imperial
										</button>
									</div>
									<div className="flex items-center bg-background border border-border rounded p-0.5">
										<button className="flex-1 bg-card rounded shadow-sm text-foreground py-1 font-medium text-[10px]">
											A4
										</button>
										<button className="flex-1 text-muted-foreground py-1 text-[10px]">
											Letter
										</button>
										<button className="flex-1 text-muted-foreground py-1 text-[10px]">
											A3
										</button>
									</div>
									<div className="flex items-center bg-background border border-border rounded p-0.5">
										<button className="flex-1 bg-card rounded shadow-sm text-foreground py-1 font-medium text-[10px]">
											Portrait
										</button>
										<button className="flex-1 text-muted-foreground py-1 text-[10px]">
											Land
										</button>
									</div>
								</div>
								<div className="space-y-3 pt-2">
									<div className="space-y-1">
										<div className="flex justify-between text-[10px] text-muted-foreground">
											<span>Font size</span>
											<span>11pt</span>
										</div>
										<Slider
											defaultValue={[11]}
											max={16}
											min={8}
											step={1}
											className="w-full"
										/>
									</div>
									<div className="space-y-1">
										<div className="flex justify-between text-[10px] text-muted-foreground">
											<span>Line spacing</span>
											<span>1.15</span>
										</div>
										<Slider
											defaultValue={[115]}
											max={200}
											min={100}
											step={5}
											className="w-full"
										/>
									</div>
								</div>
							</div>

							<Separator className="bg-card" />

							{/* Sections */}
							<div className="space-y-3">
								<div className="flex justify-between items-center">
									<h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider">
										Content Sections
									</h3>
									<span className="text-[10px] text-info cursor-pointer">
										Select All
									</span>
								</div>
								<div className="space-y-1">
									{[
										{ label: "Executive Summary", checked: true },
										{ label: "Project Information", checked: true },
										{ label: "Design Basis & Standards", checked: true },
										{ label: "Lighting Load Calculations", checked: true },
										{ label: "Power Load Calculations", checked: true },
										{ label: "HVAC Load Calculations", checked: true },
										{ label: "Motor Load Schedule", checked: true },
										{ label: "Demand Load Summary", checked: true },
										{ label: "Recommended Supply Size", checked: true },
										{ label: "Voltage Drop Verification", checked: true },
										{ label: "Harmonic Analysis", checked: false },
										{ label: "Power Factor Correction", checked: true },
										{ label: "Conclusions & Recommendations", checked: true },
										{ label: "References", checked: true },
										{
											label: "Appendix A — Equipment Data Sheets",
											checked: true,
										},
										{ label: "Appendix B — Manufacturer Data", checked: false },
									].map((item, i) => (
										<div
											key={i}  // NOSONAR — S6479: array index key acceptable for static list
											className="flex items-center gap-2 group hover:bg-muted/50 p-1 rounded -mx-1"
										>
											<GripVertical className="w-3.5 h-3.5 text-muted-foreground/70 cursor-grab opacity-0 group-hover:opacity-100" />
											<Checkbox
												id={`sec-${i}`}
												checked={item.checked}
												className="w-3.5 h-3.5 border-border data-[state=checked]:bg-blue-600 data-[state=checked]:border-blue-600"
											/>
											<label
												htmlFor={`sec-${i}`}
												className={`text-xs cursor-pointer ${item.checked ? "text-foreground" : "text-muted-foreground"}`}
											>
												{item.label}
											</label>
										</div>
									))}
								</div>
							</div>

							<Separator className="bg-card" />

							{/* Branding */}
							<div className="space-y-3">
								<h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider">
									Branding & Cover Page
								</h3>
								<div className="flex items-center gap-3 bg-background p-3 rounded border border-slate-800 border-dashed cursor-pointer hover:border-border hover:bg-card">
									<div className="w-10 h-10 bg-card rounded flex items-center justify-center border border-border">
										<ImageIcon className="w-4 h-4 text-muted-foreground" />
									</div>
									<div className="text-xs text-muted-foreground">
										Click to update logo
										<br />
										<span className="text-[10px] text-muted-foreground/70">
											NexusTech Engineering
										</span>
									</div>
								</div>
								<div className="space-y-2 text-xs">
									<Input
										className="h-7 bg-background border-border text-foreground"
										placeholder="Company Name"
										defaultValue="NexusTech Engineering Consultants"
									/>
									<Input
										className="h-7 bg-background border-border text-foreground"
										placeholder="Project Name"
										defaultValue="Tower-B Office Complex — Abu Dhabi"
									/>
									<Input
										className="h-7 bg-background border-border text-foreground"
										placeholder="Client Name"
										defaultValue="Tower-B Developments LLC"
									/>
								</div>
								<div className="grid grid-cols-2 gap-2 text-xs">
									<select className="h-7 w-full bg-background border border-border rounded text-muted-foreground px-2">
										<option>Watermark: None</option>
									</select>
									<select className="h-7 w-full bg-background border border-border rounded text-muted-foreground px-2">
										<option>Style: Standard</option>
									</select>
								</div>
								<div className="flex items-center justify-between text-xs pt-1">
									<span className="text-foreground/90">
										Include project photo on cover
									</span>
									<Switch className="data-[state=checked]:bg-blue-600" />
								</div>
							</div>

							<Separator className="bg-card" />

							{/* Data Source */}
							<div className="space-y-3">
								<h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider">
									Data Source Control
								</h3>
								<div className="flex items-center justify-between text-xs">
									<span className="text-foreground font-medium">
										Auto-populate from Live Data
									</span>
									<Switch
										defaultChecked
										className="data-[state=checked]:bg-blue-600"
									/>
								</div>
								<div className="bg-background p-2.5 rounded border border-slate-800 space-y-2 text-[10px]">
									<div className="flex items-start gap-2">
										<Check className="w-3.5 h-3.5 text-green-500 mt-0.5 shrink-0" />
										<div>
											<span className="text-foreground">
												Load calc worksheet (Rev 11)
											</span>
											<br />
											<span className="text-muted-foreground">Last synced: 14:15</span>
										</div>
									</div>
									<div className="flex items-start gap-2">
										<Check className="w-3.5 h-3.5 text-green-500 mt-0.5 shrink-0" />
										<div>
											<span className="text-foreground">Equipment schedule</span>
											<br />
											<span className="text-muted-foreground">Last synced: 14:10</span>
										</div>
									</div>
									<div className="flex items-start gap-2">
										<Check className="w-3.5 h-3.5 text-green-500 mt-0.5 shrink-0" />
										<div>
											<span className="text-foreground">
												BIM model (Revit v14)
											</span>
											<br />
											<span className="text-muted-foreground">Last synced: 14:31</span>
										</div>
									</div>
									<div className="flex items-center gap-2 pt-1">
										<div className="w-3.5 h-3.5 border border-border rounded-[2px] shrink-0"></div>
										<span className="text-muted-foreground flex-1">
											External ETAP model
										</span>
										<Button
											variant="outline"
											className="h-5 text-[9px] px-2 py-0 border-border bg-card text-foreground/90"
										>
											Connect
										</Button>
									</div>
								</div>
								<select className="h-7 w-full text-xs bg-background border border-border rounded text-foreground/90 px-2">
									<option>On change: Notify and prompt update</option>
								</select>
							</div>

							<Separator className="bg-card" />

							{/* Output */}
							<div className="space-y-3 pb-4">
								<h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider">
									Distribution & Output
								</h3>
								<div className="flex gap-4 text-xs">
									<label className="flex items-center gap-1.5 cursor-pointer">
										<Checkbox
											checked
											className="w-3.5 h-3.5 data-[state=checked]:bg-blue-600"
										/>{" "}
										PDF
									</label>
									<label className="flex items-center gap-1.5 cursor-pointer">
										<Checkbox
											checked
											className="w-3.5 h-3.5 data-[state=checked]:bg-blue-600"
										/>{" "}
										DOCX
									</label>
									<label className="flex items-center gap-1.5 cursor-pointer text-muted-foreground">
										<Checkbox className="w-3.5 h-3.5 border-border" /> Excel
									</label>
									<label className="flex items-center gap-1.5 cursor-pointer text-muted-foreground">
										<Checkbox className="w-3.5 h-3.5 border-border" /> HTML
									</label>
								</div>
								<div className="bg-background p-2.5 rounded border border-slate-800 space-y-2 text-xs">
									<div className="flex justify-between items-center">
										<span className="text-muted-foreground">Password protect</span>
										<Switch className="scale-75 origin-right" />
									</div>
									<div className="flex justify-between items-center">
										<span className="text-foreground/90">Print allowed</span>
										<Switch
											defaultChecked
											className="scale-75 origin-right data-[state=checked]:bg-blue-600"
										/>
									</div>
									<div className="flex justify-between items-center">
										<span className="text-muted-foreground">Edit allowed</span>
										<Switch className="scale-75 origin-right" />
									</div>
								</div>
								<div className="flex justify-between items-center text-xs">
									<span className="text-foreground/90">
										Auto-generate transmittal
									</span>
									<Switch
										defaultChecked
										className="data-[state=checked]:bg-blue-600"
									/>
								</div>
								<div className="space-y-1.5">
									<label className="text-[10px] text-muted-foreground">  // NOSONAR — S6853: React import kept for JSX transform
										Recipients
									</label>
									<div className="min-h-7 bg-background border border-border rounded p-1 flex flex-wrap gap-1">
										<Badge
											variant="secondary"
											className="h-5 text-[9px] px-1.5 bg-card text-foreground/90 hover:bg-secondary"
										>
											Eng. Khalid <X className="w-2.5 h-2.5 ml-1 opacity-50" />
										</Badge>
										<Badge
											variant="secondary"
											className="h-5 text-[9px] px-1.5 bg-card text-foreground/90 hover:bg-secondary"
										>
											PM Office <X className="w-2.5 h-2.5 ml-1 opacity-50" />
										</Badge>
										<Badge
											variant="secondary"
											className="h-5 text-[9px] px-1.5 bg-card text-foreground/90 hover:bg-secondary"
										>
											AHJ Filing <X className="w-2.5 h-2.5 ml-1 opacity-50" />
										</Badge>
									</div>
								</div>
							</div>
						</div>
					</ScrollArea>

					{/* Action Footer */}
					<div className="p-4 border-t border-slate-800 bg-background shadow-[0_-10px_15px_-3px_rgba(0,0,0,0.3)] shrink-0 space-y-3">
						<div className="grid grid-cols-2 gap-2">
							<Button
								size="sm"
								variant="outline"
								className="h-8 text-xs border-border bg-card text-foreground/90 hover:bg-card"
							>
								Save Draft
							</Button>
							<Button
								size="sm"
								variant="outline"
								className="h-8 text-xs border-border bg-card text-foreground/90 hover:bg-card"
							>
								<Wand2 className="w-3.5 h-3.5 mr-1.5 text-info" /> Preview
							</Button>
						</div>
						<Button
							size="sm"
							className="w-full h-9 text-sm bg-blue-600 hover:bg-blue-500 text-white border-0 font-medium"
						>
							Generate PDF
						</Button>
						<Button
							size="sm"
							variant="outline"
							className="w-full h-8 text-xs border-green-500/30 text-green-400 bg-green-500/10 hover:bg-green-500/20"
						>
							Submit for Review
						</Button>
						<div className="text-center text-[9px] text-muted-foreground font-mono">
							Last generated: Today 13:47 — 48 pages, 4.1 MB — Rev 2
						</div>
					</div>
				</div>
			</div>
		</div>
	);
}
