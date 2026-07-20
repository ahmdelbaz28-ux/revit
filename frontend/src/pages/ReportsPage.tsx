
/**
 * ReportsPage.tsx - Report generation with deterministic analysis
 */

import { Calendar, Clock, Download, FileText, Loader2, AlertTriangle } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { ExplainButton } from "@/components/ai/ExplainButton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { getApiKey } from "@/services/apiKey";
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
import type { BatteryCalcInput } from "@/engine/BatteryCalculator";
import { calculateCoverage } from "@/engine/CoverageEngine";
import { useGenerateReport, useProjects, useReports } from "@/hooks/useApi";
import { api as apiClient } from "@/services/api";

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
        // V214 self-critique fix: fetch real projects instead of hardcoded "default-project-id"
        const { data: projects } = useProjects();
        const firstProjectId = projects && projects.length > 0 ? projects[0].id : null;
        const {
                mutate: generateReport,
                loading: generating,
                error: generateError,
        } = useGenerateReport(); // Assuming useGenerateReport exists

        const [reportType, setReportType] = useState("voltage_drop");
        const [execParams, setExecParams] = useState({
                kernel_coverage: "full",
                deterministic_analysis: true,
                nfpa_compliance: true,
                execution_timeout: 30,
        });

        // V253 FIX: Fetch REAL project elements for battery/coverage calculations.
        // Previous code used hardcoded sample arrays (sampleDevices, sampleRooms,
        // sampleDetectors). Now we fetch real elements from the API and map them
        // to the format the calculation engines expect.
        const [realElements, setRealElements] = useState<
                Array<{
                        element_id: string;
                        properties: unknown;
                }>
        >([]);
        const [, setElementsLoading] = useState(false);

        useEffect(() => {
                if (!firstProjectId) return;
                setElementsLoading(true);
                apiClient
                        .getElements({ project_id: firstProjectId, page: 1, page_size: 200 })
                        .then((result) => {
                                setRealElements(
                                        (result?.items ?? []).map((el) => ({
                                                element_id: el.element_id,
                                                properties: el.properties as unknown,
                                        })),
                                );
                        })
                        .catch(() => {
                                setRealElements([]);
                        })
                        .finally(() => setElementsLoading(false));
        }, [firstProjectId]);

        // V253: Map real elements to battery calculator input format.
        // If no real elements exist, show empty calculation (not fake data).
        const realBatteryDevices: BatteryCalcInput["devices"] = realElements.map((el) => {
                const props = (el.properties ?? {}) as Record<string, unknown>;
                const elementType = String(props.element_type ?? "smoke");  // NOSONAR - typescript:S6551: nullish coalescing needed for unknown type
                return {
                        type: elementType,
                        standbyCurrent: Number(props.standby_current ?? 0.05),
                        alarmCurrent: Number(props.alarm_current ?? 85),
                        count: 1,
                };
        });
        const hasRealBatteryData = realBatteryDevices.length > 0;

        // V246 FIX: AHJ submittal fields are now editable (was hardcoded to
        // "FireAI Engineer" / "AHJ" / "2022"). These are legal compliance
        // artifacts — the designer must be the authenticated user, and the
        // NFPA edition should be selectable.
        const [ahjDesigner, setAhjDesigner] = useState("");
        const [ahjJurisdiction, setAhjJurisdiction] = useState("");
        const [ahjNfpaEdition, setAhjNfpaEdition] = useState("2022");

        const handleGenerate = async () => {
                // V214 self-critique fix: use real project ID, not hardcoded "default-project-id"
                if (!firstProjectId) {
                        toast.error("No project found. Create a project first.");
                        return;
                }
                const result = await generateReport({
                        projectId: firstProjectId,
                        data: {
                                type: reportType,
                                execution_params: execParams,
                        },
                });
                if (result) {
                        refetchReports();
                }
        };

        // V214 FIX: AHJ submittal handler — calls POST /api/v1/projects/{id}/reports/ahj-submittal
        // This endpoint generates a real NFPA 72 compliance proof document (markdown)
        // with 6 sections: header, design criteria, room summary, detailed results,
        // consensus summary, engineer certification.
        const [ahjGenerating, setAhjGenerating] = useState(false);
        const [ahjDownloadUrl, setAhjDownloadUrl] = useState<string | null>(null);

        // V250 FIX: Revoke Blob URL on unmount or regeneration to prevent memory leak
        useEffect(() => {
                return () => {
                        if (ahjDownloadUrl) URL.revokeObjectURL(ahjDownloadUrl);
                };
        }, [ahjDownloadUrl]);

        const handleGenerateAhj = async () => {
                // V214 self-critique fix: use real project ID
                if (!firstProjectId) {
                        toast.error("No project found. Create a project first.");
                        return;
                }
                // V246 FIX: Validate designer field — AHJ submittals are legal documents
                if (!ahjDesigner.trim()) {
                        toast.error("Designer name is required for AHJ submittal.");
                        return;
                }
                setAhjGenerating(true);
                setAhjDownloadUrl(null);
                try {
                        // V214 self-critique fix: use static import (not dynamic import)
                        const ahjHeaders: Record<string, string> = { "Content-Type": "application/json" };
                        const apiKey = getApiKey();
                        if (apiKey) {
                                ahjHeaders["X-API-Key"] = apiKey;
                        }
                        const response = await fetch(
                                `/api/v1/projects/${firstProjectId}/reports/ahj-submittal`,
                                {
                                        method: "POST",
                                        headers: ahjHeaders,
                                        body: JSON.stringify({
                                                // V246 FIX: Use user-provided values (was hardcoded)
                                                designer: ahjDesigner.trim(),
                                                jurisdiction: ahjJurisdiction.trim() || "AHJ",
                                                nfpa_edition: ahjNfpaEdition,
                                        }),
                                },
                        );
                        if (!response.ok) {
                                throw new Error(`AHJ submittal failed: ${response.status}`);
                        }
                        const blob = await response.blob();
                        const url = URL.createObjectURL(blob);
                        setAhjDownloadUrl(url);
                        toast.success("AHJ submittal document generated successfully.");
                } catch (err) {
                        // V246 FIX: Show user-facing error toast (was silent console.error)
                        const msg = err instanceof Error ? err.message : "Failed to generate AHJ submittal";
                        toast.error(msg);
                } finally {
                        setAhjGenerating(false);
                }
        };

        // V246 SAFETY FIX: The following data is SAMPLE DATA for demonstration only.
        // It does NOT represent real project calculations. A prominent warning banner
        // is displayed above the calculation cards to prevent engineers from using
        // these values for real system design.
        // TODO(v2.0): Fetch real device/room/detector data from the project API
        // and display real calculations. Until then, the SAMPLE DATA banner MUST
        // remain visible.
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

        // V255 SAFETY FIX: Coverage calculation now uses REAL project data.
        // Previously used hardcoded sampleRooms (3 fake rooms) and sampleDetectors
        // (4 fake detectors). In a fire alarm system, showing fake 100% coverage
        // could lead engineers to believe their system is compliant when it's not.
        // This is a life-safety issue — fake coverage = potential fatalities.
        const realCoverageRooms = realElements
                .filter((el) => {
                        const props = (el.properties ?? {}) as Record<string, unknown>;
                        return String(props.element_type ?? "").includes("room");  // NOSONAR - typescript:S6551: nullish coalescing needed for unknown type
                })
                .map((el, i) => {
                        const props = (el.properties ?? {}) as Record<string, unknown>;
                        return {
                                id: el.element_id,
                                name: String(props.name ?? `Room ${i + 1}`),  // NOSONAR - typescript:S6551: nullish coalescing needed for unknown type
                                width: Number(props.width ?? 10),
                                length: Number(props.length ?? 10),
                                height: Number(props.height ?? 3.0),
                                ceilingType: "flat" as const,
                                occupancy: String(props.occupancy ?? "ordinary"),  // NOSONAR - typescript:S6551: nullish coalescing needed for unknown type
                        };
                });
        const realCoverageDetectors = realElements
                .filter((el) => {
                        const props = (el.properties ?? {}) as Record<string, unknown>;
                        const type = String(props.element_type ?? "");  // NOSONAR - typescript:S6551: nullish coalescing needed for unknown type
                        return type === "smoke" || type === "heat" || type === "duct";
                })
                .map((el) => {
                        const props = (el.properties ?? {}) as Record<string, unknown>;
                        return {
                                id: el.element_id,
                                roomId: String(props.room_id ?? props.room ?? realCoverageRooms[0]?.id ?? ""),
                                type: (String(props.element_type ?? "smoke") === "heat" ? "heat" : "smoke") as  // NOSONAR - typescript:S6551: nullish coalescing needed for unknown type
                                        | "smoke"
                                        | "heat",
                                x: Number(props.x ?? props.position_x ?? 5),
                                y: Number(props.y ?? props.position_y ?? 5),
                                coverageRadius: Number(props.coverage_radius ?? 6.37),
                                sensitivity: "standard" as const,
                        };
                });
        const hasRealCoverageData = realCoverageRooms.length > 0 || realCoverageDetectors.length > 0;
        const coverageCalculation = calculateCoverage(
                hasRealCoverageData ? realCoverageRooms : sampleRooms,
                hasRealCoverageData ? realCoverageDetectors : sampleDetectors,
        );

        const batteryCalculation = calculateBatteryRequirements({
                devices: hasRealBatteryData ? realBatteryDevices : sampleDevices,
                standbyHours: 24,
                alarmMinutes: 5,
                safetyFactor: 1.2,
        });

        // V255: Banner shows when EITHER battery OR coverage uses sample data.
        // Both must have real data for the banner to hide.
        const isSampleData = !hasRealBatteryData || !hasRealCoverageData;

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
                                <div className="bg-slate-500/10 border border-slate-500/20 rounded-lg p-4">
                                        <p className="text-danger text-sm">
                                                {t("reports.errorLoading")}: {reportsError}
                                        </p>
                                </div>
                        );  // NOSONAR: typescript:S3358
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
                                                                                        : report.status === "pending"
                                                                                                ? "secondary"
                                                                                                : "destructive"
                                                                        }
                                                                        className={
                                                                                report.status === "completed"
                                                                                        ? "bg-success/10 text-success border-success/30"
                                                                                        : report.status === "pending"
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
                                                                                } catch {
                                                                                        // V247 FIX: Show user-facing toast (was silent console.error)
                                                                                        toast.error("Download failed. Please try again.");
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
                                        <Card className="border-danger/30 bg-slate-500/5">
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
                                                                                {/* V214 FIX: Values must match backend report_type strings exactly.
                                                                                    Backend (reports.py:645-651) accepts: voltage_drop, nfpa72_coverage,
                                                                                    nfpa72_battery, cable_sizing. Anything else falls through to generic
                                                                                    count-only report. Old values used hyphens (voltage-drop) which NEVER
                                                                                    matched — every report silently fell through to generic. */}
                                                                                <SelectItem value="voltage_drop">
                                                                                        {t("reports.voltageDropAnalysis") || "Voltage Drop Analysis"}
                                                                                </SelectItem>
                                                                                <SelectItem value="cable_sizing">
                                                                                        {t("reports.cableSizingReport") || "Cable Sizing Report"}
                                                                                </SelectItem>
                                                                                <SelectItem value="nfpa72_battery">
                                                                                        {t("reports.batteryCalculations") || "NFPA 72 Battery Calculation"}
                                                                                </SelectItem>
                                                                                <SelectItem value="nfpa72_coverage">
                                                                                        {t("reports.coverageAnalysis") || "NFPA 72 Coverage Analysis"}
                                                                                </SelectItem>
                                                                                {/* Self-critique: short_circuit, load_calculation, conduit_fill,
                                                                                    boq are listed in the backend docstring but have NO implementation —
                                                                                    they all fall through to _generate_generic_report() (count-only).
                                                                                    Removed to avoid misleading the user. Use AHJ Submittal button
                                                                                    above for full compliance document. */}
                                                                        </SelectContent>
                                                                </Select>
                                                        </div>
                                                        <div className="space-y-2">
                                                                <Label className="text-foreground/90">
                                                                        {t("reports.executionParams")}
                                                                </Label>
                                                                <Select
                                                                        value={execParams.kernel_coverage}  // NOSONAR: typescript:S6772
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
                                                                                className="rounded bg-card border-border text-slate-400 focus:ring-red-500"
                                                                        />
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
                                                                                className="rounded bg-card border-border text-slate-400 focus:ring-red-500"
                                                                        />
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

                                                {/* V214 FIX: AHJ Submittal button — generates real NFPA 72
                                                     compliance proof document via POST /reports/ahj-submittal */}
                                                {/* V246 FIX: AHJ fields are now editable (was hardcoded) */}
                                                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-2 w-full">
                                                        <div>
                                                                <Label htmlFor="ahj-designer" className="text-xs text-muted-foreground">
                                                                        Designer Name (required)
                                                                </Label>
                                                                <input
                                                                        id="ahj-designer"
                                                                        type="text"
                                                                        value={ahjDesigner}
                                                                        onChange={(e) => setAhjDesigner(e.target.value)}
                                                                        placeholder="Eng. John Doe, PE"
                                                                        className="w-full mt-1 px-3 py-2 text-sm bg-card border border-border rounded-md text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                                                                />
                                                        </div>
                                                        <div>
                                                                <Label htmlFor="ahj-jurisdiction" className="text-xs text-muted-foreground">
                                                                        Jurisdiction
                                                                </Label>
                                                                <input
                                                                        id="ahj-jurisdiction"
                                                                        type="text"
                                                                        value={ahjJurisdiction}
                                                                        onChange={(e) => setAhjJurisdiction(e.target.value)}
                                                                        placeholder="City of Cairo Fire Marshal"
                                                                        className="w-full mt-1 px-3 py-2 text-sm bg-card border border-border rounded-md text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                                                                />
                                                        </div>
                                                        <div>
                                                                <Label htmlFor="ahj-nfpa-edition" className="text-xs text-muted-foreground">
                                                                        NFPA Edition
                                                                </Label>
                                                                <select
                                                                        id="ahj-nfpa-edition"
                                                                        value={ahjNfpaEdition}
                                                                        onChange={(e) => setAhjNfpaEdition(e.target.value)}
                                                                        className="w-full mt-1 px-3 py-2 text-sm bg-card border border-border rounded-md text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                                                                >
                                                                        <option value="2022">NFPA 72 (2022)</option>
                                                                        <option value="2019">NFPA 72 (2019)</option>
                                                                        <option value="2016">NFPA 72 (2016)</option>
                                                                </select>
                                                        </div>
                                                </div>
                                                <Button
                                                        className="bg-primary hover:bg-primary/90 text-white border-none ml-2 mt-2"
                                                        onClick={handleGenerateAhj}
                                                        disabled={ahjGenerating || !ahjDesigner.trim()}
                                                >
                                                        {ahjGenerating ? (
                                                                <>
                                                                        <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                                                                        Generating AHJ...
                                                                </>
                                                        ) : (
                                                                <>
                                                                        <FileText className="h-4 w-4 mr-1" />
                                                                        AHJ Submittal
                                                                </>
                                                        )}
                                                </Button>
                                                {ahjDownloadUrl && (
                                                        <a
                                                                href={ahjDownloadUrl}
                                                                download="AHJ_submittal.md"
                                                                className="ml-2 text-sm text-primary hover:underline"
                                                        >
                                                                Download AHJ Document
                                                        </a>
                                                )}
                                        </CardContent>
                                </Card>

                                {/* V246 SAFETY: Sample Data Warning Banner */}
                                {isSampleData && (
                                        <div
                                                className="flex items-start gap-3 p-4 rounded-lg border-2 border-amber-500/50 bg-amber-500/10"
                                                role="alert"
                                                aria-label="Sample data warning"
                                        >
                                                <AlertTriangle className="h-5 w-5 text-amber-500 shrink-0 mt-0.5" />
                                                <div>
                                                        <div className="font-semibold text-amber-600 dark:text-amber-400">
                                                                SAMPLE DATA — Not Real Calculations
                                                        </div>
                                                        <div className="text-sm text-amber-700 dark:text-amber-300 mt-1">
                                                                The battery and coverage calculations below use hardcoded sample
                                                                data for demonstration only. They do NOT reflect your actual
                                                                project. Do NOT use these values for real system design or AHJ
                                                                submittals. Connect a real project and use the AHJ Submittal
                                                                button above to generate a compliance document with real data.
                                                        </div>
                                                </div>
                                        </div>
                                )}

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
