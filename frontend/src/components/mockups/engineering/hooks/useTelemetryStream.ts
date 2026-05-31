import { useEffect } from "react";
import { useStore, actions } from "@/store/simpleStore";
import { dataService } from "@/services/dataService";

export function useTelemetryStream() {
  const dataMode = useStore((s) => s.dataMode);
  const liveData = useStore((s) => s.liveData);
  const connectionStatus = useStore((s) => s.connectionStatus);

  useEffect(() => {
    if (dataMode === 'live') {
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
