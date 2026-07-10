
import {
	Archive,
	Box,
	ChevronRight,
	Clock,
	Cloud,
	Database,
	Download,
	FileText,
	FolderOpen,
	FolderPlus,
	History,
	Layout,
	LayoutTemplate,
	Link as LinkIcon,
	MoreHorizontal,
	RefreshCw,
	Search,
	Upload,
	X,
} from "lucide-react";
import type React from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

export function FileManager() {
	return (
		<div className="w-screen h-screen bg-background/80 backdrop-blur-md flex items-center justify-center p-8 font-sans dark text-foreground">
			<div className="w-full max-w-[1200px] h-full max-h-[800px] bg-[#0f1115] border border-white/10 shadow-2xl rounded-md flex flex-col overflow-hidden ring-1 ring-primary/20">
				{/* Header */}
				<div className="h-16 border-b border-white/10 flex items-center justify-between px-6 bg-[#15181e]">
					<div className="flex flex-col">
						<h1 className="text-lg font-bold text-white tracking-wide">
							File Management Center
						</h1>
						<div className="flex items-center text-xs text-muted-foreground gap-1 mt-0.5">
							<span className="hover:text-white cursor-pointer">
								NexusCAD Pro
							</span>
							<ChevronRight className="w-3 h-3" />
							<span className="hover:text-white cursor-pointer">Projects</span>
							<ChevronRight className="w-3 h-3" />
							<span className="text-primary font-medium">
								Tower-B Office Complex
							</span>
						</div>
					</div>

					<div className="flex items-center gap-2">
						<div className="flex gap-1 bg-[#0a0a0c] p-1 rounded-md border border-white/5 mr-4">
							<ToolbarBtn icon={<FolderPlus />} label="New" />
							<ToolbarBtn icon={<Upload />} label="Import" />
							<ToolbarBtn icon={<Download />} label="Export" />
							<Separator
								orientation="vertical"
								className="h-6 mx-1 bg-white/10"
							/>
							<ToolbarBtn icon={<RefreshCw />} label="Convert" />
							<ToolbarBtn icon={<Database />} label="Backup" />
						</div>
						<Button
							variant="ghost"
							size="icon"
							className="h-8 w-8 text-muted-foreground hover:bg-destructive/20 hover:text-destructive rounded-full"
						>
							<X className="w-5 h-5" />
						</Button>
					</div>
				</div>

				<div className="flex flex-1 overflow-hidden">
					{/* Left Sidebar - Navigation */}
					<div className="w-64 border-r border-white/10 bg-[#0a0a0c] flex flex-col">
						<div className="p-4">
							<div className="relative">
								<Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
								<Input
									className="h-9 w-full bg-[#15181e] border-white/10 pl-9 text-xs"
									placeholder="Search files..."
								/>
							</div>
						</div>
						<ScrollArea className="flex-1 px-2">
							<div className="space-y-1 pb-4">
								<NavGroup icon={<Clock />} title="Recent Files" />
								<NavGroup
									icon={<FolderOpen />}
									title="Projects"
									active
									expanded
								>
									<NavItem title="Tower-B Office Complex" active />
									<NavItem title="City Water Treatment Plant" />
									<NavItem title="Highway Bridge Expansion" />
								</NavGroup>
								<NavGroup icon={<Cloud />} title="Cloud Storage" />
								<NavGroup icon={<LayoutTemplate />} title="Templates" />
								<NavGroup icon={<Archive />} title="Archived" />
							</div>
						</ScrollArea>
					</div>

					{/* Main Grid */}
					<div className="flex-1 bg-[#0f1115] flex flex-col">
						<div className="h-12 border-b border-white/5 flex items-center justify-between px-6">
							<div className="text-sm font-medium">Tower-B Office Complex</div>
							<div className="flex gap-2">
								<Badge
									variant="outline"
									className="bg-[#15181e] border-white/10 text-xs text-foreground/90 font-normal"
								>
									All Files
								</Badge>
								<Badge
									variant="outline"
									className="bg-transparent border-transparent text-xs text-muted-foreground font-normal hover:bg-white/5 cursor-pointer"
								>
									DWG
								</Badge>
								<Badge
									variant="outline"
									className="bg-transparent border-transparent text-xs text-muted-foreground font-normal hover:bg-white/5 cursor-pointer"
								>
									RVT
								</Badge>
								<Badge
									variant="outline"
									className="bg-transparent border-transparent text-xs text-muted-foreground font-normal hover:bg-white/5 cursor-pointer"
								>
									PDF
								</Badge>
							</div>
						</div>
						<ScrollArea className="flex-1 p-6">
							<div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
								<FileCard
									name="Tower-B-Electrical-Rev14.dwg"
									type="dwg"
									size="47 MB"
									date="Today, 14:32"
									rev="14"
									status="Approved"
									selected
								/>
								<FileCard
									name="Structural-BIM-Model.rvt"
									type="rvt"
									size="234 MB"
									date="Yesterday"
									rev="8"
									status="In Review"
								/>
								<FileCard
									name="Fire-Alarm-System.dwg"
									type="dwg"
									size="12 MB"
									date="Oct 12, 2023"
									rev="5"
									status="Draft"
								/>
								<FileCard
									name="MEP-Coordination.ifc"
									type="ifc"
									size="89 MB"
									date="Oct 10, 2023"
									rev="3"
									status="Approved"
								/>
								<FileCard
									name="Load-Calculations.xlsx"
									type="xlsx"
									size="2 MB"
									date="Oct 08, 2023"
									rev="11"
									status="Approved"
								/>
								<FileCard
									name="Code-Compliance-Report.pdf"
									type="pdf"
									size="4 MB"
									date="Oct 01, 2023"
									rev="2"
									status="In Review"
								/>
							</div>
						</ScrollArea>
					</div>

					{/* Right Sidebar - Inspector */}
					<div className="w-80 border-l border-white/10 bg-[#15181e] flex flex-col">
						<div className="p-6 border-b border-white/5 flex flex-col items-center justify-center text-center">
							<div className="w-20 h-20 bg-blue-500/10 rounded-md border border-blue-500/30 flex items-center justify-center mb-4">
								<Layout className="w-10 h-10 text-info" />
							</div>
							<h3 className="font-semibold text-white text-sm break-all">
								Tower-B-Electrical-Rev14.dwg
							</h3>
							<div className="text-xs text-muted-foreground mt-1 font-mono">
								AutoCAD Drawing
							</div>
						</div>

						<ScrollArea className="flex-1">
							<div className="p-6 space-y-6">
								{/* Properties */}
								<div className="space-y-3">
									<h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
										Properties
									</h4>
									<PropRow label="Size" value="47.2 MB" />
									<PropRow label="Created" value="Sep 15, 2023" />
									<PropRow label="Modified" value="Today, 14:32" />
									<PropRow label="Author" value="J. Smith" />
									<PropRow label="Checksum" value="a8f2c9...b1" mono />
								</div>

								<Separator className="bg-white/10" />

								{/* Status */}
								<div className="space-y-3">
									<h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
										Workflow
									</h4>
									<div className="flex justify-between items-center">
										<span className="text-xs text-muted-foreground">
											Current Status
										</span>
										<Badge className="bg-emerald-500/10 text-success border-success/30 hover:bg-emerald-500/20">
											Approved
										</Badge>
									</div>
									<div className="flex justify-between items-center mt-2">
										<span className="text-xs text-muted-foreground">
											Collaborators
										</span>
										<div className="flex -space-x-2">
											<div className="w-6 h-6 rounded-full bg-blue-600 border border-[#15181e] text-[8px] flex items-center justify-center font-bold">
												JS
											</div>
											<div className="w-6 h-6 rounded-full bg-primary border border-[#15181e] text-[8px] flex items-center justify-center font-bold">
												AW
											</div>
											<div className="w-6 h-6 rounded-full bg-slate-600 border border-[#15181e] text-[8px] flex items-center justify-center font-bold">
												+2
											</div>
										</div>
									</div>
								</div>

								<Separator className="bg-white/10" />

								{/* Revisions */}
								<div className="space-y-3">
									<h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2 flex items-center gap-2">
										<History className="w-3 h-3" /> History
									</h4>
									<div className="relative pl-3 border-l border-white/10 ml-2 space-y-4">
										<div className="relative">
											<div className="absolute w-2 h-2 bg-primary rounded-full -left-[17px] top-1.5 ring-4 ring-[#15181e]"></div>
											<div className="text-xs font-medium text-white">
												Rev 14{" "}
												<span className="text-primary ml-1">(Current)</span>
											</div>
											<div className="text-[10px] text-muted-foreground">
												Today, 14:32 by J. Smith
											</div>
										</div>
										<div className="relative">
											<div className="absolute w-2 h-2 bg-slate-600 rounded-full -left-[17px] top-1.5 ring-4 ring-[#15181e]"></div>
											<div className="text-xs font-medium text-foreground/90">
												Rev 13
											</div>
											<div className="text-[10px] text-muted-foreground">
												Yesterday by A. Wong
											</div>
										</div>
										<div className="relative">
											<div className="absolute w-2 h-2 bg-slate-600 rounded-full -left-[17px] top-1.5 ring-4 ring-[#15181e]"></div>
											<div className="text-xs font-medium text-foreground/90">
												Rev 12
											</div>
											<div className="text-[10px] text-muted-foreground">
												Oct 12 by J. Smith
											</div>
										</div>
									</div>
								</div>

								<Separator className="bg-white/10" />

								{/* Dependencies */}
								<div className="space-y-3">
									<h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2 flex items-center gap-2">
										<LinkIcon className="w-3 h-3" /> Dependencies
									</h4>
									<div className="bg-[#0a0a0c] border border-white/5 rounded-md p-3">
										<div className="text-xs text-white mb-2">
											References 3 files:
										</div>
										<div className="space-y-2">
											<div className="flex items-center gap-2 text-xs text-muted-foreground">
												<Box className="w-3 h-3 text-primary" />{" "}
												Structural-BIM.rvt
											</div>
											<div className="flex items-center gap-2 text-xs text-muted-foreground">
												<Layout className="w-3 h-3 text-info" />{" "}
												Site-Plan.dwg
											</div>
											<div className="flex items-center gap-2 text-xs text-muted-foreground">
												<FileText className="w-3 h-3 text-success" />{" "}
												Equipment-Specs.xlsx
											</div>
										</div>
									</div>
								</div>
							</div>
						</ScrollArea>

						{/* Actions */}
						<div className="p-4 border-t border-white/5 bg-[#15181e] space-y-2">
							<Button className="w-full text-xs font-semibold bg-primary hover:bg-primary/90 text-primary-foreground h-9">
								Open in Workspace
							</Button>
							<div className="grid grid-cols-2 gap-2">
								<Button
									variant="outline"
									className="w-full text-xs h-8 bg-[#0a0a0c] border-white/10 hover:bg-white/5"
								>
									Convert IFC
								</Button>
								<Button
									variant="outline"
									className="w-full text-xs h-8 bg-[#0a0a0c] border-white/10 hover:bg-white/5"
								>
									Export PDF
								</Button>
							</div>
						</div>
					</div>
				</div>

				{/* Bottom Status Bar */}
				<div className="h-8 border-t border-white/10 bg-[#0a0a0c] flex items-center justify-between px-6 text-[10px] font-mono text-muted-foreground">
					<div className="flex items-center gap-4">
						<div className="flex items-center gap-2">
							<RefreshCw className="w-3 h-3 animate-spin text-primary" />
							<span>Conversion queue: 2 items</span>
						</div>
						<Separator orientation="vertical" className="h-4 bg-white/10" />
						<div className="text-emerald-500">Import validation: Ready</div>
					</div>
					<div>All changes saved to cloud</div>
				</div>
			</div>
		</div>
	);
}

