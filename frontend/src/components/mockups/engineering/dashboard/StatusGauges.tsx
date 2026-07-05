interface StatusGaugesProps {
	liveData: Record<string, unknown>;
	dataMode: string;
}

export function StatusGauges({ liveData, dataMode }: StatusGaugesProps) {
	const voltage = (liveData.voltage as number) || 220;
	const current = (liveData.current as number) || 15;
	const frequency = (liveData.frequency as number) || 50;

	return (
		<div className="flex gap-4 text-xs font-mono">
			<div className="bg-background/80 px-2 py-1 rounded border border-border">
				<span className="text-muted-foreground">V:</span>{" "}
				<span className="text-primary font-bold">{voltage.toFixed(1)}</span>
			</div>
			<div className="bg-background/80 px-2 py-1 rounded border border-border">
				<span className="text-muted-foreground">I:</span>{" "}
				<span className="text-primary font-bold">{current.toFixed(2)}</span>
			</div>
			<div className="bg-background/80 px-2 py-1 rounded border border-border">
				<span className="text-muted-foreground">F:</span>{" "}
				<span className="text-primary font-bold">{frequency.toFixed(2)}</span>
			</div>
			{dataMode === "live" && (
				<>
					<div className="bg-background/80 px-2 py-1 rounded border border-border text-emerald-500">
						<span className="text-muted-foreground">Ping:</span>{" "}
						<span className="font-bold">45ms</span>
					</div>
					<div className="bg-background/80 px-2 py-1 rounded border border-border text-emerald-500">
						<span className="text-muted-foreground">Rate:</span>{" "}
						<span className="font-bold">1/s</span>
					</div>
				</>
			)}
		</div>
	);
}

export default StatusGauges;
