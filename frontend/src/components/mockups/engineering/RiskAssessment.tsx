import { Activity, Factory, MapPin, ShieldAlert } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";

type ZoneType = "hospital" | "industrial" | "commercial" | "residential";

interface RiskRule {
	code: string;
	requirement: string;
	action: string;
}

export function RiskAssessment() {
	const [zone, setZone] = useState<ZoneType | null>(null);

	const getRules = (z: ZoneType): RiskRule[] => {
		switch (z) {
			case "hospital":
				return [
					{
						code: "NFPA 99",
						requirement: "Essential Electrical Systems (EES) required.",
						action: "Add Automatic Transfer Switch (ATS) & Generator.",
					},
					{
						code: "IEC 60364-7-710",
						requirement: "Medical IT systems for Group 2 rooms.",
						action:
							"Isolate critical care circuits with IT isolation transformers.",
					},
				];
			case "industrial":
				return [
					{
						code: "NFPA 70E",
						requirement: "Arc Flash Hazard Analysis.",
						action: "Label all panels with Arc Flash boundaries.",
					},
					{
						code: "IEEE 519",
						requirement: "Harmonic control.",
						action: "Install Harmonic Filters for VFD loads.",
					},
				];
			case "commercial":
				return [
					{
						code: "ASHRAE 90.1",
						requirement: "Lighting power density limits.",
						action: "Use LED fixtures with occupancy sensors.",
					},
				];
			default:
				return [];
		}
	};

	const rules = zone ? getRules(zone) : [];

	return (
		<div className="p-4 space-y-4 h-full overflow-y-auto">
			<h2 className="text-lg font-bold text-foreground flex items-center gap-2">
				<ShieldAlert className="text-orange-500" /> Risk Assessment
			</h2>

			<div className="space-y-2">
				<label className="text-xs font-bold text-muted-foreground">
					Project Location Type
				</label>
				<Select onValueChange={(v) => setZone(v as ZoneType)}>
					<SelectTrigger>
						<SelectValue placeholder="Select Environment..." />
					</SelectTrigger>
					<SelectContent>
						<SelectItem value="hospital">
							<div className="flex items-center gap-2">
								<Activity size={16} /> Hospital (Critical)
							</div>
						</SelectItem>
						<SelectItem value="industrial">
							<div className="flex items-center gap-2">
								<Factory size={16} /> Industrial Plant
							</div>
						</SelectItem>
						<SelectItem value="commercial">
							<div className="flex items-center gap-2">
								<MapPin size={16} /> Commercial Building
							</div>
						</SelectItem>
						<SelectItem value="residential">Residential</SelectItem>
					</SelectContent>
				</Select>
			</div>

			{zone && (
				<div className="space-y-3 mt-4 animate-in fade-in slide-in-from-bottom-4">
					<div className="text-xs font-bold text-orange-400 uppercase tracking-wider">
						Applicable Codes & Actions
					</div>
					{rules.map((rule, idx) => (
						<Card key={idx} className="bg-orange-950/20 border-orange-500/30">
							<CardContent className="p-3 space-y-2">
								<div className="flex justify-between items-center">
									<span className="text-xs font-mono bg-orange-500/20 text-orange-300 px-2 py-0.5 rounded">
										{rule.code}
									</span>
								</div>
								<p className="text-xs text-foreground">{rule.requirement}</p>
								<div className="pt-2 border-t border-orange-500/20">
									<p className="text-xs text-blue-300 font-bold">
										✅ Auto-Action:
									</p>
									<p className="text-xs text-muted-foreground">{rule.action}</p>
								</div>
							</CardContent>
						</Card>
					))}
					<Button
						className="w-full mt-4 bg-orange-600 hover:bg-orange-700"
						onClick={() => alert("Risk Report Added to Project Files")}
					>
						Download Compliance Certificate
					</Button>
				</div>
			)}
		</div>
	);
}
