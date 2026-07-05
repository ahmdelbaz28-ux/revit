import { AlertTriangle, CheckCircle2, Save, X, XCircle } from "lucide-react";
import type React from "react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type { Detector as CanvasDetector, DetectorType } from "./CanvasEditor";

interface DeviceProperty {
	id: string;
	address: string; // "Loop-1, Address-42"
	zone: string; // "Zone 2-02"
	location: string; // "Room 205, Level 2"
	detectorType: DetectorType;
	heightAFF: number; // Above Finished Floor (meters)
	manufacturer: string; // "Hochiki", "System Sensor"
	modelNumber: string;
	sensitivityLevel: "high" | "standard" | "low";
	coverageArea: number; // m²
	status: "normal" | "warning" | "fault";
	lastTestDate?: string;
}

interface DevicePropertiesProps {
	device: CanvasDetector | null;
	onSave: (updatedDevice: Partial<DeviceProperty>) => void;
	onClose: () => void;
}

export const DeviceProperties: React.FC<DevicePropertiesProps> = ({
	device,
	onSave,
	onClose,
}) => {
	const { t } = useTranslation();
	const [editedDevice, setEditedDevice] = useState<Partial<DeviceProperty>>({
		id: device?.id,
		address: device?.address || "",
		zone: device?.zone || "",
		location: device?.location || "",
		detectorType: device?.type || "smoke",
		heightAFF: device?.heightAFF || 2.7, // Default ceiling height
		manufacturer: device?.manufacturer || "",
		modelNumber: device?.model || "",
		sensitivityLevel: device?.sensitivity || "standard",
		coverageArea: device?.coverageRadius
			? Math.PI * device.coverageRadius * device.coverageRadius
			: 0,
		status: device?.status || "normal",
		lastTestDate:
			device?.lastTestDate || new Date().toISOString().split("T")[0],
	});

	const handleChange = (field: keyof DeviceProperty, value: any) => {
		setEditedDevice((prev) => ({
			...prev,
			[field]: value,
		}));
	};

	const handleSave = () => {
		if (device) {
			// Merge with existing device data to ensure all required fields are present
			const updatedDevice = {
				...device,
				...editedDevice,
				id: device.id, // Preserve the original ID
				x: device.x, // Preserve position
				y: device.y,
				coverageRadius: editedDevice.coverageArea
					? Math.sqrt(editedDevice.coverageArea / Math.PI)
					: device.coverageRadius,
			};

			onSave(updatedDevice);
		}
	};

	if (!device) {
		return (
			<div className="fixed top-4 right-4 w-80 bg-slate-800 border border-slate-700 rounded-lg shadow-lg z-50">
				<Card className="border-slate-700 bg-slate-800">
					<CardHeader className="pb-3">
						<div className="flex justify-between items-center">
							<CardTitle className="text-lg text-slate-100">
								{t("fireAlarm.deviceProperties")}
							</CardTitle>
							<Button variant="ghost" size="sm" onClick={onClose}>
								<X className="h-4 w-4" />
							</Button>
						</div>
					</CardHeader>
					<CardContent>
						<p className="text-slate-400">{t("fireAlarm.selectDevice")}</p>
					</CardContent>
				</Card>
			</div>
		);
	}

	return (
		<div className="fixed top-4 right-4 w-80 bg-slate-800 border border-slate-700 rounded-lg shadow-lg z-50">
			<Card className="border-slate-700 bg-slate-800">
				<CardHeader className="pb-3">
					<div className="flex justify-between items-center">
						<CardTitle className="text-lg text-slate-100">
							{t("fireAlarm.deviceProperties")}
						</CardTitle>
						<Button variant="ghost" size="sm" onClick={onClose}>
							<X className="h-4 w-4" />
						</Button>
					</div>
				</CardHeader>
				<CardContent>
					<div className="space-y-4">
						<div>
							<Label className="text-slate-300">{t("fireAlarm.address")}</Label>
							<Input
								value={editedDevice.address || ""}
								onChange={(e) => handleChange("address", e.target.value)}
								placeholder={t("fireAlarm.addressPlaceholder") || undefined}
								className="bg-slate-900 border-slate-600 text-slate-100"
							/>
						</div>

						<div>
							<Label className="text-slate-300">{t("fireAlarm.zone")}</Label>
							<Input
								value={editedDevice.zone || ""}
								onChange={(e) => handleChange("zone", e.target.value)}
								placeholder={t("fireAlarm.zonePlaceholder") || undefined}
								className="bg-slate-900 border-slate-600 text-slate-100"
							/>
						</div>

						<div>
							<Label className="text-slate-300">
								{t("fireAlarm.location")}
							</Label>
							<Input
								value={editedDevice.location || ""}
								onChange={(e) => handleChange("location", e.target.value)}
								placeholder={t("fireAlarm.locationPlaceholder") || undefined}
								className="bg-slate-900 border-slate-600 text-slate-100"
							/>
						</div>

						<div>
							<Label className="text-slate-300">
								{t("fireAlarm.detectorType")}
							</Label>
							<Select
								value={editedDevice.detectorType}
								onValueChange={(value: DetectorType) =>
									handleChange("detectorType", value)
								}
							>
								<SelectTrigger className="bg-slate-900 border-slate-600 text-slate-100">
									<SelectValue />
								</SelectTrigger>
								<SelectContent className="bg-slate-800 border-slate-700">
									<SelectItem value="smoke">
										{t("fireAlarm.smokeDet")}
									</SelectItem>
									<SelectItem value="heat">{t("fireAlarm.heatDet")}</SelectItem>
									<SelectItem value="pull">
										{t("fireAlarm.pullStation")}
									</SelectItem>
									<SelectItem value="horns">
										{t("fireAlarm.hornStrobe")}
									</SelectItem>
									<SelectItem value="speaker">
										{t("fireAlarm.speaker")}
									</SelectItem>
									<SelectItem value="facp">{t("fireAlarm.facp")}</SelectItem>
								</SelectContent>
							</Select>
						</div>

						<div>
							<Label className="text-slate-300">
								{t("fireAlarm.heightAff")}
							</Label>
							<Input
								type="number"
								value={editedDevice.heightAFF || ""}
								onChange={(e) =>
									handleChange("heightAFF", parseFloat(e.target.value) || 0)
								}
								placeholder={t("fireAlarm.heightAffPlaceholder") || undefined}
								className="bg-slate-900 border-slate-600 text-slate-100"
							/>
						</div>

						<div>
							<Label className="text-slate-300">
								{t("fireAlarm.manufacturer")}
							</Label>
							<Input
								value={editedDevice.manufacturer || ""}
								onChange={(e) => handleChange("manufacturer", e.target.value)}
								placeholder={
									t("fireAlarm.manufacturerPlaceholder") || undefined
								}
								className="bg-slate-900 border-slate-600 text-slate-100"
							/>
						</div>

						<div>
							<Label className="text-slate-300">{t("fireAlarm.model")}</Label>
							<Input
								value={editedDevice.modelNumber || ""}
								onChange={(e) => handleChange("modelNumber", e.target.value)}
								placeholder={t("fireAlarm.modelPlaceholder") || undefined}
								className="bg-slate-900 border-slate-600 text-slate-100"
							/>
						</div>

						<div>
							<Label className="text-slate-300">
								{t("fireAlarm.sensitivity")}
							</Label>
							<Select
								value={editedDevice.sensitivityLevel}
								onValueChange={(value: "high" | "standard" | "low") =>
									handleChange("sensitivityLevel", value)
								}
							>
								<SelectTrigger className="bg-slate-900 border-slate-600 text-slate-100">
									<SelectValue />
								</SelectTrigger>
								<SelectContent className="bg-slate-800 border-slate-700">
									<SelectItem value="high">{t("fireAlarm.high")}</SelectItem>
									<SelectItem value="standard">
										{t("fireAlarm.standard")}
									</SelectItem>
									<SelectItem value="low">{t("fireAlarm.low")}</SelectItem>
								</SelectContent>
							</Select>
						</div>

						<div>
							<Label className="text-slate-300">
								{t("fireAlarm.coverageArea")}
							</Label>
							<Input
								type="number"
								value={editedDevice.coverageArea || ""}
								onChange={(e) =>
									handleChange("coverageArea", parseFloat(e.target.value) || 0)
								}
								placeholder={
									t("fireAlarm.coverageAreaPlaceholder") || undefined
								}
								className="bg-slate-900 border-slate-600 text-slate-100"
							/>
						</div>

						<div>
							<Label className="text-slate-300">{t("fireAlarm.status")}</Label>
							<div className="flex items-center gap-2">
								<Badge
									variant="secondary"
									className={
										editedDevice.status === "normal"
											? "bg-emerald-600/20 text-emerald-400 border-emerald-500/30"
											: editedDevice.status === "warning"
												? "bg-amber-600/20 text-amber-400 border-amber-500/30"
												: "bg-red-600/20 text-red-400 border-red-500/30"
									}
								>
									{editedDevice.status === "normal" && (
										<CheckCircle2 className="h-3 w-3 mr-1" />
									)}
									{editedDevice.status === "warning" && (
										<AlertTriangle className="h-3 w-3 mr-1" />
									)}
									{editedDevice.status === "fault" && (
										<XCircle className="h-3 w-3 mr-1" />
									)}
									{editedDevice.status}
								</Badge>
							</div>
						</div>

						<div>
							<Label className="text-slate-300">
								{t("fireAlarm.lastTest")}
							</Label>
							<Input
								type="date"
								value={editedDevice.lastTestDate || ""}
								onChange={(e) => handleChange("lastTestDate", e.target.value)}
								className="bg-slate-900 border-slate-600 text-slate-100"
							/>
						</div>

						<div className="flex gap-2 pt-2">
							<Button
								className="flex-1 bg-red-600 hover:bg-red-700 text-white border-none"
								onClick={handleSave}
							>
								<Save className="h-4 w-4 mr-2" />
								{t("common.save")}
							</Button>
							<Button
								variant="outline"
								className="border-slate-600 text-slate-300"
								onClick={onClose}
							>
								{t("common.cancel")}
							</Button>
						</div>
					</div>
				</CardContent>
			</Card>
		</div>
	);
};