function ToolbarBtn({ icon, label }: { icon: React.ReactNode; label: string }) {
	return (
		<Button
			variant="ghost"
			className="h-8 px-2 flex items-center gap-1.5 text-xs text-muted-foreground hover:text-white hover:bg-white/5"
		>
			<div className="[&>svg]:w-3.5 [&>svg]:h-3.5">{icon}</div>
			<span>{label}</span>
		</Button>
	);
}

function NavGroup({
	icon,
	title,
	active,
	expanded,
	children,
}: {
	icon: React.ReactNode;
	title: string;
	active?: boolean;
	expanded?: boolean;
	children?: React.ReactNode;
}) {
	return (
		<div className="mb-1">
			<div
				className={`flex items-center gap-2 px-3 py-2 rounded-md cursor-pointer ${active ? "bg-white/5 text-white font-medium" : "text-muted-foreground hover:bg-white/5 hover:text-foreground"}`}
			>
				<div
					className={`[&>svg]:w-4 [&>svg]:h-4 ${active ? "text-primary" : ""}`}
				>
					{icon}
				</div>
				<span className="text-sm">{title}</span>
			</div>
			{expanded && children && (
				<div className="ml-5 mt-1 border-l border-white/5 pl-2 space-y-1">
					{children}
				</div>
			)}
		</div>
	);
}

