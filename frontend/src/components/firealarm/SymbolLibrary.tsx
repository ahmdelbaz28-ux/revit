
import type React from "react";
import { useTranslation } from "react-i18next";

// Define detector types
type DetectorType =
	| "smoke"
	| "heat"
	| "pull"
	| "horns"
	| "speaker"
	| "facp"
	| "duct"
	| "aspirating"
	| "flow"
	| "tamper";

// Define status types
type StatusType = "normal" | "active" | "fault" | "disable" | "selected";

interface SymbolProps {
	size?: "sm" | "md" | "lg";
	status?: StatusType;
	className?: string;
}

interface SymbolLibraryProps extends SymbolProps {
	type: DetectorType;
}

// Helper function to get status color
const getStatusColor = (status: StatusType) => {
	switch (status) {
		case "normal":
			return "#10B981"; // Green
		case "active":
			return "#3B82F6"; // Blue
		case "fault":
			return "#EF4444"; // Red
		case "disable":
			return "#9CA3AF"; // Gray
		case "selected":
			return "#F59E0B"; // Amber
		default:
			return "#10B981"; // Green
	}
};

// Smoke Detector Symbol
export const SmokeDetector: React.FC<SymbolLibraryProps> = ({
	size = "md",
	status = "normal",
	className = "",
}) => {
	const sizeMap = {
		sm: 24,
		md: 32,
		lg: 48,
	};

	const sizeValue = sizeMap[size];
	const color = getStatusColor(status);

	return (
		<svg
			width={sizeValue}
			height={sizeValue}
			viewBox="0 0 24 24"
			className={className}
		>
			<circle
				cx="12"
				cy="12"
				r="10"
				fill={color}
				stroke="#FFFFFF"
				strokeWidth="2"
			/>
			<text
				x="12"
				y="16"
				textAnchor="middle"
				fill="#FFFFFF"
				fontSize="10"
				fontWeight="bold"
			>
				S
			</text>
		</svg>
	);
};

// Heat Detector Symbol
export const HeatDetector: React.FC<SymbolLibraryProps> = ({
	size = "md",
	status = "normal",
	className = "",
}) => {
	const sizeMap = {
		sm: 24,
		md: 32,
		lg: 48,
	};

	const sizeValue = sizeMap[size];
	const color = getStatusColor(status);

	return (
		<svg
			width={sizeValue}
			height={sizeValue}
			viewBox="0 0 24 24"
			className={className}
		>
			<polygon
				points="12,4 20,20 4,20"
				fill={color}
				stroke="#FFFFFF"
				strokeWidth="2"
			/>
			<text
				x="12"
				y="16"
				textAnchor="middle"
				fill="#FFFFFF"
				fontSize="10"
				fontWeight="bold"
			>
				H
			</text>
		</svg>
	);
};

// Pull Station Symbol
export const PullStation: React.FC<SymbolLibraryProps> = ({
	size = "md",
	status = "normal",
	className = "",
}) => {
	const sizeMap = {
		sm: 24,
		md: 32,
		lg: 48,
	};

	const sizeValue = sizeMap[size];
	const color = getStatusColor(status);

	return (
		<svg
			width={sizeValue}
			height={sizeValue}
			viewBox="0 0 24 24"
			className={className}
		>
			<rect
				x="4"
				y="6"
				width="16"
				height="12"
				rx="2"
				fill={color}
				stroke="#FFFFFF"
				strokeWidth="2"
			/>
			<text
				x="12"
				y="16"
				textAnchor="middle"
				fill="#FFFFFF"
				fontSize="10"
				fontWeight="bold"
			>
				P
			</text>
		</svg>
	);
};

// Horn/Strobe Symbol
export const HornStrobe: React.FC<SymbolLibraryProps> = ({
	size = "md",
	status = "normal",
	className = "",
}) => {
	const sizeMap = {
		sm: 24,
		md: 32,
		lg: 48,
	};

	const sizeValue = sizeMap[size];
	const color = getStatusColor(status);

	return (
		<svg
			width={sizeValue}
			height={sizeValue}
			viewBox="0 0 24 24"
			className={className}
		>
			<rect
				x="3"
				y="8"
				width="18"
				height="8"
				rx="2"
				fill={color}
				stroke="#FFFFFF"
				strokeWidth="2"
			/>
			<path d="M8 12 L16 12" stroke="#FFFFFF" strokeWidth="2" />
			<path d="M12 8 L12 16" stroke="#FFFFFF" strokeWidth="2" />
		</svg>
	);
};

