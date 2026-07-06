import {
	ChevronDown,
	ChevronRight,
	Cpu,
	Folder,
	FolderOpen,
	MonitorSpeaker,
	Settings,
	Square,
	Thermometer,
	Volume2,
} from "lucide-react";
import type React from "react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

interface Device {
	id: string;
	name: string;
	type: string;
	zone: string;
	status: "normal" | "warning" | "fault";
	address: string;
}

interface Zone {
	id: string;
	name: string;
	parent?: string;
	type: "panel" | "loop" | "circuit" | "zone" | "integration";
	devices: Device[];
	children?: Zone[];
}

interface ZoneNodeProps {
	zone: Zone;
	level: number;
	selectedDevice: string | null;
	onDeviceSelect: (deviceId: string) => void;
	onZoomToZone: (zoneId: string) => void;
}

const ZoneNode: React.FC<ZoneNodeProps> = ({
	zone,
	level,
	selectedDevice,
	onDeviceSelect,
	onZoomToZone,
}) => {
	const { t } = useTranslation();
	const [expanded, setExpanded] = useState(true);

	// Determine icon based on type
	const getIcon = (type: string, expanded: boolean) => {
		switch (type) {
			case "panel":
				return expanded ? (
					<FolderOpen className="h-4 w-4" />
				) : (
					<Folder className="h-4 w-4" />
				);
			case "loop":
				return <Settings className="h-4 w-4" />;
			case "circuit":
				return <Cpu className="h-4 w-4" />;
			case "zone":
				return <Square className="h-4 w-4" />;
			default:
				return <Folder className="h-4 w-4" />;
		}
	};

	// Determine status color based on devices
	const getStatusColor = () => {
		if (zone.devices.some((d) => d.status === "fault")) return "text-red-500";
		if (zone.devices.some((d) => d.status === "warning"))
			return "text-amber-500";
		return "text-emerald-500";
	};

	return (
		<div className="select-none">
			<div
				className={`flex items-center gap-2 py-1 px-2 rounded hover:bg-slate-700 cursor-pointer ${
					selectedDevice && zone.devices.some((d) => d.id === selectedDevice)
						? "bg-slate-700"
						: ""
				}`}
				style={{ paddingLeft: `${level * 20 + 8}px` }}
				onClick={{{() => {					if (zone.children && zone.children.length > 0) {						setExpanded(!expanded);
					} else {
						onZoomToZone(zone.id);
					}
				}}
			>
				{zone.children && zone.children.length > 0 ? (
					expanded ? (
						<ChevronDown className="h-4 w-4" />
					) : (
						<ChevronRight className="h-4 w-4" />
					)
				) : (
					<div className="w-4 h-4" />
				)}
				{getIcon(zone.type, expanded)}
				<span className="text-sm truncate">{zone.name}</span>
				{zone.devices.length > 0 && (
					<span
						className={`ml-auto text-xs px-2 py-0.5 rounded-full ${getStatusColor()} bg-slate-800`}
					>
						{zone.devices.length} {t("fireAlarm.devices")}
					</span>
				)}
			</div>

			{expanded && zone.children && (
				<div>
					{zone.children.map((child) => (
						<ZoneNode
							key={child.id}
							zone={child}
							level={level + 1}
							selectedDevice={selectedDevice}
							onDeviceSelect={onDeviceSelect}
							onZoomToZone={onZoomToZone}
						/>
					))}

					{zone.devices.map((device) => (
						<div
							key={device.id}
							className={`flex items-center gap-2 py-1 px-2 rounded hover:bg-slate-700 cursor-pointer ${
								selectedDevice === device.id ? "bg-slate-700" : ""
							}`}
							style={{ paddingLeft: `${(level + 1) * 20 + 8}px` }}
							onClick={{() => onDeviceSelect(device.id) onKeyDown={(e) => e.key === "Enter" && {() => onDeviceSelect(device.id)}						>
							<div className="w-4" />
							{device.type === "smoke" && (
								<MonitorSpeaker className="h-4 w-4" />
							)}
							{device.type === "heat" && <Thermometer className="h-4 w-4" />}
							{device.type === "pull" && <Square className="h-4 w-4" />}
							{device.type === "horns" && <Volume2 className="h-4 w-4" />}
							{device.type === "facp" && <Settings className="h-4 w-4" />}
							<span className="text-sm truncate">{device.name}</span>
							<span
								className={`ml-auto text-xs px-2 py-0.5 rounded-full ${
									device.status === "normal"
										? "text-emerald-500 bg-emerald-500/10"
										: device.status === "warning"
											? "text-amber-500 bg-amber-500/10"
											: "text-red-500 bg-red-500/10"
								}`}
							>
								{device.status}
							</span>
						</div>
					))}
				</div>
			)}
		</div>
	);
};

interface ZoneNavigatorProps {
	zones: Zone[];
	selectedDevice: string | null;
	onDeviceSelect: (deviceId: string) => void;
	onZoomToZone: (zoneId: string) => void;
}

export const ZoneNavigator: React.FC<ZoneNavigatorProps> = ({
	zones,
	selectedDevice,
	onDeviceSelect,
	onZoomToZone,
}) => {
	const { t } = useTranslation();

	return (
		<div className="h-full overflow-y-auto">
			<div className="mb-3 px-2">
				<h3 className="text-sm font-medium text-slate-300">
					{t("fireAlarm.systemNavigator")}
				</h3>
			</div>

			<div className="space-y-1">
				{zones.map((zone) => (
					<ZoneNode
						key={zone.id}
						zone={zone}
						level={0}
						selectedDevice={selectedDevice}
						onDeviceSelect={onDeviceSelect}
						onZoomToZone={onZoomToZone}
					/>
				))}
			</div>
		</div>
	);
};