function NavItem({ title, active }: { title: string; active?: boolean }) {
	return (
		<div
			className={`px-3 py-1.5 rounded text-xs cursor-pointer truncate ${active ? "bg-primary/10 text-primary font-medium" : "text-muted-foreground hover:bg-white/5 hover:text-foreground/90"}`}
		>
			{title}
		</div>
	);
}

function FileCard({
	name,
	type,
	size,
	date,
	rev,
	status,
	selected,
}: {
	name: string;
	type: string;
	size: string;
	date: string;
	rev: string;
	status: string;
	selected?: boolean;
}) {
	let Icon = Layout;
	let iconColor = "text-info";
	let iconBg = "bg-blue-400/10 border-blue-400/20";

	if (type === "rvt") {
		Icon = Box;
		iconColor = "text-primary";
		iconBg = "bg-orange-400/10 border-orange-400/20";
	} else if (type === "ifc") {
		Icon = Box;
		iconColor = "text-green-400";
		iconBg = "bg-green-400/10 border-green-400/20";
	} else if (type === "pdf") {
		Icon = FileText;
		iconColor = "text-danger";
		iconBg = "bg-slate-500/10 border-slate-500/20";
	} else if (type === "xlsx") {
		Icon = FileText;
		iconColor = "text-success";
		iconBg = "bg-emerald-400/10 border-emerald-400/20";
	}

	let statusColor = "bg-slate-500/10 text-muted-foreground border-border/30";
	if (status === "Approved")
		statusColor = "bg-emerald-500/10 text-success border-success/30";
	if (status === "In Review")
		statusColor = "bg-primary/10 text-primary border-primary/30";

	return (
		<div
			className={`p-4 rounded-lg border transition-all cursor-pointer group flex flex-col gap-3 ${selected ? "bg-primary/5 border-primary/40 shadow-[0_0_15px_rgba(0,168,255,0.1)] ring-1 ring-primary/20" : "bg-[#15181e] border-white/5 hover:border-white/20 hover:bg-[#1a1d24]"}`}
		>
			<div className="flex justify-between items-start">
				<div
					className={`w-10 h-10 rounded border flex items-center justify-center ${iconBg}`}
				>
					<Icon className={`w-5 h-5 ${iconColor}`} />
				</div>
				<Button
					variant="ghost"
					size="icon"
					className="w-6 h-6 text-muted-foreground opacity-0 group-hover:opacity-100 hover:text-white"
				>
					<MoreHorizontal className="w-4 h-4" />
				</Button>
			</div>

			<div>
				<div
					className="text-sm font-semibold text-white truncate mb-1"
					title={name}
				>
					{name}
				</div>
				<div className="flex items-center gap-2 text-[10px] text-muted-foreground font-mono">
					<span>{size}</span>
					<span>•</span>
					<span>{date}</span>
				</div>
			</div>

			<div className="flex items-center justify-between mt-1 pt-3 border-t border-white/5">
				<div className="flex items-center gap-2 text-xs">
					<Badge
						variant="outline"
						className={`text-[10px] py-0 px-1.5 h-4 ${statusColor}`}
					>
						{status}
					</Badge>
					<span className="text-muted-foreground font-mono">v{rev}</span>
				</div>
				<div className="w-5 h-5 rounded-full bg-blue-600 border border-[#15181e] text-[8px] flex items-center justify-center font-bold text-white">
					JS
				</div>
			</div>
		</div>
	);
}

function PropRow({
	label,
	value,
	mono,
}: {
	label: string;
	value: string;
	mono?: boolean;
}) {
	return (
		<div className="flex justify-between items-center text-xs">
			<span className="text-muted-foreground">{label}</span>
			<span className={`text-white ${mono ? "font-mono text-[10px]" : ""}`}>
				{value}
			</span>
		</div>
	);
}
