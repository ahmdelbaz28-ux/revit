import { Battery, Box, Plus, Power, Zap } from "lucide-react";
import type React from "react";
import type { DeviceType } from "@/store/simpleStore";

interface PaletteItem {
	type: DeviceType;
	label: string;
	icon: React.ReactNode;
	defaultLoad: number;
	color: string;
}

const DEVICES: PaletteItem[] = [
	{
		type: "GENERATOR",
		label: "Generator",
		icon: <Zap size={16} />,
		defaultLoad: 500,
		color: "text-amber-400",
	},
	{
		type: "BATTERY",
		label: "Battery Bank",
		icon: <Battery size={16} />,
		defaultLoad: 300,
		color: "text-emerald-400",
	},
	{
		type: "LOAD",
		label: "Critical Load",
		icon: <Power size={16} />,
		defaultLoad: 150,
		color: "text-blue-400",
	},
	{
		type: "PANEL",
		label: "Distribution Panel",
		icon: <Box size={16} />,
		defaultLoad: 50,
		color: "text-slate-400",
	},
];

interface DevicePaletteProps {
	onSelect: (type: DeviceType, load: number) => void;
	selectedType: DeviceType | null;
}

export function DevicePalette({ onSelect, selectedType }: DevicePaletteProps) {
	return (
		<div className="w-64 bg-card border-r border-border flex flex-col h-full">
			<div className="p-4 border-b border-border">
				<h3 className="font-bold text-sm text-foreground">Device Library</h3>
				<p className="text-xs text-muted-foreground mt-1">
					Select a device then click on canvas
				</p>
			</div>
			<div className="flex-1 overflow-y-auto p-4 space-y-3">
				{DEVICES.map((dev) => (
					<button
						key={dev.type}
						onClick={() => onSelect(dev.type, dev.defaultLoad)}
						className={`w-full flex items-center gap-3 p-3 rounded-lg border transition-all ${
							selectedType === dev.type
								? "bg-primary/10 border-primary ring-1 ring-primary"
								: "bg-muted/50 border-border hover:bg-muted hover:border-muted-foreground"
						}`}
					>
						<div className={`${dev.color}`}>{dev.icon}</div>
						<div className="text-left">
							<div className="text-xs font-bold text-foreground">
								{dev.label}
							</div>
							<div className="text-[10px] text-muted-foreground">
								Rating: {dev.defaultLoad}A
							</div>
						</div>
						{selectedType === dev.type && (
							<Plus size={14} className="ml-auto text-primary" />
						)}
					</button>
				))}
			</div>
			<div className="p-4 border-t border-border">
				<button
					onClick={() =>
						window.dispatchEvent(new CustomEvent("nexus-reset-project"))
					}
					className="w-full py-2 text-xs text-destructive hover:bg-destructive/10 rounded border border-transparent hover:border-destructive transition-colors"
				>
					Reset Project
				</button>
			</div>
		</div>
	);
}
