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
                        className="h-7 bg-card border-t border-border flex items-center px-3 gap-3 text-xs shrink-0"
                        data-onboarding="status-bar"
                >
                        <span className="text-muted-foreground font-medium">
                                BAZSPARK {APP_VERSION}
                        </span>

                        <div className="h-3 w-px bg-secondary" />

                        <span className="text-muted-foreground truncate max-w-[40vw]" title={backendUrl}>
                                {backendUrl}
                        </span>

                        <div className="h-3 w-px bg-secondary" />

                        <span className="text-muted-foreground capitalize">{environment}</span>

                        <div className="flex-1" />

                        <div className="flex items-center gap-1.5">
                                <span
                                        className={`h-1.5 w-1.5 rounded-full ${isConnected ? "bg-green-500" : "bg-red-500"}`}
                                />
                                <span className="text-muted-foreground">
                                        {isConnected ? "Connected" : "Disconnected"}
                                </span>
                        </div>
                </footer>
        );
};

export default StatusBar;
