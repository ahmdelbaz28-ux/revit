import { FaultSimulationWorkspace } from "./FaultSimulationWorkspace";

/**
 * Demo component showing how to integrate FaultSimulationWorkspace
 * with a parent component's state or a global state manager (like Zustand).
 */
export function FaultSimulationIntegrationDemo() {
	return (
		<div className="relative h-screen w-screen">
			{/*
        FaultSimulationWorkspace now uses the internal store directly.
        This demo shows the workspace component with all its features.
      */}
			<FaultSimulationWorkspace />

			{/* Optional: Info panel */}
			<div className="absolute bottom-4 left-4 bg-background/90 p-4 rounded-lg border border-border shadow-lg max-w-xs text-xs">
				<div className="font-bold mb-2 text-foreground">Integration Demo</div>
				<p className="text-muted-foreground mb-3">
					FaultSimulationWorkspace uses the global store for state management.
				</p>
				<button
					onClick={() => {
						import("@/store/simpleStore").then(({ actions }) => {
							actions.addFault("gen-01");
						});
					}}
					className="w-full py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded font-medium"
				>
					External Trigger: Gen Fault
				</button>
			</div>
		</div>
	);
}

export default FaultSimulationIntegrationDemo;
