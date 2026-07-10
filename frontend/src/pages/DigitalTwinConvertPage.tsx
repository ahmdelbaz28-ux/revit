
/**
 * DigitalTwinConvertPage.tsx — Conversion panel + history timeline
 */

import { useEffect, useState } from "react";
import { ConversionPanel } from "@/components/shared/ConversionPanel";
import { HistoryTimeline } from "@/components/shared/HistoryTimeline";
import { Badge } from "@/components/ui/badge";
import { digitalTwinService } from "@/services/digitalTwinService";

export function DigitalTwinConvertPage() {
	const [status, setStatus] = useState<Record<string, unknown> | null>(null);

	useEffect(() => {
		const fetchStatus = async () => {
			try {
				const s = await digitalTwinService.getStatus();
				setStatus(s as Record<string, unknown>);
			} catch {
				setStatus(null);
			}
		};
		fetchStatus();
	}, []);

	return (
		<div className="flex-1 overflow-auto p-6 max-w-6xl mx-auto space-y-6">
			<div className="flex items-center justify-between">
				<div>
					<h1 className="text-2xl font-bold text-foreground">
						Digital Twin — Convert
					</h1>
					<p className="text-sm text-muted-foreground mt-1">
						Bidirectional conversion between AutoCAD and Revit
					</p>
				</div>
				{status && (
					<Badge
						variant="outline"
						className="border-emerald-600/30 text-success"
					>
						Service: {String(status.status || "unknown")}
					</Badge>
				)}
			</div>
			<ConversionPanel />
			<HistoryTimeline />
		</div>
	);
}
