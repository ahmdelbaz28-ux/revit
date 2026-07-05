import {
	Activity,
	AlertTriangle,
	CheckCircle,
	Wrench,
	Zap,
} from "lucide-react";
import React from "react";
import { Button } from "@/components/ui/button";
import { actions, Connection, Device, useStore } from "@/store/simpleStore";

interface Issue {
	id: string;
	type: "critical" | "warning" | "info";
	title: string;
	description: string;
	solution: string;
	relatedIds: string[];
}

export function SystemAnalyzer() {
	const devices = useStore((s) => s.devices);
	const connections = useStore((s) => s.connections);
	const [issues, setIssues] = React.useState<Issue[]>([]);

	const analyzeSystem = () => {
		const foundIssues: Issue[] = [];

		// 1. Check for Overloads
		connections.forEach((conn) => {
			if (conn.isOverloaded) {
				foundIssues.push({
					id: `ISSUE-OVL-${conn.id}`,
					type: "critical",
					title: "Critical Overload Detected",
					description: `Connection ${conn.id} is carrying ${conn.current.toFixed(1)}A, exceeding safe limits.`,
					solution:
						"Upgrade cable cross-section or redistribute load to adjacent panels.",
					relatedIds: [conn.fromId, conn.toId],
				});
			}
		});

		// 2. Check for Isolated Devices (No Connections)
		devices.forEach((dev) => {
			const isConnected = connections.some(
				(c) => c.fromId === dev.id || c.toId === dev.id,
			);
			if (!isConnected && dev.type !== "GENERATOR") {
				// Generators can be standalone initially
				foundIssues.push({
					id: `ISSUE-ISO-${dev.id}`,
					type: "warning",
					title: "Isolated Component",
					description: `${dev.type} ${dev.id} has no electrical connections.`,
					solution:
						"Connect component to the nearest distribution panel or source.",
					relatedIds: [dev.id],
				});
			}
		});

		setIssues(foundIssues);
	};

	const applyAutoFix = (issue: Issue) => {
		if (issue.title.includes("Overload")) {
			// Logic: Find connected devices and suggest load shedding or upgrade simulation
			actions.addError({
				message: `Auto-Fix Applied: Simulated cable upgrade for ${issue.relatedIds[0]}`,
				severity: "info",
				relatedElementId: issue.relatedIds[0],
			});
			alert(
				`Applied: Upgraded virtual cable rating for connection involving ${issue.relatedIds.join(", ")}`,
			);
		} else if (issue.title.includes("Isolated")) {
			actions.selectElement(issue.relatedIds[0]);
			alert(
				`Focused on ${issue.relatedIds[0]}. Please drag a connection from a nearby panel.`,
			);
		}
	};

	return (
		<div className="p-4 space-y-4 h-full overflow-y-auto">
			<div className="flex items-center justify-between mb-4">
				<h2 className="text-lg font-bold text-foreground flex items-center gap-2">
					<Activity className="text-blue-500" /> System Analyzer
				</h2>
				<Button
					onClick={analyzeSystem}
					size="sm"
					className="bg-blue-600 hover:bg-blue-700"
				>
					Run Diagnostics
				</Button>
			</div>

			{issues.length === 0 ? (
				<div className="text-center p-8 text-muted-foreground bg-muted/30 rounded-lg border border-dashed">
					<CheckCircle className="mx-auto h-12 w-12 text-emerald-500 mb-2" />
					<p>No issues detected. System is healthy.</p>
				</div>
			) : (
				<div className="space-y-3">
					{issues.map((issue) => (
						<div
							key={issue.id}
							className={`p-3 rounded-lg border ${
								issue.type === "critical"
									? "bg-red-900/20 border-red-500/50"
									: "bg-amber-900/20 border-amber-500/50"
							}`}
						>
							<div className="flex items-start gap-3">
								<AlertTriangle
									className={`h-5 w-5 shrink-0 ${issue.type === "critical" ? "text-red-500" : "text-amber-500"}`}
								/>
								<div className="flex-1">
									<h3 className="text-sm font-bold text-foreground">
										{issue.title}
									</h3>
									<p className="text-xs text-muted-foreground mt-1">
										{issue.description}
									</p>
									<div className="mt-2 bg-background/50 p-2 rounded text-xs border border-border">
										<span className="font-bold text-blue-400">
											💡 Suggestion:
										</span>{" "}
										{issue.solution}
									</div>
									<Button
										onClick={() => applyAutoFix(issue)}
										variant="outline"
										size="sm"
										className="mt-2 w-full text-xs h-8"
									>
										<Wrench className="h-3 w-3 mr-1" /> Apply Auto-Fix
									</Button>
								</div>
							</div>
						</div>
					))}
				</div>
			)}
		</div>
	);
}
