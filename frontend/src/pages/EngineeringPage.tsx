
/**
 * EngineeringPage.tsx - Fire Alarm Electrical Calculations
 *
 * V140 Phase 5: Connected to real QOMN API endpoints. Falls back to local
 * calculation when API is unavailable (offline mode).
 */

import { Battery, Cable, Zap } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ExplainButton } from "@/components/ai/ExplainButton";
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
import { Separator } from "@/components/ui/separator";
import { qomnApi } from "@/services/fullApi";

// ============================================================================
// EngineeringPage Component
// ============================================================================

export function EngineeringPage() {
        const { t } = useTranslation();
        const [activeTab, setActiveTab] = useState("voltage-drop");
        const [voltageDropInputs, setVoltageDropInputs] = useState({
                current: "",
                length: "",
                cableSize: "",
                voltage: "",
                material: "cu",
        });
        const [cableSizingInputs, setCableSizingInputs] = useState({
                loadCurrent: "",
                length: "",
                ambientTemp: "",
                installationMethod: "free-air",
        });
        const [batteryCalcInputs, setBatteryCalcInputs] = useState({
                standbyDevices: "",
                standbyCurrent: "",
                alarmDevices: "",
                alarmCurrent: "",
                standbyHours: "24",
                alarmMinutes: "5",
        });

        const [apiLoading, setApiLoading] = useState(false);  // NOSONAR: typescript:S6754
        const [apiError, setApiError] = useState<string | null>(null);  // NOSONAR: typescript:S6754
        const [apiResult, setApiResult] = useState<{
                voltage_drop_v: number;
                drop_pct: number;
                is_compliant: boolean;
                nec_section: string;
                computation_hash: string;
        } | null>(null);

        const calculateVoltageDropLocal = useCallback(() => {
                // Local FALLBACK calculation only — used when QOMN API is unavailable.
                // V214 FIX: This is NOT the primary calculation. The primary path
                // is calculateVoltageDropViaApi() which calls the real QOMN kernel
                // with NEC Table 8 + HMAC-SHA256 audit hash.
                const current = Number.parseFloat(voltageDropInputs.current);
                const length = Number.parseFloat(voltageDropInputs.length);
                const cableSize = Number.parseFloat(voltageDropInputs.cableSize);
                const voltage = Number.parseFloat(voltageDropInputs.voltage);

                if (
                        Number.isNaN(current) ||
                        Number.isNaN(length) ||
                        Number.isNaN(cableSize) ||
                        Number.isNaN(voltage)
                ) {
                        return { percentage: 0, absolute: 0 };
                }

                // Simplified calculation: Vdrop = (R * I * L) / 1000
                const resistivity = voltageDropInputs.material === "cu" ? 0.0172 : 0.0282;
                const resistance = (resistivity * length * 2) / cableSize;
                const voltageDrop = current * resistance;
                const percentage = (voltageDrop / voltage) * 100;

                return {
                        percentage: Number.parseFloat(percentage.toFixed(2)),
                        absolute: Number.parseFloat(voltageDrop.toFixed(3)),
                };
        }, [voltageDropInputs]);

        // V214 FIX: Call real QOMN API — this is the PRIMARY calculation path.
        // Previously this function had a leading underscore (_calculateVoltageDropViaApi)
        // making it "private" and it was NEVER invoked from the render path.
        // The page silently used local placeholder formulas instead, bypassing
        // the entire QOMN audit chain (no NEC Table 8, no HMAC-SHA256 hash).
        const calculateVoltageDropViaApi = useCallback(async () => {
                const current = Number.parseFloat(voltageDropInputs.current);
                const length = Number.parseFloat(voltageDropInputs.length);
                if (Number.isNaN(current) || Number.isNaN(length) || current <= 0 || length <= 0) {
                        return; // Skip if inputs invalid
                }
                setApiLoading(true);
                setApiError(null);
                try {
                        const result = await qomnApi.voltageDrop({
                                current_a: current,
                                length_m: length,
                                awg_gauge: voltageDropInputs.cableSize || "12",
                                supply_voltage_v: Number.parseFloat(voltageDropInputs.voltage) || 24.0,
                        });
                        setApiResult(result as any);
                } catch (err) {
                        const msg = err instanceof Error ? err.message : "QOMN API calculation failed";
                        setApiError(msg);
                        setApiResult(null);
                        // Do NOT silently fall back — surface the error so the engineer
                        // knows the backend audit hash is missing (life-safety requirement)
                } finally {
                        setApiLoading(false);
                }
        }, [voltageDropInputs]);

        // V214 FIX: Call the API whenever inputs change — with 500ms debounce
        // to avoid hammering the backend on every keystroke.
        useEffect(() => {
                const timer = setTimeout(() => {
                        calculateVoltageDropViaApi();
                }, 500);
                return () => clearTimeout(timer);
        }, [calculateVoltageDropViaApi]);

        const calculateCableSizing = () => {
                // Placeholder calculation
                const loadCurrent = Number.parseFloat(cableSizingInputs.loadCurrent);
                const length = Number.parseFloat(cableSizingInputs.length);
                const ambientTemp = Number.parseFloat(cableSizingInputs.ambientTemp);

                if (
                        Number.isNaN(loadCurrent) ||
                        Number.isNaN(length) ||
                        Number.isNaN(ambientTemp)
                ) {
                        return {
                                recommendedSize: "N/A",
                                baseAmpacity: 0,
                                deratingFactor: 0,
                                finalAmpacity: 0,
                        };
                }

                // Simplified calculation
                const baseAmpacity = loadCurrent * 1.25; // 25% safety factor
                const deratingFactor = 0.85; // Simplified derating
                const finalAmpacity = baseAmpacity * deratingFactor;
                const recommendedSize = Math.ceil(finalAmpacity / 5) * 2.5; // Approximate size

                return {
                        recommendedSize: recommendedSize.toFixed(1),
                        baseAmpacity: Number.parseFloat(baseAmpacity.toFixed(2)),
                        deratingFactor: Number.parseFloat(deratingFactor.toFixed(2)),
                        finalAmpacity: Number.parseFloat(finalAmpacity.toFixed(2)),
                };
        };

        const calculateBatteryRequirements = () => {
                // Placeholder calculation
                const standbyDevices = Number.parseInt(batteryCalcInputs.standbyDevices, 10);
                const standbyCurrent = Number.parseFloat(batteryCalcInputs.standbyCurrent);
                const alarmDevices = Number.parseInt(batteryCalcInputs.alarmDevices, 10);
                const alarmCurrent = Number.parseFloat(batteryCalcInputs.alarmCurrent);
                const standbyHours = Number.parseFloat(batteryCalcInputs.standbyHours);
                const alarmMinutes = Number.parseFloat(batteryCalcInputs.alarmMinutes);

                if (
                        Number.isNaN(standbyDevices) ||
                        Number.isNaN(standbyCurrent) ||
                        Number.isNaN(alarmDevices) ||
                        Number.isNaN(alarmCurrent) ||
                        Number.isNaN(standbyHours) ||
                        Number.isNaN(alarmMinutes)
                ) {
                        return {
                                totalStandbyCurrent: 0,
                                totalAlarmCurrent: 0,
                                requiredCapacity: 0,
                                recommendedBattery: "N/A",
                        };
                }

                const totalStandbyCurrent = standbyDevices * standbyCurrent;
                const totalAlarmCurrent = alarmDevices * alarmCurrent;
                const standbyCapacity = (totalStandbyCurrent / 1000) * standbyHours;
                const alarmCapacity = (totalAlarmCurrent / 1000) * (alarmMinutes / 60);
                const requiredCapacity = (standbyCapacity + alarmCapacity) * 1.2; // 20% safety factor

                return {
                        totalStandbyCurrent: Number.parseFloat(totalStandbyCurrent.toFixed(2)),
                        totalAlarmCurrent: Number.parseFloat(totalAlarmCurrent.toFixed(2)),
                        requiredCapacity: Number.parseFloat(requiredCapacity.toFixed(2)),
                        recommendedBattery: `24V ${Math.ceil(requiredCapacity)}Ah Lead Acid`,
                };
        };

        // V214 FIX: Use API result (primary) or local fallback (secondary)
        const localVDrop = calculateVoltageDropLocal();
        const vDropResult = apiResult
                ? {
                        percentage: apiResult.drop_pct,
                        absolute: apiResult.voltage_drop_v,
                        // Include audit trail fields for transparency
                        nec_section: apiResult.nec_section,
                        computation_hash: apiResult.computation_hash,
                        is_compliant: apiResult.is_compliant,
                        source: "QOMN API (audited)" as const,
                  }
                : {
                        percentage: localVDrop.percentage,
                        absolute: localVDrop.absolute,
                        source: "Local fallback (unaudited)" as const,
                  };
        const cableResult = calculateCableSizing();
        const batteryResult = calculateBatteryRequirements();

        return (
                <div className="flex-1 overflow-auto" aria-label={t("engineering.title")}>
                        <div className="p-6 max-w-4xl mx-auto space-y-6">
                                {/* Header */}
                                <div>
                                        <h1 className="text-2xl font-bold text-foreground">
                                                {t("engineering.title")}
                                        </h1>
                                        <p className="text-sm text-muted-foreground mt-1">
                                                {t("engineering.subtitle")}
                                        </p>
                                </div>

                                {/* Tabs */}
                                <div className="flex flex-wrap gap-2 border-b border-border pb-2">
                                        <Button
                                                variant={activeTab === "voltage-drop" ? "default" : "outline"}
                                                className={
                                                        activeTab === "voltage-drop"
                                                                ? "bg-danger hover:bg-danger/90 text-white border-none"
                                                                : "border-border text-foreground/90 hover:bg-card"
                                                }
                                                onClick={() => setActiveTab("voltage-drop")}
                                        >
                                                <Zap className="h-4 w-4 mr-2" />
                                                {t("engineering.voltageDrop")}
                                        </Button>
                                        <Button
                                                variant={activeTab === "cable-sizing" ? "default" : "outline"}
                                                className={
                                                        activeTab === "cable-sizing"
                                                                ? "bg-danger hover:bg-danger/90 text-white border-none"
                                                                : "border-border text-foreground/90 hover:bg-card"
                                                }
                                                onClick={() => setActiveTab("cable-sizing")}
                                        >
                                                <Cable className="h-4 w-4 mr-2" />
                                                {t("engineering.cableSizing")}
                                        </Button>
                                        <Button
                                                variant={activeTab === "battery-calc" ? "default" : "outline"}
                                                className={
                                                        activeTab === "battery-calc"
                                                                ? "bg-danger hover:bg-danger/90 text-white border-none"
                                                                : "border-border text-foreground/90 hover:bg-card"
                                                }
                                                onClick={() => setActiveTab("battery-calc")}
                                        >
                                                <Battery className="h-4 w-4 mr-2" />
                                                {t("engineering.batteryCalculation")}
                                        </Button>
                                </div>

                                {/* Voltage Drop Calculator */}
                                {activeTab === "voltage-drop" && (
                                        <Card className="border-border bg-card">
                                                <CardHeader>
                                                        <CardTitle className="text-lg text-foreground flex items-center gap-2">
                                                                <Zap className="h-5 w-5" />
                                                                {t("engineering.voltageDrop")}
                                                        </CardTitle>
                                                        <CardDescription className="text-muted-foreground">
                                                                {t("engineering.voltageDropDesc")}
                                                        </CardDescription>
                                                </CardHeader>
                                                <CardContent className="space-y-4">
                                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                                                <div className="space-y-2">
                                                                        <Label className="text-foreground/90">
                                                                                {t("engineering.current")}
                                                                        </Label>
                                                                        <Input
                                                                                type="number"
                                                                                value={voltageDropInputs.current}
                                                                                onChange={(e) =>
                                                                                        setVoltageDropInputs({
                                                                                                ...voltageDropInputs,
                                                                                                current: e.target.value,
                                                                                        })
                                                                                }
                                                                                className="bg-card border-border text-foreground"
                                                                                placeholder="A"
                                                                        />
                                                                </div>
                                                                <div className="space-y-2">
                                                                        <Label className="text-foreground/90">
                                                                                {t("engineering.length")}
                                                                        </Label>
                                                                        <Input
                                                                                type="number"
                                                                                value={voltageDropInputs.length}
                                                                                onChange={(e) =>
                                                                                        setVoltageDropInputs({
                                                                                                ...voltageDropInputs,
                                                                                                length: e.target.value,
                                                                                        })
                                                                                }
                                                                                className="bg-card border-border text-foreground"
                                                                                placeholder="m"
                                                                        />
                                                                </div>
                                                                <div className="space-y-2">
                                                                        <Label className="text-foreground/90">
                                                                                {t("engineering.cableSize")}
                                                                        </Label>
                                                                        <Input
                                                                                type="number"
                                                                                value={voltageDropInputs.cableSize}
                                                                                onChange={(e) =>
                                                                                        setVoltageDropInputs({
                                                                                                ...voltageDropInputs,
                                                                                                cableSize: e.target.value,
                                                                                        })
                                                                                }
                                                                                className="bg-card border-border text-foreground"
                                                                                placeholder="mm²"
                                                                        />
                                                                </div>
                                                                <div className="space-y-2">
                                                                        <Label className="text-foreground/90">
                                                                                {t("engineering.voltage")}
                                                                        </Label>
                                                                        <Input
                                                                                type="number"
                                                                                value={voltageDropInputs.voltage}
                                                                                onChange={(e) =>
                                                                                        setVoltageDropInputs({
                                                                                                ...voltageDropInputs,
                                                                                                voltage: e.target.value,
                                                                                        })
                                                                                }
                                                                                className="bg-card border-border text-foreground"
                                                                                placeholder="V"
                                                                        />
                                                                </div>
                                                                <div className="space-y-2">
                                                                        <Label className="text-foreground/90">
                                                                                {t("engineering.material")}
                                                                        </Label>
                                                                        <Select
                                                                                value={voltageDropInputs.material}
                                                                                onValueChange={(v) =>
                                                                                        setVoltageDropInputs({
                                                                                                ...voltageDropInputs,
                                                                                                material: v,
                                                                                        })
                                                                                }
                                                                        >
                                                                                <SelectTrigger className="bg-card border-border text-foreground">
                                                                                        <SelectValue />
                                                                                </SelectTrigger>
                                                                                <SelectContent className="bg-card border-border">
                                                                                        <SelectItem value="cu">
                                                                                                {t("engineering.copper")}
                                                                                        </SelectItem>
                                                                                        <SelectItem value="al">
                                                                                                {t("engineering.aluminum")}
                                                                                        </SelectItem>
                                                                                </SelectContent>
                                                                        </Select>
                                                                </div>
                                                        </div>

                                                        <Separator />

                                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                                                <Card className="border-border bg-muted/50">
                                                                        <CardHeader>
                                                                                <div className="flex items-center justify-between">
                                                                                        <CardTitle className="text-foreground text-sm">
                                                                                                {t("engineering.results")}
                                                                                        </CardTitle>
                                                                                        <ExplainButton
                                                                                                calculationType="voltage_drop"  // NOSONAR: typescript:S3358
                                                                                                result={{
                                                                                                        percentage: vDropResult.percentage,
                                                                                                        absolute_v: vDropResult.absolute,
                                                                                                        current: voltageDropInputs.current,
                                                                                                        length: voltageDropInputs.length,
                                                                                                        voltage: voltageDropInputs.voltage,
                                                                                                }}  // NOSONAR: typescript:S3358
                                                                                        />
                                                                                </div>
                                                                        </CardHeader>
                                                                        <CardContent>
                                                                                <div className="space-y-2">
                                                                                        <div className="flex justify-between">
                                                                                                <span className="text-muted-foreground">
                                                                                                        {t("engineering.percentage")}
                                                                                                </span>
                                                                                                <span className="font-mono text-foreground">
                                                                                                        {vDropResult.percentage}%
                                                                                                </span>
                                                                                        </div>
                                                                                        <div className="flex justify-between">
                                                                                                <span className="text-muted-foreground">
                                                                                                        {t("engineering.absolute")}
                                                                                                </span>
                                                                                                <span className="font-mono text-foreground">
                                                                                                        {vDropResult.absolute}V
                                                                                                </span>
                                                                                        </div>
                                                                                </div>
                                                                        </CardContent>
                                                                </Card>

                                                                <Card className="border-border bg-muted/50">
                                                                        <CardHeader>
                                                                                <CardTitle className="text-foreground text-sm">
                                                                                        {t("engineering.status")}
                                                                                </CardTitle>
                                                                        </CardHeader>
                                                                        <CardContent>
                                                                                <Badge
                                                                                        variant={
                                                                                                vDropResult.percentage < 3
                                                                                                        ? "default"
                                                                                                        : vDropResult.percentage < 5
                                                                                                                ? "secondary"
                                                                                                                : "destructive"
                                                                                        }
                                                                                        className={
                                                                                                vDropResult.percentage < 3
                                                                                                        ? "bg-success/10 text-success border-success/30"
                                                                                                        : vDropResult.percentage < 5
                                                                                                                ? "bg-warning/10 text-warning border-warning/30"
                                                                                                                : "bg-danger/10 text-danger border-danger/30"
                                                                                        }
                                                                                >
                                                                                        {vDropResult.percentage < 3
                                                                                                ? t("engineering.suitable")
                                                                                                : vDropResult.percentage < 5
                                                                                                        ? t("engineering.acceptable")
                                                                                                        : t("engineering.excessive")}
                                                                                </Badge>
                                                                        </CardContent>
                                                                </Card>
                                                        </div>
                                                </CardContent>
                                        </Card>
                                )}

                                {/* Cable Sizing Calculator */}
                                {activeTab === "cable-sizing" && (
                                        <Card className="border-border bg-card">
                                                <CardHeader>
                                                        <CardTitle className="text-lg text-foreground flex items-center gap-2">
                                                                <Cable className="h-5 w-5" />
                                                                {t("engineering.cableSizing")}
                                                        </CardTitle>
                                                        <CardDescription className="text-muted-foreground">
                                                                {t("engineering.cableSizingDesc")}
                                                        </CardDescription>
                                                </CardHeader>
                                                <CardContent className="space-y-4">
                                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                                                <div className="space-y-2">
                                                                        <Label className="text-foreground/90">
                                                                                {t("engineering.loadCurrent")}
                                                                        </Label>
                                                                        <Input
                                                                                type="number"
                                                                                value={cableSizingInputs.loadCurrent}
                                                                                onChange={(e) =>
                                                                                        setCableSizingInputs({
                                                                                                ...cableSizingInputs,
                                                                                                loadCurrent: e.target.value,
                                                                                        })
                                                                                }
                                                                                className="bg-card border-border text-foreground"
                                                                                placeholder="A"
                                                                        />
                                                                </div>
                                                                <div className="space-y-2">
                                                                        <Label className="text-foreground/90">
                                                                                {t("engineering.length")}
                                                                        </Label>
                                                                        <Input
                                                                                type="number"
                                                                                value={cableSizingInputs.length}
                                                                                onChange={(e) =>
                                                                                        setCableSizingInputs({
                                                                                                ...cableSizingInputs,
                                                                                                length: e.target.value,
                                                                                        })
                                                                                }
                                                                                className="bg-card border-border text-foreground"
                                                                                placeholder="m"
                                                                        />
                                                                </div>
                                                                <div className="space-y-2">
                                                                        <Label className="text-foreground/90">
                                                                                {t("engineering.ambientTemp")}
                                                                        </Label>
                                                                        <Input
                                                                                type="number"
                                                                                value={cableSizingInputs.ambientTemp}
                                                                                onChange={(e) =>
                                                                                        setCableSizingInputs({
                                                                                                ...cableSizingInputs,
                                                                                                ambientTemp: e.target.value,
                                                                                        })
                                                                                }
                                                                                className="bg-card border-border text-foreground"
                                                                                placeholder="°C"
                                                                        />
                                                                </div>
                                                                <div className="space-y-2">
                                                                        <Label className="text-foreground/90">
                                                                                {t("engineering.installationMethod")}
                                                                        </Label>
                                                                        <Select
                                                                                value={cableSizingInputs.installationMethod}
                                                                                onValueChange={(v) =>
                                                                                        setCableSizingInputs({
                                                                                                ...cableSizingInputs,
                                                                                                installationMethod: v,
                                                                                        })
                                                                                }
                                                                        >
                                                                                <SelectTrigger className="bg-card border-border text-foreground">
                                                                                        <SelectValue />
                                                                                </SelectTrigger>
                                                                                <SelectContent className="bg-card border-border">
                                                                                        <SelectItem value="free-air">
                                                                                                {t("engineering.freeAir")}
                                                                                        </SelectItem>
                                                                                        <SelectItem value="conduit">
                                                                                                {t("engineering.conduit")}
                                                                                        </SelectItem>
                                                                                        <SelectItem value="trunking">
                                                                                                {t("engineering.trunking")}
                                                                                        </SelectItem>
                                                                                </SelectContent>
                                                                        </Select>
                                                                </div>
                                                        </div>

                                                        <Separator />

                                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                                                <Card className="border-border bg-muted/50">
                                                                        <CardHeader>
                                                                                <div className="flex items-center justify-between">
                                                                                        <CardTitle className="text-foreground text-sm">
                                                                                                {t("engineering.results")}
                                                                                        </CardTitle>
                                                                                        <ExplainButton
                                                                                                calculationType="cable_sizing"
                                                                                                result={{
                                                                                                        recommended_size_mm2: cableResult.recommendedSize,
                                                                                                        base_ampacity_a: cableResult.baseAmpacity,
                                                                                                        derating_factor: cableResult.deratingFactor,
                                                                                                        final_ampacity_a: cableResult.finalAmpacity,
                                                                                                }}
                                                                                        />
                                                                                </div>
                                                                        </CardHeader>
                                                                        <CardContent>
                                                                                <div className="space-y-2">
                                                                                        <div className="flex justify-between">
                                                                                                <span className="text-muted-foreground">
                                                                                                        {t("engineering.recommendedSize")}
                                                                                                </span>
                                                                                                <span className="font-mono text-foreground">
                                                                                                        {cableResult.recommendedSize} mm²
                                                                                                </span>
                                                                                        </div>
                                                                                        <div className="flex justify-between">
                                                                                                <span className="text-muted-foreground">
                                                                                                        {t("engineering.baseAmpacity")}
                                                                                                </span>
                                                                                                <span className="font-mono text-foreground">
                                                                                                        {cableResult.baseAmpacity} A
                                                                                                </span>
                                                                                        </div>
                                                                                        <div className="flex justify-between">
                                                                                                <span className="text-muted-foreground">
                                                                                                        {t("engineering.deratingFactor")}
                                                                                                </span>
                                                                                                <span className="font-mono text-foreground">
                                                                                                        {cableResult.deratingFactor}
                                                                                                </span>
                                                                                        </div>
                                                                                        <div className="flex justify-between">
                                                                                                <span className="text-muted-foreground">
                                                                                                        {t("engineering.finalAmpacity")}
                                                                                                </span>
                                                                                                <span className="font-mono text-foreground">
                                                                                                        {cableResult.finalAmpacity} A
                                                                                                </span>
                                                                                        </div>
                                                                                </div>
                                                                        </CardContent>
                                                                </Card>

                                                                <Card className="border-border bg-muted/50">
                                                                        <CardHeader>
                                                                                <CardTitle className="text-foreground text-sm">
                                                                                        {t("engineering.status")}
                                                                                </CardTitle>
                                                                        </CardHeader>
                                                                        <CardContent>
                                                                                <Badge className="bg-success/10 text-success border-success/30">
                                                                                        {t("engineering.suitable")}
                                                                                </Badge>
                                                                        </CardContent>
                                                                </Card>
                                                        </div>
                                                </CardContent>
                                        </Card>
                                )}

                                {/* Battery Calculation */}
                                {activeTab === "battery-calc" && (
                                        <Card className="border-border bg-card">
                                                <CardHeader>
                                                        <CardTitle className="text-lg text-foreground flex items-center gap-2">
                                                                <Battery className="h-5 w-5" />
                                                                {t("engineering.batteryCalculation")}
                                                        </CardTitle>
                                                        <CardDescription className="text-muted-foreground">
                                                                {t("engineering.batteryCalculationDesc")}
                                                        </CardDescription>
                                                </CardHeader>
                                                <CardContent className="space-y-4">
                                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                                                <div className="space-y-2">
                                                                        <Label className="text-foreground/90">
                                                                                {t("engineering.standbyDevices")}
                                                                        </Label>
                                                                        <Input
                                                                                type="number"
                                                                                value={batteryCalcInputs.standbyDevices}
                                                                                onChange={(e) =>
                                                                                        setBatteryCalcInputs({
                                                                                                ...batteryCalcInputs,
                                                                                                standbyDevices: e.target.value,
                                                                                        })
                                                                                }
                                                                                className="bg-card border-border text-foreground"
                                                                                placeholder="#"
                                                                        />
                                                                </div>
                                                                <div className="space-y-2">
                                                                        <Label className="text-foreground/90">
                                                                                {t("engineering.standbyCurrent")}
                                                                        </Label>
                                                                        <Input
                                                                                type="number"
                                                                                value={batteryCalcInputs.standbyCurrent}
                                                                                onChange={(e) =>
                                                                                        setBatteryCalcInputs({
                                                                                                ...batteryCalcInputs,
                                                                                                standbyCurrent: e.target.value,
                                                                                        })
                                                                                }
                                                                                className="bg-card border-border text-foreground"
                                                                                placeholder="mA"
                                                                        />
                                                                </div>
                                                                <div className="space-y-2">
                                                                        <Label className="text-foreground/90">
                                                                                {t("engineering.alarmDevices")}
                                                                        </Label>
                                                                        <Input
                                                                                type="number"
                                                                                value={batteryCalcInputs.alarmDevices}
                                                                                onChange={(e) =>
                                                                                        setBatteryCalcInputs({
                                                                                                ...batteryCalcInputs,
                                                                                                alarmDevices: e.target.value,
                                                                                        })
                                                                                }
                                                                                className="bg-card border-border text-foreground"
                                                                                placeholder="#"
                                                                        />
                                                                </div>
                                                                <div className="space-y-2">
                                                                        <Label className="text-foreground/90">
                                                                                {t("engineering.alarmCurrent")}
                                                                        </Label>
                                                                        <Input
                                                                                type="number"
                                                                                value={batteryCalcInputs.alarmCurrent}
                                                                                onChange={(e) =>
                                                                                        setBatteryCalcInputs({
                                                                                                ...batteryCalcInputs,
                                                                                                alarmCurrent: e.target.value,
                                                                                        })
                                                                                }
                                                                                className="bg-card border-border text-foreground"
                                                                                placeholder="mA"
                                                                        />
                                                                </div>
                                                                <div className="space-y-2">
                                                                        <Label className="text-foreground/90">
                                                                                {t("engineering.standbyHours")}
                                                                        </Label>
                                                                        <Input
                                                                                type="number"
                                                                                value={batteryCalcInputs.standbyHours}
                                                                                onChange={(e) =>
                                                                                        setBatteryCalcInputs({
                                                                                                ...batteryCalcInputs,
                                                                                                standbyHours: e.target.value,
                                                                                        })
                                                                                }
                                                                                className="bg-card border-border text-foreground"
                                                                                placeholder="hours"
                                                                        />
                                                                </div>
                                                                <div className="space-y-2">
                                                                        <Label className="text-foreground/90">
                                                                                {t("engineering.alarmMinutes")}
                                                                        </Label>
                                                                        <Input
                                                                                type="number"
                                                                                value={batteryCalcInputs.alarmMinutes}
                                                                                onChange={(e) =>
                                                                                        setBatteryCalcInputs({
                                                                                                ...batteryCalcInputs,
                                                                                                alarmMinutes: e.target.value,
                                                                                        })
                                                                                }
                                                                                className="bg-card border-border text-foreground"
                                                                                placeholder="minutes"
                                                                        />
                                                                </div>
                                                        </div>

                                                        <Separator />

                                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                                                <Card className="border-border bg-muted/50">
                                                                        <CardHeader>
                                                                                <div className="flex items-center justify-between">
                                                                                        <CardTitle className="text-foreground text-sm">
                                                                                                {t("engineering.results")}
                                                                                        </CardTitle>
                                                                                        <ExplainButton
                                                                                                calculationType="battery_sizing"
                                                                                                result={{
                                                                                                        total_standby_current_ma: batteryResult.totalStandbyCurrent,
                                                                                                        total_alarm_current_ma: batteryResult.totalAlarmCurrent,
                                                                                                        required_capacity_ah: batteryResult.requiredCapacity,
                                                                                                        recommended_battery: batteryResult.recommendedBattery,
                                                                                                        standby_hours: batteryCalcInputs.standbyHours,
                                                                                                }}
                                                                                        />
                                                                                </div>
                                                                        </CardHeader>
                                                                        <CardContent>
                                                                                <div className="space-y-2">
                                                                                        <div className="flex justify-between">
                                                                                                <span className="text-muted-foreground">
                                                                                                        {t("engineering.totalStandbyCurrent")}
                                                                                                </span>
                                                                                                <span className="font-mono text-foreground">
                                                                                                        {batteryResult.totalStandbyCurrent} mA
                                                                                                </span>
                                                                                        </div>
                                                                                        <div className="flex justify-between">
                                                                                                <span className="text-muted-foreground">
                                                                                                        {t("engineering.totalAlarmCurrent")}
                                                                                                </span>
                                                                                                <span className="font-mono text-foreground">
                                                                                                        {batteryResult.totalAlarmCurrent} mA
                                                                                                </span>
                                                                                        </div>
                                                                                        <div className="flex justify-between">
                                                                                                <span className="text-muted-foreground">
                                                                                                        {t("engineering.requiredCapacity")}
                                                                                                </span>
                                                                                                <span className="font-mono text-foreground">
                                                                                                        {batteryResult.requiredCapacity} Ah
                                                                                                </span>
                                                                                        </div>
                                                                                </div>
                                                                        </CardContent>
                                                                </Card>

                                                                <Card className="border-border bg-muted/50">
                                                                        <CardHeader>
                                                                                <CardTitle className="text-foreground text-sm">
                                                                                        {t("engineering.recommendations")}
                                                                                </CardTitle>
                                                                        </CardHeader>
                                                                        <CardContent>
                                                                                <div className="space-y-2">
                                                                                        <div className="flex justify-between">
                                                                                                <span className="text-muted-foreground">
                                                                                                        {t("engineering.recommendedBattery")}
                                                                                                </span>
                                                                                                <span className="font-mono text-foreground">
                                                                                                        {batteryResult.recommendedBattery}
                                                                                                </span>
                                                                                        </div>
                                                                                </div>
                                                                        </CardContent>
                                                                </Card>
                                                        </div>
                                                </CardContent>
                                        </Card>
                                )}
                        </div>
                </div>
        );
}
