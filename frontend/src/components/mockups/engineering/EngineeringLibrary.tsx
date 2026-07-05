import {
	Battery,
	Box,
	Eye,
	Power,
	Siren,
	Thermometer,
	Wifi,
	Zap,
} from "lucide-react";
import type React from "react";
import type { DeviceType } from "@/store/simpleStore";

// تعريف موسع لأنواع العناصر لتشمل أجهزة الاستشعار والأنظمة
export type AdvancedDeviceType =
	| DeviceType
	| "SENSOR_MOTION"
	| "SENSOR_SMOKE"
	| "CAMERA"
	| "SPEAKER";

interface LibraryItem {
	id: AdvancedDeviceType;
	label: string;
	category: "Power" | "Safety" | "Security" | "Network";
	icon: React.ReactNode;
	defaultLoad: number;
	description: string;
}

const LIBRARY_ITEMS: LibraryItem[] = [
	// أجهزة الطاقة (من السابق)
	{
		id: "GENERATOR",
		label: "Generator",
		category: "Power",
		icon: <Zap size={18} />,
		defaultLoad: 500,
		description: "Main Power Source",
	},
	{
		id: "BATTERY",
		label: "Battery Bank",
		category: "Power",
		icon: <Battery size={18} />,
		defaultLoad: 300,
		description: "DC Backup System",
	},
	{
		id: "LOAD",
		label: "Critical Load",
		category: "Power",
		icon: <Power size={18} />,
		defaultLoad: 150,
		description: "General Consumption",
	},

	// أجهزة السلامة (جديد)
	{
		id: "SENSOR_SMOKE",
		label: "Smoke Detector",
		category: "Safety",
		icon: <Siren size={18} />,
		defaultLoad: 5,
		description: "Fire Alarm Sensor",
	},
	{
		id: "SENSOR_MOTION",
		label: "Motion Sensor",
		category: "Safety",
		icon: <Wifi size={18} />,
		defaultLoad: 2,
		description: "Intrusion Detection",
	},

	// الأجهزة الأمنية (جديد)
	{
		id: "CAMERA",
		label: "IP Camera",
		category: "Security",
		icon: <Eye size={18} />,
		defaultLoad: 15,
		description: "Surveillance Unit",
	},
	{
		id: "SPEAKER",
		label: "PA Speaker",
		category: "Security",
		icon: <Box size={18} />,
		defaultLoad: 20,
		description: "Public Address",
	},
];

interface EngineeringLibraryProps {
	onDragStart: (item: LibraryItem) => void;
}

export function EngineeringLibrary({ onDragStart }: EngineeringLibraryProps) {
	const handleDrag = (e: React.DragEvent, item: LibraryItem) => {
		e.dataTransfer.setData("application/json", JSON.stringify(item));
		e.dataTransfer.effectAllowed = "copy";
		onDragStart(item);
	};

	return (
		<div className="w-72 bg-card border-r border-border flex flex-col h-full select-none">
			<div className="p-4 border-b border-border bg-muted/30">
				<h3 className="font-bold text-sm text-foreground flex items-center gap-2">
					<Box className="w-4 h-4" /> Engineering Library
				</h3>
				<p className="text-[10px] text-muted-foreground mt-1">
					Drag components to the canvas
				</p>
			</div>

			<div className="flex-1 overflow-y-auto p-3 space-y-6">
				{["Power", "Safety", "Security", "Network"].map((cat) => (
					<div key={cat}>
						<h4 className="text-[10px] font-bold uppercase text-muted-foreground mb-2 px-1">
							{cat} Systems
						</h4>
						<div className="space-y-2">
							{LIBRARY_ITEMS.filter((i) => i.category === cat).map((item) => (
								<div
									key={item.id}
									draggable
									onDragStart={(e) => handleDrag(e, item)}
									className="group flex items-center gap-3 p-3 rounded-md border border-border bg-background hover:border-primary hover:shadow-md transition-all cursor-grab active:cursor-grabbing"
								>
									<div className="text-primary group-hover:scale-110 transition-transform">
										{item.icon}
									</div>
									<div className="flex-1 min-w-0">
										<div className="text-xs font-bold text-foreground truncate">
											{item.label}
										</div>
										<div className="text-[9px] text-muted-foreground truncate">
											{item.description}
										</div>
									</div>
									<div className="text-[9px] font-mono text-muted-foreground bg-muted px-1 rounded">
										{item.defaultLoad}A
									</div>
								</div>
							))}
						</div>
					</div>
				))}
			</div>
		</div>
	);
}
