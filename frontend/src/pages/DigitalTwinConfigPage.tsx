// NOSONAR
/**
 * DigitalTwinConfigPage.tsx — Config editor for Digital Twin settings
 */

import { useEffect, useState } from "react";
import { ConfigEditor } from "@/components/shared/ConfigEditor";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { digitalTwinService } from "@/services/digitalTwinService";

export function DigitalTwinConfigPage() {
	const [mappings, setMappings] = useState<unknown[]>([]);

	useEffect(() => {
		const fetchMappings = async () => {
			try {
				const m = await digitalTwinService.getMappings();
				setMappings(Array.isArray(m) ? m : []);
			} catch {
				setMappings([]);
			}
		};
		fetchMappings();
	}, []);

	return (
		<div className="flex-1 overflow-auto p-6 max-w-4xl mx-auto space-y-6">
			<div>
				<h1 className="text-2xl font-bold text-foreground">
					Digital Twin — Configuration
				</h1>
				<p className="text-sm text-muted-foreground mt-1">
					Edit conversion settings and view available mappings
				</p>
			</div>
			<ConfigEditor
				title="Conversion Configuration"
				description="JSON configuration for the digital twin conversion engine"
				loadConfig={async () =>
					(await digitalTwinService.getConfig()) as Record<string, unknown>
				}
				saveConfig={async (config) => {
					await digitalTwinService.setConfig(config);
				}}
			/>
			<Card className="border-border bg-card">
				<CardHeader>
					<CardTitle className="text-foreground">
						Available Mappings ({mappings.length})
					</CardTitle>
				</CardHeader>
				<CardContent>
					{mappings.length === 0 ? (
						<p className="text-muted-foreground text-sm">No mappings available</p>
					) : (
						<div className="space-y-2">
							{mappings.map((m, i) => (
								<div
									key={i}  // NOSONAR — S6479: array index key acceptable for static list
									className="flex items-center gap-2 p-2 bg-muted/50 rounded border border-border"
								>
									<Badge
										variant="outline"
										className="border-border text-foreground/90"
									>
										{typeof m === "object" && m
											? String(
													(m as Record<string, unknown>).name ||  // NOSONAR - typescript:S6551
														`Mapping ${i + 1}`,
												)
											: `Mapping ${i + 1}`}
									</Badge>
									<pre className="text-xs text-muted-foreground flex-1 overflow-auto">
										{JSON.stringify(m, null, 2)}
									</pre>
								</div>
							))}
						</div>
					)}
				</CardContent>
			</Card>
		</div>
	);
}
