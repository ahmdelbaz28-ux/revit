import {
	Activity,
	ActivitySquare,
	AlertTriangle,
	Bell,
	Building2,
	CheckCircle2,
	ChevronDown,
	ChevronRight,
	Droplets,
	Plus,
	Settings,
	Thermometer,
	User,
	Wind,
	XCircle,
	Zap,
} from "lucide-react";
import type React from "react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

export function BMSDashboard() {
	const [activeZone, setActiveZone] = useState("Server Room");

	return (
		<div className="flex flex-col h-screen w-screen overflow-hidden bg-slate-900 text-slate-100 font-sans">
			{/* Top Toolbar */}
			<div className="h-14 flex items-center justify-between px-4 bg-slate-800 border-b border-slate-700 shrink-0">
				<div className="flex items-center gap-4">
					<div className="flex items-center gap-2 text-blue-400 font-bold tracking-wide">
						<Building2 className="h-5 w-5" />
						<span>NexusCAD Pro — BMS Integration</span>
					</div>
					<Separator orientation="vertical" className="h-6 bg-slate-600" />
					<div className="text-sm font-medium text-slate-300">
						Project: Tower-B Office Complex
					</div>
				</div>

				<Tabs defaultValue="overview" className="h-full flex items-center">
					<TabsList className="bg-transparent gap-1">
						<TabsTrigger
							value="overview"
							className="data-[state=active]:bg-slate-700 data-[state=active]:text-blue-400"
						>
							Overview
						</TabsTrigger>
						<TabsTrigger
							value="hvac"
							className="data-[state=active]:bg-slate-700 data-[state=active]:text-blue-400"
						>
							HVAC
						</TabsTrigger>
						<TabsTrigger
							value="electrical"
							className="data-[state=active]:bg-slate-700 data-[state=active]:text-blue-400"
						>
							Electrical
						</TabsTrigger>
						<TabsTrigger
							value="lighting"
							className="data-[state=active]:bg-slate-700 data-[state=active]:text-blue-400"
						>
							Lighting
						</TabsTrigger>
						<TabsTrigger
							value="energy"
							className="data-[state=active]:bg-slate-700 data-[state=active]:text-blue-400"
						>
							Energy
						</TabsTrigger>
						<TabsTrigger
							value="alarms"
							className="data-[state=active]:bg-slate-700 data-[state=active]:text-blue-400"
						>
							Alarms
						</TabsTrigger>
						<TabsTrigger
							value="schedules"
							className="data-[state=active]:bg-slate-700 data-[state=active]:text-blue-400"
						>
							Schedules
						</TabsTrigger>
						<TabsTrigger
							value="reports"
							className="data-[state=active]:bg-slate-700 data-[state=active]:text-blue-400"
						>
							Reports
						</TabsTrigger>
					</TabsList>
				</Tabs>

				<div className="flex items-center gap-4 text-sm">
					<div className="flex flex-col items-end text-xs text-slate-400 font-mono">
						<span className="text-slate-200">14:52:33</span>
						<span>15 May 2026</span>
					</div>
					<Separator orientation="vertical" className="h-6 bg-slate-600" />
					<div className="flex items-center gap-1 text-slate-300">
						<Thermometer className="h-4 w-4" />
						<span>34°C</span>
					</div>
					<Separator orientation="vertical" className="h-6 bg-slate-600" />
					<div className="relative cursor-pointer">
						<Bell className="h-5 w-5 text-slate-300 hover:text-white" />
						<Badge className="absolute -top-2 -right-2 h-4 w-4 p-0 flex items-center justify-center bg-red-500 text-[9px] hover:bg-red-600">
							3
						</Badge>
					</div>
					<Separator orientation="vertical" className="h-6 bg-slate-600" />
					<div className="flex items-center gap-2 text-slate-300 cursor-pointer hover:text-white">
						<User className="h-4 w-4" />
						<span>Ahmed</span>
					</div>
					<Settings className="h-5 w-5 text-slate-400 cursor-pointer hover:text-white" />
				</div>
			</div>

			<div className="flex flex-1 overflow-hidden">
				{/* Left Panel */}
				<div className="w-[220px] bg-slate-800 border-r border-slate-700 flex flex-col shrink-0">
					<div className="p-3 text-xs font-semibold uppercase tracking-wider text-slate-500 border-b border-slate-700">
						Building Navigator
					</div>
					<ScrollArea className="flex-1 p-2">
						<div className="space-y-0.5">
							<NavNode title="Tower-B" expanded status="normal">
								<NavNode title="Basement" status="normal">
									<NavNode title="B2" status="normal" />
									<NavNode title="B1" status="normal" />
								</NavNode>
								<NavNode title="Ground Floor" status="normal" />
								<NavNode title="Level 1–3" expanded status="warning">
									<NavNode title="Level 1" status="normal" />
									<NavNode title="Level 2" expanded active status="alarm">
										<NavNode title="Office Zone A" status="normal" />
										<NavNode title="Office Zone B" status="normal" />
										<NavNode title="Server Room" status="alarm" />
										<NavNode title="Meeting Rooms" status="normal" />
										<NavNode title="Corridors" status="normal" />
									</NavNode>
									<NavNode title="Level 3" status="normal" />
								</NavNode>
								<NavNode title="Level 4–6" status="normal" />
								<NavNode title="Roof" status="normal" />
								<NavNode title="Mechanical Floor" status="normal" />
							</NavNode>
						</div>
					</ScrollArea>
				</div>

				{/* Center Canvas */}
				<div className="flex-1 bg-slate-900 relative overflow-hidden flex flex-col">
					<div className="absolute inset-0 p-8 flex items-center justify-center">
						{/* SVG Floor Plan */}
						<div className="relative w-full max-w-4xl aspect-[4/3] border-2 border-slate-600 bg-slate-800/50 rounded-sm">
							{/* Outer walls */}

							{/* Office Zone A */}
							<div className="absolute top-0 left-0 w-[40%] h-[60%] border-r border-b border-slate-600 bg-green-500/10 p-2 flex flex-col">
								<span className="text-xs font-bold text-slate-300">
									Office Zone A
								</span>
								<div className="mt-auto text-[10px] text-slate-400 font-mono">
									22.4°C | 65% RH | CO2: 412ppm | Occ: 24/30
								</div>
								<Thermometer className="absolute top-2 right-2 h-4 w-4 text-green-400" />
								<div className="absolute top-8 left-8 w-4 h-4 border border-blue-400 bg-blue-500/20"></div>{" "}
								{/* FCU */}
								<svg className="absolute inset-0 w-full h-full pointer-events-none">
									<path
										d="M 32 32 L 100 32"
										stroke="blue"
										strokeWidth="1"
										strokeDasharray="4 2"
										fill="none"
									/>
									<path
										d="M 100 40 L 32 40"
										stroke="red"
										strokeWidth="1"
										strokeDasharray="4 2"
										fill="none"
									/>
								</svg>
							</div>

							{/* Office Zone B */}
							<div className="absolute top-0 left-[40%] w-[40%] h-[60%] border-r border-b border-slate-600 bg-green-500/10 p-2 flex flex-col">
								<span className="text-xs font-bold text-slate-300">
									Office Zone B
								</span>
								<div className="mt-auto text-[10px] text-slate-400 font-mono">
									23.1°C | 61% RH | CO2: 438ppm | Occ: 18/30
								</div>
								<Thermometer className="absolute top-2 right-2 h-4 w-4 text-green-400" />
								<div className="absolute top-8 right-8 w-4 h-4 border border-blue-400 bg-blue-500/20"></div>{" "}
								{/* FCU */}
							</div>

							{/* Server Room */}
							<div className="absolute top-0 right-0 w-[20%] h-[40%] border-b border-slate-600 bg-red-500/20 p-2 flex flex-col shadow-[inset_0_0_20px_rgba(239,68,68,0.5)] animate-pulse">
								<span className="text-xs font-bold text-slate-100 flex items-center gap-1">
									<AlertTriangle className="h-3 w-3 text-red-500" />
									Server Room
								</span>
								<div className="mt-auto text-[10px] text-red-300 font-mono font-bold">
									19.8°C | ALARM
								</div>
								<Thermometer className="absolute top-2 right-2 h-4 w-4 text-red-500" />
							</div>

							{/* Meeting Room 201 */}
							<div className="absolute top-[60%] left-0 w-[25%] h-[40%] border-r border-slate-600 bg-blue-500/10 p-2 flex flex-col">
								<span className="text-xs font-bold text-slate-300">
									Meeting 201
								</span>
								<div className="mt-auto text-[10px] text-slate-400 font-mono">
									21.5°C | Unoccupied
								</div>
							</div>

							{/* Meeting Room 202 */}
							<div className="absolute top-[60%] left-[25%] w-[25%] h-[40%] border-r border-slate-600 bg-green-500/10 p-2 flex flex-col">
								<span className="text-xs font-bold text-slate-300">
									Meeting 202
								</span>
								<div className="mt-auto text-[10px] text-slate-400 font-mono">
									22.8°C | Occupied
								</div>
							</div>

							{/* Corridor */}
							<div className="absolute top-[60%] left-[50%] right-0 h-[40%] bg-slate-800 p-2 flex flex-col border-t border-slate-600">
								<span className="text-xs font-bold text-slate-400">
									Corridor
								</span>
								<div className="mt-auto text-[10px] text-slate-500 font-mono">
									23.5°C
								</div>
							</div>

							{/* Duct paths overlaid globally */}
							<svg className="absolute inset-0 w-full h-full pointer-events-none z-10">
								<path
									d="M 80% 20% L 60% 20% L 60% 80% L 20% 80%"
									stroke="#3b82f6"
									strokeWidth="2"
									strokeDasharray="5 5"
									fill="none"
									opacity="0.6"
								/>
								<path
									d="M 20% 75% L 55% 75% L 55% 25% L 80% 25%"
									stroke="#ef4444"
									strokeWidth="2"
									strokeDasharray="5 5"
									fill="none"
									opacity="0.6"
								/>
							</svg>
						</div>
					</div>

					{/* Zoom/Pan controls */}
					<div className="absolute bottom-4 right-4 flex bg-slate-800 rounded border border-slate-700 shadow-lg">
						<Button
							variant="ghost"
							size="icon"
							className="h-8 w-8 text-slate-400 hover:text-white"
						>
							<Plus className="h-4 w-4" />
						</Button>
						<Separator orientation="vertical" className="h-8 bg-slate-700" />
						<Button
							variant="ghost"
							size="icon"
							className="h-8 w-8 text-slate-400 hover:text-white"
						>
							<span className="text-lg leading-none">-</span>
						</Button>
					</div>
				</div>

				{/* Right Panel */}
				<div className="w-[300px] bg-slate-800 border-l border-slate-700 flex flex-col shrink-0 overflow-y-auto">
					<div className="p-3 border-b border-slate-700 flex justify-between items-start bg-slate-800/50">
						<div>
							<div className="text-sm font-bold text-slate-200">
								Server Room
							</div>
							<div className="text-xs text-slate-400">Level 2 • 24.5 m²</div>
						</div>
						<Badge className="bg-red-500/20 text-red-400 border border-red-500/50 hover:bg-red-500/30">
							ALARM
						</Badge>
					</div>

					<div className="p-4 space-y-6">
						{/* Live Points */}
						<div>
							<h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
								Live Points
							</h3>
							<div className="space-y-1">
								<PointRow
									label="Supply Air Temp"
									value="16.2°C"
									status="Normal"
									color="text-green-400"
								/>
								<PointRow
									label="Return Air Temp"
									value="19.8°C"
									status="HIGH ALARM"
									color="text-red-400"
									bg="bg-red-500/10"
									border="border-red-500/30"
								/>
								<PointRow
									label="Humidity"
									value="45% RH"
									status="Normal"
									color="text-green-400"
								/>
								<PointRow
									label="Differential Press."
									value="+12 Pa"
									status="Normal"
									color="text-green-400"
								/>
								<PointRow
									label="FCU-2-SR Status"
									value="ON - Max"
									status="Running"
									color="text-blue-400"
								/>
								<PointRow
									label="CRAC Unit-1"
									value="ON"
									status="Running"
									color="text-blue-400"
								/>
								<PointRow
									label="CRAC Unit-2"
									value="ON - FAULT"
									status="FAULT"
									color="text-red-400"
									bg="bg-red-500/10"
								/>
							</div>
						</div>

						{/* Active Alarms */}
						<div>
							<h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
								Active Alarms
							</h3>
							<div className="space-y-2">
								<div className="p-2 bg-slate-900 border border-red-500/30 rounded text-xs">
									<div className="flex justify-between font-mono text-[10px] text-red-400 mb-1">
										<span>ALM-2847</span>
										<span>14:43</span>
									</div>
									<div className="text-slate-300">
										Return air temp 19.8°C &gt; 19.0°C limit
									</div>
								</div>
								<div className="p-2 bg-slate-900 border border-red-500/30 rounded text-xs">
									<div className="flex justify-between font-mono text-[10px] text-red-400 mb-1">
										<span>ALM-2851</span>
										<span>14:51</span>
									</div>
									<div className="text-slate-300">
										CRAC Unit-2 fault — compressor trip
									</div>
								</div>
								<div className="flex gap-2 mt-2">
									<Button
										size="sm"
										variant="secondary"
										className="w-full text-xs h-7 bg-slate-700 hover:bg-slate-600"
									>
										Acknowledge
									</Button>
									<Button
										size="sm"
										variant="outline"
										className="w-full text-xs h-7 border-slate-600"
									>
										Dispatch
									</Button>
								</div>
							</div>
						</div>

						{/* Manual Override */}
						<div>
							<h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
								Control Override
							</h3>
							<div className="space-y-3 p-3 bg-slate-900 rounded border border-slate-700">
								<div className="flex items-center justify-between">
									<span className="text-xs text-slate-300">FCU-2-SR Mode</span>
									<div className="flex items-center gap-2">
										<span className="text-[10px] text-yellow-400 font-mono">
											MANUAL
										</span>
										<Switch defaultChecked />
									</div>
								</div>
								<div className="flex items-center justify-between">
									<span className="text-xs text-slate-300">CRAC Unit-1</span>
									<div className="flex items-center gap-2">
										<span className="text-[10px] text-slate-400 font-mono">
											AUTO
										</span>
										<Switch />
									</div>
								</div>
							</div>
						</div>

						{/* Setpoints */}
						<div>
							<h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
								Setpoints
							</h3>
							<div className="space-y-2">
								<div className="flex items-center justify-between p-2 bg-slate-900 rounded border border-slate-700">
									<span className="text-xs text-slate-300">Cooling SP</span>
									<div className="flex items-center gap-2">
										<span className="text-sm font-mono text-blue-400">
											18.0°C
										</span>
										<div className="flex flex-col">
											<Button
												variant="ghost"
												size="icon"
												className="h-4 w-4 rounded-none"
											>
												<span className="text-[10px]">▲</span>
											</Button>
											<Button
												variant="ghost"
												size="icon"
												className="h-4 w-4 rounded-none"
											>
												<span className="text-[10px]">▼</span>
											</Button>
										</div>
									</div>
								</div>
								<div className="flex items-center justify-between p-2 bg-slate-900 rounded border border-slate-700">
									<span className="text-xs text-slate-300">Humidity SP</span>
									<div className="flex items-center gap-2">
										<span className="text-sm font-mono text-blue-400">45%</span>
										<Button
											size="sm"
											variant="ghost"
											className="h-6 text-[10px] text-blue-400 hover:text-blue-300"
										>
											Apply
										</Button>
									</div>
								</div>
							</div>
						</div>

						{/* Trend Chart */}
						<div>
							<h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
								Trend (2h)
							</h3>
							<div className="h-20 bg-slate-900 border border-slate-700 rounded relative p-2">
								<div className="absolute top-4 left-0 w-full h-[1px] bg-red-500/50 border-b border-dashed border-red-500/50"></div>
								<svg
									className="w-full h-full preserve-aspect-ratio-none"
									viewBox="0 0 100 100"
									preserveAspectRatio="none"
								>
									<path
										d="M 0 80 Q 20 80 40 70 T 60 50 T 80 20 L 100 10"
										fill="none"
										stroke="#60a5fa"
										strokeWidth="2"
									/>
								</svg>
								<div className="absolute bottom-1 right-2 text-[9px] text-slate-500">
									19.8°C
								</div>
							</div>
						</div>
					</div>
				</div>
			</div>

			{/* Bottom Status Bar */}
			<div className="h-8 bg-slate-900 border-t border-slate-700 flex items-center justify-between px-4 text-[10px] font-mono shrink-0">
				<div className="flex items-center gap-4 text-slate-400">
					<span>System: 847 pts</span>
					<Separator orientation="vertical" className="h-4 bg-slate-700" />
					<span className="text-red-400">3 Alarm</span>
					<Separator orientation="vertical" className="h-4 bg-slate-700" />
					<span className="text-orange-400">12 Warn</span>
					<Separator orientation="vertical" className="h-4 bg-slate-700" />
					<span className="text-green-400">834 Norm</span>
				</div>
				<div className="flex items-center gap-4 text-slate-400">
					<span>Energy today: 4,823 kWh</span>
					<Separator orientation="vertical" className="h-4 bg-slate-700" />
					<span>Peak: 1.24 MW @ 11:20</span>
					<Separator orientation="vertical" className="h-4 bg-slate-700" />
					<span className="text-green-400 flex items-center gap-1">
						<CheckCircle2 className="h-3 w-3" /> BMS Server Online
					</span>
					<Separator orientation="vertical" className="h-4 bg-slate-700" />
					<span>BACnet/IP</span>
				</div>
			</div>
		</div>
	);
}

