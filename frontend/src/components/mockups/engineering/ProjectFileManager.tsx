
import {
	Archive,
	ArrowLeft,
	ArrowRight,
	ArrowUp,
	Box,
	ChevronDown,
	ChevronRight,
	Clock,
	Clock3,
	Eye,
	File,
	FileBox,
	FileIcon,
	FileText,
	FolderOpen,
	Grid,
	Link as LinkIcon,
	List,
	Lock,
	MoreHorizontal,
	Plus,
	RefreshCw,
	Search,
	Star,
	TableProperties,
	Upload,
	Users,
	X,
} from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

export function ProjectFileManager() {
	const [activeView, setActiveView] = useState("List");
	const [selectedFileId, setSelectedFileId] = useState<number | null>(1);

	const files = [
		{
			id: 1,
			name: "Tower-B-LV-Main-Switchboard.dwg",
			type: "DWG",
			size: "48.2 MB",
			rev: "Rev 14",
			date: "Today 14:32",
			author: "Ahmed Al-Rashidi",
			status: "Approved",
			approval: "Issued for Construction",
			color: "blue",
		},
		{
			id: 2,
			name: "Tower-B-LV-Floor-Plans-L1.dwg",
			type: "DWG",
			size: "22.4 MB",
			rev: "Rev 12",
			date: "Nov 12",
			author: "Ahmed",
			status: "Approved",
			approval: "Issued for Review",
			color: "blue",
		},
		{
			id: 3,
			name: "Tower-B-LV-Floor-Plans-L2.dwg",
			type: "DWG",
			size: "24.1 MB",
			rev: "Rev 11",
			date: "Nov 10",
			author: "Sarah Chen",
			status: "In Review",
			approval: "For Review",
			color: "blue",
		},
		{
			id: 4,
			name: "Tower-B-LV-Floor-Plans-L3.dwg",
			type: "DWG",
			size: "23.8 MB",
			rev: "Rev 10",
			date: "Nov 8",
			author: "Ahmed",
			status: "Approved",
			approval: "Issued for Review",
			color: "blue",
		},
		{
			id: 5,
			name: "Tower-B-Panel-Schedule-MDB-A.xlsx",
			type: "XLSX",
			size: "1.8 MB",
			rev: "Rev 6",
			date: "Nov 11",
			author: "Marcus",
			status: "Approved",
			approval: "For Construction",
			color: "green",
		},
		{
			id: 6,
			name: "Tower-B-Panel-Schedule-MDB-B.xlsx",
			type: "XLSX",
			size: "1.9 MB",
			rev: "Rev 5",
			date: "Nov 9",
			author: "Marcus",
			status: "Draft",
			approval: "Preliminary",
			color: "green",
		},
		{
			id: 7,
			name: "Tower-B-Panel-Schedule-LP.xlsx",
			type: "XLSX",
			size: "2.4 MB",
			rev: "Rev 8",
			date: "Nov 12",
			author: "Marcus",
			status: "Approved",
			approval: "For Construction",
			color: "green",
		},
		{
			id: 8,
			name: "Tower-B-Cable-Schedule-LV.xlsx",
			type: "XLSX",
			size: "3.2 MB",
			rev: "Rev 4",
			date: "Nov 7",
			author: "James Okafor",
			status: "In Review",
			approval: "For Review",
			color: "green",
		},
		{
			id: 9,
			name: "Tower-B-Load-Calculations.pdf",
			type: "PDF",
			size: "4.1 MB",
			rev: "Rev 11",
			date: "Today 13:55",
			author: "James",
			status: "Approved",
			approval: "Issued for Construction",
			color: "red",
		},
		{
			id: 10,
			name: "Tower-B-SLD-Main.dwg",
			type: "DWG",
			size: "31.7 MB",
			rev: "Rev 9",
			date: "Nov 11",
			author: "Ahmed",
			status: "In Review",
			approval: "For Review",
			color: "blue",
		},
		{
			id: 11,
			name: "Tower-B-Arc-Flash-Report.pdf",
			type: "PDF",
			size: "8.3 MB",
			rev: "Rev 3",
			date: "Nov 10",
			author: "Ahmed",
			status: "Approved",
			approval: "For Information",
			color: "red",
		},
		{
			id: 12,
			name: "Tower-B-Earthing-Design.dwg",
			type: "DWG",
			size: "15.2 MB",
			rev: "Rev 5",
			date: "Nov 8",
			author: "Fatima",
			status: "Draft",
			approval: "Preliminary",
			color: "blue",
		},
		{
			id: 13,
			name: "LV-Switchgear-Spec.docx",
			type: "DOCX",
			size: "0.8 MB",
			rev: "Rev 7",
			date: "Nov 5",
			author: "Sarah",
			status: "Approved",
			approval: "For Construction",
			color: "blue",
		},
		{
			id: 14,
			name: "Voltage-Drop-Calculations.xlsx",
			type: "XLSX",
			size: "1.2 MB",
			rev: "Rev 3",
			date: "Nov 6",
			author: "James",
			status: "Approved",
			approval: "For Information",
			color: "green",
		},
		{
			id: 15,
			name: "Electrical-Material-Schedule.xlsx",
			type: "XLSX",
			size: "2.8 MB",
			rev: "Rev 2",
			date: "Nov 4",
			author: "Ahmed",
			status: "Draft",
			approval: "Preliminary",
			color: "green",
		},
	];

	const getStatusColor = (status: string) => {
		if (status === "Approved")
			return "bg-green-500/20 text-green-400 border-green-500/30";
		if (status === "In Review")
			return "bg-primary/20 text-primary border-primary/30";
		return "bg-slate-500/20 text-muted-foreground border-border/30";
	};

	const getApprovalColor = (approval: string) => {
		if (approval.includes("Construction"))
			return "bg-blue-500/20 text-info border-blue-500/30";
		if (approval.includes("Review"))
			return "bg-primary/20 text-primary border-primary/30";
		if (approval.includes("Information"))
			return "bg-purple-500/20 text-purple-400 border-purple-500/30";
		return "bg-slate-500/20 text-muted-foreground border-border/30";
	};

	const getFileIcon = (type: string, className?: string) => {
		switch (type) {
			case "DWG":
				return <FileIcon className={`text-info ${className}`} />;
			case "PDF":
				return <FileText className={`text-danger ${className}`} />;
			case "XLSX":
				return <TableProperties className={`text-green-400 ${className}`} />;
			case "DOCX":
				return <FileBox className={`text-info ${className}`} />;
			default:
				return <File className={`text-muted-foreground ${className}`} />;
		}
	};

	const selectedFile = files.find((f) => f.id === selectedFileId);

	return (
		<div className="flex flex-col h-screen w-screen overflow-hidden bg-card text-foreground font-sans dark">
			{/* Top Menu Bar */}
			<div className="h-9 flex items-center justify-between px-4 bg-background border-b border-slate-800 shrink-0">
				<div className="flex text-xs space-x-4 text-muted-foreground">
					<span className="text-foreground font-bold flex items-center gap-2">
						<Box className="w-3.5 h-3.5 text-blue-500" /> NexusCAD
					</span>
					<span className="hover:text-foreground cursor-pointer">File</span>
					<span className="hover:text-foreground cursor-pointer">Edit</span>
					<span className="hover:text-foreground cursor-pointer">View</span>
					<span className="hover:text-foreground cursor-pointer">Project</span>
					<span className="hover:text-foreground cursor-pointer">
						Version Control
					</span>
					<span className="hover:text-foreground cursor-pointer">Tools</span>
					<span className="hover:text-foreground cursor-pointer">Help</span>
				</div>
				<div className="flex items-center gap-3">
					<div className="relative">
						<Search className="h-3 w-3 absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
						<input
							type="text"
							placeholder="Search files..."
							className="bg-card border-border rounded text-xs pl-7 pr-2 py-1 w-48 text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-blue-500"
						/>
					</div>
					<Button
						size="sm"
						variant="default"
						className="h-6 text-[11px] px-3 bg-blue-600 hover:bg-blue-500 rounded flex gap-1 items-center"
					>
						New <ChevronDown className="w-3 h-3" />
					</Button>
					<Button
						size="sm"
						variant="outline"
						className="h-6 text-[11px] px-3 border-border hover:bg-card text-foreground/90 rounded flex gap-1 items-center"
					>
						<Upload className="w-3 h-3" /> Upload
					</Button>
					<Button
						size="sm"
						variant="outline"
						className="h-6 text-[11px] px-3 border-border hover:bg-card text-foreground/90 rounded flex gap-1 items-center"
					>
						<RefreshCw className="w-3 h-3 text-success" /> Sync Cloud
					</Button>
				</div>
			</div>

			{/* Second Toolbar */}
			<div className="h-10 flex items-center justify-between px-4 bg-card border-b border-slate-800 shrink-0">
				<div className="flex items-center gap-3">
					<div className="flex gap-1 mr-2 text-muted-foreground">
						<Button
							variant="ghost"
							size="icon"
							className="h-6 w-6 rounded hover:bg-card"
						>
							<ArrowLeft className="w-3.5 h-3.5" />
						</Button>
						<Button
							variant="ghost"
							size="icon"
							className="h-6 w-6 rounded hover:bg-card"
						>
							<ArrowRight className="w-3.5 h-3.5" />
						</Button>
						<Button
							variant="ghost"
							size="icon"
							className="h-6 w-6 rounded hover:bg-card"
						>
							<ArrowUp className="w-3.5 h-3.5" />
						</Button>
						<Button
							variant="ghost"
							size="icon"
							className="h-6 w-6 rounded hover:bg-card"
						>
							<RefreshCw className="w-3.5 h-3.5" />
						</Button>
					</div>
					<div className="flex items-center text-xs text-muted-foreground gap-2 bg-background px-3 py-1 rounded border border-slate-800">
						<span className="hover:text-info cursor-pointer">
							NexusCAD Pro
						</span>{" "}
						<ChevronRight className="w-3 h-3" />
						<span className="hover:text-info cursor-pointer">Projects</span>{" "}
						<ChevronRight className="w-3 h-3" />
						<span className="hover:text-info cursor-pointer text-foreground">
							Tower-B Office Complex
						</span>{" "}
						<ChevronRight className="w-3 h-3 text-muted-foreground/70" />
						<span className="hover:text-info cursor-pointer text-info font-medium">
							Electrical
						</span>
					</div>
				</div>
				<div className="flex items-center gap-4">
					<div className="flex items-center gap-2">
						<div className="flex bg-background rounded border border-slate-800 overflow-hidden">
							<Button
								variant="ghost"
								size="sm"
								className={`h-6 w-8 rounded-none px-0 ${activeView === "Grid" ? "bg-card text-info" : "text-muted-foreground hover:text-foreground/90"}`}
								onClick={() => setActiveView("Grid")}
							>
								<Grid className="w-3.5 h-3.5" />
							</Button>
							<Button
								variant="ghost"
								size="sm"
								className={`h-6 w-8 rounded-none px-0 ${activeView === "List" ? "bg-card text-info" : "text-muted-foreground hover:text-foreground/90"}`}
								onClick={() => setActiveView("List")}
							>
								<List className="w-3.5 h-3.5" />
							</Button>
							<Button
								variant="ghost"
								size="sm"
								className={`h-6 w-8 rounded-none px-0 ${activeView === "Tree" ? "bg-card text-info" : "text-muted-foreground hover:text-foreground/90"}`}
								onClick={() => setActiveView("Tree")}
							>
								<TableProperties className="w-3.5 h-3.5" />
							</Button>
							<Button
								variant="ghost"
								size="sm"
								className={`h-6 w-8 rounded-none px-0 ${activeView === "Timeline" ? "bg-card text-info" : "text-muted-foreground hover:text-foreground/90"}`}
								onClick={() => setActiveView("Timeline")}
							>
								<Clock className="w-3.5 h-3.5" />
							</Button>
						</div>
					</div>
					<Separator orientation="vertical" className="h-5 bg-card" />
					<div className="flex gap-2 items-center text-xs">
						<Badge
							variant="outline"
							className="bg-muted/50 text-foreground/90 border-border h-6 cursor-pointer hover:bg-card pr-1"
						>
							DWG{" "}
							<X className="w-3 h-3 ml-1 text-muted-foreground hover:text-foreground" />
						</Badge>
						<Badge
							variant="outline"
							className="bg-green-900/20 text-green-400 border-green-900/50 h-6 cursor-pointer hover:bg-green-900/40 pr-1"
						>
							Approved{" "}
							<X className="w-3 h-3 ml-1 text-green-600 hover:text-green-300" />
						</Badge>
						<Badge
							variant="outline"
							className="bg-muted/50 text-foreground/90 border-border h-6 cursor-pointer hover:bg-card pr-1"
						>
							Rev 14+{" "}
							<X className="w-3 h-3 ml-1 text-muted-foreground hover:text-foreground" />
						</Badge>
						<Badge
							variant="outline"
							className="bg-muted/50 text-foreground/90 border-border h-6 cursor-pointer hover:bg-card pr-1"
						>
							Modified this week{" "}
							<X className="w-3 h-3 ml-1 text-muted-foreground hover:text-foreground" />
						</Badge>
						<Button
							variant="ghost"
							size="sm"
							className="h-6 text-[11px] text-muted-foreground border border-dashed border-border px-2"
						>
							+ Add Filter
						</Button>
					</div>
				</div>
			</div>

			<div className="flex flex-1 overflow-hidden">
				{/* Left Sidebar */}
				<div className="w-[240px] flex flex-col border-r border-slate-800 bg-muted/50 shrink-0">
					<ScrollArea className="flex-1">
						<div className="p-3">
							<div className="mb-4">
								<div className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider mb-2 px-2">
									Quick Access
								</div>
								<div className="space-y-0.5">
									<div className="flex items-center gap-2 text-xs px-2 py-1.5 rounded hover:bg-card cursor-pointer text-foreground/90">
										<Clock3 className="w-3.5 h-3.5 text-muted-foreground" /> Recent
										Files
									</div>
									<div className="flex items-center gap-2 text-xs px-2 py-1.5 rounded hover:bg-card cursor-pointer text-foreground/90">
										<Star className="w-3.5 h-3.5 text-yellow-500" /> Starred
										Items
										<span className="ml-auto text-[10px] bg-card text-muted-foreground px-1.5 rounded">
											3
										</span>
									</div>
									<div className="flex items-center gap-2 text-xs px-2 py-1.5 rounded hover:bg-card cursor-pointer text-foreground/90">
										<Users className="w-3.5 h-3.5 text-info" /> Shared with
										Me
										<span className="ml-auto text-[10px] bg-card text-muted-foreground px-1.5 rounded">
											8
										</span>
									</div>
									<div className="flex items-center gap-2 text-xs px-2 py-1.5 rounded hover:bg-card cursor-pointer text-foreground/90">
										<Eye className="w-3.5 h-3.5 text-primary" /> Pending
										Review
										<span className="ml-auto text-[10px] bg-primary text-white px-1.5 rounded">
											3
										</span>
									</div>
									<div className="flex items-center gap-2 text-xs px-2 py-1.5 rounded hover:bg-card cursor-pointer text-foreground/90">
										<Upload className="w-3.5 h-3.5 text-muted-foreground" /> My Uploads
										<span className="ml-auto text-[10px] bg-card text-muted-foreground px-1.5 rounded">
											12
										</span>
									</div>
								</div>
							</div>

							<div>
								<div className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider mb-2 px-2">
									Project Tree
								</div>
								<div className="space-y-0.5 font-sans text-xs">
									<div className="flex items-center gap-1.5 px-1 py-1 rounded hover:bg-card cursor-pointer text-foreground font-medium">
										<ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
										<FolderOpen className="w-3.5 h-3.5 text-info" />
										Tower-B Office Complex
									</div>
									<div className="pl-4 space-y-0.5">
										<div className="flex items-center gap-1.5 px-1 py-1 rounded hover:bg-card cursor-pointer text-foreground font-medium">
											<ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
											<FolderOpen className="w-3.5 h-3.5 text-info" />
											01_Electrical
										</div>
										<div className="pl-4 space-y-0.5">
											<div className="flex items-center gap-1.5 px-1 py-1 rounded hover:bg-card cursor-pointer text-foreground/90">
												<ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
												<FolderOpen className="w-3.5 h-3.5 text-muted-foreground" />
												01.1_Power Distribution
											</div>
											<div className="pl-4 space-y-0.5">
												<div className="flex items-center justify-between px-1 py-1 rounded hover:bg-card cursor-pointer text-muted-foreground">
													<div className="flex items-center gap-1.5">
														<FolderOpen className="w-3.5 h-3.5 text-muted-foreground/70" />{" "}
														01.1.1_High Voltage
													</div>
													<span className="text-[9px] text-muted-foreground/70">2</span>
												</div>
												<div className="flex items-center justify-between px-1 py-1 rounded bg-blue-500/10 cursor-pointer text-info font-medium">
													<div className="flex items-center gap-1.5">
														<FolderOpen className="w-3.5 h-3.5 text-info fill-blue-400/20" />{" "}
														01.1.2_Low Voltage
													</div>
													<span className="text-[9px] text-info">8</span>
												</div>
												<div className="flex items-center justify-between px-1 py-1 rounded hover:bg-card cursor-pointer text-muted-foreground">
													<div className="flex items-center gap-1.5">
														<FolderOpen className="w-3.5 h-3.5 text-muted-foreground/70" />{" "}
														01.1.3_UPS & Emergency
													</div>
													<span className="text-[9px] text-muted-foreground/70">3</span>
												</div>
											</div>
											{[
												"01.2_Lighting",
												"01.3_Lightning Protection",
												"01.4_Earthing & Bonding",
												"01.5_Load Calculations",
												"01.6_Arc Flash Studies",
												"01.7_Panel Schedules",
												"01.8_SLD Drawings",
											].map((item) => (
												<div
													key={item}
													className="flex items-center gap-1.5 px-1 py-1 rounded hover:bg-card cursor-pointer text-foreground/90"
												>
													<ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />
													<FolderOpen className="w-3.5 h-3.5 text-muted-foreground" />
													{item}
												</div>
											))}
										</div>
										{[
											"02_Fire Alarm & Life Safety",
											"03_Security & ELV",
											"04_Mechanical & HVAC",
											"05_Structural",
											"06_BIM Models",
											"07_Reports & Submittals",
											"08_Standards & References",
											"09_Correspondence",
											"10_As-Built Documents",
										].map((item) => (
											<div
												key={item}
												className="flex items-center gap-1.5 px-1 py-1 rounded hover:bg-card cursor-pointer text-foreground/90"
											>
												<ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />
												<FolderOpen className="w-3.5 h-3.5 text-muted-foreground" />
												{item}
											</div>
										))}
									</div>
								</div>
							</div>
						</div>
					</ScrollArea>

					<div className="p-3 border-t border-slate-800 bg-card">
						<div className="flex gap-2 mb-3">
							<Button
								variant="outline"
								size="sm"
								className="h-7 text-[10px] flex-1 border-border hover:bg-card"
							>
								<Plus className="w-3 h-3 mr-1" /> Folder
							</Button>
							<Button
								variant="outline"
								size="sm"
								className="h-7 text-[10px] flex-1 border-border hover:bg-card"
							>
								<Upload className="w-3 h-3 mr-1" /> Files
							</Button>
						</div>
						<div className="space-y-1">
							<div className="flex justify-between text-[10px] text-muted-foreground">
								<span>Storage</span>
								<span>4.7 GB / 50 GB</span>
							</div>
							<div className="h-1.5 w-full bg-card rounded-full overflow-hidden">
								<div
									className="h-full bg-blue-500"
									style={{ width: "9.4%" }}
								></div>
							</div>
						</div>
					</div>
				</div>

				{/* Main File List */}
				<div className="flex-1 flex flex-col min-w-0 bg-background">
					<div className="flex-1 overflow-auto relative">
						<table className="w-full text-left text-[11px] whitespace-nowrap">
							<thead className="sticky top-0 bg-card border-b border-slate-800 text-muted-foreground z-10">
								<tr>
									<th className="w-8 px-4 py-2 font-medium">
										<input
											type="checkbox"
											className="rounded border-border bg-card accent-blue-500"
										/>
									</th>
									<th className="w-8 px-2 py-2 font-medium"></th>
									<th className="px-4 py-2 font-medium cursor-pointer hover:text-foreground">
										Name <ChevronDown className="w-3 h-3 inline-block" />
									</th>
									<th className="px-4 py-2 font-medium cursor-pointer hover:text-foreground">
										Type
									</th>
									<th className="px-4 py-2 font-medium cursor-pointer hover:text-foreground">
										Size
									</th>
									<th className="px-4 py-2 font-medium cursor-pointer hover:text-foreground">
										Revision
									</th>
									<th className="px-4 py-2 font-medium cursor-pointer hover:text-foreground">
										Modified
									</th>
									<th className="px-4 py-2 font-medium cursor-pointer hover:text-foreground">
										Modified By
									</th>
									<th className="px-4 py-2 font-medium cursor-pointer hover:text-foreground">
										Status
									</th>
									<th className="px-4 py-2 font-medium cursor-pointer hover:text-foreground">
										Approval
									</th>
									<th className="px-4 py-2 font-medium"></th>
								</tr>
							</thead>
							<tbody className="divide-y divide-slate-800/50">
								{files.map((f) => (
									<tr
										key={f.id}
										className={`group cursor-pointer ${selectedFileId === f.id ? "bg-blue-500/10 hover:bg-blue-500/15" : "hover:bg-muted/50"}`}
										onClick={() => setSelectedFileId(f.id)}
									>
										<td className="px-4 py-2.5">
											<input
												type="checkbox"
												checked={selectedFileId === f.id}
												readOnly
												className="rounded border-border bg-card accent-blue-500"
											/>
										</td>
										<td className="px-2 py-2.5">
											{getFileIcon(f.type, "w-4 h-4")}
										</td>
										<td className="px-4 py-2.5 font-medium text-foreground truncate max-w-[200px]">
											{f.name}
										</td>
										<td className="px-4 py-2.5 text-muted-foreground">{f.type}</td>
										<td className="px-4 py-2.5 text-muted-foreground">{f.size}</td>
										<td className="px-4 py-2.5 text-muted-foreground">{f.rev}</td>
										<td className="px-4 py-2.5 text-muted-foreground">{f.date}</td>
										<td className="px-4 py-2.5">
											<div className="flex items-center gap-1.5 text-foreground/90">
												<div className="w-5 h-5 rounded-full bg-card flex items-center justify-center text-[9px] font-bold border border-border">
													{f.author
														.split(" ")
														.map((n) => n[0])
														.join("")
														.substring(0, 2)}
												</div>
												{f.author}
											</div>
										</td>
										<td className="px-4 py-2.5">
											<Badge
												variant="outline"
												className={`h-5 text-[9px] px-1.5 ${getStatusColor(f.status)}`}
											>
												{f.status}{" "}
												{f.status === "Approved"
													? "✓"
													: f.status === "In Review"  // NOSONAR: typescript:S3358
														? "⏳"
														: "✏"}
											</Badge>
										</td>
										<td className="px-4 py-2.5">
											<Badge
												variant="outline"
												className={`h-5 text-[9px] px-1.5 ${getApprovalColor(f.approval)}`}
											>
												{f.approval}
											</Badge>
										</td>
										<td className="px-4 py-2.5 text-right opacity-0 group-hover:opacity-100 transition-opacity">
											<Button
												variant="ghost"
												size="icon"
												className="h-6 w-6 text-muted-foreground hover:text-foreground"
											>
												<MoreHorizontal className="w-4 h-4" />
											</Button>
										</td>
									</tr>
								))}
							</tbody>
						</table>
					</div>

					{/* Bottom Bar */}
					<div className="h-8 border-t border-slate-800 bg-card flex items-center justify-between px-4 text-[10px] text-muted-foreground shrink-0">
						<div className="flex items-center gap-3">
							<span>
								15 files | {selectedFileId ? "1 selected" : "0 selected"} |
								Total: 291.9 MB
							</span>
							<Separator orientation="vertical" className="h-3 bg-secondary" />
							<span>
								Project: Tower-B | 01.1.2_Low Voltage |{" "}
								<span className="text-info">Filter active</span>
							</span>
						</div>
						<div className="flex items-center gap-2">
							<span className="hover:text-foreground cursor-pointer">
								Bulk Download
							</span>
							<span className="hover:text-foreground cursor-pointer">
								Bulk Share
							</span>
							<span className="hover:text-foreground cursor-pointer">
								Generate Transmittal
							</span>
							<span className="hover:text-foreground cursor-pointer">Move</span>
							<span className="text-danger hover:text-slate-400 cursor-pointer">
								Delete
							</span>
						</div>
					</div>
				</div>

				{/* Right Inspector */}
				{selectedFile && (
					<div className="w-[320px] flex flex-col border-l border-slate-800 bg-card shrink-0">
						<ScrollArea className="flex-1">
							<div className="p-4 space-y-6">
								{/* Header */}
								<div className="space-y-3">
									<div className="w-12 h-12 rounded bg-blue-500/10 border border-blue-500/30 flex items-center justify-center">
										{getFileIcon(selectedFile.type, "w-6 h-6")}
									</div>
									<div>
										<h3 className="font-bold text-foreground text-sm leading-tight break-words">
											{selectedFile.name}
										</h3>
										<div className="text-xs text-muted-foreground mt-1">
											{selectedFile.rev} | {selectedFile.size} |{" "}
											{selectedFile.type}
										</div>
									</div>
								</div>

								{/* Status */}
								<div className="space-y-2 bg-background p-3 rounded border border-slate-800">
									<div className="flex justify-between items-center text-xs">
										<span className="text-muted-foreground">Approval</span>
										<Badge
											variant="outline"
											className={`h-5 px-1.5 ${getApprovalColor(selectedFile.approval)}`}
										>
											{selectedFile.approval}
										</Badge>
									</div>
									<div className="flex justify-between items-center text-xs">
										<span className="text-muted-foreground">Review Status</span>
										<Badge
											variant="outline"
											className={`h-5 px-1.5 ${getStatusColor(selectedFile.status)}`}
										>
											{selectedFile.status}
										</Badge>
									</div>
									<div className="flex justify-between items-center text-xs pt-2 border-t border-slate-800">
										<span className="text-muted-foreground">Lock</span>
										<span className="text-foreground/90 flex items-center gap-1">
											<Lock className="w-3 h-3 text-primary" /> Checked out
											by {selectedFile.author}
										</span>
									</div>
								</div>

								{/* Properties */}
								<div>
									<h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
										Properties
									</h4>
									<div className="space-y-1.5 text-xs">
										<div className="grid grid-cols-[100px_1fr] gap-2">
											<span className="text-muted-foreground">Created</span>
											<span className="text-foreground/90">
												Oct 15, 2024 — Ahmed Al-Rashidi
											</span>
										</div>
										<div className="grid grid-cols-[100px_1fr] gap-2">
											<span className="text-muted-foreground">Modified</span>
											<span className="text-foreground/90">
												{selectedFile.date} — {selectedFile.author}
											</span>
										</div>
										<div className="grid grid-cols-[100px_1fr] gap-2">
											<span className="text-muted-foreground">Format</span>
											<span className="text-foreground/90">
												AutoCAD 2024 (.dwg)
											</span>
										</div>
										<div className="grid grid-cols-[100px_1fr] gap-2">
											<span className="text-muted-foreground">SHA-256</span>
											<span className="text-muted-foreground font-mono text-[10px]">
												a3f7...d291
											</span>
										</div>
										<div className="grid grid-cols-[100px_1fr] gap-2">
											<span className="text-muted-foreground">Project Code</span>
											<span className="text-foreground/90">TWR-B-EL-MS-001</span>
										</div>
									</div>
								</div>

								{/* Revision History */}
								<div>
									<h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
										Revision History
									</h4>
									<div className="relative border-l border-border ml-2 space-y-4 pb-2">
										<div className="relative pl-4">
											<div className="absolute w-2 h-2 bg-blue-500 rounded-full -left-[4.5px] top-1.5"></div>
											<div className="text-xs">
												<span className="font-semibold text-foreground">
													Rev 14
												</span>{" "}
												<span className="text-muted-foreground">
													— {selectedFile.date}
												</span>
											</div>
											<div className="text-[11px] text-muted-foreground mt-0.5">
												{selectedFile.author} — "Final compliance corrections"
											</div>
											<Badge className="bg-blue-500/20 text-info border-blue-500/30 h-4 px-1 text-[8px] mt-1 hover:bg-blue-500/20">
												CURRENT
											</Badge>
										</div>
										<div className="relative pl-4">
											<div className="absolute w-2 h-2 bg-slate-600 rounded-full -left-[4.5px] top-1.5"></div>
											<div className="text-xs">
												<span className="font-semibold text-foreground/90">
													Rev 13
												</span>{" "}
												<span className="text-muted-foreground">
													— Yesterday 16:45
												</span>
											</div>
											<div className="text-[11px] text-muted-foreground mt-0.5">
												Sarah — "Updated panel LP-3A"
											</div>
										</div>
										<div className="relative pl-4">
											<div className="absolute w-2 h-2 bg-slate-600 rounded-full -left-[4.5px] top-1.5"></div>
											<div className="text-xs">
												<span className="font-semibold text-foreground/90">
													Rev 12
												</span>{" "}
												<span className="text-muted-foreground">— Nov 12 11:20</span>
											</div>
											<div className="text-[11px] text-muted-foreground mt-0.5">
												Ahmed — "Added coordination notes"
											</div>
										</div>
										<div className="relative pl-4">
											<div className="absolute w-2 h-2 bg-green-500 rounded-full -left-[4.5px] top-1.5"></div>
											<div className="text-xs">
												<span className="font-semibold text-foreground/90">
													Rev 11
												</span>{" "}
												<span className="text-muted-foreground">— Nov 10</span>
											</div>
											<div className="text-[11px] text-muted-foreground mt-0.5">
												Marcus — "Approved for client review"
											</div>
											<Badge className="bg-green-500/20 text-green-400 border-green-500/30 h-4 px-1 text-[8px] mt-1 hover:bg-green-500/20">
												APPROVED
											</Badge>
										</div>
									</div>
									<Button
										variant="ghost"
										className="w-full text-[10px] text-info mt-2 h-6"
									>
										Show all 14 revisions...
									</Button>
								</div>

								{/* Dependencies */}
								<div>
									<h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
										Dependencies
									</h4>
									<div className="bg-background rounded border border-slate-800 p-2">
										<div className="text-xs text-foreground/90 mb-1.5 flex items-center gap-1.5">
											<LinkIcon className="w-3 h-3 text-muted-foreground" /> References
											4 files:
										</div>
										<ul className="text-[10px] text-muted-foreground space-y-1 pl-4 list-disc marker:text-slate-700">
											<li>Tower-B-Panel-Schedule-MDB-A.xlsx</li>
											<li>Tower-B-SLD-Main.dwg</li>
											<li>Tower-B-Load-Calculations.pdf</li>
											<li>LV-Switchgear-Spec.docx</li>
										</ul>
										<Separator className="my-2 bg-card" />
										<div className="text-xs text-foreground/90 flex items-center gap-1.5">
											<LinkIcon className="w-3 h-3 text-muted-foreground" /> Referenced
											by 2 files
										</div>
									</div>
								</div>

								{/* Permissions */}
								<div>
									<h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
										Permissions
									</h4>
									<div className="text-xs space-y-1.5 text-muted-foreground">
										<div className="flex justify-between">
											<span className="text-muted-foreground">Your access:</span>{" "}
											<span className="text-foreground/90">Full Control</span>
										</div>
										<div className="flex justify-between">
											<span className="text-muted-foreground">Team access:</span>{" "}
											<span>Edit (6 users), View (12)</span>
										</div>
										<div className="flex justify-between">
											<span className="text-muted-foreground">External:</span>{" "}
											<span>View only (3 clients)</span>
										</div>
									</div>
								</div>
							</div>
						</ScrollArea>

						{/* Actions Grid */}
						<div className="p-4 border-t border-slate-800 bg-background space-y-2">
							<div className="grid grid-cols-2 gap-2">
								<Button
									size="sm"
									className="h-7 text-xs bg-blue-600 hover:bg-blue-500"
								>
									Open
								</Button>
								<Button
									size="sm"
									variant="outline"
									className="h-7 text-xs border-border hover:bg-card"
								>
									Download
								</Button>
								<Button
									size="sm"
									variant="outline"
									className="h-7 text-xs border-border hover:bg-card"
								>
									Share
								</Button>
								<Button
									size="sm"
									variant="outline"
									className="h-7 text-xs border-border hover:bg-card"
								>
									Copy Link
								</Button>
							</div>
							<Separator className="bg-card" />
							<div className="grid grid-cols-2 gap-2">
								<Button
									size="sm"
									variant="outline"
									className="h-7 text-xs border-border hover:bg-card text-primary hover:text-orange-300"
								>
									Check Out
								</Button>
								<Button
									size="sm"
									variant="outline"
									className="h-7 text-xs border-border hover:bg-card"
								>
									New Revision
								</Button>
								<Button
									size="sm"
									variant="outline"
									className="h-7 text-xs border-border hover:bg-card text-[10px]"
								>
									View History
								</Button>
								<Button
									size="sm"
									variant="outline"
									className="h-7 text-xs border-border hover:bg-card text-[10px]"
								>
									Compare Revs
								</Button>
							</div>
							<Separator className="bg-card" />
							<Button
								size="sm"
								variant="outline"
								className="w-full h-7 text-xs border-border hover:bg-card text-green-400"
							>
								Submit for Review
							</Button>
							<Button
								size="sm"
								variant="outline"
								className="w-full h-7 text-xs border-border hover:bg-card"
							>
								Generate Transmittal
							</Button>
							<Button
								size="sm"
								variant="ghost"
								className="w-full h-7 text-xs text-muted-foreground hover:text-foreground/90 hover:bg-card"
							>
								<Archive className="w-3.5 h-3.5 mr-1.5" /> Archive
							</Button>
						</div>
					</div>
				)}
			</div>
		</div>
	);
}
