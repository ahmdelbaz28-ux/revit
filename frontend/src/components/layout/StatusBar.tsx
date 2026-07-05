import type React from "react";

interface StatusBarProps {
	backendUrl: string;
	isConnected: boolean;
	environment: string;
}

const StatusBar: React.FC<StatusBarProps> = ({
	backendUrl,
	isConnected,
	environment,
}) => {
	return (
		<footer
			className="h-7 bg-slate-900 border-t border-slate-700 flex items-center px-3 gap-4 text-xs shrink-0"
			data-onboarding="status-bar"
		>
			<span className="text-slate-500">BAZSPARK V55.0.0</span>

			<div className="h-3 w-px bg-slate-700" />

			<span className="text-slate-500 truncate" title={backendUrl}>
				{backendUrl}
			</span>

			<div className="h-3 w-px bg-slate-700" />

			<span className="text-slate-500">{environment}</span>

			<div className="flex-1" />

			<div className="flex items-center gap-1.5">
				<span
					className={`h-1.5 w-1.5 rounded-full ${isConnected ? "bg-green-500" : "bg-red-500"}`}
				/>
				<span className="text-slate-500">
					{isConnected ? "Connected" : "Disconnected"}
				</span>
			</div>
		</footer>
	);
};

export default StatusBar;
