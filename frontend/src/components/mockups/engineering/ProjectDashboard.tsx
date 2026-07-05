import {
	Activity,
	AlertTriangle,
	ArrowUpRight,
	BarChart2,
	CheckCircle,
	CheckCircle2,
	Clock,
	FileDown,
	FolderOpen,
	GitCommit,
	LayoutDashboard,
	Maximize,
	MessageSquare,
	Search,
	Settings,
	Share2,
	ShieldAlert,
	Users,
	Zap,
} from "lucide-react";
import type React from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

export function ProjectDashboard() {
	return (
		<div className="flex flex-col h-screen w-screen overflow-hidden bg-background text-foreground dark font-sans">
			{/* Header */}
			<div className="h-16 flex items-center justify-between px-6 border-b bg-card shrink-0">
				<div className="flex items-center gap-4">
					<div className="w-10 h-10 rounded bg-blue-500 flex items-center justify-center shadow-lg shadow-blue-500/20">
						<LayoutDashboard className="h-5 w-5 text-white" />
					</div>
					<div>
						<h1 className="font-bold tracking-wide text-lg leading-tight">
							Project Command Center
						</h1>
						<div className="text-xs text-muted-foreground flex items-center gap-2 mt-0.5">
							<span className="font-semibold text-slate-300">
								Tower-B Office Complex
							</span>
							<span>•</span>
							<span>
								Phase:{" "}
								<span className="text-blue-400 font-medium">
									Construction Documents
								</span>
							</span>
							<span>•</span>
							<span>Due: Dec 15, 2024</span>
						</div>
					</div>
				</div>

				<div className="flex items-center gap-4">
					<div className="text-[10px] font-mono text-emerald-400 flex items-center gap-1.5 animate-pulse">
						<div className="w-1.5 h-1.5 rounded-full bg-emerald-500"></div> Last
						updated: 2 mins ago
					</div>
					<div className="flex gap-2">
						<Button variant="outline" size="sm" className="h-8 text-xs bg-card">
							<BarChart2 className="h-3.5 w-3.5 mr-1.5" /> Add Widget
						</Button>
						<Button variant="outline" size="sm" className="h-8 text-xs bg-card">
							<FileDown className="h-3.5 w-3.5 mr-1.5" /> Export Dashboard
						</Button>
						<Button variant="outline" size="sm" className="h-8 text-xs bg-card">
							<Share2 className="h-3.5 w-3.5 mr-1.5" /> Share
						</Button>
						<Button variant="ghost" size="icon" className="h-8 w-8">
							<Maximize className="h-4 w-4" />
						</Button>
					</div>
				</div>
			</div>

			<ScrollArea className="flex-1 bg-[#0a0a0f]">
				<div className="p-6 space-y-6 max-w-[1600px] mx-auto">
					{/* Top KPI Row */}
					<div className="grid grid-cols-4 gap-4">
						{/* Card 1 */}
						<div className="bg-card/50 border border-slate-800 rounded-xl p-5 shadow-lg backdrop-blur-sm">
							<div className="flex justify-between items-start mb-2">
								<div className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
									Overall Progress
								</div>
								<Activity className="h-4 w-4 text-blue-400" />
							</div>
							<div className="flex items-end gap-3 mb-3">
								<div className="text-4xl font-bold font-mono tracking-tighter">
									73%
								</div>
								<Badge className="mb-1 bg-emerald-500/10 text-emerald-400 border-emerald-500/20 hover:bg-emerald-500/10">
									On Schedule
								</Badge>
							</div>
							<div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden mb-2">
								<div
									className="h-full bg-blue-500 rounded-full"
									style={{ width: "73%" }}
								></div>
							</div>
							<div className="text-xs text-muted-foreground">
								847 of 1,162 tasks complete
							</div>
						</div>

						{/* Card 2 */}
						<div className="bg-card/50 border border-slate-800 rounded-xl p-5 shadow-lg backdrop-blur-sm">
							<div className="flex justify-between items-start mb-2">
								<div className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
									Compliance Score
								</div>
								<ShieldAlert className="h-4 w-4 text-emerald-400" />
							</div>
							<div className="flex items-end gap-3 mb-3">
								<div className="text-4xl font-bold font-mono tracking-tighter text-emerald-400">
									94.7<span className="text-2xl">%</span>
								</div>
								<div className="text-xs font-mono text-emerald-400 flex items-center mb-1 bg-emerald-500/10 px-1.5 py-0.5 rounded border border-emerald-500/20">
									<ArrowUpRight className="h-3 w-3 mr-0.5" /> 2.1%
								</div>
							</div>
							<div className="flex items-center gap-2 text-xs">
								<Badge className="bg-red-500 text-white hover:bg-red-600 border-transparent shadow-[0_0_10px_rgba(239,68,68,0.5)]">
									3 Critical Issues
								</Badge>
								<span className="text-muted-foreground">needs review</span>
							</div>
						</div>

						{/* Card 3 */}
						<div className="bg-card/50 border border-slate-800 rounded-xl p-5 shadow-lg backdrop-blur-sm">
							<div className="flex justify-between items-start mb-2">
								<div className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
									Active Drawings
								</div>
								<FolderOpen className="h-4 w-4 text-orange-400" />
							</div>
							<div className="flex items-end gap-3 mb-4">
								<div className="text-4xl font-bold font-mono tracking-tighter">
									48
								</div>
								<div className="text-xs text-slate-400 mb-1">Rev 14 latest</div>
							</div>
							<div className="flex h-2 rounded-full overflow-hidden w-full gap-0.5">
								<div
									className="bg-emerald-500 h-full"
									style={{ width: "65%" }}
									title="31 Approved"
								></div>
								<div
									className="bg-orange-400 h-full"
									style={{ width: "25%" }}
									title="12 In Review"
								></div>
								<div
									className="bg-slate-600 h-full"
									style={{ width: "10%" }}
									title="5 Draft"
								></div>
							</div>
							<div className="flex justify-between text-[10px] text-muted-foreground mt-1.5 font-mono">
								<span>31 Approved</span>
								<span>12 Review</span>
								<span>5 Draft</span>
							</div>
						</div>

						{/* Card 4 */}
						<div className="bg-card/50 border border-slate-800 rounded-xl p-5 shadow-lg backdrop-blur-sm">
							<div className="flex justify-between items-start mb-2">
								<div className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
									Team Activity
								</div>
								<Users className="h-4 w-4 text-purple-400" />
							</div>
							<div className="flex items-end gap-3 mb-3">
								<div className="text-2xl font-bold">5 Online Now</div>
							</div>
							<div className="flex -space-x-2 mb-3">
								<Avatar initials="AH" color="bg-blue-600" />
								<Avatar initials="SJ" color="bg-emerald-600" />
								<Avatar initials="MK" color="bg-purple-600" />
								<Avatar initials="FT" color="bg-orange-600" />
								<Avatar initials="JD" color="bg-cyan-600" />
							</div>
							<div className="text-xs text-muted-foreground flex justify-between items-center">
								<span>
									<span className="text-foreground font-semibold">23</span>{" "}
									changes today
								</span>
								<span className="font-mono text-[10px]">Last: 4m ago</span>
							</div>
						</div>
					</div>

					{/* Main Grid */}
					<div className="grid grid-cols-12 gap-6">
						{/* LEFT COLUMN - 7 cols */}
						<div className="col-span-7 space-y-6">
							{/* Widget 1: Task Progress */}
							<Widget
								title="Task Progress by Discipline"
								icon={<BarChart2 className="w-4 h-4" />}
							>
								<div className="space-y-4 py-2">
									<ProgressBar
										label="Structural"
										percent={91}
										color="bg-emerald-500"
										count="142/156"
									/>
									<ProgressBar
										label="Fire Alarm"
										percent={84}
										color="bg-emerald-400"
										count="89/106"
									/>
									<ProgressBar
										label="Electrical"
										percent={78}
										color="bg-blue-500"
										count="312/400"
									/>
									<ProgressBar
										label="BIM Modeling"
										percent={70}
										color="bg-blue-400"
										count="140/200"
									/>
									<ProgressBar
										label="Mechanical"
										percent={65}
										color="bg-orange-400"
										count="130/200"
									/>
									<ProgressBar
										label="Civil"
										percent={45}
										color="bg-slate-500"
										count="45/100"
									/>
								</div>
							</Widget>

							{/* Widget 2: Timeline */}
							<Widget
								title="Recent Activity Timeline"
								icon={<Clock className="w-4 h-4" />}
							>
								<div className="relative pl-4 space-y-6 before:absolute before:inset-0 before:ml-5 before:-translate-x-px md:before:mx-auto md:before:translate-x-0 before:h-full before:w-0.5 before:bg-gradient-to-b before:from-transparent before:via-slate-700 before:to-transparent pt-2 pb-2">
									<TimelineItem
										time="14 min ago"
										user="Ahmed"
										icon={<ShieldAlert className="w-3.5 h-3.5 text-white" />}
										color="bg-red-500"
										text="Compliance check run — 3 critical issues flagged in Fire Alarm."
									/>
									<TimelineItem
										time="1h ago"
										user="Sarah"
										icon={<FileDown className="w-3.5 h-3.5 text-white" />}
										color="bg-blue-500"
										text="Rev 14 Electrical plan submitted for review."
									/>
									<TimelineItem
										time="2h ago"
										user="System"
										icon={
											<AlertTriangle className="w-3.5 h-3.5 text-slate-800" />
										}
										color="bg-orange-400"
										text="Clash detection complete: 5 new clashes in MEP vs Structural."
									/>
									<TimelineItem
										time="3h ago"
										user="James"
										icon={<Zap className="w-3.5 h-3.5 text-white" />}
										color="bg-yellow-500"
										text="Arc flash labels generated for panels MDB-A, MDB-B."
									/>
									<TimelineItem
										time="4h ago"
										user="Ahmed"
										icon={<Activity className="w-3.5 h-3.5 text-white" />}
										color="bg-blue-400"
										text="Load calculation updated — total demand increased 3.2%."
									/>
									<TimelineItem
										time="5h ago"
										user="System"
										icon={<GitCommit className="w-3.5 h-3.5 text-white" />}
										color="bg-emerald-500"
										text="BIM model automatically synchronized with Revit central file."
									/>
								</div>
							</Widget>

							{/* Widget 3: Milestones */}
							<Widget
								title="Upcoming Milestones"
								icon={<CheckCircle2 className="w-4 h-4" />}
							>
								<div className="overflow-hidden border border-slate-800 rounded-lg">
									<table className="w-full text-left text-sm">
										<thead className="bg-slate-800/50 text-slate-400 text-xs uppercase tracking-wider font-semibold border-b border-slate-700">
											<tr>
												<th className="px-4 py-3">Milestone</th>
												<th className="px-4 py-3">Due Date</th>
												<th className="px-4 py-3">Status</th>
												<th className="px-4 py-3">Owner</th>
											</tr>
										</thead>
										<tbody className="divide-y divide-slate-800 bg-card/30">
											<tr className="hover:bg-muted/50 transition-colors">
												<td className="px-4 py-3 font-medium">
													Electrical CD submission
												</td>
												<td className="px-4 py-3 font-mono text-xs text-muted-foreground">
													Nov 30
												</td>
												<td className="px-4 py-3">
													<Badge className="bg-emerald-500/10 text-emerald-400 border-emerald-500/20">
														On Track
													</Badge>
												</td>
												<td className="px-4 py-3 text-muted-foreground">
													Ahmed
												</td>
											</tr>
											<tr className="hover:bg-muted/50 transition-colors">
												<td className="px-4 py-3 font-medium">
													Fire alarm shop drawings
												</td>
												<td className="px-4 py-3 font-mono text-xs text-muted-foreground">
													Dec 05
												</td>
												<td className="px-4 py-3">
													<Badge className="bg-orange-500/10 text-orange-400 border-orange-500/20">
														At Risk
													</Badge>
												</td>
												<td className="px-4 py-3 text-muted-foreground">
													Fatima
												</td>
											</tr>
											<tr className="hover:bg-muted/50 transition-colors">
												<td className="px-4 py-3 font-medium">
													AHJ permit application
												</td>
												<td className="px-4 py-3 font-mono text-xs text-muted-foreground">
													Dec 10
												</td>
												<td className="px-4 py-3">
													<Badge className="bg-emerald-500/10 text-emerald-400 border-emerald-500/20">
														On Track
													</Badge>
												</td>
												<td className="px-4 py-3 text-muted-foreground">
													James
												</td>
											</tr>
											<tr className="hover:bg-muted/50 transition-colors">
												<td className="px-4 py-3 font-medium">
													100% CD complete
												</td>
												<td className="px-4 py-3 font-mono text-xs text-muted-foreground">
													Dec 15
												</td>
												<td className="px-4 py-3">
													<Badge className="bg-emerald-500/10 text-emerald-400 border-emerald-500/20">
														On Track
													</Badge>
												</td>
												<td className="px-4 py-3 text-muted-foreground">
													Ahmed
												</td>
											</tr>
										</tbody>
									</table>
								</div>
							</Widget>
						</div>

						{/* RIGHT COLUMN - 5 cols */}
						<div className="col-span-5 space-y-6">
							{/* Widget 4: Issue Tracker */}
							<Widget
								title="Issue Tracker Summary"
								icon={<ShieldAlert className="w-4 h-4" />}
							>
								<div className="flex flex-col items-center justify-center py-6">
									{/* CSS Donut Chart */}
									<div
										className="relative w-48 h-48 rounded-full bg-slate-800 flex items-center justify-center mb-6"
										style={{
											background:
												"conic-gradient(#ef4444 0% 25%, #f97316 25% 75%, #eab308 75% 100%)",
										}}
									>
										<div className="w-36 h-36 bg-card rounded-full flex flex-col items-center justify-center shadow-inner">
											<div className="text-3xl font-bold font-mono">47</div>
											<div className="text-xs text-muted-foreground uppercase tracking-wider font-semibold">
												Total Issues
											</div>
										</div>
									</div>

									<div className="w-full grid grid-cols-3 gap-2">
										<div className="bg-red-500/10 border border-red-500/20 rounded p-2 text-center">
											<div className="text-lg font-bold text-red-500 font-mono">
												12
											</div>
											<div className="text-[10px] text-muted-foreground uppercase">
												Critical
											</div>
										</div>
										<div className="bg-orange-500/10 border border-orange-500/20 rounded p-2 text-center">
											<div className="text-lg font-bold text-orange-400 font-mono">
												23
											</div>
											<div className="text-[10px] text-muted-foreground uppercase">
												Major
											</div>
										</div>
										<div className="bg-yellow-500/10 border border-yellow-500/20 rounded p-2 text-center">
											<div className="text-lg font-bold text-yellow-400 font-mono">
												12
											</div>
											<div className="text-[10px] text-muted-foreground uppercase">
												Minor
											</div>
										</div>
									</div>
								</div>
							</Widget>

							{/* Widget 5: File Size */}
							<Widget
								title="Project Storage"
								icon={<FolderOpen className="w-4 h-4" />}
							>
								<div className="py-2">
									<div className="flex justify-between items-end mb-2">
										<div className="text-2xl font-bold font-mono">
											4.7{" "}
											<span className="text-sm text-muted-foreground font-sans">
												GB
											</span>
										</div>
										<div className="text-xs text-muted-foreground font-mono">
											Total: 50.0 GB
										</div>
									</div>
									<div className="h-3 w-full bg-slate-800 rounded-full flex overflow-hidden mb-4">
										<div
											className="bg-blue-500 h-full"
											style={{ width: "45%" }}
											title="DWG"
										></div>
										<div
											className="bg-orange-400 h-full"
											style={{ width: "35%" }}
											title="RVT"
										></div>
										<div
											className="bg-red-400 h-full"
											style={{ width: "15%" }}
											title="PDF"
										></div>
										<div
											className="bg-slate-500 h-full"
											style={{ width: "5%" }}
											title="Other"
										></div>
									</div>
									<div className="grid grid-cols-2 gap-y-2 text-xs">
										<div className="flex items-center gap-2">
											<div className="w-2 h-2 rounded-full bg-blue-500"></div>
											<span className="text-muted-foreground w-10">DWG</span>
											<span className="font-mono font-medium">2.1 GB</span>
										</div>
										<div className="flex items-center gap-2">
											<div className="w-2 h-2 rounded-full bg-orange-400"></div>
											<span className="text-muted-foreground w-10">RVT</span>
											<span className="font-mono font-medium">1.8 GB</span>
										</div>
										<div className="flex items-center gap-2">
											<div className="w-2 h-2 rounded-full bg-red-400"></div>
											<span className="text-muted-foreground w-10">PDF</span>
											<span className="font-mono font-medium">0.6 GB</span>
										</div>
										<div className="flex items-center gap-2">
											<div className="w-2 h-2 rounded-full bg-slate-500"></div>
											<span className="text-muted-foreground w-10">Other</span>
											<span className="font-mono font-medium">0.2 GB</span>
										</div>
									</div>
								</div>
							</Widget>

							{/* Widget 6: Engineering Hours */}
							<Widget
								title="Engineering Hours (Week)"
								icon={<Clock className="w-4 h-4" />}
							>
								<div className="space-y-3 py-1">
									<HourRow
										label="Electrical Design"
										used={142}
										budget={160}
										color="bg-blue-500"
									/>
									<HourRow
										label="BIM Coordination"
										used={38}
										budget={40}
										color="bg-orange-400"
									/>
									<HourRow
										label="Compliance Review"
										used={12}
										budget={20}
										color="bg-emerald-500"
									/>
									<HourRow
										label="Report Generation"
										used={8}
										budget={10}
										color="bg-purple-500"
									/>
									<div className="pt-3 border-t border-slate-800 mt-2 flex justify-between items-center">
										<span className="font-bold text-sm">Total Hours</span>
										<span className="font-mono font-bold text-blue-400">
											200 / 230h
										</span>
									</div>
								</div>
							</Widget>

							{/* Widget 7: Collaboration Stats */}
							<Widget
								title="Collaboration Pulse"
								icon={<MessageSquare className="w-4 h-4" />}
							>
								<div className="grid grid-cols-2 gap-4">
									<div className="bg-card/50 border border-slate-800 p-3 rounded-lg text-center">
										<div className="text-2xl font-bold font-mono text-emerald-400 mb-1">
											83%
										</div>
										<div className="text-[10px] text-muted-foreground uppercase">
											Comments Resolved
										</div>
										<div className="text-[10px] font-mono text-slate-500 mt-1">
											34 of 41
										</div>
									</div>
									<div className="bg-card/50 border border-slate-800 p-3 rounded-lg text-center">
										<div className="text-2xl font-bold font-mono text-orange-400 mb-1">
											3
										</div>
										<div className="text-[10px] text-muted-foreground uppercase">
											Approvals Pending
										</div>
										<div className="text-[10px] font-mono text-slate-500 mt-1">
											Due today
										</div>
									</div>
								</div>
							</Widget>
						</div>
					</div>
				</div>
			</ScrollArea>
		</div>
	);
}

