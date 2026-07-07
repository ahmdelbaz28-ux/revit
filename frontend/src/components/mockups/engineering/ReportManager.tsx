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
		<div className="flex flex-col h-screen w-screen overflow-hidden bg-slate-900 text-slate-100 font-sans dark">
			{/* Top Toolbar */}
			<div className="h-14 flex items-center justify-between px-6 border-b border-slate-800 bg-slate-950 shrink-0">
				<div className="flex items-center gap-6">
					<div className="flex items-center gap-2">
						<div className="w-8 h-8 rounded bg-blue-500/20 border border-blue-500/30 flex items-center justify-center">
							<FileText className="w-4 h-4 text-blue-400" />
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
								className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${activeTab === tab ? "bg-slate-800 text-blue-400" : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"}`}
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
						className="h-8 border-slate-700 text-slate-300 hover:bg-slate-800"
					>
						Import Template
					</Button>
					<Button
						size="sm"
						variant="outline"
						className="h-8 border-slate-700 text-slate-300 hover:bg-slate-800"
					>
						Bulk Generate
					</Button>
					<Button
						size="sm"
						variant="ghost"
						className="h-8 w-8 p-0 text-slate-400 hover:text-slate-200"
					>
						<Settings className="w-4 h-4" />
					</Button>
				</div>
			</div>

			<div className="flex flex-1 overflow-hidden">
				{/* Left Panel */}
				<div className="w-[260px] flex flex-col border-r border-slate-800 bg-slate-900/50 shrink-0">
					<div className="p-3 border-b border-slate-800 bg-slate-900">
						<div className="relative">
							<Search className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-slate-500" />
							<input
								type="text"
								placeholder="Filter reports..."
								className="w-full bg-slate-950 border border-slate-800 rounded pl-7 pr-2 py-1.5 text-xs text-slate-200 placeholder:text-slate-500 focus:border-blue-500 outline-none"
							/>
						</div>
						<div className="flex gap-1 mt-2 overflow-x-auto pb-1 scrollbar-hide">
							{["All", "Draft", "In Review", "Approved", "Submitted"].map(
								(f) => (
									<Badge
										key={f}
										variant="outline"
										className={`shrink-0 h-5 text-[9px] px-1.5 cursor-pointer ${f === "All" ? "bg-slate-800 text-slate-200 border-slate-700" : "text-slate-400 border-slate-800 hover:bg-slate-800"}`}
									>
										{f}
									</Badge>
								),
							)}
						</div>
					</div>

					<ScrollArea className="flex-1">
						<div className="p-2 space-y-0.5 text-xs font-sans">
							<div className="flex items-center gap-1.5 px-2 py-1.5 rounded hover:bg-slate-800 cursor-pointer text-slate-200 font-medium">
								<Folder className="w-3.5 h-3.5 text-slate-400" /> All Reports{" "}
								<span className="ml-auto text-slate-500 text-[10px]">47</span>
							</div>

							<div className="flex items-center gap-1.5 px-2 py-1.5 rounded bg-slate-800 text-blue-400 font-medium cursor-pointer">
								<ChevronDown className="w-3.5 h-3.5" />
								<Folder className="w-3.5 h-3.5 fill-blue-400/20" />
								Electrical Engineering{" "}
								<span className="ml-auto text-blue-500 text-[10px]">18</span>
							</div>
							<div className="pl-6 space-y-0.5">
								<div className="flex items-center gap-1.5 px-2 py-1 rounded bg-blue-500/10 text-slate-200 cursor-pointer">
									Load Calculations{" "}
									<span className="ml-auto text-slate-500 text-[10px]">6</span>
								</div>
								<div className="flex items-center gap-1.5 px-2 py-1 rounded hover:bg-slate-800 text-slate-400 cursor-pointer">
									Arc Flash Studies{" "}
									<span className="ml-auto text-slate-600 text-[10px]">3</span>
								</div>
								<div className="flex items-center gap-1.5 px-2 py-1 rounded hover:bg-slate-800 text-slate-400 cursor-pointer">
									Short Circuit Analysis{" "}
									<span className="ml-auto text-slate-600 text-[10px]">2</span>
								</div>
								<div className="flex items-center gap-1.5 px-2 py-1 rounded hover:bg-slate-800 text-slate-400 cursor-pointer">
									Protection Coordination{" "}
									<span className="ml-auto text-slate-600 text-[10px]">2</span>
								</div>
								<div className="flex items-center gap-1.5 px-2 py-1 rounded hover:bg-slate-800 text-slate-400 cursor-pointer">
									Power Quality{" "}
									<span className="ml-auto text-slate-600 text-[10px]">1</span>
								</div>
								<div className="flex items-center gap-1.5 px-2 py-1 rounded hover:bg-slate-800 text-slate-400 cursor-pointer">
									As-Built Packages{" "}
									<span className="ml-auto text-slate-600 text-[10px]">4</span>
								</div>
							</div>

							<div className="flex items-center gap-1.5 px-2 py-1.5 rounded hover:bg-slate-800 text-slate-300 font-medium cursor-pointer mt-1">
								<ChevronRight className="w-3.5 h-3.5 text-slate-500" />
								<Folder className="w-3.5 h-3.5 text-orange-400" />
								Fire & Life Safety{" "}
								<span className="ml-auto text-slate-500 text-[10px]">8</span>
							</div>
							<div className="flex items-center gap-1.5 px-2 py-1.5 rounded hover:bg-slate-800 text-slate-300 font-medium cursor-pointer">
								<ChevronRight className="w-3.5 h-3.5 text-slate-500" />
								<Folder className="w-3.5 h-3.5 text-purple-400" />
								BIM & Coordination{" "}
								<span className="ml-auto text-slate-500 text-[10px]">5</span>
							</div>
							<div className="flex items-center gap-1.5 px-2 py-1.5 rounded hover:bg-slate-800 text-slate-300 font-medium cursor-pointer">
								<ChevronRight className="w-3.5 h-3.5 text-slate-500" />
								<Folder className="w-3.5 h-3.5 text-emerald-400" />
								Compliance & Permitting{" "}
								<span className="ml-auto text-slate-500 text-[10px]">7</span>
							</div>
							<div className="flex items-center gap-1.5 px-2 py-1.5 rounded hover:bg-slate-800 text-slate-300 font-medium cursor-pointer">
								<ChevronRight className="w-3.5 h-3.5 text-slate-500" />
								<Folder className="w-3.5 h-3.5 text-slate-400" />
								Project Management{" "}
								<span className="ml-auto text-slate-500 text-[10px]">9</span>
							</div>
						</div>
					</ScrollArea>
				</div>

				{/* Center Panel */}
				<div className="flex-1 flex flex-col bg-slate-950 min-w-0">
					<div className="p-4 border-b border-slate-800 flex justify-between items-center bg-slate-900/50">
						<h2 className="text-lg font-semibold text-slate-200">
							Load Calculations
						</h2>
						<div className="text-xs text-slate-400 flex items-center gap-2">
							Sort by:{" "}
							<span className="text-slate-200 cursor-pointer border-b border-slate-700 border-dashed pb-0.5">
								Date ▼
							</span>
						</div>
					</div>

					<ScrollArea className="flex-1 p-4">
						<div className="space-y-3 max-w-3xl mx-auto">
							{/* Card 1 */}
							<div className="bg-slate-900 border-2 border-blue-500 rounded-lg p-4 shadow-lg shadow-blue-900/10 cursor-pointer">
								<div className="flex justify-between items-start mb-2">
									<div className="flex gap-3">
										<FileText className="w-8 h-8 text-red-400 shrink-0" />
										<div>
											<h3 className="font-bold text-slate-100 text-base">
												Load Calculation Report — Tower-B Office Complex
											</h3>
											<div className="text-xs text-slate-400 mt-1">
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

								<div className="grid grid-cols-2 gap-2 text-xs text-slate-400 mt-4 mb-4 p-3 bg-slate-950 rounded border border-slate-800">
									<div>
										<span className="text-slate-500">Created:</span> Nov 5, 2024
									</div>
									<div>
										<span className="text-slate-500">Modified:</span> Today
										14:15
									</div>
									<div>
										<span className="text-slate-500">Author:</span> Ahmed
										Al-Rashidi
									</div>
									<div>
										<span className="text-slate-500">Template:</span> IEC 60364
										Load Calc v4.2
									</div>
									<div className="col-span-2">
										<span className="text-slate-500">Approval:</span>{" "}
										<span className="text-blue-400">
											Issued for Construction
										</span>
									</div>
								</div>

								<div className="flex gap-2">
									<Button
										size="sm"
										className="h-7 text-xs bg-slate-800 hover:bg-slate-700"
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
										className="h-7 text-xs border-slate-700 hover:bg-slate-800"
									>
										Download PDF
									</Button>
									<Button
										size="sm"
										variant="outline"
										className="h-7 text-xs border-slate-700 hover:bg-slate-800"
									>
										Submit
									</Button>
									<Button
										size="sm"
										variant="ghost"
										className="h-7 w-7 p-0 ml-auto text-slate-400 hover:text-slate-200"
									>
										...
									</Button>
								</div>
							</div>

							{/* Card 2 */}
							<div className="bg-slate-900 border border-slate-800 rounded-lg p-4 hover:border-slate-700 cursor-pointer transition-colors">
								<div className="flex justify-between items-start mb-2">
									<div className="flex gap-3">
										<FileText className="w-8 h-8 text-red-400 shrink-0" />
										<div>
											<h3 className="font-semibold text-slate-200 text-sm">
												Arc Flash Hazard Analysis — All Panels
											</h3>
											<div className="text-xs text-slate-400 mt-1">
												EL-AF-2024-007 | Rev: 2 | Pages: 124
											</div>
										</div>
									</div>
									<Badge
										variant="outline"
										className="bg-orange-500/20 text-orange-400 border-orange-500/30"
									>
										In Review
									</Badge>
								</div>
								<div className="flex justify-between text-xs text-slate-500 mt-3 mb-4">
									<span>Nov 10 | James Okafor</span>
									<span className="text-orange-400">For Review</span>
								</div>
								<div className="flex gap-2">
									<Button
										size="sm"
										variant="outline"
										className="h-7 text-xs border-slate-800 hover:bg-slate-800"
									>
										Open
									</Button>
									<Button
										size="sm"
										variant="outline"
										className="h-7 text-xs border-slate-800 hover:bg-slate-800"
									>
										Edit
									</Button>
									<Button
										size="sm"
										variant="outline"
										className="h-7 text-xs border-slate-800 hover:bg-slate-800"
									>
										Download
									</Button>
									<Button
										size="sm"
										variant="outline"
										className="h-7 text-xs border-slate-800 hover:bg-slate-800"
									>
										Submit
									</Button>
								</div>
							</div>

							{/* Card 3 */}
							<div className="bg-slate-900 border border-slate-800 rounded-lg p-4 hover:border-slate-700 cursor-pointer transition-colors">
								<div className="flex justify-between items-start mb-2">
									<div className="flex gap-3">
										<FileText className="w-8 h-8 text-red-400 shrink-0" />
										<div>
											<h3 className="font-semibold text-slate-200 text-sm">
												NEC 2023 Compliance Report
											</h3>
											<div className="text-xs text-slate-400 mt-1">
												EL-CR-2024-022 | Rev: 1 | Pages: 31
											</div>
										</div>
									</div>
									<Badge
										variant="outline"
										className="bg-slate-500/20 text-slate-400 border-slate-500/30"
									>
										Draft
									</Badge>
								</div>
								<div className="flex justify-between text-xs text-slate-500 mt-3 mb-4">
									<span>Today 14:47 | Ahmed</span>
									<span className="text-slate-400">Preliminary</span>
								</div>
								<div className="flex gap-2">
									<Button
										size="sm"
										variant="outline"
										className="h-7 text-xs border-slate-800 hover:bg-slate-800"
									>
										Open
									</Button>
									<Button
										size="sm"
										variant="outline"
										className="h-7 text-xs border-slate-800 hover:bg-slate-800"
									>
										Edit
									</Button>
									<Button
										size="sm"
										variant="outline"
										className="h-7 text-xs border-slate-800 hover:bg-slate-800"
									>
										Download
									</Button>
									<Button
										size="sm"
										variant="outline"
										className="h-7 text-xs border-slate-800 hover:bg-slate-800"
									>
										Submit
									</Button>
								</div>
							</div>

							{/* Card 4 */}
							<div className="bg-slate-900 border border-slate-800 rounded-lg p-4 hover:border-slate-700 cursor-pointer transition-colors opacity-75">
								<div className="flex justify-between items-start mb-2">
									<div className="flex gap-3">
										<FileBox className="w-8 h-8 text-blue-400 shrink-0" />
										<div>
											<h3 className="font-semibold text-slate-300 text-sm">
												BIM Coordination Clash Detection Report
											</h3>
											<div className="text-xs text-slate-500 mt-1">
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
								<div className="flex justify-between text-xs text-slate-500 mt-3">
									<span>Nov 8 | Sarah Chen</span>
									<span className="text-purple-400/70">For Information</span>
								</div>
							</div>

							{/* Card 5 */}
							<div className="bg-slate-900 border border-slate-800 rounded-lg p-4 hover:border-slate-700 cursor-pointer transition-colors opacity-75">
								<div className="flex justify-between items-start mb-2">
									<div className="flex gap-3">
										<FileText className="w-8 h-8 text-red-400/70 shrink-0" />
										<div>
											<h3 className="font-semibold text-slate-300 text-sm">
												NFPA 72 Compliance Verification
											</h3>
											<div className="text-xs text-slate-500 mt-1">
												FS-CR-2024-005 | Rev: 2 | Pages: 22
											</div>
										</div>
									</div>
									<Badge
										variant="outline"
										className="bg-blue-500/10 text-blue-400 border-blue-500/30"
									>
										Submitted
									</Badge>
								</div>
								<div className="flex justify-between text-xs text-slate-500 mt-3">
									<span>Nov 1 | James Okafor</span>
									<span className="text-blue-400/70">Submitted to AHJ</span>
								</div>
							</div>
						</div>
					</ScrollArea>
				</div>

				{/* Right Editor Panel */}
				<div className="w-[360px] flex flex-col border-l border-slate-800 bg-slate-900 shrink-0">
					<div className="h-12 border-b border-slate-800 flex items-center px-4 bg-slate-950">
						<h2 className="font-bold text-sm text-slate-200 truncate">
							EL-LC-2024-014 Editor
						</h2>
					</div>

					<ScrollArea className="flex-1">
						<div className="p-4 space-y-6">
							{/* Identity */}
							<div className="space-y-3">
								<h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider">
									Report Identity
								</h3>
								<div className="space-y-1.5">
									<label className="text-[10px] text-slate-400">  // NOSONAR — S6853: React import kept for JSX transform
										Report Title
									</label>
									<Input
										className="h-7 text-xs bg-slate-950 border-slate-700 text-slate-200"
										defaultValue="Load Calculation Report — Tower-B Office Complex"
									/>
								</div>
								<div className="grid grid-cols-2 gap-3">
									<div className="space-y-1.5">
										<label className="text-[10px] text-slate-400">  // NOSONAR — S6853: React import kept for JSX transform
											Report Number
										</label>
										<Input
											className="h-7 text-xs bg-slate-950 border-slate-700 text-slate-200"
											defaultValue="EL-LC-2024-014"
										/>
									</div>
									<div className="space-y-1.5">
										<label className="text-[10px] text-slate-400">  // NOSONAR — S6853: React import kept for JSX transform
											Revision
										</label>
										<div className="flex items-center">
											<Button
												variant="outline"
												className="h-7 w-7 p-0 rounded-r-none border-slate-700 bg-slate-800 text-slate-400"
											>
												-
											</Button>
											<Input
												className="h-7 text-xs bg-slate-950 border-slate-700 border-x-0 rounded-none text-center font-mono w-full"
												defaultValue="3"
											/>
											<Button
												variant="outline"
												className="h-7 w-7 p-0 rounded-l-none border-slate-700 bg-slate-800 text-slate-400"
											>
												+
											</Button>
										</div>
									</div>
								</div>
								<div className="grid grid-cols-2 gap-3">
									<div className="space-y-1.5 relative">
										<label className="text-[10px] text-slate-400">Date</label>  // NOSONAR — S6853: React import kept for JSX transform
										<Input
											className="h-7 text-xs bg-slate-950 border-slate-700 text-slate-200 pl-7"
											defaultValue="Nov 15, 2024"
										/>
										<Calendar className="w-3 h-3 absolute left-2 top-7 text-slate-500" />
									</div>
									<div className="space-y-1.5">
										<label className="text-[10px] text-slate-400">Status</label>  // NOSONAR — S6853: React import kept for JSX transform
										<select className="h-7 w-full text-xs bg-slate-950 border border-slate-700 rounded text-slate-200 px-2 outline-none">  // NOSONAR - typescript:S6772
											<option>Issued for Construction</option>
											<option>For Review</option>
											<option>Draft</option>
										</select>
									</div>
								</div>
							</div>

							<Separator className="bg-slate-800" />

							{/* Authorship */}
							<div className="space-y-3">
								<h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider">
									Authorship & Approval
								</h3>
								<div className="space-y-2 text-xs">
									<div className="flex flex-col gap-1">
										<span className="text-[10px] text-slate-400">
											Prepared by
										</span>
										<select className="h-7 bg-slate-950 border border-slate-700 rounded text-slate-200 px-2">
											<option>
												Ahmed Al-Rashidi, Lead Electrical Engineer
											</option>
										</select>
									</div>
									<div className="flex flex-col gap-1">
										<span className="text-[10px] text-slate-400">
											Checked by
										</span>
										<select className="h-7 bg-slate-950 border border-slate-700 rounded text-slate-200 px-2">
											<option>Marcus Williams, Senior Engineer</option>
										</select>
									</div>
									<div className="flex flex-col gap-1">
										<span className="text-[10px] text-slate-400">
											Approved by
										</span>
										<select className="h-7 bg-slate-950 border border-slate-700 rounded text-slate-200 px-2">
											<option>Sarah Chen, Principal Engineer</option>
										</select>
									</div>
									<div className="flex flex-col gap-1">
										<span className="text-[10px] text-slate-400">
											Client Rep
										</span>
										<Input
											className="h-7 text-xs bg-slate-950 border-slate-700 text-slate-200"
											defaultValue="Eng. Khalid Al-Mansouri"
										/>
									</div>
								</div>
								<div className="space-y-2 pt-2">
									<div className="flex items-center justify-between">
										<span className="text-xs text-slate-300">
											Include digital stamp
										</span>
										<Switch
											defaultChecked
											className="data-[state=checked]:bg-blue-600"
										/>
									</div>
									<div className="flex items-center justify-between">
										<span className="text-xs text-slate-300">
											Apply PKI signature
										</span>
										<Switch
											defaultChecked
											className="data-[state=checked]:bg-blue-600"
										/>
									</div>
								</div>
							</div>

							<Separator className="bg-slate-800" />

							{/* Standard */}
							<div className="space-y-3">
								<h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider">
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
										className="bg-slate-800 border-slate-700 text-slate-300 cursor-pointer h-6 px-3 rounded-full hover:bg-slate-700"
									>
										NEC 2023
									</Badge>
									<Badge
										variant="outline"
										className="bg-slate-800 border-slate-700 text-slate-300 cursor-pointer h-6 px-3 rounded-full hover:bg-slate-700"
									>
										BS 7671
									</Badge>
								</div>
								<select className="h-7 w-full text-xs bg-slate-950 border border-slate-700 rounded text-slate-200 px-2">
									<option>IEC Load Calc v4.2 — updated Nov 2024</option>
								</select>
								<div className="grid grid-cols-2 gap-3 text-xs">
									<select className="h-7 w-full bg-slate-950 border border-slate-700 rounded text-slate-200 px-2">
										<option>English</option>
										<option>العربية</option>
									</select>
									<div className="flex items-center bg-slate-950 border border-slate-700 rounded p-0.5">
										<button className="flex-1 bg-slate-800 rounded shadow-sm text-blue-400 py-1 font-medium text-[10px]">
											SI
										</button>
										<button className="flex-1 text-slate-400 py-1 text-[10px] hover:text-slate-200">
											Imperial
										</button>
									</div>
									<div className="flex items-center bg-slate-950 border border-slate-700 rounded p-0.5">
										<button className="flex-1 bg-slate-800 rounded shadow-sm text-slate-200 py-1 font-medium text-[10px]">
											A4
										</button>
										<button className="flex-1 text-slate-400 py-1 text-[10px]">
											Letter
										</button>
										<button className="flex-1 text-slate-400 py-1 text-[10px]">
											A3
										</button>
									</div>
									<div className="flex items-center bg-slate-950 border border-slate-700 rounded p-0.5">
										<button className="flex-1 bg-slate-800 rounded shadow-sm text-slate-200 py-1 font-medium text-[10px]">
											Portrait
										</button>
										<button className="flex-1 text-slate-400 py-1 text-[10px]">
											Land
										</button>
									</div>
								</div>
								<div className="space-y-3 pt-2">
									<div className="space-y-1">
										<div className="flex justify-between text-[10px] text-slate-400">
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
										<div className="flex justify-between text-[10px] text-slate-400">
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

							<Separator className="bg-slate-800" />

							{/* Sections */}
							<div className="space-y-3">
								<div className="flex justify-between items-center">
									<h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider">
										Content Sections
									</h3>
									<span className="text-[10px] text-blue-400 cursor-pointer">
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
											className="flex items-center gap-2 group hover:bg-slate-800/50 p-1 rounded -mx-1"
										>
											<GripVertical className="w-3.5 h-3.5 text-slate-600 cursor-grab opacity-0 group-hover:opacity-100" />
											<Checkbox
												id={`sec-${i}`}
												checked={item.checked}
												className="w-3.5 h-3.5 border-slate-500 data-[state=checked]:bg-blue-600 data-[state=checked]:border-blue-600"
											/>
											<label
												htmlFor={`sec-${i}`}
												className={`text-xs cursor-pointer ${item.checked ? "text-slate-200" : "text-slate-500"}`}
											>
												{item.label}
											</label>
										</div>
									))}
								</div>
							</div>

							<Separator className="bg-slate-800" />

							{/* Branding */}
							<div className="space-y-3">
								<h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider">
									Branding & Cover Page
								</h3>
								<div className="flex items-center gap-3 bg-slate-950 p-3 rounded border border-slate-800 border-dashed cursor-pointer hover:border-slate-600 hover:bg-slate-900">
									<div className="w-10 h-10 bg-slate-800 rounded flex items-center justify-center border border-slate-700">
										<ImageIcon className="w-4 h-4 text-slate-500" />
									</div>
									<div className="text-xs text-slate-400">
										Click to update logo
										<br />
										<span className="text-[10px] text-slate-600">
											NexusTech Engineering
										</span>
									</div>
								</div>
								<div className="space-y-2 text-xs">
									<Input
										className="h-7 bg-slate-950 border-slate-700 text-slate-200"
										placeholder="Company Name"
										defaultValue="NexusTech Engineering Consultants"
									/>
									<Input
										className="h-7 bg-slate-950 border-slate-700 text-slate-200"
										placeholder="Project Name"
										defaultValue="Tower-B Office Complex — Abu Dhabi"
									/>
									<Input
										className="h-7 bg-slate-950 border-slate-700 text-slate-200"
										placeholder="Client Name"
										defaultValue="Tower-B Developments LLC"
									/>
								</div>
								<div className="grid grid-cols-2 gap-2 text-xs">
									<select className="h-7 w-full bg-slate-950 border border-slate-700 rounded text-slate-400 px-2">
										<option>Watermark: None</option>
									</select>
									<select className="h-7 w-full bg-slate-950 border border-slate-700 rounded text-slate-400 px-2">
										<option>Style: Standard</option>
									</select>
								</div>
								<div className="flex items-center justify-between text-xs pt-1">
									<span className="text-slate-300">
										Include project photo on cover
									</span>
									<Switch className="data-[state=checked]:bg-blue-600" />
								</div>
							</div>

							<Separator className="bg-slate-800" />

							{/* Data Source */}
							<div className="space-y-3">
								<h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider">
									Data Source Control
								</h3>
								<div className="flex items-center justify-between text-xs">
									<span className="text-slate-200 font-medium">
										Auto-populate from Live Data
									</span>
									<Switch
										defaultChecked
										className="data-[state=checked]:bg-blue-600"
									/>
								</div>
								<div className="bg-slate-950 p-2.5 rounded border border-slate-800 space-y-2 text-[10px]">
									<div className="flex items-start gap-2">
										<Check className="w-3.5 h-3.5 text-green-500 mt-0.5 shrink-0" />
										<div>
											<span className="text-slate-200">
												Load calc worksheet (Rev 11)
											</span>
											<br />
											<span className="text-slate-500">Last synced: 14:15</span>
										</div>
									</div>
									<div className="flex items-start gap-2">
										<Check className="w-3.5 h-3.5 text-green-500 mt-0.5 shrink-0" />
										<div>
											<span className="text-slate-200">Equipment schedule</span>
											<br />
											<span className="text-slate-500">Last synced: 14:10</span>
										</div>
									</div>
									<div className="flex items-start gap-2">
										<Check className="w-3.5 h-3.5 text-green-500 mt-0.5 shrink-0" />
										<div>
											<span className="text-slate-200">
												BIM model (Revit v14)
											</span>
											<br />
											<span className="text-slate-500">Last synced: 14:31</span>
										</div>
									</div>
									<div className="flex items-center gap-2 pt-1">
										<div className="w-3.5 h-3.5 border border-slate-600 rounded-[2px] shrink-0"></div>
										<span className="text-slate-500 flex-1">
											External ETAP model
										</span>
										<Button
											variant="outline"
											className="h-5 text-[9px] px-2 py-0 border-slate-700 bg-slate-900 text-slate-300"
										>
											Connect
										</Button>
									</div>
								</div>
								<select className="h-7 w-full text-xs bg-slate-950 border border-slate-700 rounded text-slate-300 px-2">
									<option>On change: Notify and prompt update</option>
								</select>
							</div>

							<Separator className="bg-slate-800" />

							{/* Output */}
							<div className="space-y-3 pb-4">
								<h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider">
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
									<label className="flex items-center gap-1.5 cursor-pointer text-slate-500">
										<Checkbox className="w-3.5 h-3.5 border-slate-600" /> Excel
									</label>
									<label className="flex items-center gap-1.5 cursor-pointer text-slate-500">
										<Checkbox className="w-3.5 h-3.5 border-slate-600" /> HTML
									</label>
								</div>
								<div className="bg-slate-950 p-2.5 rounded border border-slate-800 space-y-2 text-xs">
									<div className="flex justify-between items-center">
										<span className="text-slate-400">Password protect</span>
										<Switch className="scale-75 origin-right" />
									</div>
									<div className="flex justify-between items-center">
										<span className="text-slate-300">Print allowed</span>
										<Switch
											defaultChecked
											className="scale-75 origin-right data-[state=checked]:bg-blue-600"
										/>
									</div>
									<div className="flex justify-between items-center">
										<span className="text-slate-400">Edit allowed</span>
										<Switch className="scale-75 origin-right" />
									</div>
								</div>
								<div className="flex justify-between items-center text-xs">
									<span className="text-slate-300">
										Auto-generate transmittal
									</span>
									<Switch
										defaultChecked
										className="data-[state=checked]:bg-blue-600"
									/>
								</div>
								<div className="space-y-1.5">
									<label className="text-[10px] text-slate-400">  // NOSONAR — S6853: React import kept for JSX transform
										Recipients
									</label>
									<div className="min-h-7 bg-slate-950 border border-slate-700 rounded p-1 flex flex-wrap gap-1">
										<Badge
											variant="secondary"
											className="h-5 text-[9px] px-1.5 bg-slate-800 text-slate-300 hover:bg-slate-700"
										>
											Eng. Khalid <X className="w-2.5 h-2.5 ml-1 opacity-50" />
										</Badge>
										<Badge
											variant="secondary"
											className="h-5 text-[9px] px-1.5 bg-slate-800 text-slate-300 hover:bg-slate-700"
										>
											PM Office <X className="w-2.5 h-2.5 ml-1 opacity-50" />
										</Badge>
										<Badge
											variant="secondary"
											className="h-5 text-[9px] px-1.5 bg-slate-800 text-slate-300 hover:bg-slate-700"
										>
											AHJ Filing <X className="w-2.5 h-2.5 ml-1 opacity-50" />
										</Badge>
									</div>
								</div>
							</div>
						</div>
					</ScrollArea>

					{/* Action Footer */}
					<div className="p-4 border-t border-slate-800 bg-slate-950 shadow-[0_-10px_15px_-3px_rgba(0,0,0,0.3)] shrink-0 space-y-3">
						<div className="grid grid-cols-2 gap-2">
							<Button
								size="sm"
								variant="outline"
								className="h-8 text-xs border-slate-700 bg-slate-900 text-slate-300 hover:bg-slate-800"
							>
								Save Draft
							</Button>
							<Button
								size="sm"
								variant="outline"
								className="h-8 text-xs border-slate-700 bg-slate-900 text-slate-300 hover:bg-slate-800"
							>
								<Wand2 className="w-3.5 h-3.5 mr-1.5 text-blue-400" /> Preview
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
						<div className="text-center text-[9px] text-slate-500 font-mono">
							Last generated: Today 13:47 — 48 pages, 4.1 MB — Rev 2
						</div>
					</div>
				</div>
			</div>
		</div>
	);
}
