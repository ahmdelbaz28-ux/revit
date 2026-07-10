
interface ControlPanelProps {
	isFaulty: (id: string) => boolean;
	onFaultToggle: (id: string) => void;
	onStressTest: () => void;
}

export function ControlPanel({
	isFaulty,
	onFaultToggle,
	onStressTest,
}: ControlPanelProps) {
	return (
		<div className="bg-card rounded-md border border-border p-6 flex flex-col">
			<div className="text-xs font-bold text-muted-foreground uppercase tracking-wider mb-4">
				Simulation Control
			</div>

			<div className="space-y-4">
				<div className="p-4 bg-muted/50 rounded-lg border border-border">
					<div className="text-xs font-bold mb-2">Inject Faults</div>
					<div className="space-y-2">
						<button
							onClick={() => onFaultToggle("gen-01")}
							className={`w-full py-2 rounded-md text-xs font-medium transition-colors ${
								isFaulty("gen-01")
									? "bg-destructive text-destructive-foreground hover:bg-destructive/90"
									: "bg-muted border border-border hover:bg-accent"
							}`}
						>
							{isFaulty("gen-01") ? "Clear Gen Fault" : "Simulate Gen Overload"}
						</button>
						<button
							onClick={() => onFaultToggle("bat-01")}
							className={`w-full py-2 rounded-md text-xs font-medium transition-colors ${
								isFaulty("bat-01")
									? "bg-destructive text-destructive-foreground hover:bg-destructive/90"
									: "bg-muted border border-border hover:bg-accent"
							}`}
						>
							{isFaulty("bat-01")
								? "Clear Battery Fault"
								: "Simulate Battery Failure"}
						</button>
						<button
							onClick={onStressTest}
							className="w-full py-2 rounded-md text-xs font-medium bg-primary/10 text-primary border border-primary/20 hover:bg-primary/20 transition-colors"
						>
							Run Stress Test (50 Faults)
						</button>
					</div>
				</div>
			</div>
		</div>
	);
}

export default ControlPanel;
