// NOSONAR
import { Button } from "@/components/ui/button";
import { useStore } from "@/store/simpleStore";

export function ReportManager() {
	const canvasElements = useStore((s) => s.canvasElements);

	const generateReport = () => {
		// Conflict Detection
		const conflicts: string[] = [];
		const devices = canvasElements.filter((el) => el.type !== "cable");
		const cables = canvasElements.filter((el) => el.type === "cable");

		// 1. Unconnected terminals
		devices.forEach((dev) => {
			const isConnected = cables.some(
				(c) => c.from === dev.id || c.to === dev.id,
			);
			if (!isConnected) {
				conflicts.push(
					`Device ${dev.id} (${dev.type}) is not connected to any network.`,
				);
			}
		});

		// 2. Voltage mismatches
		cables.forEach((cable) => {
			const fromEl = devices.find((el) => el.id === cable.from);
			const toEl = devices.find((el) => el.id === cable.to);
			if (fromEl && toEl && fromEl.voltage !== toEl.voltage) {
				conflicts.push(
					`Voltage mismatch on cable ${cable.id}: ${fromEl.type} (${fromEl.voltage}V) -> ${toEl.type} (${toEl.voltage}V)`,
				);
			}
		});

		return {
			totalDevices: devices.length,
			totalCables: cables.length,
			conflicts,
		};
	};

	const report = generateReport();

	return (
		<div className="p-6 text-foreground h-full overflow-auto bg-card/50 border rounded-lg">
			<div className="flex justify-between items-center mb-4">
				<h2 className="text-xl font-bold text-primary">
					Intelligent Report Manager
				</h2>
				<Button onClick={() => window.print()} variant="outline">
					Print / Export PDF
				</Button>
			</div>

			<div className="grid grid-cols-2 gap-4 mb-4">
				<div className="p-4 border rounded bg-card">
					<h3 className="font-semibold mb-2">System Summary</h3>
					<div className="text-sm space-y-1 font-mono">
						<div>Total Devices: {report.totalDevices}</div>
						<div>Total Cables: {report.totalCables}</div>
					</div>
				</div>
				<div className="p-4 border rounded bg-card">
					<h3 className="font-semibold mb-2">Health Status</h3>
					<div
						className={`text-sm font-bold ${report.conflicts.length === 0 ? "text-emerald-400" : "text-orange-400"}`}
					>
						{report.conflicts.length === 0
							? "All Systems Operational"
							: `${report.conflicts.length} Issues Detected`}
					</div>
				</div>
			</div>

			<div
				className={`p-4 border rounded ${report.conflicts.length > 0 ? "border-red-500/50 bg-red-500/10" : "border-emerald-500/50 bg-emerald-500/10"}`}
			>
				<h3
					className={`font-semibold mb-2 ${report.conflicts.length > 0 ? "text-red-400" : "text-emerald-400"}`}
				>
					Conflict Detection & Validation
				</h3>
				{report.conflicts.length === 0 ? (
					<p className="text-sm">
						No conflicts detected in the current design.
					</p>
				) : (
					<ul className="text-sm list-disc pl-5 space-y-1">
						{report.conflicts.map((conf, i) => (
							<li key={`${i}-${conf.substring(0, 20)}`} className="text-foreground">
								{conf}
							</li>
						))}
					</ul>
				)}
			</div>
		</div>
	);
}
