/**
 * MiningPage.tsx — Mining Fire Protection Dashboard
 *
 * V214: Exposes the fireai.mining module via the UI.
 * Supports NFPA 120/122, MSHA 30 CFR Part 75, IEC 60079-10-1.
 *
 * 5 tools:
 *   1. Methane hazard classification (MSHA §75.323)
 *   2. Ventilation compliance check (MSHA §75.326-327)
 *   3. CO hazard classification (MSHA §75.351)
 *   4. Conveyor suppression design (NFPA 120 §8.4)
 *   5. Full compliance report (MSHA + NFPA 120)
 */

import { AlertTriangle, CheckCircle2, Download, FileText, Loader2, Pickaxe, Wind } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
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
import {
        Select,
        SelectContent,
        SelectItem,
        SelectTrigger,
        SelectValue,
} from "@/components/ui/select";
import { miningApi } from "@/services/miningApi";

type Tab = "methane" | "ventilation" | "co" | "conveyor" | "report";

export function MiningPage() {
        const [activeTab, setActiveTab] = useState<Tab>("methane");
        const [loading, setLoading] = useState(false);

        // Methane state
        const [methanePct, setMethanePct] = useState("0.5");
        const [methaneResult, setMethaneResult] = useState<Record<string, unknown> | null>(null);

        // Ventilation state
        const [airflow, setAirflow] = useState("5.0");
        const [ventLocation, setVentLocation] = useState("working_face");
        const [ventResult, setVentResult] = useState<Record<string, unknown> | null>(null);

        // CO state
        const [coPpm, setCoPpm] = useState("10");
        const [coResult, setCoResult] = useState<Record<string, unknown> | null>(null);

        // Conveyor state
        const [beltLength, setBeltLength] = useState("500");
        const [beltWidth, setBeltWidth] = useState("1.2");
        const [conveyorResult, setConveyorResult] = useState<Record<string, unknown> | null>(null);

        // Report state
        const [mineName, setMineName] = useState("Test Mine");
        const [sectionName, setSectionName] = useState("Section A");
        const [reportResult, setReportResult] = useState<Record<string, unknown> | null>(null);

        const handleMethaneCheck = async () => {
                setLoading(true);
                try {
                        const result = await miningApi.methaneCheck({
                                concentration_pct: parseFloat(methanePct),
                        });
                        setMethaneResult(result as Record<string, unknown>);
                        toast.success(`Methane hazard: ${result.hazard_level}`);
                } catch (err) {
                        toast.error(`Check failed: ${err instanceof Error ? err.message : "Unknown"}`);
                } finally {
                        setLoading(false);
                }
        };

        const handleVentCheck = async () => {
                setLoading(true);
                try {
                        const result = await miningApi.ventilationCheck({
                                airflow_m3_s: parseFloat(airflow),
                                location_type: ventLocation,
                        });
                        setVentResult(result as Record<string, unknown>);
                        toast.success(`Compliant: ${result.is_compliant}`);
                } catch (err) {
                        toast.error(`Check failed: ${err instanceof Error ? err.message : "Unknown"}`);
                } finally {
                        setLoading(false);
                }
        };

        const handleCoCheck = async () => {
                setLoading(true);
                try {
                        const result = await miningApi.coCheck({
                                co_ppm: parseFloat(coPpm),
                        });
                        setCoResult(result as Record<string, unknown>);
                        toast.success(`CO hazard: ${result.hazard_level}`);
                } catch (err) {
                        toast.error(`Check failed: ${err instanceof Error ? err.message : "Unknown"}`);
                } finally {
                        setLoading(false);
                }
        };

        const handleConveyor = async () => {
                setLoading(true);
                try {
                        const result = await miningApi.conveyorSuppression({
                                belt_length_m: parseFloat(beltLength),
                                belt_width_m: parseFloat(beltWidth),
                        });
                        setConveyorResult(result as Record<string, unknown>);
                        toast.success("Suppression design generated");
                } catch (err) {
                        toast.error(`Design failed: ${err instanceof Error ? err.message : "Unknown"}`);
                } finally {
                        setLoading(false);
                }
        };

        const handleReport = async () => {
                setLoading(true);
                try {
                        const result = await miningApi.complianceReport({
                                mine_name: mineName,
                                section_name: sectionName,
                                methane_pct: parseFloat(methanePct),
                                co_ppm: parseFloat(coPpm),
                                airflow_m3_s: parseFloat(airflow),
                                conveyor_length_m: parseFloat(beltLength),
                                conveyor_width_m: parseFloat(beltWidth),
                        });
                        setReportResult(result as Record<string, unknown>);
                        toast.success(`Overall status: ${result.overall_status}`);
                } catch (err) {
                        toast.error(`Report failed: ${err instanceof Error ? err.message : "Unknown"}`);
                } finally {
                        setLoading(false);
                }
        };

        const hazardColor = (level: string) => {
                if (level === "normal") return "bg-emerald-600";
                if (level === "notify" || level === "alert") return "bg-amber-500";
                return "bg-red-600";
        };

        return (
                <div className="flex-1 overflow-auto p-6 max-w-5xl mx-auto space-y-6">
                        <div>
                                <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
                                        <Pickaxe className="h-6 w-6 text-primary" />
                                        Mining Fire Protection
                                </h1>
                                <p className="text-sm text-muted-foreground mt-1">
                                        NFPA 120-2022 · NFPA 122-2022 · MSHA 30 CFR Part 75 · IEC 60079-10-1
                                </p>
                        </div>

                        {/* Tab selector */}
                        <div className="flex flex-wrap gap-2 border-b border-border pb-2">
                                {([
                                        ["methane", "Methane CH₄"],
                                        ["ventilation", "Ventilation"],
                                        ["co", "CO Monitoring"],
                                        ["conveyor", "Conveyor Fire"],
                                        ["report", "Compliance Report"],
                                ] as const).map(([tab, label]) => (
                                        <Button
                                                key={tab}
                                                variant={activeTab === tab ? "default" : "outline"}
                                                onClick={() => setActiveTab(tab)}
                                                className={activeTab === tab ? "bg-primary text-white" : ""}
                                        >
                                                {label}
                                        </Button>
                                ))}
                        </div>

                        {/* Methane Tab */}
                        {activeTab === "methane" && (
                                <Card className="border-border bg-card">
                                        <CardHeader>
                                                <CardTitle className="flex items-center gap-2">
                                                        <AlertTriangle className="h-5 w-5 text-amber-500" />
                                                        Methane Hazard Classification
                                                </CardTitle>
                                                <CardDescription>MSHA 30 CFR §75.323 — Methane Detection</CardDescription>
                                        </CardHeader>
                                        <CardContent className="space-y-4">
                                                <div className="flex items-end gap-3">
                                                        <div className="space-y-2 flex-1">
                                                                <Label>CH₄ Concentration (% by volume)</Label>
                                                                <Input
                                                                        type="number"
                                                                        step="0.1"
                                                                        value={methanePct}
                                                                        onChange={(e) => setMethanePct(e.target.value)}
                                                                        placeholder="0.5"
                                                                />
                                                        </div>
                                                        <Button onClick={handleMethaneCheck} disabled={loading}>
                                                                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Check"}
                                                        </Button>
                                                </div>
                                                {methaneResult && (
                                                        <div className="space-y-2 p-4 rounded-lg bg-muted/50">
                                                                <div className="flex items-center gap-2">
                                                                        <Badge className={hazardColor(methaneResult.hazard_level as string)}>
                                                                                {methaneResult.hazard_level as string}
                                                                        </Badge>
                                                                        {methaneResult.is_in_explosive_range ? (
                                                                                <span className="text-red-600 font-semibold">⚠️ IN EXPLOSIVE RANGE (5-15%)</span>
                                                                        ) : (
                                                                                <span className="text-emerald-600">Below LEL (5%)</span>
                                                                        )}
                                                                </div>
                                                                <p className="text-sm text-muted-foreground">
                                                                        Distance to LEL: {methaneResult.distance_to_lel_pct as number}%
                                                                </p>
                                                        </div>
                                                )}
                                        </CardContent>
                                </Card>
                        )}

                        {/* Ventilation Tab */}
                        {activeTab === "ventilation" && (
                                <Card className="border-border bg-card">
                                        <CardHeader>
                                                <CardTitle className="flex items-center gap-2">
                                                        <Wind className="h-5 w-5 text-primary" />
                                                        Ventilation Compliance Check
                                                </CardTitle>
                                                <CardDescription>MSHA 30 CFR §75.326-327 — Minimum Airflow Requirements</CardDescription>
                                        </CardHeader>
                                        <CardContent className="space-y-4">
                                                <div className="grid grid-cols-2 gap-4">
                                                        <div className="space-y-2">
                                                                <Label>Airflow (m³/s)</Label>
                                                                <Input
                                                                        type="number"
                                                                        step="0.1"
                                                                        value={airflow}
                                                                        onChange={(e) => setAirflow(e.target.value)}
                                                                />
                                                        </div>
                                                        <div className="space-y-2">
                                                                <Label>Location Type</Label>
                                                                <Select value={ventLocation} onValueChange={setVentLocation}>
                                                                        <SelectTrigger><SelectValue /></SelectTrigger>
                                                                        <SelectContent>
                                                                                <SelectItem value="working_face">Working Face</SelectItem>
                                                                                <SelectItem value="last_open_crosscut">Last Open Crosscut</SelectItem>
                                                                                <SelectItem value="belt_entry">Belt Entry</SelectItem>
                                                                        </SelectContent>
                                                                </Select>
                                                        </div>
                                                </div>
                                                <Button onClick={handleVentCheck} disabled={loading}>
                                                        {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Check Compliance"}
                                                </Button>
                                                {ventResult && (
                                                        <div className="space-y-2 p-4 rounded-lg bg-muted/50">
                                                                <div className="flex items-center gap-2">
                                                                        {ventResult.is_compliant ? (
                                                                                <><CheckCircle2 className="h-5 w-5 text-emerald-600" /><span className="text-emerald-600 font-semibold">COMPLIANT</span></>
                                                                        ) : (
                                                                                <><AlertTriangle className="h-5 w-5 text-red-600" /><span className="text-red-600 font-semibold">NON-COMPLIANT</span></>
                                                                        )}
                                                                </div>
                                                                {(ventResult.violations as string[])?.map((v, i) => (
                                                                        <p key={i} className="text-sm text-red-600">• {v}</p>
                                                                ))}
                                                        </div>
                                                )}
                                        </CardContent>
                                </Card>
                        )}

                        {/* CO Tab */}
                        {activeTab === "co" && (
                                <Card className="border-border bg-card">
                                        <CardHeader>
                                                <CardTitle className="flex items-center gap-2">
                                                        <AlertTriangle className="h-5 w-5 text-amber-500" />
                                                        CO Hazard Classification
                                                </CardTitle>
                                                <CardDescription>MSHA 30 CFR §75.351 — CO Monitoring at Belt Entries</CardDescription>
                                        </CardHeader>
                                        <CardContent className="space-y-4">
                                                <div className="flex items-end gap-3">
                                                        <div className="space-y-2 flex-1">
                                                                <Label>CO Concentration (ppm)</Label>
                                                                <Input
                                                                        type="number"
                                                                        value={coPpm}
                                                                        onChange={(e) => setCoPpm(e.target.value)}
                                                                        placeholder="10"
                                                                />
                                                        </div>
                                                        <Button onClick={handleCoCheck} disabled={loading}>
                                                                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Check"}
                                                        </Button>
                                                </div>
                                                {coResult && (
                                                        <div className="space-y-2 p-4 rounded-lg bg-muted/50">
                                                                <Badge className={hazardColor(coResult.hazard_level as string)}>
                                                                        {coResult.hazard_level as string}
                                                                </Badge>
                                                                <div className="text-sm text-muted-foreground space-y-1">
                                                                        <p>Alert: {(coResult.thresholds as Record<string, number>)?.alert_ppm} ppm</p>
                                                                        <p>Evacuate: {(coResult.thresholds as Record<string, number>)?.evacuate_ppm} ppm</p>
                                                                        <p>Withdraw: {(coResult.thresholds as Record<string, number>)?.withdraw_ppm} ppm</p>
                                                                        <p>Imminent: {(coResult.thresholds as Record<string, number>)?.imminent_ppm} ppm</p>
                                                                </div>
                                                        </div>
                                                )}
                                        </CardContent>
                                </Card>
                        )}

                        {/* Conveyor Tab */}
                        {activeTab === "conveyor" && (
                                <Card className="border-border bg-card">
                                        <CardHeader>
                                                <CardTitle className="flex items-center gap-2">
                                                        <FileText className="h-5 w-5 text-primary" />
                                                        Conveyor Belt Fire Suppression Design
                                                </CardTitle>
                                                <CardDescription>NFPA 120-2022 §8.4 + MSHA 30 CFR §75.1108</CardDescription>
                                        </CardHeader>
                                        <CardContent className="space-y-4">
                                                <div className="grid grid-cols-2 gap-4">
                                                        <div className="space-y-2">
                                                                <Label>Belt Length (m)</Label>
                                                                <Input type="number" value={beltLength} onChange={(e) => setBeltLength(e.target.value)} />
                                                        </div>
                                                        <div className="space-y-2">
                                                                <Label>Belt Width (m)</Label>
                                                                <Input type="number" step="0.1" value={beltWidth} onChange={(e) => setBeltWidth(e.target.value)} />
                                                        </div>
                                                </div>
                                                <Button onClick={handleConveyor} disabled={loading}>
                                                        {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Design Suppression"}
                                                </Button>
                                                {conveyorResult && (
                                                        <div className="space-y-2 p-4 rounded-lg bg-muted/50">
                                                                {(conveyorResult.design as Record<string, unknown>) && (
                                                                        <>
                                                                                <p className="text-sm">Nozzle Groups: {(conveyorResult.design as Record<string, unknown>).number_of_nozzle_groups as number}</p>
                                                                                <p className="text-sm">Water Flow: {(conveyorResult.design as Record<string, unknown>).water_flow_rate_lpm as number} L/min</p>
                                                                                <p className="text-sm">Total Water: {(conveyorResult.design as Record<string, unknown>).total_water_volume_l as number} L</p>
                                                                                <p className="text-sm">Duration: {(conveyorResult.design as Record<string, unknown>).water_duration_min as number} min</p>
                                                                                {(conveyorResult.design as Record<string, unknown>).is_compliant ? (
                                                                                        <Badge className="bg-emerald-600">COMPLIANT</Badge>
                                                                                ) : (
                                                                                        <Badge className="bg-red-600">NON-COMPLIANT</Badge>
                                                                                )}
                                                                        </>
                                                                )}
                                                        </div>
                                                )}
                                        </CardContent>
                                </Card>
                        )}

                        {/* Report Tab */}
                        {activeTab === "report" && (
                                <Card className="border-border bg-card">
                                        <CardHeader>
                                                <CardTitle className="flex items-center gap-2">
                                                        <FileText className="h-5 w-5 text-primary" />
                                                        Full MSHA + NFPA 120 Compliance Report
                                                </CardTitle>
                                                <CardDescription>Aggregated compliance check for mine section</CardDescription>
                                        </CardHeader>
                                        <CardContent className="space-y-4">
                                                <div className="grid grid-cols-2 gap-4">
                                                        <div className="space-y-2">
                                                                <Label>Mine Name</Label>
                                                                <Input value={mineName} onChange={(e) => setMineName(e.target.value)} />
                                                        </div>
                                                        <div className="space-y-2">
                                                                <Label>Section Name</Label>
                                                                <Input value={sectionName} onChange={(e) => setSectionName(e.target.value)} />
                                                        </div>
                                                </div>
                                                <Button onClick={handleReport} disabled={loading}>
                                                        {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Generate Report"}
                                                </Button>
                                                {reportResult && (
                                                        <div className="space-y-2 p-4 rounded-lg bg-muted/50">
                                                                <Badge className={
                                                                        reportResult.overall_status === "PASS" ? "bg-emerald-600" :
                                                                        reportResult.overall_status === "WARNING" ? "bg-amber-500" : "bg-red-600"
                                                                }>
                                                                        {reportResult.overall_status as string}
                                                                </Badge>
                                                                {(reportResult.checks as Array<Record<string, string>>)?.map((check, i) => (
                                                                        <div key={i} className="text-sm border-l-2 border-border pl-3 mt-2">
                                                                                <p className="font-medium">{check.rule_id}: {check.status}</p>
                                                                                <p className="text-muted-foreground">{check.details}</p>
                                                                        </div>
                                                                ))}
                                                                {reportResult.markdown_report ? (
                                                                        <Button
                                                                                variant="outline"
                                                                                size="sm"
                                                                                className="mt-2"
                                                                                onClick={() => {
                                                                                        const blob = new Blob([reportResult.markdown_report as string], { type: "text/markdown" });
                                                                                        const url = URL.createObjectURL(blob);
                                                                                        const a = document.createElement("a");
                                                                                        a.href = url;
                                                                                        a.download = `${mineName}_MSHA_report.md`;
                                                                                        a.click();
                                                                                }}
                                                                        >
                                                                                <Download className="h-3 w-3 mr-1" /> Download Report
                                                                        </Button>
                                                                ) : null}
                                                        </div>
                                                )}
                                        </CardContent>
                                </Card>
                        )}
                </div>
        );
}
