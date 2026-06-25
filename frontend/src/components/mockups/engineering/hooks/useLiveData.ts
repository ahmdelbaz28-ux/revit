import { useEffect, useRef, useState } from "react";
import { useStore, actions } from "@/store/simpleStore";
import { dataService } from "@/services/dataService";

export function useLiveData() {
  const dataMode = useStore((s) => s.dataMode);
  const liveData = useStore((s) => s.liveData);
  const connectionStatus = useStore((s) => s.connectionStatus);

  const [analysisResult, setAnalysisResult] = useState<{
    voltageDropPercent: number;
    lineLosses: number;
    powerFactor: number;
    isCritical: boolean;
    calculatedVoltage: number;
  } | null>(null);

  const workerRef = useRef<Worker | null>(null);

  // 1. Live Mode: Connect to DataService
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

  // 2. Initialize Calculation Worker
  useEffect(() => {
    workerRef.current = new Worker(new URL("../../../../lib/cadCalculator.worker.ts", import.meta.url), { type: "module" });
    
    workerRef.current.onmessage = (e) => {
      const { type, data } = e.data;
      if (type === "result") {
        setAnalysisResult(data);
        if (data.isCritical) {
          actions.addLog(`Analysis Alert: Voltage drop exceeded critical limit! Calculated: ${data.calculatedVoltage.toFixed(1)}V`);
        }
      }
    };

    return () => {
      workerRef.current?.terminate();
    };
  }, []);

  // 3. Send data to worker on updates
  useEffect(() => {
    if (dataMode === 'live' && workerRef.current) {
      workerRef.current.postMessage({
        type: "calculate_load_flow",
        data: liveData
      });
    }
  }, [liveData, dataMode]);

  return { liveData, dataMode, connectionStatus, analysisResult };
}
