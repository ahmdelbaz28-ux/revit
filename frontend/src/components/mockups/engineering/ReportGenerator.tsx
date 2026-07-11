
import {
	AlertCircle,
	Check,
	CheckCircle,
	ChevronDown,
	Download,
	DownloadCloud,
	FileDigit,
	FileText,
	Play,
	Settings,
	Triangle,
	Upload,
	Wand2,
} from "lucide-react";
import type React from "react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

export function ReportGenerator() {
	const [progress, _setProgress] = useState(65);

	return (
		<div className="flex flex-col h-screen w-screen overflow-hidden bg-background text-foreground dark font-sans">
			{/* Header */}
			<div className="h-16 flex items-center justify-between px-4 border-b bg-card shrink-0">
				<div className="flex items-center gap-4">
					<div className="w-10 h-10 rounded-md bg-blue-500/20 flex items-center justify-center border border-blue-500/30">
						<FileText className="h-5 w-5 text-info" />
					</div>
					<div>
						<h1 className="font-bold tracking-wide text-lg leading-tight">
							Engineering Reports & Document Generation
						</h1>
						<div className="text-[10px] font-mono text-muted-foreground flex items-center gap-2 mt-0.5">
							<span>Project: Tower-B Office Complex</span>
							<span>•</span>
							<span className="text-success">All data synced</span>
						</div>
					</div>
				</div>

				<Tabs defaultValue="new" className="h-full flex items-center">
					<TabsList className="bg-transparent gap-2">
						<TabsTrigger
							value="new"
							className="data-[state=active]:bg-primary/20 data-[state=active]:text-primary border border-transparent data-[state=active]:border-primary/30"
						>
							New Report
						</TabsTrigger>
						<TabsTrigger value="my">My Reports</TabsTrigger>
						<TabsTrigger value="templates">Templates</TabsTrigger>
						<TabsTrigger value="scheduled">Scheduled</TabsTrigger>
						<TabsTrigger value="archive">Archive</TabsTrigger>
					</TabsList>
				</Tabs>

				<div className="flex gap-2">
					<Button variant="outline" size="sm" className="h-8 gap-1">
						<DownloadCloud className="h-4 w-4" /> Import Data
					</Button>
					<Button variant="outline" size="sm" className="h-8 gap-1">
						<Settings className="h-4 w-4" /> Settings
					</Button>
					<Button
						size="sm"
						className="h-8 gap-1 shadow-[0_0_15px_rgba(0,168,255,0.4)]"
					>
						<Wand2 className="h-4 w-4" /> Generate with AI
					</Button>
				</div>
			</div>

			<div className="flex flex-1 overflow-hidden">
				{/* Left Panel - Navigator */}
				<div className="w-[260px] flex flex-col border-r bg-card/30 shrink-0">
					<div className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground border-b flex justify-between items-center bg-card/40">
						<span>Report Categories</span>
					</div>
					<ScrollArea className="flex-1">
						<div className="p-2 text-sm space-y-1">
							<TreeFolder title="Electrical Engineering" defaultOpen>
								<TreeItem title="Load Calculation Report" active />
								<TreeItem title="Arc Flash Study Report" />
								<TreeItem title="Short Circuit Analysis" />
								<TreeItem title="Protection Coordination Study" />
								<TreeItem title="Power Quality Report" />
								<TreeItem title="Single Line Diagram Package" />
								<TreeItem title="Panel Schedule Summary" />
								<TreeItem title="Cable Schedule" />
							</TreeFolder>
							<TreeFolder title="Fire Protection">
								<TreeItem title="Fire Alarm Coverage Report" />
								<TreeItem title="Hydraulic Calculation" />
								<TreeItem title="Sprinkler Head Schedule" />
							</TreeFolder>
							<TreeFolder title="BIM & Coordination">
								<TreeItem title="Clash Detection Report" />
								<TreeItem title="BIM Execution Plan" />
								<TreeItem title="Level of Development Report" />
							</TreeFolder>
							<TreeFolder title="Compliance & Permitting">
								<TreeItem title="NEC Compliance Certificate" />
								<TreeItem title="AHJ Submission Package" />
								<TreeItem title="Inspection Checklist" />
							</TreeFolder>
							<TreeFolder title="Project Management">
								<TreeItem title="Engineering Progress Report" />
								<TreeItem title="As-Built Documentation" />
								<TreeItem title="Revision History Report" />
							</TreeFolder>
						</div>
					</ScrollArea>
				</div>

				{/* Center Canvas */}
				<div className="flex-1 relative flex flex-col bg-[#0f1115] overflow-hidden">
					<ScrollArea className="flex-1 p-6">
						<div className="max-w-[800px] mx-auto bg-slate-100 rounded-sm shadow-xl min-h-[1050px] relative overflow-hidden flex flex-col">
							{/* Document Content */}
							<div className="flex-1 p-10 flex flex-col text-slate-900 font-serif">
								{/* Header */}
								<div className="flex justify-between items-start border-b-2 border-slate-300 pb-6 mb-8">
									<div className="flex items-center gap-4">
										<div className="w-16 h-16 bg-slate-200 border border-slate-300 flex items-center justify-center">
											<span className="text-muted-foreground text-[10px] font-sans">
												LOGO
											</span>
										</div>
										<div>
											<h2 className="text-xl font-bold uppercase tracking-wide text-slate-800">
												Tower-B Office Complex
											</h2>
											<div className="text-sm text-muted-foreground/70 mt-1 font-sans">
												Project ID: PRJ-8842-NY
											</div>
										</div>
									</div>
									<div className="text-right text-xs font-sans text-muted-foreground/70 space-y-1">
										<div>
											<span className="font-semibold text-slate-700">
												Report No:
											</span>{" "}
											EL-LC-2024-014
										</div>
										<div>
											<span className="font-semibold text-slate-700">
												Date:
											</span>{" "}
											Oct 24, 2024
										</div>
										<div>
											<span className="font-semibold text-slate-700">
												Prepared by:
											</span>{" "}
											A. Engineer
										</div>
										<div>
											<span className="font-semibold text-slate-700">
												Reviewed by:
											</span>{" "}
											S. Principal
										</div>
										<div>
											<span className="font-semibold text-slate-700">
												Revision:
											</span>{" "}
											14
										</div>
									</div>
								</div>

								{/* Title */}
								<h1 className="text-2xl font-bold text-center mb-8 border-b pb-2 uppercase tracking-wide">
									Electrical Load Calculation Report
									<br />
									<span className="text-lg font-normal text-muted-foreground/70">
										IEC 60364 / NEC 2023
									</span>
								</h1>

								{/* Tables */}
								<div className="space-y-8 font-sans">
									<div>
										<h3 className="font-bold text-sm bg-card text-white px-3 py-1.5 mb-2">
											1.0 LIGHTING LOAD
										</h3>
										<table className="w-full text-[11px] border-collapse border border-slate-300">
											<thead>
												<tr className="bg-slate-200 text-slate-800">
													<th className="border border-slate-300 p-2 text-left">
														Area
													</th>
													<th className="border border-slate-300 p-2 text-right">
														Floor Area (m²)
													</th>
													<th className="border border-slate-300 p-2 text-right">
														Load Density (W/m²)
													</th>
													<th className="border border-slate-300 p-2 text-right">
														Connected Load (kW)
													</th>
													<th className="border border-slate-300 p-2 text-right">
														Demand Factor
													</th>
													<th className="border border-slate-300 p-2 text-right">
														Demand Load (kW)
													</th>
												</tr>
											</thead>
											<tbody>
												<tr className="border-b border-slate-200">
													<td className="border-r border-slate-300 p-2">
														Office Level 1
													</td>
													<td className="border-r border-slate-300 p-2 text-right">
														1,250
													</td>
													<td className="border-r border-slate-300 p-2 text-right">
														12.0
													</td>
													<td className="border-r border-slate-300 p-2 text-right">
														15.0
													</td>
													<td className="border-r border-slate-300 p-2 text-right">
														1.00
													</td>
													<td className="p-2 text-right font-semibold">15.0</td>
												</tr>
												<tr className="border-b border-slate-200">
													<td className="border-r border-slate-300 p-2">
														Office Level 2
													</td>
													<td className="border-r border-slate-300 p-2 text-right">
														1,250
													</td>
													<td className="border-r border-slate-300 p-2 text-right">
														12.0
													</td>
													<td className="border-r border-slate-300 p-2 text-right">
														15.0
													</td>
													<td className="border-r border-slate-300 p-2 text-right">
														1.00
													</td>
													<td className="p-2 text-right font-semibold">15.0</td>
												</tr>
												<tr className="border-b border-slate-200 bg-slate-50">
													<td className="border-r border-slate-300 p-2">
														Lobby
													</td>
													<td className="border-r border-slate-300 p-2 text-right">
														400
													</td>
													<td className="border-r border-slate-300 p-2 text-right">
														15.0
													</td>
													<td className="border-r border-slate-300 p-2 text-right">
														6.0
													</td>
													<td className="border-r border-slate-300 p-2 text-right">
														1.00
													</td>
													<td className="p-2 text-right font-semibold">6.0</td>
												</tr>
												<tr className="border-b border-slate-200">
													<td className="border-r border-slate-300 p-2">
														Parking
													</td>
													<td className="border-r border-slate-300 p-2 text-right">
														3,500
													</td>
													<td className="border-r border-slate-300 p-2 text-right">
														3.0
													</td>
													<td className="border-r border-slate-300 p-2 text-right">
														10.5
													</td>
													<td className="border-r border-slate-300 p-2 text-right">
														0.80
													</td>
													<td className="p-2 text-right font-semibold">8.4</td>
												</tr>
												<tr>
													<td className="border-r border-slate-300 p-2">
														Mechanical Room
													</td>
													<td className="border-r border-slate-300 p-2 text-right">
														150
													</td>
													<td className="border-r border-slate-300 p-2 text-right">
														10.0
													</td>
													<td className="border-r border-slate-300 p-2 text-right">
														1.5
													</td>
													<td className="border-r border-slate-300 p-2 text-right">
														0.50
													</td>
													<td className="p-2 text-right font-semibold">0.75</td>
												</tr>
												<tr className="bg-slate-200 font-bold border-t-2 border-slate-400">
													<td
														colSpan={3}
														className="border-r border-slate-300 p-2 text-right"
													>
														SUBTOTAL
													</td>
													<td className="border-r border-slate-300 p-2 text-right">
														48.0
													</td>
													<td className="border-r border-slate-300 p-2 text-right">
														--
													</td>
													<td className="p-2 text-right text-blue-700">
														45.15
													</td>
												</tr>
											</tbody>
										</table>
									</div>

									<div>
										<h3 className="font-bold text-sm bg-card text-white px-3 py-1.5 mb-2">
											2.0 POWER & HVAC LOAD
										</h3>
										<table className="w-full text-[11px] border-collapse border border-slate-300">
											<thead>
												<tr className="bg-slate-200 text-slate-800">
													<th className="border border-slate-300 p-2 text-left">
														Equipment
													</th>
													<th className="border border-slate-300 p-2 text-right">
														Qty
													</th>
													<th className="border border-slate-300 p-2 text-right">
														Rating (kW)
													</th>
													<th className="border border-slate-300 p-2 text-right">
														Connected Load (kW)
													</th>
													<th className="border border-slate-300 p-2 text-right">
														Demand Factor
													</th>
													<th className="border border-slate-300 p-2 text-right">
														Demand Load (kW)
													</th>
												</tr>
											</thead>
											<tbody>
												<tr className="border-b border-slate-200">
													<td className="border-r border-slate-300 p-2">
														Chiller CH-1
													</td>
													<td className="border-r border-slate-300 p-2 text-right">
														2
													</td>
													<td className="border-r border-slate-300 p-2 text-right">
														450.0
													</td>
													<td className="border-r border-slate-300 p-2 text-right">
														900.0
													</td>
													<td className="border-r border-slate-300 p-2 text-right">
														0.85
													</td>
													<td className="p-2 text-right font-semibold">
														765.0
													</td>
												</tr>
												<tr className="border-b border-slate-200">
													<td className="border-r border-slate-300 p-2">
														AHU Level 1-4
													</td>
													<td className="border-r border-slate-300 p-2 text-right">
														4
													</td>
													<td className="border-r border-slate-300 p-2 text-right">
														45.0
													</td>
													<td className="border-r border-slate-300 p-2 text-right">
														180.0
													</td>
													<td className="border-r border-slate-300 p-2 text-right">
														0.80
													</td>
													<td className="p-2 text-right font-semibold">
														144.0
													</td>
												</tr>
												<tr className="border-b border-slate-200 bg-slate-50">
													<td className="border-r border-slate-300 p-2">
														General Receptacles
													</td>
													<td className="border-r border-slate-300 p-2 text-right">
														--
													</td>
													<td className="border-r border-slate-300 p-2 text-right">
														--
													</td>
													<td className="border-r border-slate-300 p-2 text-right">
														250.0
													</td>
													<td className="border-r border-slate-300 p-2 text-right">
														0.50
													</td>
													<td className="p-2 text-right font-semibold">
														125.0
													</td>
												</tr>
												<tr>
													<td className="border-r border-slate-300 p-2">
														Elevators
													</td>
													<td className="border-r border-slate-300 p-2 text-right">
														4
													</td>
													<td className="border-r border-slate-300 p-2 text-right">
														30.0
													</td>
													<td className="border-r border-slate-300 p-2 text-right">
														120.0
													</td>
													<td className="border-r border-slate-300 p-2 text-right">
														0.60
													</td>
													<td className="p-2 text-right font-semibold">72.0</td>
												</tr>
												<tr className="bg-slate-200 font-bold border-t-2 border-slate-400">
													<td
														colSpan={3}
														className="border-r border-slate-300 p-2 text-right"
													>
														SUBTOTAL
													</td>
													<td className="border-r border-slate-300 p-2 text-right">
														1,450.0
													</td>
													<td className="border-r border-slate-300 p-2 text-right">
														--
													</td>
													<td className="p-2 text-right text-blue-700">
														1,106.0
													</td>
												</tr>
											</tbody>
										</table>
									</div>

									{/* Summary Box */}
									<div className="mt-8 border-2 border-slate-800 p-6">
										<h3 className="font-bold text-lg text-slate-800 mb-4 border-b border-slate-300 pb-2">
											3.0 SUMMARY & RECOMMENDATION
										</h3>
										<div className="grid grid-cols-2 gap-x-12 gap-y-3 text-sm">
											<div className="flex justify-between border-b border-slate-200 pb-1">
												<span className="font-semibold text-muted-foreground/70">
													Total Connected:
												</span>
												<span className="font-mono font-bold text-slate-900">
													2,847 kW
												</span>
											</div>
											<div className="flex justify-between border-b border-slate-200 pb-1">
												<span className="font-semibold text-muted-foreground/70">
													Total Demand:
												</span>
												<span className="font-mono font-bold text-slate-900 text-blue-700">
													1,923 kW
												</span>
											</div>
											<div className="flex justify-between border-b border-slate-200 pb-1">
												<span className="font-semibold text-muted-foreground/70">
													Power Factor:
												</span>
												<span className="font-mono font-bold text-slate-900">
													0.85
												</span>
											</div>
											<div className="flex justify-between border-b border-slate-200 pb-1">
												<span className="font-semibold text-muted-foreground/70">
													Apparent Power:
												</span>
												<span className="font-mono font-bold text-slate-900">
													2,262 kVA
												</span>
											</div>
										</div>

										<div className="mt-6 bg-blue-50 border border-blue-200 p-4">
											<span className="font-bold text-blue-900 block mb-1 uppercase text-xs tracking-wider">
												Recommended Supply
											</span>
											<div className="text-xl font-bold font-mono text-blue-800">
												2,500 kVA, 480V, 3-Phase, 60Hz
											</div>
										</div>
									</div>
								</div>
							</div>

							{/* AI Overlay Overlaying Bottom */}
							<div className="absolute bottom-6 left-6 right-6 bg-card/95 backdrop-blur-md border border-border shadow-2xl rounded-lg p-5 flex flex-col z-20">
								<div className="flex justify-between items-center mb-4">
									<div className="flex items-center gap-3">
										<Wand2 className="h-5 w-5 text-info" />
										<span className="font-semibold text-sm text-foreground">
											AI is analyzing project data...
										</span>
									</div>
									<span className="text-xs font-mono text-info">
										{progress}%
									</span>
								</div>

								<div className="h-1.5 w-full bg-card rounded-full overflow-hidden mb-4">
									<div
										className="h-full bg-blue-500 shadow-[0_0_10px_rgba(59,130,246,0.8)] transition-all duration-500 ease-out"
										style={{ width: `${progress}%` }}
									></div>
								</div>

								<div className="grid grid-cols-2 gap-3 text-xs font-mono text-foreground/90">
									<div className="flex items-center gap-2 text-success">
										<CheckCircle className="h-4 w-4" /> Lighting loads
										extracted
									</div>
									<div className="flex items-center gap-2 text-success">
										<CheckCircle className="h-4 w-4" /> HVAC loads
										calculated
									</div>
									<div className="flex items-center gap-2 text-success">
										<CheckCircle className="h-4 w-4" /> Motor loads verified
									</div>
									<div className="flex items-center gap-2 text-info">
										<Play className="h-4 w-4 animate-pulse" /> Demand
										factors applied...
									</div>
								</div>
							</div>
						</div>
					</ScrollArea>
				</div>

				{/* Right Panel - Settings */}
				<div className="w-[300px] flex flex-col border-l bg-card/30 shrink-0">
					<div className="px-4 py-3 text-sm font-semibold uppercase tracking-wider text-foreground border-b bg-card/40">
						Report Controls
					</div>
					<ScrollArea className="flex-1">
						<div className="p-4 space-y-6">
							{/* Report Settings */}
							<div className="space-y-4">
								<div className="text-xs font-bold text-muted-foreground uppercase">
									Report Settings
								</div>

								<div className="space-y-1.5">
									<label className="text-xs font-medium text-foreground/90">
										Standard / Template
									</label>
									<div className="grid grid-cols-3 gap-1">
										<div className="bg-primary/20 text-primary border border-primary/30 text-[10px] text-center py-1.5 rounded cursor-pointer font-medium">
											IEC/NEC
										</div>
										<div className="bg-card text-muted-foreground border border-border/50 text-[10px] text-center py-1.5 rounded cursor-pointer hover:bg-muted">
											ASHRAE
										</div>
										<div className="bg-card text-muted-foreground border border-border/50 text-[10px] text-center py-1.5 rounded cursor-pointer hover:bg-muted">
											Custom
										</div>
									</div>
								</div>

								<div className="space-y-1.5">
									<label className="text-xs font-medium text-foreground/90">
										Company Logo
									</label>
									<div className="border border-dashed border-border rounded-md p-3 flex flex-col items-center justify-center bg-card/50 cursor-pointer hover:bg-card">
										<Upload className="h-4 w-4 text-muted-foreground mb-1" />
										<span className="text-[10px] text-muted-foreground">
											Upload image (PNG, JPG)
										</span>
									</div>
								</div>

								<div className="grid grid-cols-2 gap-3">
									<div className="space-y-1.5">
										<label className="text-xs font-medium text-foreground/90">
											Language
										</label>
										<div className="flex items-center justify-between bg-background border border-border rounded px-2 py-1.5 cursor-pointer">
											<span className="text-xs">English</span>
											<ChevronDown className="h-3 w-3 text-muted-foreground" />
										</div>
									</div>
									<div className="space-y-1.5">
										<label className="text-xs font-medium text-foreground/90">
											Page Size
										</label>
										<div className="flex items-center justify-between bg-background border border-border rounded px-2 py-1.5 cursor-pointer">
											<span className="text-xs">A4</span>
											<ChevronDown className="h-3 w-3 text-muted-foreground" />
										</div>
									</div>
								</div>

								<div className="space-y-2 pt-2">
									<label className="text-xs font-medium text-foreground/90">
										Include Sections
									</label>
									<div className="space-y-2">
										<label className="flex items-center gap-2 cursor-pointer">
											<div className="w-3.5 h-3.5 bg-primary rounded-[2px] flex items-center justify-center">
												<Check className="h-2.5 w-2.5 text-primary-foreground" />
											</div>
											<span className="text-xs">Executive Summary</span>
										</label>
										<label className="flex items-center gap-2 cursor-pointer">
											<div className="w-3.5 h-3.5 bg-primary rounded-[2px] flex items-center justify-center">
												<Check className="h-2.5 w-2.5 text-primary-foreground" />
											</div>
											<span className="text-xs">Detailed Calculations</span>
										</label>
										<label className="flex items-center gap-2 cursor-pointer">
											<div className="w-3.5 h-3.5 bg-primary rounded-[2px] flex items-center justify-center">
												<Check className="h-2.5 w-2.5 text-primary-foreground" />
											</div>
											<span className="text-xs">References & Codes</span>
										</label>
										<label className="flex items-center gap-2 cursor-pointer">
											<div className="w-3.5 h-3.5 border border-border rounded-[2px]"></div>
											<span className="text-xs">Appendix</span>
										</label>
									</div>
								</div>
							</div>

							<Separator />

							{/* AI Assist */}
							<div className="space-y-3">
								<div className="flex items-center justify-between">
									<div className="text-xs font-bold text-info uppercase flex items-center gap-1">
										<Wand2 className="h-3 w-3" /> AI Assist
									</div>
									<div className="text-[10px] font-mono text-success flex items-center gap-1">
										<CheckCircle className="h-2.5 w-2.5" /> 94% Confidence
									</div>
								</div>

								<Button
									variant="secondary"
									className="w-full justify-start text-xs h-8 bg-blue-500/10 text-info hover:bg-blue-500/20 border border-blue-500/30"
								>
									Generate narrative summary
								</Button>
								<Button
									variant="secondary"
									className="w-full justify-start text-xs h-8 bg-blue-500/10 text-info hover:bg-blue-500/20 border border-blue-500/30"
								>
									Auto-populate from project data
								</Button>
							</div>

							<Separator />

							{/* Export Options */}
							<div className="space-y-4">
								<div className="text-xs font-bold text-muted-foreground uppercase">
									Export Options
								</div>

								<div className="grid grid-cols-2 gap-2">
									<Button variant="outline" className="h-8 text-xs bg-card">
										<FileDigit className="h-4 w-4 mr-1.5" /> PDF
									</Button>
									<Button variant="outline" className="h-8 text-xs bg-card">
										<FileText className="h-4 w-4 mr-1.5" /> DOCX
									</Button>
									<Button variant="outline" className="h-8 text-xs bg-card">
										<FileDigit className="h-4 w-4 mr-1.5" /> Excel
									</Button>
									<Button variant="default" className="h-8 text-xs">
										<AlertCircle className="h-4 w-4 mr-1.5" /> For Review
									</Button>
								</div>

								<div className="space-y-3 pt-2">
									<div className="flex items-center justify-between">
										<span className="text-xs font-medium">
											Digital Signature
										</span>
										<Switch defaultChecked />
									</div>
									<div className="flex items-center justify-between">
										<span className="text-xs font-medium">Watermark</span>
										<div className="flex text-[10px] border border-border rounded overflow-hidden">
											<div className="px-2 py-0.5 bg-primary/20 text-primary font-semibold">
												Draft
											</div>
											<div className="px-2 py-0.5 bg-card">Final</div>
										</div>
									</div>
									<div className="space-y-1.5">
										<label className="text-[10px] text-muted-foreground">
											Stamp
										</label>
										<div className="flex items-center justify-between bg-background border border-border rounded px-2 py-1.5 cursor-pointer">
											<span className="text-xs text-primary font-semibold uppercase">
												Preliminary
											</span>
											<ChevronDown className="h-3 w-3 text-muted-foreground" />
										</div>
									</div>
								</div>
							</div>

							<Separator />

							{/* Recent */}
							<div>
								<div className="text-xs font-bold text-muted-foreground uppercase mb-3">
									Recent Reports
								</div>
								<div className="space-y-2">
									<div className="flex items-center justify-between p-2 rounded bg-card/50 border border-border/50 hover:bg-muted cursor-pointer transition-colors">
										<div>
											<div className="text-xs font-medium">
												Load Calc - Rev 13
											</div>
											<div className="text-[9px] text-muted-foreground mt-0.5">
												Oct 12 • 450 KB
											</div>
										</div>
										<div className="flex items-center gap-2">
											<Badge
												variant="outline"
												className="text-[9px] h-4 px-1 py-0 bg-emerald-500/10 text-success border-emerald-500/20"
											>
												Approved
											</Badge>
											<Download className="h-4 w-4 text-muted-foreground" />
										</div>
									</div>
									<div className="flex items-center justify-between p-2 rounded bg-card/50 border border-border/50 hover:bg-muted cursor-pointer transition-colors">
										<div>
											<div className="text-xs font-medium">
												Arc Flash Analysis
											</div>
											<div className="text-[9px] text-muted-foreground mt-0.5">
												Oct 08 • 1.2 MB
											</div>
										</div>
										<div className="flex items-center gap-2">
											<Badge
												variant="outline"
												className="text-[9px] h-4 px-1 py-0 bg-blue-500/10 text-info border-blue-500/20"
											>
												Review
											</Badge>
											<Download className="h-4 w-4 text-muted-foreground" />
										</div>
									</div>
									<div className="flex items-center justify-between p-2 rounded bg-card/50 border border-border/50 hover:bg-muted cursor-pointer transition-colors">
										<div>
											<div className="text-xs font-medium">Panel Schedule</div>
											<div className="text-[9px] text-muted-foreground mt-0.5">
												Oct 01 • 890 KB
											</div>
										</div>
										<div className="flex items-center gap-2">
											<Badge
												variant="outline"
												className="text-[9px] h-4 px-1 py-0 bg-emerald-500/10 text-success border-emerald-500/20"
											>
												Approved
											</Badge>
											<Download className="h-4 w-4 text-muted-foreground" />
										</div>
									</div>
								</div>
							</div>
						</div>
					</ScrollArea>
				</div>
			</div>
		</div>
	);
}

