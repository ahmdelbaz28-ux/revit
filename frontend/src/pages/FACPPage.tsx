/**
 * FACPPage.tsx — Fire Alarm Control Panel Selection (NFPA 72 §10.6.10).
 *
 * V216: New page — 5 backend endpoints now have UI.
 * Panel selection, verification, schedule generation, spec, panel list.
 */
import { useState } from "react";
import { Loader2, Cpu, ListChecks } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { facpApi } from "@/services/fullApi";
import { useToast } from "@/hooks/use-toast";

interface FACPForm {
	device_count: string;
	nac_circuit_count: string;
	building_size_m2: string;
	building_floors: string;
	requires_network: boolean;
	requires_voice: boolean;
	requires_releasing: boolean;
	jurisdiction: string;
	min_temperature_c: string;
}

export function FACPPage() {
	const { toast } = useToast();
	const [loading, setLoading] = useState(false);
	const [panels, setPanels] = useState<unknown[]>([]);
	const [result, setResult] = useState<Record<string, unknown> | null>(null);

	const [form, setForm] = useState<FACPForm>({
		device_count: "150",
		nac_circuit_count: "4",
		building_size_m2: "3000",
		building_floors: "3",
		requires_network: false,
		requires_voice: false,
		requires_releasing: false,
		jurisdiction: "UL",
		min_temperature_c: "0",
	});

	const handleSelect = async () => {
		setLoading(true);
		setResult(null);
		try {
			const res = await facpApi.select({
				device_count: parseInt(form.device_count),
				nac_circuit_count: parseInt(form.nac_circuit_count),
				building_size_m2: parseFloat(form.building_size_m2),
				building_floors: parseInt(form.building_floors),
				requires_network: form.requires_network,
				requires_voice: form.requires_voice,
				requires_releasing: form.requires_releasing,
				jurisdiction: form.jurisdiction,
				min_temperature_c: parseFloat(form.min_temperature_c),
			});
			setResult(res as Record<string, unknown>);
		} catch (err) {
			toast({
				title: "FACP Selection Failed",
				description: err instanceof Error ? err.message : "Failed",
				variant: "destructive",
			});
		} finally {
			setLoading(false);
		}
	};

	const handleListPanels = async () => {
		setLoading(true);
		try {
			const res = await facpApi.getPanels();
			setPanels((res as { panels?: unknown[] }).panels || []);
		} catch (err) {
			toast({
				title: "Failed to load panels",
				description: err instanceof Error ? err.message : "Failed",
				variant: "destructive",
			});
		} finally {
			setLoading(false);
		}
	};

	return (
		<div className="flex-1 overflow-auto">
			<div className="p-6 max-w-5xl mx-auto space-y-6">
				<div>
					<h1 className="text-lg font-semibold text-foreground flex items-center gap-2">
						<Cpu className="h-5 w-5 text-primary" />
						FACP Panel Selection
					</h1>
					<p className="text-sm text-muted-foreground mt-1">
						NFPA 72 §10.6.10 · UL 864 · Battery sizing with temperature/aging derating
					</p>
				</div>

				{/* Requirements Input */}
				<Card>
					<CardHeader>
						<CardTitle>Project Requirements</CardTitle>
						<CardDescription>
							Define the building and system requirements for panel selection
						</CardDescription>
					</CardHeader>
					<CardContent>
						<div className="grid grid-cols-2 md:grid-cols-3 gap-4">
							<div className="space-y-1.5">
								<Label className="text-xs text-muted-foreground">Device Count</Label>
								<Input
									type="number"
									value={form.device_count}
									onChange={(e) => setForm({ ...form, device_count: e.target.value })}
								/>
							</div>
							<div className="space-y-1.5">
								<Label className="text-xs text-muted-foreground">NAC Circuits</Label>
								<Input
									type="number"
									value={form.nac_circuit_count}
									onChange={(e) => setForm({ ...form, nac_circuit_count: e.target.value })}
								/>
							</div>
							<div className="space-y-1.5">
								<Label className="text-xs text-muted-foreground">Building Size (m²)</Label>
								<Input
									type="number"
									value={form.building_size_m2}
									onChange={(e) => setForm({ ...form, building_size_m2: e.target.value })}
								/>
							</div>
							<div className="space-y-1.5">
								<Label className="text-xs text-muted-foreground">Building Floors</Label>
								<Input
									type="number"
									value={form.building_floors}
									onChange={(e) => setForm({ ...form, building_floors: e.target.value })}
								/>
							</div>
							<div className="space-y-1.5">
								<Label className="text-xs text-muted-foreground">Min Temp (°C)</Label>
								<Input
									type="number"
									value={form.min_temperature_c}
									onChange={(e) => setForm({ ...form, min_temperature_c: e.target.value })}
								/>
							</div>
							<div className="space-y-1.5">
								<Label className="text-xs text-muted-foreground">Jurisdiction</Label>
								<Select
									value={form.jurisdiction}
									onValueChange={(v) => setForm({ ...form, jurisdiction: v })}
								>
									<SelectTrigger>
										<SelectValue />
									</SelectTrigger>
									<SelectContent>
										<SelectItem value="UL">UL</SelectItem>
										<SelectItem value="ULC">ULC</SelectItem>
										<SelectItem value="FM">FM</SelectItem>
										<SelectItem value="FDNY">FDNY</SelectItem>
									</SelectContent>
								</Select>
							</div>
						</div>

						<div className="flex flex-wrap gap-4 mt-4">
							<div className="flex items-center gap-2">
								<Checkbox
									id="network"
									checked={form.requires_network}
									onCheckedChange={(v) => setForm({ ...form, requires_network: v === true })}
								/>
								<Label htmlFor="network" className="text-xs text-muted-foreground cursor-pointer">
									Networked
								</Label>
							</div>
							<div className="flex items-center gap-2">
								<Checkbox
									id="voice"
									checked={form.requires_voice}
									onCheckedChange={(v) => setForm({ ...form, requires_voice: v === true })}
								/>
								<Label htmlFor="voice" className="text-xs text-muted-foreground cursor-pointer">
									Voice Evac
								</Label>
							</div>
							<div className="flex items-center gap-2">
								<Checkbox
									id="releasing"
									checked={form.requires_releasing}
									onCheckedChange={(v) => setForm({ ...form, requires_releasing: v === true })}
								/>
								<Label htmlFor="releasing" className="text-xs text-muted-foreground cursor-pointer">
									Releasing Service
								</Label>
							</div>
						</div>
					</CardContent>
				</Card>

				{/* Actions */}
				<div className="flex gap-3">
					<Button onClick={handleSelect} disabled={loading}>
						{loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Cpu className="h-4 w-4" />}
						Select Panel
					</Button>
					<Button onClick={handleListPanels} disabled={loading} variant="outline">
						{loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ListChecks className="h-4 w-4" />}
						List All Panels
					</Button>
				</div>

				{/* Selection Result */}
				{result && (
					<Card>
						<CardHeader>
							<CardTitle>Recommended Panel</CardTitle>
						</CardHeader>
						<CardContent>
							<div className="space-y-3">
								<div className="flex items-center gap-3">
									<Badge variant="default" className="text-sm">
										{result.recommended_model as string}
									</Badge>
									<span className="text-sm text-muted-foreground">
										{result.manufacturer as string}
									</span>
								</div>
								<div className="grid grid-cols-2 gap-3 text-sm">
									<div>
										<span className="text-muted-foreground">Capacity utilization: </span>
										<span className="font-mono text-foreground">
											{((result.capacity_utilization as number) * 100).toFixed(1)}%
										</span>
									</div>
									<div>
										<span className="text-muted-foreground">NAC utilization: </span>
										<span className="font-mono text-foreground">
											{((result.nac_utilization as number) * 100).toFixed(1)}%
										</span>
									</div>
									<div>
										<span className="text-muted-foreground">Battery size: </span>
										<span className="font-mono text-foreground">
											{result.battery_size_ah as number} Ah
										</span>
									</div>
								</div>
								{result.battery_derating_details ? (
									<div className="text-xs text-muted-foreground bg-muted p-3 rounded-md">
										<div>Method: {(result.battery_derating_details as Record<string, unknown>).method as string}</div>
										<div>Temperature derating: {(result.battery_derating_details as Record<string, unknown>).temperature_derating as number}</div>
										<div>Aging derating: {(result.battery_derating_details as Record<string, unknown>).aging_derating as number}</div>
										<div>Combined safety factor: {(result.battery_derating_details as Record<string, unknown>).combined_safety_factor as number}</div>
									</div>
								) : null}
							</div>
						</CardContent>
					</Card>
				)}

				{/* Panel Database */}
				{panels.length > 0 && (
					<Card>
						<CardHeader>
							<CardTitle>Panel Database ({panels.length})</CardTitle>
						</CardHeader>
						<CardContent>
							<div className="space-y-2">
								{panels.map((p, i) => {
									const panel = p as { model: string; manufacturer: string; device_capacity: number; nac_capacity: number };
									return (
										<div key={i} className="flex items-center justify-between text-sm border-b border-border pb-2">
											<span className="font-mono text-foreground">{panel.model}</span>
											<span className="text-muted-foreground">{panel.manufacturer}</span>
											<span className="font-mono text-muted-foreground">
												{panel.device_capacity} dev / {panel.nac_capacity} NAC
											</span>
										</div>
									);
								})}
							</div>
						</CardContent>
					</Card>
				)}
			</div>
		</div>
	);
}
