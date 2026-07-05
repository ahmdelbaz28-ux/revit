import React from "react";
import { toast } from "sonner";

interface LogItem {
	message: string;
	type?: string;
	timestamp?: number;
}

interface EventLogProps {
	eventLogs: LogItem[];
	dataMode: string;
	connectionStatus: string;
}

export function EventLog({
	eventLogs,
	dataMode,
	connectionStatus,
}: EventLogProps) {
	const exportJson = () => {
		if (dataMode === "demo" || dataMode === "simulation") {
			toast.error(
				"Export blocked: Simulation Mode does not generate valid engineering data.",
			);
			return;
		}

		if (connectionStatus === "disconnected") {
			toast.error(
				"Export blocked: Connection lost. Cannot verify data integrity.",
			);
			return;
		}

		const dataStr =
			"data:text/json;charset=utf-8," +
			encodeURIComponent(JSON.stringify(eventLogs));
		const downloadAnchorNode = document.createElement("a");
		downloadAnchorNode.setAttribute("href", dataStr);
		downloadAnchorNode.setAttribute("download", "scada_logs.json");
		document.body.appendChild(downloadAnchorNode);
		downloadAnchorNode.click();
		downloadAnchorNode.remove();
	};

	const isBlocked =
		dataMode === "demo" ||
		dataMode === "simulation" ||
		connectionStatus === "disconnected";
	const buttonColorClass = isBlocked
		? "text-muted-foreground cursor-not-allowed"
		: "text-primary hover:underline";
	const buttonClass = `text-[10px] ${buttonColorClass}`;

	return (
		<div className="bg-card rounded-xl border border-border p-6 flex-1 flex flex-col overflow-hidden">
			<div className="flex items-center justify-between mb-4">
				<div className="text-xs font-bold text-muted-foreground uppercase tracking-wider">
					SCADA Event Log
				</div>
				<button
					onClick={exportJson}
					className={buttonClass}
					disabled={isBlocked}
					title={
						isBlocked
							? "Unavailable in Simulation Mode or Disconnected"
							: "Export logs"
					}
				>
					Export JSON
				</button>
			</div>
			<div className="flex-1 bg-background/50 rounded-lg border border-border p-3 overflow-y-auto font-mono text-[10px] space-y-1">
				{eventLogs.map((log, index) => (
					<div
						key={index}
						className={`${log.message.includes("CRITICAL") || log.message.includes("CASCADE") || log.message.includes("Alert") ? "text-destructive" : "text-foreground"}`}
					>
						{log.message}
					</div>
				))}
				{eventLogs.length === 0 && (
					<div className="text-muted-foreground italic">No events logged.</div>
				)}
			</div>
		</div>
	);
}

export default EventLog;