// Speaker Symbol
export const Speaker: React.FC<SymbolLibraryProps> = ({
	size = "md",
	status = "normal",
	className = "",
}) => {
	const sizeMap = {
		sm: 24,
		md: 32,
		lg: 48,
	};

	const sizeValue = sizeMap[size];
	const color = getStatusColor(status);

	return (
		<svg
			width={sizeValue}
			height={sizeValue}
			viewBox="0 0 24 24"
			className={className}
		>
			<circle
				cx="12"
				cy="12"
				r="10"
				fill={color}
				stroke="#FFFFFF"
				strokeWidth="2"
			/>
			<path d="M10 10 L14 12 L10 14 Z" fill="#FFFFFF" />
		</svg>
	);
};

// FACP Symbol
export const FACP: React.FC<SymbolLibraryProps> = ({
	size = "md",
	status = "normal",
	className = "",
}) => {
	const sizeMap = {
		sm: 24,
		md: 32,
		lg: 48,
	};

	const sizeValue = sizeMap[size];
	const color = getStatusColor(status);

	return (
		<svg
			width={sizeValue}
			height={sizeValue}
			viewBox="0 0 24 24"
			className={className}
		>
			<rect
				x="2"
				y="4"
				width="20"
				height="16"
				rx="3"
				fill={color}
				stroke="#FFFFFF"
				strokeWidth="2"
			/>
			<rect x="4" y="6" width="16" height="12" rx="1" fill="#1E293B" />
			<circle cx="6" cy="8" r="1" fill="#10B981" />
			<circle cx="6" cy="10" r="1" fill="#EF4444" />
			<circle cx="6" cy="12" r="1" fill="#F59E0B" />
		</svg>
	);
};

// Duct Detector Symbol
export const DuctDetector: React.FC<SymbolLibraryProps> = ({
	size = "md",
	status = "normal",
	className = "",
}) => {
	const sizeMap = {
		sm: 24,
		md: 32,
		lg: 48,
	};

	const sizeValue = sizeMap[size];
	const color = getStatusColor(status);

	return (
		<svg
			width={sizeValue}
			height={sizeValue}
			viewBox="0 0 24 24"
			className={className}
		>
			<rect
				x="6"
				y="8"
				width="12"
				height="8"
				rx="1"
				fill={color}
				stroke="#FFFFFF"
				strokeWidth="2"
			/>
			<path d="M8 8 L8 6 L16 6 L16 8" stroke="#FFFFFF" strokeWidth="2" />
			<path d="M8 16 L8 18 L16 18 L16 16" stroke="#FFFFFF" strokeWidth="2" />
		</svg>
	);
};

// Aspirating Detector Symbol
export const AspiratingDetector: React.FC<SymbolLibraryProps> = ({
	size = "md",
	status = "normal",
	className = "",
}) => {
	const sizeMap = {
		sm: 24,
		md: 32,
		lg: 48,
	};

	const sizeValue = sizeMap[size];
	const color = getStatusColor(status);

	return (
		<svg
			width={sizeValue}
			height={sizeValue}
			viewBox="0 0 24 24"
			className={className}
		>
			<circle
				cx="12"
				cy="12"
				r="10"
				fill={color}
				stroke="#FFFFFF"
				strokeWidth="2"
			/>
			<circle cx="8" cy="8" r="1" fill="#FFFFFF" />
			<circle cx="12" cy="6" r="1" fill="#FFFFFF" />
			<circle cx="16" cy="8" r="1" fill="#FFFFFF" />
			<circle cx="6" cy="12" r="1" fill="#FFFFFF" />
			<circle cx="18" cy="12" r="1" fill="#FFFFFF" />
			<circle cx="8" cy="16" r="1" fill="#FFFFFF" />
			<circle cx="12" cy="18" r="1" fill="#FFFFFF" />
			<circle cx="16" cy="16" r="1" fill="#FFFFFF" />
		</svg>
	);
};

// Flow Switch Symbol
export const FlowSwitch: React.FC<SymbolLibraryProps> = ({
	size = "md",
	status = "normal",
	className = "",
}) => {
	const sizeMap = {
		sm: 24,
		md: 32,
		lg: 48,
	};

	const sizeValue = sizeMap[size];
	const color = getStatusColor(status);

	return (
		<svg
			width={sizeValue}
			height={sizeValue}
			viewBox="0 0 24 24"
			className={className}
		>
			<circle
				cx="12"
				cy="12"
				r="10"
				fill={color}
				stroke="#FFFFFF"
				strokeWidth="2"
			/>
			<text
				x="12"
				y="16"
				textAnchor="middle"
				fill="#FFFFFF"
				fontSize="10"
				fontWeight="bold"
			>
				F
			</text>
		</svg>
	);
};