function Widget({
	title,
	icon,
	children,
}: {
	title: string;
	icon: React.ReactNode;
	children: React.ReactNode;
}) {
	return (
		<div className="bg-card border border-slate-800 rounded-xl p-5 shadow-sm">
			<div className="flex items-center gap-2 mb-4 pb-3 border-b border-slate-800">
				<div className="p-1.5 rounded-md bg-slate-800 text-slate-300">
					{icon}
				</div>
				<h3 className="font-bold text-sm text-slate-100 tracking-wide uppercase">
					{title}
				</h3>
			</div>
			{children}
		</div>
	);
}

function ProgressBar({
	label,
	percent,
	color,
	count,
}: {
	label: string;
	percent: number;
	color: string;
	count: string;
}) {
	return (
		<div>
			<div className="flex justify-between items-end mb-1.5">
				<span className="text-xs font-medium text-slate-300">{label}</span>
				<span className="text-[10px] font-mono text-muted-foreground">
					{count} ({percent}%)
				</span>
			</div>
			<div className="w-full h-2 bg-slate-800 rounded-full overflow-hidden">
				<div
					className={`h-full rounded-full ${color}`}
					style={{ width: `${percent}%` }}
				></div>
			</div>
		</div>
	);
}

function TimelineItem({
	time,
	user,
	icon,
	color,
	text,
}: {
	time: string;
	user: string;
	icon: React.ReactNode;
	color: string;
	text: string;
}) {
	return (
		<div className="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group is-active">
			<div
				className={`flex items-center justify-center w-8 h-8 rounded-full border-4 border-card shrink-0 md:order-1 md:group-odd:-translate-x-1/2 md:group-even:translate-x-1/2 shadow-md ${color}`}
			>
				{icon}
			</div>
			<div className="w-[calc(100%-4rem)] md:w-[calc(50%-2.5rem)] p-3 rounded-lg border border-slate-800 bg-card/50 shadow-sm ml-4 md:ml-0 md:group-odd:mr-4 md:group-even:ml-4">
				<div className="flex items-center justify-between mb-1">
					<span className="font-bold text-xs text-slate-200">{user}</span>
					<span className="text-[10px] font-mono text-slate-500">{time}</span>
				</div>
				<div className="text-xs text-slate-400 leading-relaxed">{text}</div>
			</div>
		</div>
	);
}

function HourRow({
	label,
	used,
	budget,
	color,
}: {
	label: string;
	used: number;
	budget: number;
	color: string;
}) {
	const percent = Math.min(100, Math.round((used / budget) * 100));
	const isOver = used > budget;

	return (
		<div className="flex items-center justify-between gap-4">
			<span className="text-xs text-slate-300 w-32 truncate">{label}</span>
			<div className="flex-1 h-1.5 bg-slate-800 rounded-full overflow-hidden">
				<div
					className={`h-full rounded-full ${isOver ? "bg-red-500" : color}`}
					style={{ width: `${percent}%` }}
				></div>
			</div>
			<span
				className={`text-[10px] font-mono w-16 text-right ${isOver ? "text-red-400 font-bold" : "text-muted-foreground"}`}
			>
				{used}/{budget}h
			</span>
		</div>
	);
}

function Avatar({ initials, color }: { initials: string; color: string }) {
	return (
		<div
			className={`w-8 h-8 rounded-full border-2 border-card flex items-center justify-center text-[10px] font-bold text-white shadow-sm ${color} z-10 hover:z-20 hover:scale-110 transition-transform cursor-pointer`}
		>
			{initials}
		</div>
	);
}
