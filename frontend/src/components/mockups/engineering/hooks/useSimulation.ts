
import { useEffect } from "react";
import { actions, useStore } from "@/store/simpleStore";

export function useSimulation() {
        const faults = useStore((s) => s.faults);
        const dataMode = useStore((s) => s.dataMode);
        const connectionStatus = useStore((s) => s.connectionStatus);
        const liveData = useStore((s) => s.liveData);

        const isFaulty = (id: string) => faults.some((f) => f.id === id);

        // 1. Simulator: Live Data Fluctuations (Random Walk)
        useEffect(() => {
                const interval = setInterval(() => {
                        if (dataMode === "simulation" && connectionStatus === "connected") {
                                const currentVoltage = (liveData.voltage as number) || 220;
                                const currentCurrent = (liveData.current as number) || 15;
                                const currentFreq = (liveData.frequency as number) || 50;

                                // V211: SonarCloud S2245 — Math.random() flagged as pseudo-random.
                                // These are simulation jitter values (±0.5V voltage, ±0.1A current, ±0.01Hz freq)
                                // for a live-data MOCK display. NOT security-sensitive.
                                // Using Web Crypto API to satisfy the rule.
                                const _simRand = new Uint8Array(3);
                                crypto.getRandomValues(_simRand);
                                const deltaV = ((_simRand[0] / 255) - 0.5) * 2;
                                const deltaI = ((_simRand[1] / 255) - 0.5) * 0.2;
                                const deltaF = ((_simRand[2] / 255) - 0.5) * 0.02;

                                actions.updateLiveData({
                                        voltage: Math.min(240, Math.max(200, currentVoltage + deltaV)),
                                        current: Math.min(20, Math.max(10, currentCurrent + deltaI)),
                                        frequency: Math.min(50.5, Math.max(49.5, currentFreq + deltaF)),
                                });
                        }
                }, 1000);
                return () => clearInterval(interval);
        }, [dataMode, connectionStatus, liveData]);

        // 2. Automated Scenario: Gen Overload triggers Battery Failure
        useEffect(() => {
                if (
                        isFaulty("gen-01") &&
                        !isFaulty("bat-01") &&
                        connectionStatus === "connected"
                ) {
                        actions.addLog(
                                "CRITICAL: Generator overload detected. Cascading failure risk!",
                        );
                        const timeout = setTimeout(() => {
                                actions.addFault("bat-01");
                                actions.addLog(
                                        "CASCADE FAILURE: Battery bank failed due to sustained generator overload!",
                                );
                        }, 3000);
                        return () => clearTimeout(timeout);
                }
        }, [connectionStatus, isFaulty]);

        return { faults, isFaulty };
}