function NavNode({
	title,
	expanded = false,
	active = false,
	status,
	children,
}: {
	title: string;
	expanded?: boolean;
	active?: boolean;
	status: "normal" | "warning" | "alarm" | "offline";
	children?: React.ReactNode;
}) {
	const colors = {
		normal: "bg-green-500",
		warning: "bg-orange-500",
		alarm: "bg-red-500 animate-pulse",
		offline: "bg-slate-500",
	};

	return (
		<div className="select-none">
			<div
				className={`flex items-center gap-1.5 py-1 px-2 rounded cursor-pointer hover:bg-slate-700/50 ${active ? "bg-slate-700 text-white font-medium" : "text-slate-300"}`}
			>
				<div className="w-4 h-4 flex items-center justify-center">
					{children ? (
						expanded ? (
							<ChevronDown className="h-3 w-3 text-slate-500" />
						) : (
							<ChevronRight className="h-3 w-3 text-slate-500" />
						)
					) : (
						<div className="w-1 h-1" />
					)}
				</div>
				<div className={`w-2 h-2 rounded-full ${colors[status]}`} />
				<span className="text-xs truncate">{title}</span>
			</div>
			{expanded && children && (
				<div className="ml-3 pl-2 border-l border-slate-700 flex flex-col gap-0.5 mt-0.5">
					{children}
				</div>
			)}
		</div>
	);
}

function PointRow({
	label,
	value,
	status,
	color,
	bg = "bg-slate-900",
	border = "border-slate-800",
}: {
	label: string;
	value: string;
	status: string;
	color: string;
	bg?: string;
	border?: string;
}) {
	return (
		<div
			className={`flex items-center justify-between p-1.5 rounded border ${bg} ${border}`}
		>
			<span className="text-xs text-slate-300">{label}</span>
			<div className="flex items-center gap-2">
				<span className="text-xs font-mono font-medium text-slate-200">
					{value}
				</span>
				<span
					className={`text-[9px] uppercase px-1 rounded bg-slate-800 ${color}`}
				>
					{status}
				</span>
			</div>
		</div>
	);
}
