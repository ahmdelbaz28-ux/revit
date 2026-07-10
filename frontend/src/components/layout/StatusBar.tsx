import type React from "react";

interface StatusBarProps {
        backendUrl: string;
        isConnected: boolean;
        environment: string;
}

const APP_VERSION = "v1.55.0";

const StatusBar: React.FC<StatusBarProps> = ({
        backendUrl,
        isConnected,
        environment,
}) => {
        return (
                <footer
                        className="h-7 bg-[#0a0e17] flex items-center px-4 gap-3 text-[11px] shrink-0 text-muted-foreground border-t border-white/10"
                        data-onboarding="status-bar"
                >
                        <span className="font-medium text-cyan-400">BAZSPARK {APP_VERSION}</span>

                        <div className="h-3 w-px bg-white/10" />

                        <span className="truncate max-w-[40vw] font-mono tabular-nums" title={backendUrl}>
                                {backendUrl}
                        </span>

                        <div className="h-3 w-px bg-white/10" />

                        <span className="capitalize">{environment}</span>

                        <div className="flex-1" />

                        <div className="flex items-center gap-1.5">
                                <span
                                        className={`h-1.5 w-1.5 rounded-full ${isConnected ? "bg-success" : "bg-slate-500"}`}
                                />
                                <span className="tabular-nums">{isConnected ? "Connected" : "Disconnected"}</span>
                        </div>
                </footer>
        );
};

export default StatusBar;
