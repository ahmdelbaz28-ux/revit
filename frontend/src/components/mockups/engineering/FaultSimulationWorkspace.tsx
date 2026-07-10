
import { actions, useStore } from "@/store/simpleStore";
import {
	ControlPanel,
	EventLog,
	Header,
	HelpDrawer,
	Scene3D,
	StatusGauges,
} from "./dashboard";
import { useFaultLogic } from "./hooks/useFaultLogic";

export function FaultSimulationWorkspace() {
	const theme = useStore((s) => s.theme);
	const helpOpen = useStore((s) => s.helpOpen);
	const eventLogs = useStore((s) => s.eventLogs);
	const liveData = useStore((s) => s.liveData);
	const dataMode = useStore((s) => s.dataMode);
	const connectionStatus = useStore((s) => s.connectionStatus);
	const _faults = useStore((s) => s.faults);

	const { isFaulty, toggleFault } = useFaultLogic();

	const themeClass =
		theme === "dark" ? "dark" : theme === "blue" ? "theme-blue" : "";

	return (
		<div
			className={`${themeClass} h-screen w-screen overflow-hidden font-sans`}
		>
			<div className="bg-background text-foreground h-full w-full flex flex-col transition-colors duration-300">
				<Header
					theme={theme}
					dataMode={dataMode}
					connectionStatus={connectionStatus}
					onThemeChange={actions.setTheme}
					onDataModeChange={actions.setDataMode}
					onHelpToggle={actions.toggleHelp}
				/>

				<div className="flex flex-1 overflow-hidden relative">
					{/* Main Content Area */}
					<div className="flex-1 p-6 flex gap-6 overflow-hidden">
						{/* 3D Scene & Gauges (Left) */}
						<div className="flex-1 bg-card rounded-md border border-border p-6 flex flex-col relative overflow-hidden">
							<div className="flex items-center justify-between mb-4">
								<div className="text-xs font-bold text-muted-foreground uppercase tracking-wider">
									Live Simulation Grid
								</div>
								<StatusGauges liveData={liveData} dataMode={dataMode} />
							</div>

							<div className="flex-1 bg-background/50 rounded-lg border border-border overflow-hidden">
								<Scene3D />
							</div>

							{/* Simulation Warning */}
							<div className="absolute bottom-4 left-4 text-[10px] text-primary bg-primary/10 px-2 py-1 rounded border border-primary/20">
								SIMULATION MODE ONLY - NOT FOR ENGINEERING DECISIONS
							</div>
						</div>

						{/* Controls & Logs (Right) */}
						<div className="w-80 flex flex-col gap-6 shrink-0">
							<ControlPanel
								isFaulty={isFaulty}
								onFaultToggle={toggleFault}
								onStressTest={() => {
									actions.addLog(
										"Starting stress test with 50 concurrent faults...",
									);
									for (let i = 1; i <= 50; i++) {
										actions.addFault(`fault-${i}`);
									}
								}}
							/>
							<EventLog
								eventLogs={eventLogs.map((log) => ({
									message: log.message,
									type: log.type,
									timestamp: log.timestamp,
								}))}
								dataMode={dataMode}
								connectionStatus={connectionStatus}
							/>
						</div>
					</div>

					<HelpDrawer helpOpen={helpOpen} onHelpToggle={actions.toggleHelp} />
				</div>
			</div>
		</div>
	);
}

export default FaultSimulationWorkspace;
