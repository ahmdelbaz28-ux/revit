/**
 * HistoryTimeline.tsx — Timeline view for conversion history
 */

import { Clock, FileDown, FileUp, History, RotateCcw } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
	digitalTwinService,
	type VersionInfo,
} from "@/services/digitalTwinService";

export function HistoryTimeline() {
	const [versions, setVersions] = useState<VersionInfo[]>([]);
	const [loading, setLoading] = useState(true);
	const [rollingBack, setRollingBack] = useState<string | null>(null);

	const fetchHistory = async () => {
		setLoading(true);
		try {
			const history = await digitalTwinService.getHistory();
			setVersions(Array.isArray(history) ? history : []);
		} catch {
			setVersions([]);
		} finally {
			setLoading(false);
		}
	};

	useEffect(() => {
		fetchHistory();
	}, [fetchHistory]);

	const handleRollback = async (versionId: string) => {
		setRollingBack(versionId);
		try {
			await digitalTwinService.rollback(versionId);
			toast.success(`Rolled back to ${versionId}`);
			fetchHistory();
		} catch (err) {
			toast.error(
				`Rollback failed: ${err instanceof Error ? err.message : "Unknown error"}`,
			);
		} finally {
			setRollingBack(null);
		}
	};

	const statusColors: Record<string, string> = {
		success: "bg-emerald-500",
		partial: "bg-amber-500",
		failed: "bg-red-500",
	};

	return (
		<Card className="border-slate-700 bg-slate-800">
			<CardHeader>
				<CardTitle className="flex items-center gap-2 text-slate-100">
					<History className="h-5 w-5 text-orange-400" />
					Conversion History
				</CardTitle>
			</CardHeader>
			<CardContent>
				{loading ? (
					<div className="space-y-3">
						{[...Array(3)].map((_, i) => (  // NOSONAR - typescript:S7723
							<Skeleton key={i} className="h-16 w-full bg-slate-700" />  // NOSONAR — S6479: array index key acceptable for static list
						))}
					</div>
				) : versions.length === 0 ? (  // NOSONAR — S3358: nested ternary acceptable in this localized context
					<p className="text-center text-slate-500 py-8">
						No conversion history available
					</p>
				) : (
					<div className="space-y-3">
						{versions.map((v, idx) => (
							<div
								key={v.version_id || idx}
								className="relative flex items-start gap-4 p-3 bg-slate-900/50 rounded-lg border border-slate-700"
							>
								<div
									className={`h-3 w-3 rounded-full mt-1 shrink-0 ${statusColors[v.status] || "bg-slate-500"}`}
								/>
								<div className="flex-1 min-w-0">
									<div className="flex items-center gap-2 flex-wrap">
										<Badge
											variant="outline"
											className="border-slate-600 text-slate-300 text-xs"
										>
											{v.conversion_type}
										</Badge>
										<span className="text-xs text-slate-500 flex items-center gap-1">
											<Clock className="h-3 w-3" />
											{new Date(v.timestamp).toLocaleString()}
										</span>
									</div>
									<div className="mt-1 flex items-center gap-2 text-xs text-slate-400">
										<FileUp className="h-3 w-3" />
										<span className="truncate">{v.source_file}</span>
										<FileDown className="h-3 w-3 ml-1" />
										<span className="truncate">{v.target_file}</span>
									</div>
									<div className="mt-1 text-xs text-slate-500">
										{v.elements_count} elements · {v.status}
									</div>
								</div>
								<Button
									size="sm"
									variant="outline"
									onClick={() => handleRollback(v.version_id)}
									disabled={rollingBack === v.version_id}
									className="border-slate-600 text-slate-300 hover:bg-slate-800 shrink-0"
								>
									<RotateCcw className="h-3 w-3 mr-1" />
									{rollingBack === v.version_id
										? "Rolling back..."
										: "Rollback"}
								</Button>
							</div>
						))}
					</div>
				)}
			</CardContent>
		</Card>
	);
}