function TreeFolder({
	title,
	children,
	defaultOpen = false,
}: {
	title: string;
	children: React.ReactNode;
	defaultOpen?: boolean;
}) {
	const [open, setOpen] = useState(defaultOpen);
	return (
		<div className="mb-1">
			<div
				role="button"
				tabIndex={0}
				className="flex items-center gap-1.5 py-1.5 px-2 hover:bg-muted cursor-pointer rounded-md transition-colors"
				onClick={() => setOpen(!open)}
				onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpen(!open) } }}
			>
				<Triangle
					className={`h-3 w-3 text-muted-foreground transition-transform ${open ? "rotate-180" : "rotate-90"}`}
				/>
				<span className="text-xs font-medium text-foreground/90">{title}</span>
			</div>
			{open && (
				<div className="ml-4 pl-2 border-l border-border/50 flex flex-col gap-0.5 mt-1">
					{children}
				</div>
			)}
		</div>
	);
}

function TreeItem({
	title,
	active = false,
}: {
	title: string;
	active?: boolean;
}) {
	return (
		<div
			className={`flex items-center gap-2 py-1.5 px-2 rounded-md cursor-pointer transition-colors ${active ? "bg-blue-500/20 text-info font-medium border border-blue-500/30" : "text-muted-foreground hover:text-foreground hover:bg-muted"}`}
		>
			<FileText
				className={`h-4 w-4 ${active ? "text-info" : "text-muted-foreground"}`}
			/>
			<span className="text-[11px] truncate">{title}</span>
		</div>
	);
}
