import { useEffect } from "react";
import { dataService } from "@/services/dataService";
import { actions, useStore } from "@/store/simpleStore";

export function useTelemetryStream() {
	const dataMode = useStore((s) => s.dataMode);
	const liveData = useStore((s) => s.liveData);
	const connectionStatus = useStore((s) => s.connectionStatus);

	useEffect(() => {
		if (dataMode === "live") {
			dataService.connect();
		} else {
			dataService.disconnect();
		}
		return () => {
			dataService.disconnect();
		};
	}, [dataMode]);

	return { liveData, dataMode, connectionStatus };
}
