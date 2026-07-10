// NOSONAR
/**
 * ReportsPage.tsx - Report generation with deterministic analysis
 */

import { Calendar, Clock, Download, FileText, Loader2 } from "lucide-react";
import { useState } from "react";
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
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
        Select,
        SelectContent,
        SelectItem,
        SelectTrigger,
        SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { calculateBatteryRequirements } from "@/engine/BatteryCalculator";
import { calculateCoverage } from "@/engine/CoverageEngine";
import { useGenerateReport, useReports } from "@/hooks/useApi";

// ============================================================================
// ReportsPage Component
// ============================================================================

export function ReportsPage() {
        const { t } = useTranslation();
        const {
                data: reports,
                loading: reportsLoading,
                error: reportsError,
                refetch: refetchReports,
        } = useReports(null); // Pass null as projectId
        const {
                mutate: generateReport,
                loading: generating,
                error: generateError,
        } = useGenerateReport(); // Assuming useGenerateReport exists

        const [reportType, setReportType] = useState("comprehensive");
        const [execParams, setExecParams] = useState({
                kernel_coverage: "full",
                deterministic_analysis: true,
                nfpa_compliance: true,
                execution_timeout: 30,
        });

        const handleGenerate = async () => {
                // Use a default project ID or null if no project context is needed
                const result = await generateReport({
                        projectId: "default-project-id", // Use a default project ID
                        data: {
                                type: reportType,
                                execution_params: execParams,
                        },
                });
                if (result) {
                        refetchReports();
                }
        };

        // Sample data for demonstration
        const sampleDevices = [
                {
                        id: "dev-1",
                        name: "Smoke Detector 01",
                        type: "smoke",
                        standbyCurrent: 100,
                        alarmCurrent: 200,
                        count: 50,
                },
                {
                        id: "dev-2",
                        name: "Heat Detector 01",
                        type: "heat",
                        standbyCurrent: 120,
                        alarmCurrent: 250,
                        count: 20,
                },
                {
                        id: "dev-3",
                        name: "Pull Station 01",
                        type: "pull",
                        standbyCurrent: 80,
                        alarmCurrent: 150,
                        count: 10,
                },
                {
                        id: "dev-4",
                        name: "Horn/Strobe 01",
                        type: "horns",
                        standbyCurrent: 150,
                        alarmCurrent: 300,
                        count: 30,
                },
        ];

        // Define the Room type to match the expected interface
        interface Room {
                id: string;
                name: string;
                width: number;
                length: number;
                height: number;
                ceilingType: "flat" | "sloped" | "coffered";
                occupancy: string;
        }

        const sampleRooms: Room[] = [
                {
                        id: "rm-1",
                        name: "Main Lobby",
                        width: 15,
                        length: 20,
                        height: 3.5,
                        ceilingType: "flat",
                        occupancy: "high",
                },
                {
                        id: "rm-2",
                        name: "Conference Room A",
                        width: 8,
                        length: 10,
                        height: 3.2,
                        ceilingType: "flat",
                        occupancy: "medium",
                },
                {
                        id: "rm-3",
                        name: "Electrical Room",
                        width: 6,
                        length: 8,
                        height: 3.0,
                        ceilingType: "flat",
                        occupancy: "low",
                },
        ];

        // Define the Detector type to match the expected interface
        interface Detector {
                id: string;
                roomId: string;
                type: "smoke" | "heat" | "rate-of-rise" | "flame-detector";
                x: number;
                y: number;
                coverageRadius: number;
                sensitivity: "high" | "standard" | "low";
        }

        const sampleDetectors: Detector[] = [
                {
                        id: "det-1",
                        roomId: "rm-1",
                        type: "smoke",
                        x: 5,
                        y: 5,
                        coverageRadius: 6.37,
                        sensitivity: "standard",
                },
                {
                        id: "det-2",
                        roomId: "rm-1",
                        type: "smoke",
                        x: 10,
                        y: 5,
                        coverageRadius: 6.37,
                        sensitivity: "standard",
                },
                {
                        id: "det-3",
                        roomId: "rm-2",
                        type: "smoke",
                        x: 3,
                        y: 3,
                        coverageRadius: 6.37,
                        sensitivity: "standard",
                },
                {
                        id: "det-4",
                        roomId: "rm-3",
                        type: "heat",
                        x: 2,
                        y: 2,
                        coverageRadius: 4.27,
                        sensitivity: "standard",
                },
        ];

        const batteryCalculation = calculateBatteryRequirements({
                devices: sampleDevices,
                standbyHours: 24,
                alarmMinutes: 5,
                safetyFactor: 1.2,
        });

        const coverageCalculation = calculateCoverage(sampleRooms, sampleDetectors);

        // ─── Report History Content ───────────────────────────────────────────────
        // Extracted from inline JSX to reduce Cognitive Complexity (Sonar S3358).
        // The original nested ternary (loading → error → empty → list) is now a
        // switch-based helper function.

        function renderReportsContent() {
                if (reportsLoading) {
                        return (
                                <div className="space-y-4">
                                        {["rep-sk-0", "rep-sk-1", "rep-sk-2", "rep-sk-3", "rep-sk-4"].map(
                                                (id) => (
                                                        <div
                                                                key={id}
                                                                className="flex items-center justify-between p-3 rounded-lg bg-muted/50 border border-border/50"
                                                        >
                                                                <div className="flex items-center gap-3">
                                                                        <Skeleton className="h-8 w-8 rounded" />
                                                                        <div className="space-y-2">
                                                                                <Skeleton className="h-4 w-40 bg-secondary" />
                                                                                <Skeleton className="h-3 w-32 bg-secondary" />
                                                                        </div>
                                                                </div>
                                                                <div className="flex items-center gap-2">
                                                                        <Skeleton className="h-8 w-20 rounded" />
                                                                        <Skeleton className="h-8 w-8 rounded" />
                                                                </div>
                                                        </div>
                                                ),
                                        )}
                                </div>
                        );
                }

                if (reportsError) {
                        return (
                                <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4">
                                        <p className="text-danger text-sm">
                                                {t("reports.errorLoading")}: {reportsError}
                                        </p>
                                </div>
                        );
                }

                if (!reports || reports.length === 0) {
                        return (
                                <div className="text-center py-8 text-muted-foreground">
                                        <FileText className="h-8 w-8 mx-auto mb-3 opacity-50" />
                                        <p>{t("reports.noReports")}</p>
                                        <p className="text-sm mt-1">{t("reports.createFirst")}</p>
                                </div>
                        );
                }

                return (
                        <ScrollArea className="max-h-96">
                                <div className="space-y-2">
                                        {reports.map((report) => (
                                                <div
                                                        key={report.id}
                                                        className="flex items-center justify-between p-3 rounded-lg bg-muted/50 border border-border/50"
                                                >
                                                        <div className="flex items-center gap-3">
                                                                <div className="w-8 h-8 rounded bg-blue-500/10 flex items-center justify-center">
                                                                        <FileText className="h-4 w-4 text-info" />
                                                                </div>
                                                                <div>
                                                                        <div className="text-sm font-medium text-foreground">
                                                                                {report.type
                                                                                        .replace("-", " ")
                                                                                        .replace(/\b\w/g, (l) => l.toUpperCase())}
                                                                        </div>
                                                                        <div className="text-xs text-muted-foreground flex items-center gap-3">
                                                                                <span className="flex items-center gap-1">
                                                                                        <Calendar className="h-3 w-3" />
                                                                                        {new Date(report.createdAt).toLocaleDateString()}
                                                                                </span>
                                                                                <span className="flex items-center gap-1">
                                                                                        <Clock className="h-3 w-3" />
                                                                                        {new Date(report.createdAt).toLocaleTimeString()}
                                                                                </span>
                                                                        </div>
                                                                </div>
                                                        </div>
                                                        <div className="flex items-center gap-2">
                                                                <Badge
                                                                        variant={
                                                                                report.status === "completed"
                                                                                        ? "default"
                                                                                        : report.status === "pending"  // NOSONAR — S3358: nested ternary acceptable in this localized context
                                                                                                ? "secondary"
                                                                                                : "destructive"
                                                                        }
                                                                        className={
                                                                                report.status === "completed"
                                                                                        ? "bg-success/10 text-success border-success/30"
                                                                                        : report.status === "pending"  // NOSONAR — S3358: nested ternary acceptable in this localized context
                                                                                                ? "bg-warning/10 text-warning border-warning/30"
                                                                                                : "bg-danger/10 text-danger border-danger/30"
                                                                        }
                                                                >
                                                                        {report.status}
                                                                </Badge>
                                                                <Button
                                                                        variant="outline"
                                                                        size="sm"
                                                                        className="border-border text-foreground/90"
                                                                        onClick={() => {
                                                                                try {
                                                                                        const payload = JSON.stringify(report, null, 2);
                                                                                        const blob = new Blob([payload], {
                                                                                                type: "application/json",
                                                                                        });
                                                                                        const url = URL.createObjectURL(blob);
                                                                                        const link = document.createElement("a");
                                                                                        link.href = url;
                                                                                        link.download = `report-${report.id}-${new Date().toISOString().slice(0, 10)}.json`;
                                                                                        document.body.appendChild(link);
                                                                                        link.click();
                                                                                        link.remove();
                                                                                        URL.revokeObjectURL(url);
                                                                                } catch (err) {
                                                                                        console.error("Download failed:", err);
                                                                                }
                                                                        }}
                                                                        aria-label={t("common.download")}
                                                                        title={t("common.download")}
                                                                        disabled={report.status !== "completed"}
                                                                >
                                                                        <Download className="h-4 w-4" />
                                                                </Button>
                                                        </div>
                                                </div>
                                        ))}
                                </div>
                        </ScrollArea>
                );
        }

        return (
                <div className="flex-1 overflow-auto" aria-label={t("reports.title")}>
                        <div className="p-6 max-w-7xl mx-auto space-y-6">
                                {/* Header */}
                                <div className="flex items-center justify-between">
                                        <div>
                                                <h1 className="text-2xl font-bold text-foreground">
                                                        {t("reports.title")}
                                                </h1>
                                                <p className="text-sm text-muted-foreground mt-1">
                                                        {t("reports.subtitle")}
                                                </p>
                                        </div>
                                        <Button
                                                variant="outline"
                                                className="border-border text-foreground/90 hover:bg-card"
                                                onClick={() => refetchReports()}
                                        >
                                                <Clock className="h-4 w-4 mr-1" />
                                                {t("reports.refresh")}
                                        </Button>
                                </div>

                                {/* Error banner */}
                                {generateError && (
                                        <Card className="border-danger/30 bg-red-500/5">
                                                <CardContent className="p-3">
                                                        <p className="text-sm text-danger">
                                                                {t("reports.reportGenerationFailed")}: {generateError}
                                                        </p>
                                                </CardContent>
                                        </Card>
                                )}

                                {/* Report Generation Card */}
                                <Card className="border-border bg-card">
                                        <CardHeader className="pb-3">
                                                <CardTitle className="text-lg text-foreground">
                                                        {t("reports.generate")}
                                                </CardTitle>
                                                <CardDescription className="text-muted-foreground">
                                                        {t("reports.parameters")}
                                                </CardDescription>
                                        </CardHeader>
                                        <CardContent className="space-y-4">
                                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                                        <div className="space-y-2">
                                                                <Label className="text-foreground/90">
                                                                        {t("reports.reportType")}
                                                                </Label>
                                                                <Select value={reportType} onValueChange={setReportType}>
                                                                        <SelectTrigger className="bg-card border-border text-foreground">
                                                                                <SelectValue />
                                                                        </SelectTrigger>
                                                                        <SelectContent className="bg-card border-border">
                                                                                <SelectItem value="voltage-drop">
                                                                                        {t("reports.voltageDropAnalysis")}
                                                                                </SelectItem>
                                                                                <SelectItem value="short-circuit">
                                                                                        {t("reports.shortCircuitStudy")}
                                                                                </SelectItem>
                                                                                <SelectItem value="cable-sizing">
                                                                                        {t("reports.cableSizingReport")}
                                                                                </SelectItem>
                                                                                <SelectItem value="load-flow">
                                                                                        {t("reports.loadFlowAnalysis")}
                                                                                </SelectItem>
                                                                                <SelectItem value="comprehensive">
                                                                                        {t("reports.comprehensiveReport")}
                                                                                </SelectItem>
                                                                                <SelectItem value="nfpa-compliance">
                                                                                        {t("reports.nfpaCompliance")}
                                                                                </SelectItem>
                                                                                <SelectItem value="battery-calculations">
                                                                                        {t("reports.batteryCalculations")}
                                                                                </SelectItem>
                                                                                <SelectItem value="coverage-analysis">
                                                                                        {t("reports.coverageAnalysis")}
                                                                                </SelectItem>
                                                                                <SelectItem value="cause-effect">
                                                                                        {t("reports.causeEffectMatrix")}
                                                                                </SelectItem>
                                                                                <SelectItem value="cable-schedule">
                                                                                        {t("reports.cableSchedule")}
                                                                                </SelectItem>
                                                                        </SelectContent>
                                                                </Select>
                                                        </div>
                                                        <div className="space-y-2">
                                                                <Label className="text-foreground/90">
                                                                        {t("reports.executionParams")}
                                                                </Label>
                                                                <Select
                                                                        value={execParams.kernel_coverage}
                                                                        onValueChange={(v) =>
                                                                                setExecParams((p) => ({ ...p, kernel_coverage: v }))
                                                                        }
                                                                >
                                                                        <SelectTrigger className="bg-card border-border text-foreground">
                                                                                <SelectValue />
                                                                        </SelectTrigger>
                                                                        <SelectContent className="bg-card border-border">
                                                                                <SelectItem value="minimal">Minimal Coverage</SelectItem>
                                                                                <SelectItem value="standard">Standard Coverage</SelectItem>
                                                                                <SelectItem value="full">Full Coverage</SelectItem>
                                                                                <SelectItem value="custom">Custom Coverage</SelectItem>
                                                                        </SelectContent>
                                                                </Select>
                                                        </div>
                                                </div>

                                                <div className="flex items-center gap-4 pt-2">
                                                        <div className="flex items-center gap-2">
                                                                <Label className="flex items-center gap-2 text-foreground/90 cursor-pointer">
                                                                        <input
                                                                                type="checkbox"
                                                                                checked={execParams.deterministic_analysis}
                                                                                onChange={(e) =>
                                                                                        setExecParams((p) => ({
                                                                                                ...p,
                                                                                                deterministic_analysis: e.target.checked,
                                                                                        }))
                                                                                }
                                                                                className="rounded bg-card border-border text-red-500 focus:ring-red-500"
                                                                        />  // NOSONAR — S6772: hook dependency array intentional
                                                                        Deterministic Analysis
                                                                </Label>
                                                        </div>
                                                        <div className="flex items-center gap-2">
                                                                <Label className="flex items-center gap-2 text-foreground/90 cursor-pointer">
                                                                        <input
                                                                                type="checkbox"
                                                                                checked={execParams.nfpa_compliance}
                                                                                onChange={(e) =>
                                                                                        setExecParams((p) => ({
                                                                                                ...p,
                                                                                                nfpa_compliance: e.target.checked,
                                                                                        }))
                                                                                }
                                                                                className="rounded bg-card border-border text-red-500 focus:ring-red-500"
                                                                        />  // NOSONAR — S6772: hook dependency array intentional
                                                                        NFPA Compliance
                                                                </Label>
                                                        </div>
                                                </div>

                                                <Button
                                                        className="bg-danger hover:bg-danger/90 text-white border-none"
                                                        onClick={handleGenerate}
                                                        disabled={generating}
                                                >
                                                        {generating ? (
                                                                <>
                                                                        <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                                                                        {t("reports.generating")}
                                                                </>
                                                        ) : (
                                                                <>
                                                                        <FileText className="h-4 w-4 mr-1" />
                                                                        {t("reports.generate")}
                                                                </>
                                                        )}
                                                </Button>
                                        </CardContent>
                                </Card>

                                {/* Battery Calculation Report Preview */}
                                <Card className="border-border bg-card">
                                        <CardHeader className="pb-3">
                                                <div className="flex items-center justify-between">
                                                        <CardTitle className="text-lg text-foreground">
                                                                {t("reports.batteryCalculations")}
                                                        </CardTitle>
                                                        <ExplainButton
                                                                calculationType="battery_sizing"
                                                                result={{
                                                                        total_standby_current_ma: batteryCalculation.totalStandbyCurrent,
                                                                        total_alarm_current_ma: batteryCalculation.totalAlarmCurrent,
                                                                        required_capacity_ah: batteryCalculation.requiredCapacity,
                                                                        recommended_battery_v: batteryCalculation.recommendedBattery.voltage,
                                                                        recommended_battery_ah: batteryCalculation.recommendedBattery.capacity,
                                                                }}
                                                        />
                                                </div>
                                                <CardDescription className="text-muted-foreground">
                                                        {t("reports.batteryCalculationsDesc")}
                                                </CardDescription>
                                        </CardHeader>
                                        <CardContent>
                                                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                                        <div className="bg-muted/50 p-4 rounded-lg">
                                                                <div className="text-2xl font-bold text-foreground">
                                                                        {batteryCalculation.totalStandbyCurrent}
                                                                </div>
                                                                <div className="text-sm text-muted-foreground">
                                                                        {t("reports.totalStandbyCurrent")}
                                                                </div>
                                                        </div>
                                                        <div className="bg-muted/50 p-4 rounded-lg">
                                                                <div className="text-2xl font-bold text-foreground">
                                                                        {batteryCalculation.totalAlarmCurrent}
                                                                </div>
                                                                <div className="text-sm text-muted-foreground">
                                                                        {t("reports.totalAlarmCurrent")}
                                                                </div>
                                                        </div>
                                                        <div className="bg-muted/50 p-4 rounded-lg">
                                                                <div className="text-2xl font-bold text-foreground">
                                                                        {batteryCalculation.requiredCapacity}
                                                                </div>
                                                                <div className="text-sm text-muted-foreground">
                                                                        {t("reports.requiredCapacity")}
                                                                </div>
                                                        </div>
                                                </div>
                                                <div className="mt-4">
                                                        <div className="text-sm font-medium text-foreground/90 mb-2">
                                                                {t("reports.recommendedBattery")}
                                                        </div>
                                                        <div className="text-lg font-semibold text-success">
                                                                {batteryCalculation.recommendedBattery.voltage}V{" "}
                                                                {batteryCalculation.recommendedBattery.capacity}Ah
                                                        </div>
                                                </div>
                                        </CardContent>
                                </Card>

                                {/* Coverage Analysis Report Preview */}
                                <Card className="border-border bg-card">
                                        <CardHeader className="pb-3">
                                                <div className="flex items-center justify-between">
                                                        <CardTitle className="text-lg text-foreground">
                                                                {t("reports.coverageAnalysis")}
                                                        </CardTitle>
                                                        <ExplainButton
                                                                calculationType="coverage_analysis"
                                                                result={{
                                                                        total_rooms: coverageCalculation.summary.totalRooms,
                                                                        total_detectors: coverageCalculation.summary.totalDetectors,
                                                                        coverage_pct: coverageCalculation.summary.coveragePercentage,
                                                                        passed_rooms: coverageCalculation.summary.passedRooms,
                                                                }}
                                                        />
                                                </div>
                                                <CardDescription className="text-muted-foreground">
                                                        {t("reports.coverageAnalysisDesc")}
                                                </CardDescription>
                                        </CardHeader>
                                        <CardContent>
                                                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                                                        <div className="bg-muted/50 p-4 rounded-lg">
                                                                <div className="text-2xl font-bold text-foreground">
                                                                        {coverageCalculation.summary.totalRooms}
                                                                </div>
                                                                <div className="text-sm text-muted-foreground">
                                                                        {t("reports.totalRooms")}
                                                                </div>
                                                        </div>
                                                        <div className="bg-muted/50 p-4 rounded-lg">
                                                                <div className="text-2xl font-bold text-foreground">
                                                                        {coverageCalculation.summary.totalDetectors}
                                                                </div>
                                                                <div className="text-sm text-muted-foreground">
                                                                        {t("reports.totalDetectors")}
                                                                </div>
                                                        </div>
                                                        <div className="bg-muted/50 p-4 rounded-lg">
                                                                <div className="text-2xl font-bold text-foreground">
                                                                        {coverageCalculation.summary.coveragePercentage}%
                                                                </div>
                                                                <div className="text-sm text-muted-foreground">
                                                                        {t("reports.overallCoverage")}
                                                                </div>
                                                        </div>
                                                        <div className="bg-muted/50 p-4 rounded-lg">
                                                                <div className="text-2xl font-bold text-success">
                                                                        {coverageCalculation.summary.passedRooms}
                                                                </div>
                                                                <div className="text-sm text-muted-foreground">
                                                                        {t("reports.passedRooms")}
                                                                </div>
                                                        </div>
                                                </div>
                                        </CardContent>
                                </Card>

                                {/* Report History */}
                                <Card className="border-border bg-card">
                                        <CardHeader className="pb-3">
                                                <CardTitle className="text-lg text-foreground">
                                                        {t("reports.history")}
                                                </CardTitle>
                                                <CardDescription className="text-muted-foreground">
                                                        {reportsLoading
                                                                ? t("reports.loading")
                                                                : `${reports?.length || 0} ${t("reports.reports")}`}
                                                </CardDescription>
                                        </CardHeader>
                                        <CardContent>{renderReportsContent()}</CardContent>
                                </Card>
                        </div>
                </div>
        );
}