// Tamper Switch Symbol
export const TamperSwitch: React.FC<SymbolLibraryProps> = ({
	size = "md",
	status = "normal",
	className = "",
}) => {
	const sizeMap = {
		sm: 24,
		md: 32,
		lg: 48,
	};

	const sizeValue = sizeMap[size];
	const color = getStatusColor(status);

	return (
		<svg
			width={sizeValue}
			height={sizeValue}
			viewBox="0 0 24 24"
			className={className}
		>
			<polygon
				points="12,4 20,20 4,20"
				fill={color}
				stroke="#FFFFFF"
				strokeWidth="2"
			/>
			<circle cx="12" cy="14" r="2" fill="#FFFFFF" />
		</svg>
	);
};

// Main SymbolLibrary component
export const SymbolLibrary: React.FC = () => {
	const { t } = useTranslation();

	return (
		<div className="bg-card border border-border rounded-lg p-4">
			<h3 className="text-lg font-semibold text-foreground mb-3">
				{t("fireAlarm.symbolLibrary")}
			</h3>
			<div className="grid grid-cols-5 gap-3">
				<div className="flex flex-col items-center">
					<SmokeDetector size="md" type="smoke" />
					<span className="text-xs text-muted-foreground mt-1">
						{t("fireAlarm.smokeDet")}
					</span>
				</div>
				<div className="flex flex-col items-center">
					<HeatDetector size="md" type="heat" />
					<span className="text-xs text-muted-foreground mt-1">
						{t("fireAlarm.heatDet")}
					</span>
				</div>
				<div className="flex flex-col items-center">
					<PullStation size="md" type="pull" />
					<span className="text-xs text-muted-foreground mt-1">
						{t("fireAlarm.pullStation")}
					</span>
				</div>
				<div className="flex flex-col items-center">
					<HornStrobe size="md" type="horns" />
					<span className="text-xs text-muted-foreground mt-1">
						{t("fireAlarm.hornStrobe")}
					</span>
				</div>
				<div className="flex flex-col items-center">
					<Speaker size="md" type="speaker" />
					<span className="text-xs text-muted-foreground mt-1">
						{t("fireAlarm.speaker")}
					</span>
				</div>
				<div className="flex flex-col items-center">
					<FACP size="md" type="facp" />
					<span className="text-xs text-muted-foreground mt-1">
						{t("fireAlarm.facp")}
					</span>
				</div>
				<div className="flex flex-col items-center">
					<DuctDetector size="md" type="duct" />
					<span className="text-xs text-muted-foreground mt-1">
						{t("fireAlarm.ductDetector")}
					</span>
				</div>
				<div className="flex flex-col items-center">
					<AspiratingDetector size="md" type="aspirating" />
					<span className="text-xs text-muted-foreground mt-1">
						{t("fireAlarm.aspirating")}
					</span>
				</div>
				<div className="flex flex-col items-center">
					<FlowSwitch size="md" type="flow" />
					<span className="text-xs text-muted-foreground mt-1">
						{t("fireAlarm.flowSwitch")}
					</span>
				</div>
				<div className="flex flex-col items-center">
					<TamperSwitch size="md" type="tamper" />
					<span className="text-xs text-muted-foreground mt-1">
						{t("fireAlarm.tamperSwitch")}
					</span>
				</div>
			</div>

			<div className="mt-4">
				<h4 className="text-sm font-medium text-foreground/90 mb-2">
					{t("fireAlarm.statusLegend")}
				</h4>
				<div className="flex flex-wrap gap-3">
					<div className="flex items-center gap-2">
						<div className="w-4 h-4 rounded-full bg-green-500"></div>
						<span className="text-xs text-muted-foreground">
							{t("fireAlarm.normal")}
						</span>
					</div>
					<div className="flex items-center gap-2">
						<div className="w-4 h-4 rounded-full bg-blue-500"></div>
						<span className="text-xs text-muted-foreground">
							{t("fireAlarm.active")}
						</span>
					</div>
					<div className="flex items-center gap-2">
						<div className="w-4 h-4 rounded-full bg-slate-500"></div>
						<span className="text-xs text-muted-foreground">
							{t("fireAlarm.fault")}
						</span>
					</div>
					<div className="flex items-center gap-2">
						<div className="w-4 h-4 rounded-full bg-gray-500"></div>
						<span className="text-xs text-muted-foreground">
							{t("fireAlarm.disabled")}
						</span>
					</div>
					<div className="flex items-center gap-2">
						<div className="w-4 h-4 rounded-full bg-amber-500"></div>
						<span className="text-xs text-muted-foreground">
							{t("fireAlarm.selected")}
						</span>
					</div>
				</div>
			</div>
		</div>
	);
};
