// NOSONAR
import {
	AlertTriangle,
	Download,
	Play,
	Search,
	Settings,
	Square,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

export function LoadFlowAnalysis() {
	return (
		<div className="flex flex-col h-screen w-screen overflow-hidden bg-background text-foreground dark font-sans">
			{/* Top Toolbar */}
			<div className="h-14 flex items-center justify-between px-4 border-b bg-card shrink-0">
				<div className="flex items-center gap-4">
					<div className="font-bold tracking-wider text-sm">
						Load Flow & Power System Analysis
					</div>
					<Separator orientation="vertical" className="h-5" />
					<div className="flex space-x-1 text-xs">
						<button className="px-3 py-1 rounded bg-blue-500/10 text-blue-400 font-medium border border-blue-500/20">
							Load Flow
						</button>
						<button className="px-3 py-1 rounded text-muted-foreground hover:bg-muted">
							Short Circuit
						</button>
						<button className="px-3 py-1 rounded text-muted-foreground hover:bg-muted">
							Harmonic
						</button>
						<button className="px-3 py-1 rounded text-muted-foreground hover:bg-muted">
							Transient
						</button>
						<button className="px-3 py-1 rounded text-muted-foreground hover:bg-muted">
							Motor Starting
						</button>
					</div>
				</div>
				<div className="flex items-center gap-4">
					<span className="text-xs text-emerald-400 font-mono hidden md:inline">
						Converged in 7 iterations — 0.3s — Newton-Raphson
					</span>
					<div className="flex items-center gap-2">
						<Button
							variant="outline"
							size="sm"
							className="h-8 text-xs border-slate-700 hover:bg-slate-800"
						>
							<Settings className="h-3.5 w-3.5 mr-1" /> Settings
						</Button>
						<Button
							variant="outline"
							size="sm"
							className="h-8 text-xs border-slate-700 hover:bg-slate-800"
						>
							<Download className="h-3.5 w-3.5 mr-1" /> Export
						</Button>
						<Button
							size="sm"
							variant="destructive"
							className="h-8 text-xs bg-slate-800 text-slate-300 hover:bg-slate-700 border border-slate-700"
						>
							<Square className="h-3.5 w-3.5 mr-1" fill="currentColor" /> Stop
						</Button>
						<Button
							size="sm"
							className="h-8 text-xs bg-blue-600 hover:bg-blue-500 text-white"
						>
							<Play className="h-3.5 w-3.5 mr-1" fill="currentColor" /> Run
							Analysis
						</Button>
					</div>
				</div>
			</div>

			<div className="flex flex-1 overflow-hidden">
				{/* Left Panel - Network Tree */}
				<div className="w-[260px] flex flex-col border-r bg-card/30 shrink-0">
					<div className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground border-b flex justify-between items-center bg-card/40">
						<span>Network Tree</span>
						<Search className="h-3 w-3" />
					</div>
					<ScrollArea className="flex-1 p-2">
						<div className="text-[11px] font-mono space-y-1">
							{/* Fake Tree */}
							<div className="flex items-center gap-1 py-1 text-slate-300 hover:bg-muted rounded px-1 cursor-pointer">
								<div className="w-1.5 h-1.5 rounded-full bg-emerald-500 shrink-0"></div>
								System (11kV Utility)
							</div>
							<div className="pl-4 border-l border-slate-700/50 ml-2 space-y-1">
								<div className="flex items-center gap-1 py-1 text-slate-300 hover:bg-muted rounded px-1 cursor-pointer">
									<div className="w-1.5 h-1.5 rounded-full bg-emerald-500 shrink-0"></div>
									Bus 1: UTL-11KV
								</div>
								<div className="pl-4 border-l border-slate-700/50 ml-2 space-y-1">
									<div className="flex items-center gap-1 py-1 text-slate-300 hover:bg-muted rounded px-1 cursor-pointer">
										<div className="w-1.5 h-1.5 rounded-full bg-orange-400 shrink-0"></div>
										T1: 11kV/480V 2500kVA
									</div>
									<div className="pl-4 border-l border-slate-700/50 ml-2 space-y-1">
										<div className="flex items-center gap-1 py-1 text-slate-300 hover:bg-muted rounded px-1 cursor-pointer">
											<div className="w-1.5 h-1.5 rounded-full bg-emerald-500 shrink-0"></div>
											Bus 2: MSB-480V
										</div>
										<div className="pl-4 border-l border-slate-700/50 ml-2 space-y-1">
											<div className="flex items-center gap-1 py-1 text-slate-300 hover:bg-muted rounded px-1 cursor-pointer">
												<div className="w-1.5 h-1.5 rounded-full bg-emerald-500 shrink-0"></div>
												CB-F1: Feeder 1
											</div>
											<div className="pl-4 border-l border-slate-700/50 ml-2 space-y-1">
												<div className="flex items-center gap-1 py-1 text-slate-300 hover:bg-muted rounded px-1 cursor-pointer">
													<div className="w-1.5 h-1.5 rounded-full bg-emerald-500 shrink-0"></div>
													Bus 3: MDB-A-480V
												</div>
											</div>
											<div className="flex items-center gap-1 py-1 text-orange-300 bg-orange-500/10 rounded px-1 cursor-pointer">
												<div className="w-1.5 h-1.5 rounded-full bg-orange-500 shrink-0"></div>
												CB-F2: Feeder 2
											</div>
											<div className="pl-4 border-l border-orange-500/30 ml-2 space-y-1">
												<div className="flex items-center gap-1 py-1 text-orange-400 font-bold hover:bg-muted rounded px-1 cursor-pointer">
													<div className="w-1.5 h-1.5 rounded-full bg-orange-500 shrink-0"></div>
													Bus 4: MDB-B-480V
												</div>
											</div>
											<div className="flex items-center gap-1 py-1 text-slate-300 hover:bg-muted rounded px-1 cursor-pointer">
												<div className="w-1.5 h-1.5 rounded-full bg-emerald-500 shrink-0"></div>
												CB-E: Emergency
											</div>
										</div>
									</div>
								</div>
							</div>
						</div>
					</ScrollArea>
				</div>

				{/* Center - Diagram */}
				<div
					className="flex-1 relative bg-[#0a0a0f] overflow-hidden flex justify-center items-center"
					style={{
						backgroundImage:
							"radial-gradient(rgba(255,255,255,0.03) 1px, transparent 1px)",
						backgroundSize: "20px 20px",
					}}
				>
					<svg
						width="800"
						height="600"
						viewBox="0 0 800 600"
						className="drop-shadow-2xl"
					>
						{/* UTL-11KV */}
						<rect x="250" y="50" width="300" height="8" fill="#10b981" rx="2" />
						<text
							x="400"
							y="40"
							fill="#e2e8f0"
							fontSize="14"
							fontWeight="bold"
							textAnchor="middle"
						>
							UTL-11KV
						</text>
						<rect
							x="310"
							y="65"
							width="180"
							height="24"
							fill="#0f172a"
							stroke="#1e293b"
							rx="4"
						/>
						<text
							x="400"
							y="81"
							fill="#10b981"
							fontSize="11"
							fontFamily="monospace"
							textAnchor="middle"
						>
							11kV | 1.04 pu | 0°
						</text>

						<line
							x1="400"
							y1="58"
							x2="400"
							y2="120"
							stroke="#10b981"
							strokeWidth="3"
						/>

						{/* Transformer */}
						<circle
							cx="400"
							cy="140"
							r="20"
							fill="none"
							stroke="#f59e0b"
							strokeWidth="3"
						/>
						<circle
							cx="400"
							cy="170"
							r="20"
							fill="none"
							stroke="#f59e0b"
							strokeWidth="3"
						/>
						<text
							x="435"
							y="160"
							fill="#f8fafc"
							fontSize="12"
							fontWeight="bold"
						>
							T1
						</text>

						{/* T1 Results */}
						<rect
							x="440"
							y="130"
							width="140"
							height="40"
							fill="#0f172a"
							stroke="#f59e0b"
							rx="2"
						/>
						<text
							x="445"
							y="145"
							fill="#f59e0b"
							fontSize="10"
							fontFamily="monospace"
						>
							P = 1.52 MW
						</text>
						<text
							x="445"
							y="157"
							fill="#f59e0b"
							fontSize="10"
							fontFamily="monospace"
						>
							Q = 0.89 MVAR
						</text>
						<text
							x="445"
							y="169"
							fill="#f59e0b"
							fontSize="10"
							fontFamily="monospace"
						>
							98.2% Loading
						</text>
						{/* Flow arrow */}
						<polygon points="395,100 405,100 400,110" fill="#f59e0b" />

						<line
							x1="400"
							y1="190"
							x2="400"
							y2="250"
							stroke="#10b981"
							strokeWidth="3"
						/>

						{/* MSB-480V */}
						<rect
							x="150"
							y="250"
							width="500"
							height="8"
							fill="#10b981"
							rx="2"
						/>
						<text
							x="400"
							y="240"
							fill="#e2e8f0"
							fontSize="14"
							fontWeight="bold"
							textAnchor="middle"
						>
							MSB-480V (Swing)
						</text>
						<rect
							x="310"
							y="265"
							width="180"
							height="24"
							fill="#0f172a"
							stroke="#1e293b"
							rx="4"
						/>
						<text
							x="400"
							y="281"
							fill="#10b981"
							fontSize="11"
							fontFamily="monospace"
							textAnchor="middle"
						>
							480V | 1.00 pu | -2.3°
						</text>

						{/* Branches */}
						<line
							x1="200"
							y1="258"
							x2="200"
							y2="400"
							stroke="#10b981"
							strokeWidth="3"
						/>
						<line
							x1="400"
							y1="258"
							x2="400"
							y2="400"
							stroke="#f59e0b"
							strokeWidth="3"
						/>
						<line
							x1="600"
							y1="258"
							x2="600"
							y2="400"
							stroke="#10b981"
							strokeWidth="3"
						/>

						<polygon points="195,350 205,350 200,360" fill="#10b981" />
						<polygon points="395,350 405,350 400,360" fill="#f59e0b" />

						{/* Feeder Results */}
						<rect
							x="80"
							y="320"
							width="110"
							height="40"
							fill="#0f172a"
							stroke="#1e293b"
							rx="2"
						/>
						<text
							x="85"
							y="335"
							fill="#10b981"
							fontSize="10"
							fontFamily="monospace"
						>
							P = 0.71 MW
						</text>
						<text
							x="85"
							y="347"
							fill="#10b981"
							fontSize="10"
							fontFamily="monospace"
						>
							Q = 0.42 MVAR
						</text>
						<text
							x="85"
							y="359"
							fill="#10b981"
							fontSize="10"
							fontFamily="monospace"
						>
							53.5% Load
						</text>

						<rect
							x="410"
							y="320"
							width="110"
							height="40"
							fill="#0f172a"
							stroke="#f59e0b"
							rx="2"
						/>
						<text
							x="415"
							y="335"
							fill="#f59e0b"
							fontSize="10"
							fontFamily="monospace"
						>
							P = 0.81 MW
						</text>
						<text
							x="415"
							y="347"
							fill="#f59e0b"
							fontSize="10"
							fontFamily="monospace"
						>
							Q = 0.51 MVAR
						</text>
						<text
							x="415"
							y="359"
							fill="#f59e0b"
							fontSize="10"
							fontFamily="monospace"
						>
							61.1% Load
						</text>

						{/* MDB-A */}
						<rect
							x="150"
							y="400"
							width="100"
							height="8"
							fill="#10b981"
							rx="2"
						/>
						<text
							x="200"
							y="390"
							fill="#e2e8f0"
							fontSize="12"
							fontWeight="bold"
							textAnchor="middle"
						>
							MDB-A
						</text>
						<rect
							x="130"
							y="415"
							width="140"
							height="24"
							fill="#0f172a"
							stroke="#1e293b"
							rx="4"
						/>
						<text
							x="200"
							y="431"
							fill="#10b981"
							fontSize="10"
							fontFamily="monospace"
							textAnchor="middle"
						>
							479V | 0.998 pu
						</text>
						<polygon
							points="190,450 210,450 200,470"
							fill="#1e293b"
							stroke="#64748b"
						/>
						<text
							x="200"
							y="485"
							fill="#94a3b8"
							fontSize="10"
							fontFamily="monospace"
							textAnchor="middle"
						>
							362 kW
						</text>

						{/* MDB-B (Warning) */}
						<rect
							x="350"
							y="400"
							width="100"
							height="8"
							fill="#f59e0b"
							rx="2"
						/>
						<text
							x="400"
							y="390"
							fill="#f59e0b"
							fontSize="12"
							fontWeight="bold"
							textAnchor="middle"
						>
							MDB-B
						</text>
						<rect
							x="330"
							y="415"
							width="140"
							height="24"
							fill="#0f172a"
							stroke="#f59e0b"
							rx="4"
						/>
						<text
							x="400"
							y="431"
							fill="#f59e0b"
							fontSize="10"
							fontFamily="monospace"
							textAnchor="middle"
						>
							471V | 0.981 pu
						</text>
						<polygon
							points="390,450 410,450 400,470"
							fill="#1e293b"
							stroke="#f59e0b"
						/>
						<text
							x="400"
							y="485"
							fill="#94a3b8"
							fontSize="10"
							fontFamily="monospace"
							textAnchor="middle"
						>
							443 kW
						</text>

						{/* ATS */}
						<rect
							x="550"
							y="400"
							width="100"
							height="8"
							fill="#10b981"
							rx="2"
						/>
						<text
							x="600"
							y="390"
							fill="#e2e8f0"
							fontSize="12"
							fontWeight="bold"
							textAnchor="middle"
						>
							ATS-480V
						</text>
						<rect
							x="530"
							y="415"
							width="140"
							height="24"
							fill="#0f172a"
							stroke="#1e293b"
							rx="4"
						/>
						<text
							x="600"
							y="431"
							fill="#10b981"
							fontSize="10"
							fontFamily="monospace"
							textAnchor="middle"
						>
							478.5V | 0.997 pu
						</text>
						<circle cx="600" cy="460" r="15" fill="none" stroke="#64748b" />
						<text
							x="600"
							y="464"
							fill="#64748b"
							fontSize="12"
							fontWeight="bold"
							textAnchor="middle"
						>
							G
						</text>
					</svg>

					{/* Legend Overlay */}
					<div className="absolute right-4 bottom-4 bg-slate-900 border border-slate-700 p-3 rounded-md backdrop-blur-sm shadow-xl text-xs">
						<div className="font-bold text-slate-300 mb-2">Color Coding</div>
						<div className="flex items-center gap-2 mb-1">
							<div className="w-3 h-3 bg-emerald-500 rounded-sm"></div>{" "}
							<span className="text-slate-400">
								Normal (≥0.95 pu / &lt;90%)
							</span>
						</div>
						<div className="flex items-center gap-2 mb-1">
							<div className="w-3 h-3 bg-orange-500 rounded-sm"></div>{" "}
							<span className="text-slate-400">
								Warning (0.90-0.95 / &gt;90%)
							</span>
						</div>
						<div className="flex items-center gap-2">
							<div className="w-3 h-3 bg-red-500 rounded-sm"></div>{" "}
							<span className="text-slate-400">
								Critical (&lt;0.90 / &gt;100%)
							</span>
						</div>
					</div>
				</div>

				{/* Right Panel - Results */}
				<div className="w-[300px] flex flex-col border-l bg-card/30 shrink-0">
					<div className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-foreground border-b flex justify-between items-center bg-card/40">
						<span>Results Summary</span>
					</div>
					<ScrollArea className="flex-1">
						<div className="p-4 space-y-6">
							{/* Warnings Box */}
							<div className="border border-orange-500/50 bg-orange-500/10 rounded-md p-3">
								<div className="flex items-center gap-2 text-orange-400 font-bold text-xs mb-2 uppercase">
									<AlertTriangle className="h-4 w-4" /> System Warnings
								</div>
								<ul className="text-xs text-slate-300 space-y-2 list-disc pl-4">
									<li>
										Bus <span className="font-mono text-orange-300">MDB-B</span>{" "}
										voltage 0.981 pu — below 0.985 pu threshold
									</li>
									<li>
										Transformer{" "}
										<span className="font-mono text-orange-300">T1</span>{" "}
										loading 98.2% — approaching rated capacity
									</li>
								</ul>
								<Button
									size="sm"
									variant="outline"
									className="w-full mt-3 h-7 text-[10px] border-orange-500/30 text-orange-400 bg-transparent hover:bg-orange-500/20"
								>
									View Recommendations
								</Button>
							</div>

							{/* Voltage Profile */}
							<div>
								<h4 className="text-xs font-bold text-muted-foreground uppercase border-b border-border/50 pb-1 mb-2">
									Bus Voltage Profile
								</h4>
								<div className="bg-slate-900 rounded border border-slate-800 overflow-hidden">
									<table className="w-full text-left text-[11px]">
										<thead className="bg-slate-800 text-slate-400">
											<tr>
												<th className="px-2 py-1.5 font-medium">Bus</th>
												<th className="px-2 py-1.5 font-medium">pu</th>
												<th className="px-2 py-1.5 font-medium">Status</th>
											</tr>
										</thead>
										<tbody className="divide-y divide-slate-800 font-mono">
											<tr>
												<td className="px-2 py-1.5">UTL-11KV</td>
												<td className="px-2 py-1.5">1.040</td>
												<td className="px-2 py-1.5 text-emerald-400">Normal</td>
											</tr>
											<tr>
												<td className="px-2 py-1.5">MSB-480V</td>
												<td className="px-2 py-1.5">1.000</td>
												<td className="px-2 py-1.5 text-slate-400">Swing</td>
											</tr>
											<tr>
												<td className="px-2 py-1.5">MDB-A</td>
												<td className="px-2 py-1.5">0.998</td>
												<td className="px-2 py-1.5 text-emerald-400">Normal</td>
											</tr>
											<tr className="bg-orange-500/10">
												<td className="px-2 py-1.5 text-orange-400">MDB-B</td>
												<td className="px-2 py-1.5 text-orange-400 font-bold">
													0.981
												</td>
												<td className="px-2 py-1.5 text-orange-400 font-bold">
													Warning
												</td>
											</tr>
											<tr>
												<td className="px-2 py-1.5">ATS-480V</td>
												<td className="px-2 py-1.5">0.997</td>
												<td className="px-2 py-1.5 text-emerald-400">Normal</td>
											</tr>
										</tbody>
									</table>
								</div>
							</div>

							{/* Branch Loading */}
							<div>
								<h4 className="text-xs font-bold text-muted-foreground uppercase border-b border-border/50 pb-1 mb-2">
									Branch Loading
								</h4>
								<div className="bg-slate-900 rounded border border-slate-800 overflow-hidden">
									<table className="w-full text-left text-[11px]">
										<thead className="bg-slate-800 text-slate-400">
											<tr>
												<th className="px-2 py-1.5 font-medium">Branch</th>
												<th className="px-2 py-1.5 font-medium">% Load</th>
												<th className="px-2 py-1.5 font-medium">Status</th>
											</tr>
										</thead>
										<tbody className="divide-y divide-slate-800 font-mono">
											<tr className="bg-orange-500/10">
												<td className="px-2 py-1.5 text-orange-400">T1 Main</td>
												<td className="px-2 py-1.5 text-orange-400 font-bold">
													98.2%
												</td>
												<td className="px-2 py-1.5 text-orange-400 font-bold">
													Warning
												</td>
											</tr>
											<tr>
												<td className="px-2 py-1.5">Feeder F1</td>
												<td className="px-2 py-1.5">53.5%</td>
												<td className="px-2 py-1.5 text-emerald-400">Normal</td>
											</tr>
											<tr>
												<td className="px-2 py-1.5">Feeder F2</td>
												<td className="px-2 py-1.5">61.1%</td>
												<td className="px-2 py-1.5 text-emerald-400">Normal</td>
											</tr>
											<tr>
												<td className="px-2 py-1.5">Emergency</td>
												<td className="px-2 py-1.5">9.0%</td>
												<td className="px-2 py-1.5 text-emerald-400">Normal</td>
											</tr>
										</tbody>
									</table>
								</div>
							</div>

							{/* System Summary */}
							<div>
								<h4 className="text-xs font-bold text-muted-foreground uppercase border-b border-border/50 pb-1 mb-2">
									System Summary
								</h4>
								<div className="space-y-2 text-xs">
									<div className="flex justify-between">
										<span className="text-slate-400">Generation</span>
										<span className="font-mono">1,523 kW + 499 kVAR</span>
									</div>
									<div className="flex justify-between">
										<span className="text-slate-400">Total Load</span>
										<span className="font-mono">1,498 kW + 879 kVAR</span>
									</div>
									<div className="flex justify-between">
										<span className="text-slate-400">Total Losses</span>
										<span className="font-mono text-red-400">
											25.3 kW (1.66%)
										</span>
									</div>
									<div className="flex justify-between">
										<span className="text-slate-400">Power Factor</span>
										<span className="font-mono">0.864 lag</span>
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
