
import {
	CheckCircle2,
	Eye,
	FileEdit,
	History,
	Link2,
	MessageSquare,
	Mic,
	MonitorPlay,
	MousePointer2,
	Phone,
	Send,
	Settings,
	UploadCloud,
	UserPlus,
	Users,
	Video,
} from "lucide-react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export function Collaboration() {
	const members = [
		{
			id: 1,
			name: "Ahmed Al-Rashidi",
			role: "Host",
			initials: "AA",
			color: "bg-blue-500",
			status: "online",
			action: "Editing: Electrical Floor 3",
			self: true,
		},
		{
			id: 2,
			name: "Sarah Chen",
			role: "BIM Coord",
			initials: "SC",
			color: "bg-purple-500",
			status: "online",
			action: "Viewing: BIM Model",
		},
		{
			id: 3,
			name: "Marcus Williams",
			role: "Struct. Lead",
			initials: "MW",
			color: "bg-primary",
			status: "away",
			action: "Reviewing: Load Calcs",
		},
		{
			id: 4,
			name: "Fatima Al-Zahra",
			role: "Fire Eng.",
			initials: "FA",
			color: "bg-rose-500",
			status: "online",
			action: "Editing: Fire Alarm Plan",
		},
		{
			id: 5,
			name: "James Okafor",
			role: "Compliance",
			initials: "JO",
			color: "bg-emerald-500",
			status: "online",
			action: "Checking: Compliance",
		},
	];

	return (
		<div className="flex flex-col h-screen w-screen overflow-hidden bg-background text-foreground dark font-sans">
			{/* Header */}
			<div className="h-16 flex items-center justify-between px-6 border-b bg-card shrink-0">
				<div className="flex items-center gap-4">
					<div className="w-10 h-10 rounded-md bg-blue-500/20 flex items-center justify-center border border-blue-500/30">
						<Users className="h-5 w-5 text-info" />
					</div>
					<div>
						<h1 className="font-bold tracking-wide text-lg leading-tight">
							Live Collaboration — Tower-B
						</h1>
						<div className="text-[10px] font-mono text-muted-foreground flex items-center gap-2">
							<span>
								Session: <span className="text-foreground/90">SES-2024-4821</span>
							</span>
							<span>•</span>
							<span className="flex items-center gap-1">
								<div className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse"></div>{" "}
								5 members online
							</span>
							<span>•</span>
							<span>1h 23m elapsed</span>
						</div>
					</div>
				</div>

				<div className="flex items-center gap-3">
					<div className="flex -space-x-2 mr-4">
						{members
							.filter((m) => m.status === "online")
							.map((m) => (
								<Avatar
									key={m.id}
									className={`h-8 w-8 border-2 border-card ring-2 ring-transparent hover:ring-${m.color.split("-")[1]}-400 z-10 transition-all`}
								>
									<AvatarFallback
										className={`${m.color} text-white text-[10px] font-bold`}
									>
										{m.initials}
									</AvatarFallback>
								</Avatar>
							))}
					</div>
					<Button variant="outline" size="sm" className="h-9 gap-1.5">
						<UserPlus className="h-4 w-4" /> Invite
					</Button>
					<Button variant="outline" size="sm" className="h-9 gap-1.5">
						<Link2 className="h-4 w-4" /> Copy Link
					</Button>
					<Separator orientation="vertical" className="h-6" />
					<Button
						variant="default"
						size="sm"
						className="h-9 gap-1.5 bg-emerald-600 hover:bg-emerald-700 text-white border-emerald-500 shadow-[0_0_15px_rgba(16,185,129,0.3)]"
					>
						<Phone className="h-4 w-4" /> Join Voice
					</Button>
				</div>
			</div>

			<div className="flex flex-1 overflow-hidden">
				{/* Left Column - Team Panel */}
				<div className="w-[280px] flex flex-col border-r bg-card/30 shrink-0">
					<div className="p-3 border-b bg-card/50 font-semibold text-sm">
						Session Members
					</div>

					<ScrollArea className="flex-1">
						<div className="p-3 space-y-4">
							<div className="space-y-2">
								{members.map((member) => (
									<div
										key={member.id}
										className="p-2.5 bg-card border border-border/50 rounded-lg hover:border-primary/30 transition-colors cursor-pointer group"
									>
										<div className="flex gap-3 items-center">
											<div className="relative">
												<Avatar className="h-9 w-9">
													<AvatarFallback
														className={`${member.color} text-white text-xs font-bold`}
													>
														{member.initials}
													</AvatarFallback>
												</Avatar>
												<div
													className={`absolute bottom-0 right-0 w-2.5 h-2.5 border-2 border-card rounded-full ${member.status === "online" ? "bg-emerald-500" : "bg-amber-500"}`}
												></div>
											</div>
											<div className="flex-1 min-w-0">
												<div className="flex justify-between items-center mb-0.5">
													<div className="text-sm font-semibold truncate pr-2">
														{member.name}{" "}
														{member.self && (
															<span className="text-muted-foreground font-normal text-xs">
																(You)
															</span>
														)}
													</div>
													<Badge
														variant="outline"
														className="text-[9px] px-1 py-0 h-4 bg-muted/50 whitespace-nowrap shrink-0 border-none"
													>
														{member.role}
													</Badge>
												</div>
												<div className="text-[10px] text-muted-foreground flex items-center gap-1 truncate">
													{member.action.includes("Edit") ? (
														<FileEdit className="h-3 w-3 shrink-0" />
													) : (
														<Eye className="h-3 w-3 shrink-0" />
													)}
													<span className="truncate">{member.action}</span>
												</div>
											</div>
										</div>
									</div>
								))}
							</div>

							<Separator />

							<div>
								<div className="text-xs font-semibold uppercase text-muted-foreground mb-3">
									Voice Call
								</div>
								<div className="bg-card border border-border rounded-lg p-3 relative overflow-hidden">
									<div className="absolute inset-0 bg-emerald-500/5"></div>

									<div className="flex items-center justify-between mb-3 relative z-10">
										<div className="flex items-center gap-2">
											<div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></div>
											<span className="text-xs font-semibold text-success">
												Live (3)
											</span>
										</div>
										<span className="text-[10px] font-mono">42:15</span>
									</div>

									<div className="flex gap-2 mb-4 relative z-10">
										<Avatar className="h-8 w-8 ring-2 ring-emerald-500 ring-offset-2 ring-offset-slate-900">
											<AvatarFallback className="bg-blue-500 text-[10px]">
												AA
											</AvatarFallback>
										</Avatar>
										<Avatar className="h-8 w-8">
											<AvatarFallback className="bg-purple-500 text-[10px]">
												SC
											</AvatarFallback>
										</Avatar>
										<Avatar className="h-8 w-8">
											<AvatarFallback className="bg-emerald-500 text-[10px]">
												JO
											</AvatarFallback>
										</Avatar>
									</div>

									{/* Waveform fake */}
									<div className="flex items-end justify-between h-4 mb-4 gap-[2px] opacity-70 px-2 relative z-10">
										{Array.from({ length: 20 }).map((_, i) => (
											<div
												key={i}
												className="w-1 bg-emerald-500 rounded-t-sm"
												style={{
													height: `${Math.max(10, crypto.getRandomValues(new Uint32Array(1))[0] / 0xFFFFFFFF * 100)}%`,
												}}
											></div>
										))}
									</div>

									<div className="flex justify-center gap-2 relative z-10">
										<Button
											variant="secondary"
											size="icon"
											className="h-8 w-8 rounded-full bg-secondary hover:bg-slate-600 border-none"
										>
											<Mic className="h-4 w-4" />
										</Button>
										<Button
											variant="secondary"
											size="icon"
											className="h-8 w-8 rounded-full bg-secondary hover:bg-slate-600 border-none"
										>
											<Video className="h-4 w-4" />
										</Button>
										<Button
											variant="secondary"
											size="icon"
											className="h-8 w-8 rounded-full bg-secondary hover:bg-slate-600 border-none"
										>
											<MonitorPlay className="h-4 w-4" />
										</Button>
										<Button
											variant="destructive"
											size="icon"
											className="h-8 w-8 rounded-full"
										>
											<Phone className="h-4 w-4 rotate-[135deg]" />
										</Button>
									</div>
								</div>
							</div>
						</div>
					</ScrollArea>
				</div>

				{/* Center Column - Activity & Canvas */}
				<div className="flex-1 flex flex-col bg-[#0f1115] relative border-r border-border/50">
					{/* Mini Canvas Preview */}
					<div
						className="h-[60%] border-b relative overflow-hidden bg-background"
						style={{
							backgroundImage: "radial-gradient(#1e293b 1px, transparent 1px)",
							backgroundSize: "20px 20px",
						}}
					>
						{/* Drawing content */}
						<div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[300px]">
							<div className="absolute inset-0 border-2 border-border"></div>
							<div className="absolute top-[100px] left-[50px] w-[400px] h-0.5 bg-primary/40"></div>
							<div className="absolute top-[200px] left-[50px] w-[400px] h-0.5 bg-primary/40"></div>

							<div className="absolute top-[80px] left-[150px] w-8 h-10 border border-primary bg-card"></div>
							<div className="absolute top-[180px] left-[250px] w-8 h-10 border border-primary bg-card"></div>

							{/* Highlight selection */}
							<div className="absolute top-[70px] left-[140px] w-[100px] h-[120px] bg-blue-500/10 border border-blue-500/50"></div>

							{/* Remote Cursor 1 */}
							<div className="absolute top-[90px] left-[180px] flex items-start gap-1 z-20">
								<MousePointer2
									className="w-5 h-5 text-purple-400 fill-purple-400 rotate-[-15deg]"
									style={{ filter: "drop-shadow(0 2px 4px rgba(0,0,0,0.5))" }}
								/>
								<div className="bg-purple-500 text-white text-[10px] px-1.5 py-0.5 rounded shadow-md mt-4 font-medium">
									Sarah C.
								</div>
							</div>

							{/* Remote Cursor 2 */}
							<div className="absolute top-[220px] left-[320px] flex items-start gap-1 z-20">
								<MousePointer2
									className="w-5 h-5 text-rose-400 fill-rose-400 rotate-[-15deg]"
									style={{ filter: "drop-shadow(0 2px 4px rgba(0,0,0,0.5))" }}
								/>
								<div className="bg-rose-500 text-white text-[10px] px-1.5 py-0.5 rounded shadow-md mt-4 font-medium">
									Fatima A.
								</div>
							</div>

							{/* Annotation */}
							<div className="absolute top-[150px] left-[260px] z-10">
								<div className="w-4 h-4 rounded-full bg-primary/20 border-2 border-primary flex items-center justify-center animate-pulse"></div>
								<div className="absolute top-2 left-6 bg-card border border-border p-2 rounded-md shadow-lg w-[160px]">
									<div className="text-[9px] font-bold text-primary mb-1">
										Marcus W.
									</div>
									<div className="text-[10px] leading-tight">
										Verify load schedule before sizing this panel.
									</div>
								</div>
							</div>
						</div>

						<div className="absolute bottom-4 right-4 bg-card/80 backdrop-blur text-[10px] font-mono px-2 py-1 rounded border">
							Live Canvas: Electrical Floor 3
						</div>
					</div>

					{/* Activity Feed */}
					<div className="flex-1 flex flex-col bg-card/10">
						<div className="p-2 border-b bg-card/40 flex items-center gap-2">
							<History className="h-4 w-4 text-muted-foreground" />
							<span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
								Recent Activity
							</span>
						</div>
						<ScrollArea className="flex-1">
							<div className="p-4 space-y-4">
								<ActivityItem
									color="bg-purple-500"
									initials="SC"
									time="2 min ago"
									text={
										<span>
											<span className="font-semibold text-foreground">
												Sarah Chen
											</span>{" "}
											added Smoke Detector SD-051 in Room 312
										</span>
									}
								/>
								<ActivityItem
									color="bg-rose-500"
									initials="FA"
									time="4 min ago"
									text={
										<span>
											<span className="font-semibold text-foreground">
												Fatima Al-Zahra
											</span>{" "}
											commented on Panel LP-3A: "Verify load schedule before
											sizing"
										</span>
									}
								/>
								<ActivityItem
									color="bg-blue-500"
									initials="AA"
									time="7 min ago"
									text={
										<span>
											<span className="font-semibold text-foreground">
												Ahmed Al-Rashidi
											</span>{" "}
											ran compliance check — 3 issues found
										</span>
									}
								/>
								<ActivityItem
									color="bg-primary"
									initials="MW"
									time="12 min ago"
									text={
										<span>
											<span className="font-semibold text-foreground">
												Marcus Williams
											</span>{" "}
											approved Revision 14 of Electrical Floor Plan
										</span>
									}
								/>
								<ActivityItem
									color="bg-secondary"
									initials="SYS"
									time="18 min ago"
									text={
										<span className="text-success font-mono">
											System: Auto-save complete — all changes synchronized
										</span>
									}
									isSystem
								/>
							</div>
						</ScrollArea>
					</div>
				</div>

				{/* Right Column - Comments & Approvals */}
				<div className="w-[340px] flex flex-col bg-card/30 shrink-0 shadow-[-5px_0_15px_rgba(0,0,0,0.1)]">
					<Tabs defaultValue="comments" className="flex flex-col h-full">
						<TabsList className="h-12 w-full justify-start rounded-none border-b bg-card/50 px-2">
							<TabsTrigger
								value="comments"
								className="text-xs data-[state=active]:bg-background"
							>
								Comments{" "}
								<Badge className="ml-2 h-4 px-1 py-0 text-[9px] bg-primary/20 text-primary">
									3
								</Badge>
							</TabsTrigger>
							<TabsTrigger
								value="approvals"
								className="text-xs data-[state=active]:bg-background"
							>
								Approvals
							</TabsTrigger>
						</TabsList>

						<TabsContent
							value="comments"
							className="m-0 flex-1 flex flex-col h-[calc(100%-3rem)]"
						>
							<div className="px-3 py-2 border-b flex gap-2 overflow-x-auto scrollbar-hide">
								<Badge
									variant="secondary"
									className="text-[10px] cursor-pointer bg-muted"
								>
									All
								</Badge>
								<Badge
									variant="outline"
									className="text-[10px] cursor-pointer text-primary border-primary/30"
								>
									Unresolved
								</Badge>
								<Badge variant="outline" className="text-[10px] cursor-pointer">
									Mine
								</Badge>
								<Badge variant="outline" className="text-[10px] cursor-pointer">
									Flagged
								</Badge>
							</div>

							<ScrollArea className="flex-1 p-3">
								<div className="space-y-4">
									{/* Thread 1 */}
									<div className="bg-card border rounded-lg p-3">
										<div className="flex justify-between items-start mb-3">
											<div className="text-xs font-semibold text-foreground flex items-center gap-1.5">
												<MessageSquare className="h-4 w-4 text-primary" />{" "}
												Panel LP-3A
											</div>
											<Badge
												variant="outline"
												className="text-[9px] h-4 px-1 text-primary border-primary/30"
											>
												Unresolved
											</Badge>
										</div>

										<div className="space-y-3 pl-2 border-l-2 border-muted">
											<div className="flex gap-2">
												<Avatar className="h-5 w-5">
													<AvatarFallback className="bg-rose-500 text-[8px]">
														FA
													</AvatarFallback>
												</Avatar>
												<div>
													<div className="flex items-center gap-2">
														<span className="text-[10px] font-semibold text-foreground/90">
															Fatima A.
														</span>
														<span className="text-[9px] text-muted-foreground">
															10:42 AM
														</span>
													</div>
													<p className="text-xs text-muted-foreground mt-0.5">
														Verify load schedule before sizing. Current demand
														shows 87% utilization.
													</p>
												</div>
											</div>
											<div className="flex gap-2">
												<Avatar className="h-5 w-5">
													<AvatarFallback className="bg-blue-500 text-[8px]">
														AA
													</AvatarFallback>
												</Avatar>
												<div>
													<div className="flex items-center gap-2">
														<span className="text-[10px] font-semibold text-foreground/90">
															Ahmed (You)
														</span>
														<span className="text-[9px] text-muted-foreground">
															10:45 AM
														</span>
													</div>
													<p className="text-xs text-muted-foreground mt-0.5">
														Agreed. I'll update after contractor confirmation.
													</p>
												</div>
											</div>
										</div>

										<div className="mt-3 flex gap-2">
											<Input
												placeholder="Reply..."
												className="h-7 text-xs bg-muted/50"
											/>
											<Button size="icon" className="h-7 w-7 shrink-0">
												<Send className="h-3 w-3" />
											</Button>
										</div>
									</div>

									{/* Thread 2 */}
									<div className="bg-card border border-emerald-500/20 rounded-lg p-3">
										<div className="flex justify-between items-start mb-3">
											<div className="text-xs font-semibold text-foreground flex items-center gap-1.5">
												<MessageSquare className="h-4 w-4 text-emerald-500" />{" "}
												Cable Route Level 3
											</div>
											<Badge
												variant="outline"
												className="text-[9px] h-4 px-1 text-success border-success/30"
											>
												<CheckCircle2 className="w-3 h-3 mr-1" />
												Resolved
											</Badge>
										</div>
										<div className="space-y-3 pl-2 border-l-2 border-emerald-500/20">
											<div className="flex gap-2">
												<Avatar className="h-5 w-5">
													<AvatarFallback className="bg-primary text-[8px]">
														MW
													</AvatarFallback>
												</Avatar>
												<div>
													<div className="flex items-center gap-2">
														<span className="text-[10px] font-semibold text-foreground/90">
															Marcus W.
														</span>
														<span className="text-[9px] text-muted-foreground">
															Yesterday
														</span>
													</div>
													<p className="text-xs text-muted-foreground mt-0.5">
														Route approved per structural review. No conflicts
														with beams.
													</p>
												</div>
											</div>
										</div>
									</div>
								</div>
							</ScrollArea>
						</TabsContent>

						<TabsContent
							value="approvals"
							className="m-0 flex-1 p-4 flex flex-col gap-4"
						>
							<div className="bg-card border border-primary/20 rounded-lg p-4 relative overflow-hidden">
								<div className="absolute top-0 left-0 w-full h-1 bg-primary/40">
									<div className="h-full bg-primary w-1/2"></div>
								</div>
								<div className="text-xs font-semibold uppercase text-muted-foreground mb-1 mt-1">
									Current Stage
								</div>
								<h3 className="text-lg font-bold text-foreground mb-4">
									Engineering Review
								</h3>

								<div className="space-y-4 relative before:absolute before:inset-0 before:ml-3 before:-translate-x-px md:before:mx-auto md:before:translate-x-0 before:h-full before:w-0.5 before:bg-gradient-to-b before:from-transparent before:via-border before:to-transparent">
									<div className="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group is-active">
										<div className="flex items-center justify-center w-6 h-6 rounded-full border-2 border-emerald-500 bg-card text-emerald-500 shrink-0 md:order-1 md:group-odd:-translate-x-1/2 md:group-even:translate-x-1/2 shadow">
											<CheckCircle2 className="w-3.5 h-3.5" />
										</div>
										<div className="w-[calc(100%-3rem)] md:w-[calc(50%-1.5rem)] text-xs text-muted-foreground px-2">
											Draft
										</div>
									</div>
									<div className="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group is-active">
										<div className="flex items-center justify-center w-6 h-6 rounded-full border-2 border-primary bg-card text-primary shrink-0 md:order-1 md:group-odd:-translate-x-1/2 md:group-even:translate-x-1/2 shadow">
											<div className="w-2 h-2 rounded-full bg-primary animate-pulse"></div>
										</div>
										<div className="w-[calc(100%-3rem)] md:w-[calc(50%-1.5rem)] text-xs font-bold text-foreground px-2 text-right">
											Engineering Review
										</div>
									</div>
									<div className="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group is-active">
										<div className="flex items-center justify-center w-6 h-6 rounded-full border-2 border-border bg-card text-muted-foreground shrink-0 md:order-1 md:group-odd:-translate-x-1/2 md:group-even:translate-x-1/2 shadow"></div>
										<div className="w-[calc(100%-3rem)] md:w-[calc(50%-1.5rem)] text-xs text-muted-foreground px-2">
											Client Review
										</div>
									</div>
									<div className="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group is-active">
										<div className="flex items-center justify-center w-6 h-6 rounded-full border-2 border-border bg-card text-muted-foreground shrink-0 md:order-1 md:group-odd:-translate-x-1/2 md:group-even:translate-x-1/2 shadow"></div>
										<div className="w-[calc(100%-3rem)] md:w-[calc(50%-1.5rem)] text-xs text-muted-foreground px-2 text-right">
											Final Approval
										</div>
									</div>
								</div>

								<div className="mt-6 pt-4 border-t border-border/50">
									<div className="text-xs text-muted-foreground mb-2">
										Pending approvals from:
									</div>
									<div className="flex gap-2">
										<Badge
											variant="outline"
											className="text-[10px] bg-muted py-1"
										>
											<Avatar className="w-4 h-4 mr-1">
												<AvatarFallback className="bg-primary text-[6px]">
													MW
												</AvatarFallback>
											</Avatar>{" "}
											Marcus W.
										</Badge>
										<Badge
											variant="outline"
											className="text-[10px] bg-muted py-1"
										>
											<Avatar className="w-4 h-4 mr-1">
												<AvatarFallback className="bg-emerald-500 text-[6px]">
													JO
												</AvatarFallback>
											</Avatar>{" "}
											James O.
										</Badge>
									</div>
								</div>
							</div>

							<Button className="w-full h-10 mt-auto">
								<UploadCloud className="h-4 w-4 mr-2" /> Request Final Approval
							</Button>
						</TabsContent>
					</Tabs>
				</div>
			</div>
		</div>
	);
}

function ActivityItem({ color, initials, text, time, isSystem = false }: any) {
	return (
		<div className="flex gap-3">
			{isSystem ? (
				<div className="w-7 h-7 rounded bg-card border border-border flex items-center justify-center shrink-0 mt-0.5">
					<Settings className="w-3.5 h-3.5 text-muted-foreground" />
				</div>
			) : (
				<Avatar className="w-7 h-7 shrink-0 mt-0.5">
					<AvatarFallback
						className={`${color} text-white text-[9px] font-bold`}
					>
						{initials}
					</AvatarFallback>
				</Avatar>
			)}
			<div className="flex-1">
				<p className="text-xs text-muted-foreground leading-tight">{text}</p>
				<div className="text-[9px] text-muted-foreground mt-1">{time}</div>
			</div>
		</div>
	);
}
