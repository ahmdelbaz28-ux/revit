/**
 * DemoDataBanner.tsx — visible banner shown when the app is running on mock
 * / simulated data instead of a real backend connection.
 *
 * F-08 FIX (Engineering Review): the previous code silently fell back to
 * `mockWorker.generateSimulatedData()` when the real WebSocket failed, with
 * only a small `dataMode.toUpperCase()` label in the dashboard Header. In a
 * production deployment this meant an engineer could be looking at completely
 * fabricated telemetry without any visible warning — a serious safety issue
 * for a fire-alarm design tool.
 *
 * This banner is rendered at the top of the AppShell whenever `dataMode` is
 * not "live" OR `connectionStatus` is not "connected". It uses high-contrast
 * amber-on-black styling so it cannot be missed, and includes both Arabic
 * and English text so it is unambiguous for the project's primary audience.
 */

import { useStore } from "@/store/simpleStore";

export function DemoDataBanner() {
        const dataMode = useStore((s) => s.dataMode);
        const connectionStatus = useStore((s) => s.connectionStatus);

        const isLive = dataMode === "live" && connectionStatus === "connected";
        if (isLive) return null;

        // Build the reason text so the user knows WHY they're seeing demo data.
        const reason =
                dataMode !== "live"
                        ? `data mode = ${dataMode}`
                        : `connection = ${connectionStatus}`;

        return (
                <div
                        role="alert"
                        aria-live="polite"
                        style={{
                                background: "#000000",
                                color: "#fbbf24",
                                borderBottom: "2px solid #fbbf24",
                                padding: "8px 16px",
                                fontFamily: "system-ui, -apple-system, sans-serif",
                                fontSize: "13px",
                                fontWeight: 600,
                                textAlign: "center",
                                letterSpacing: "0.3px",
                                position: "sticky",
                                top: 0,
                                zIndex: 9999,
                                pointerEvents: "auto",
                        }}
                >
                        <span aria-hidden="true" style={{ marginRight: "8px" }}>
                                ⚠️
                        </span>
                        <strong>بيانات تجريبية</strong>
                        <span style={{ margin: "0 8px", opacity: 0.6 }}>|</span>
                        <strong>DEMO DATA</strong>
                        <span style={{ marginLeft: "8px", fontWeight: 400, opacity: 0.85 }}>
                                — {reason}. لا تستخدم هذه البيانات لتقديم تصميم فعلي للـ AHJ.
                                Do NOT submit designs based on this data for AHJ review.
                        </span>
                </div>
        );
}
