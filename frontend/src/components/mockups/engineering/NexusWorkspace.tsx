import {
	Activity,
	AlertTriangle,
	Layers,
	Settings,
	Shield,
	ShieldAlert,
	TrendingUp,
} from "lucide-react";
import { useState } from "react";
import { actions, useStore } from "@/store/simpleStore";
import { EngineeringCanvas } from "./EngineeringCanvas";
import { EngineeringLibrary } from "./EngineeringLibrary";
import { ImportExportManager } from "./ImportExportManager";
import { RiskAssessment } from "./RiskAssessment";
import { SystemAnalyzer } from "./SystemAnalyzer";
import { SystemOptimizer } from "./SystemOptimizer";

type TabType = "controls" | "analyzer" | "optimizer" | "risk";

export function NexusWorkspace() {
	const errors = useStore((s) => s.errors);
	const hasCriticalErrors = errors.some((e) => e.severity === "critical");
	const [draggedItem, setDraggedItem] = useState<any>(null);
	const [activeTab, setActiveTab] = useState<TabType>("analyzer");

	return (
		<div className="flex h-screen w-screen bg-background text-foreground overflow-hidden">
			{/* Left Sidebar: Engineering Library */}
			<EngineeringLibrary onDragStart={(item) => setDraggedItem(item)} />

			{/* Center: Main Canvas Area */}
			<div
				className="flex-1 flex flex-col relative border-r border-border"
				onDragEnd={() => setDraggedItem(null)}
			>
				{/* Top Header */}
				<div className="h-14 border-b border-border flex items-center justify-between px-6 bg-card/50 backdrop-blur-md shrink-0">
					<div className="flex items-center gap-3">
						<div className="flex items-center gap-2">
							<Shield className="h-5 w-5 text-primary" />
							<span className="font-bold text-sm uppercase tracking-widest">
								NexusCAD Pro
							</span>
						</div>
						<div className="h-5 w-px bg-border" />
						<ImportExportManager />
					</div>

					<div className="flex items-center gap-4 text-xs">
						<span className="text-muted-foreground flex items-center gap-1">
							<Layers size={12} /> Auto-Save: Active
						</span>
						{hasCriticalErrors && (
							<span className="flex items-center gap-1 text-destructive font-bold animate-pulse bg-destructive/10 px-2 py-1 rounded">
								<AlertTriangle size={14} /> System Critical
							</span>
						)}
					</div>
				</div>

				{/* Canvas Workspace */}
				<div className="flex-1 relative">
					<EngineeringCanvas onItemDrop={() => setDraggedItem(null)} />

					{/* Drag & Drop Overlay */}
					{draggedItem && (
						<div className="absolute inset-0 pointer-events-none flex items-center justify-center bg-primary/5 backdrop-blur-sm">
							<div className="bg-primary/20 border-2 border-primary border-dashed rounded-xl p-10 text-primary font-bold text-xl transform rotate-[-5deg]">
								Drop {draggedItem.label} Here
							</div>
						</div>
					)}
				</div>

				{/* Floating Error Log */}
				{errors.length > 0 && (
					<div className="absolute bottom-4 left-4 right-4 bg-destructive/10 border border-destructive/50 backdrop-blur-md rounded-lg p-3 max-h-48 overflow-y-auto shadow-2xl z-20">
						<div className="flex justify-between items-center mb-2 sticky top-0 bg-transparent backdrop-blur-sm z-10">
							<span className="text-xs font-bold text-destructive flex items-center gap-2">
								<Activity size={14} /> System Alerts ({errors.length})
							</span>
							<button
								onClick={() => actions.clearErrors()}
								className="text-[10px] text-destructive hover:underline hover:text-destructive-foreground transition-colors"
							>
								Clear All
							</button>
						</div>
						{errors.map((err) => (
							<div
								key={err.id}
								className="text-xs text-destructive mb-1.5 flex items-start gap-2 font-mono"
							>
								<span className="opacity-50 shrink-0">
									[{new Date(err.timestamp).toLocaleTimeString()}]
								</span>
								<span className="leading-tight">{err.message}</span>
							</div>
						))}
					</div>
				)}
			</div>

			{/* Right Sidebar: System Intelligence Suite */}
			<div className="w-80 bg-card flex flex-col h-full shrink-0">
				{/* Tabs Header */}
				<div className="flex items-center border-b border-border bg-muted/20">
					<button
						onClick={() => setActiveTab("controls")}
						className={`flex-1 py-3 flex justify-center border-b-2 transition-colors ${activeTab === "controls" ? "border-primary text-primary bg-primary/5" : "border-transparent text-muted-foreground hover:text-foreground hover:bg-muted/50"}`}
						title="Controls"
					>
						<Settings size={18} />
					</button>
					<button
						onClick={() => setActiveTab("analyzer")}
						className={`flex-1 py-3 flex justify-center border-b-2 transition-colors ${activeTab === "analyzer" ? "border-blue-500 text-blue-500 bg-blue-500/5" : "border-transparent text-muted-foreground hover:text-foreground hover:bg-muted/50"}`}
						title="System Analyzer"
					>
						<Activity size={18} />
					</button>
					<button
						onClick={() => setActiveTab("optimizer")}
						className={`flex-1 py-3 flex justify-center border-b-2 transition-colors ${activeTab === "optimizer" ? "border-emerald-500 text-emerald-500 bg-emerald-500/5" : "border-transparent text-muted-foreground hover:text-foreground hover:bg-muted/50"}`}
						title="Optimizer"
					>
						<TrendingUp size={18} />
					</button>
					<button
						onClick={() => setActiveTab("risk")}
						className={`flex-1 py-3 flex justify-center border-b-2 transition-colors ${activeTab === "risk" ? "border-orange-500 text-orange-500 bg-orange-500/5" : "border-transparent text-muted-foreground hover:text-foreground hover:bg-muted/50"}`}
						title="Risk Assessment"
					>
						<ShieldAlert size={18} />
					</button>
				</div>

				{/* Tab Content */}
				<div className="flex-1 overflow-hidden">
					{activeTab === "controls" && (
						<div className="p-6 text-center text-muted-foreground text-sm flex flex-col items-center justify-center h-full">
							<Settings className="h-12 w-12 opacity-20 mb-4" />
							<p>Project controls and properties will appear here.</p>
						</div>
					)}
					{activeTab === "analyzer" && <SystemAnalyzer />}
					{activeTab === "optimizer" && <SystemOptimizer />}
					{activeTab === "risk" && <RiskAssessment />}
				</div>
			</div>
		</div>
	);
}
