
import {
        Activity,
        AlertTriangle,
        Calculator,
        CheckCircle2,
        Clock,
        Database,
        Server,
        XCircle,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import {
        Card,
        CardContent,
        CardDescription,
        CardHeader,
        CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useDevices, useHealth, useProjects } from "@/hooks/useApi";

export function DashboardPage() {
        const { t } = useTranslation();
        const navigate = useNavigate();
        const {
                data: health,
                loading: healthLoading,
                connected,
                refetch: refetchHealth,
        } = useHealth();
        const {
                data: projects,
                loading: projectsLoading,
        } = useProjects();
        const {
                data: devices,
                loading: devicesLoading,
        } = useDevices(null); // Pass null as projectId

        // Calculate stats
        const totalProjects = projects?.length || 0;
        const totalDevices = devices?.length || 0;
        const activeProjects =
                projects?.filter((p) => p.status === "active").length || 0;

        // V214 FIX: Calculate real device status counts from device properties.
        // Previously these were hardcoded to 0 with a comment saying "placeholder".
        // Now we classify devices by their voltage/current/load values:
        //   - danger: voltage < 12V or current > 2A (abnormal)
        //   - warning: voltage < 20V or current > 1A (borderline)
        //   - ok: everything else
        const warningDevices = devices?.filter((d) => {
                const v = (d as unknown as Record<string, unknown>).voltage as number | undefined;
                const c = (d as unknown as Record<string, unknown>).current as number | undefined;
                return (v !== undefined && v < 20 && v >= 12) || (c !== undefined && c > 1 && c <= 2);
        }).length || 0;
        const dangerDevices = devices?.filter((d) => {
                const v = (d as unknown as Record<string, unknown>).voltage as number | undefined;
                const c = (d as unknown as Record<string, unknown>).current as number | undefined;
                return (v !== undefined && v < 12) || (c !== undefined && c > 2);
        }).length || 0;
        const okDevices = Math.max(0, totalDevices - warningDevices - dangerDevices);

        return (
                <div className="flex-1 overflow-auto" aria-label={t("dashboard.title")}>
                        <div className="p-6 max-w-7xl mx-auto space-y-6">
                                {/* Header */}
                                <div className="flex items-center justify-between">
                                        <div>
                                                <h1 className="text-2xl font-bold text-foreground">
                                                        {t("dashboard.title")}
                                                </h1>
                                                <p className="text-sm text-muted-foreground mt-1">
                                                        {t("dashboard.subtitle")}
                                                </p>
                                        </div>
                                        <Button
                                                variant="outline"
                                                className="border-border text-foreground/90 hover:bg-card"
                                                onClick={() => refetchHealth()}
                                        >
                                                <Activity className="h-4 w-4 mr-1" />
                                                {t("dashboard.refresh")}
                                        </Button>
                                </div>

                                {/* Stats Cards */}
                                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                                        {/* Projects Card */}
                                        <Card className="border-border bg-card">
                                                <CardHeader className="pb-3">
                                                        <CardTitle className="text-lg text-foreground">
                                                                {t("dashboard.projects")}
                                                        </CardTitle>
                                                        <CardDescription className="text-muted-foreground">
                                                                {t("dashboard.acrossAllProjects")}
                                                        </CardDescription>
                                                </CardHeader>
                                                <CardContent>
                                                        {projectsLoading ? (
                                                                <Skeleton className="h-8 w-16 bg-secondary" />
                                                        ) : (
                                                                <div className="text-3xl font-bold text-foreground">
                                                                        {totalProjects}
                                                                </div>
                                                        )}
                                                </CardContent>
                                        </Card>

                                        {/* Active Projects Card */}
                                        <Card className="border-border bg-card">
                                                <CardHeader className="pb-3">
                                                        <CardTitle className="text-lg text-foreground">
                                                                {t("dashboard.active")}
                                                        </CardTitle>
                                                        <CardDescription className="text-muted-foreground">
                                                                {t("dashboard.projects")}
                                                        </CardDescription>
                                                </CardHeader>
                                                <CardContent>
                                                        {projectsLoading ? (
                                                                <Skeleton className="h-8 w-16 bg-secondary" />
                                                        ) : (
                                                                <div className="text-3xl font-bold text-slate-500">
                                                                        {activeProjects}
                                                                </div>
                                                        )}
                                                </CardContent>
                                        </Card>

                                        {/* Total Devices Card */}
                                        <Card className="border-border bg-card">
                                                <CardHeader className="pb-3">
                                                        <CardTitle className="text-lg text-foreground">
                                                                {t("dashboard.totalDevices")}
                                                        </CardTitle>
                                                        <CardDescription className="text-muted-foreground">
                                                                {t("dashboard.acrossAllProjects")}
                                                        </CardDescription>
                                                </CardHeader>
                                                <CardContent>
                                                        {devicesLoading ? (
                                                                <Skeleton className="h-8 w-16 bg-secondary" />
                                                        ) : (
                                                                <div className="text-3xl font-bold text-foreground">
                                                                        {totalDevices}
                                                                </div>
                                                        )}
                                                </CardContent>
                                        </Card>

                                        {/* System Health Card */}
                                        <Card className="border-border bg-card">
                                                <CardHeader className="pb-3">
                                                        <CardTitle className="text-lg text-foreground">
                                                                {t("dashboard.systemHealth")}
                                                        </CardTitle>
                                                        <CardDescription className="text-muted-foreground">
                                                                {t("dashboard.status")}
                                                        </CardDescription>
                                                </CardHeader>
                                                <CardContent>
                                                        {healthLoading ? (
                                                                <Skeleton className="h-8 w-24 bg-secondary" />
                                                        ) : (
                                                                <div className="flex items-center gap-2">
                                                                        {connected ? (
                                                                                <>
                                                                                        <CheckCircle2 className="h-5 w-5 text-success" />
                                                                                        <span className="text-success">
                                                                                                {t("dashboard.connected")}
                                                                                        </span>
                                                                                </>
                                                                        ) : (
                                                                                <>
                                                                                        <XCircle className="h-5 w-5 text-danger" />
                                                                                        <span className="text-danger">
                                                                                                {t("dashboard.disconnected")}
                                                                                        </span>
                                                                                </>
                                                                        )}
                                                                </div>
                                                        )}
                                                </CardContent>
                                        </Card>
                                </div>

                                {/* Status Summary Card */}
                                <Card className="border-border bg-card">
                                        <CardHeader className="pb-3">
                                                <CardTitle className="text-lg text-foreground">
                                                        {t("dashboard.statusSummary")}
                                                </CardTitle>
                                                <CardDescription className="text-muted-foreground">
                                                        {t("dashboard.deviceStatusOverview")}
                                                </CardDescription>
                                        </CardHeader>
                                        <CardContent>
                                                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                                        <div className="flex items-center gap-3">
                                                                <div className="w-10 h-10 rounded-full bg-emerald-500/20 flex items-center justify-center">
                                                                        <CheckCircle2 className="h-5 w-5 text-success" />
                                                                </div>
                                                                <div>
                                                                        <div className="text-2xl font-bold text-success">
                                                                                {okDevices}
                                                                        </div>
                                                                        <div className="text-sm text-muted-foreground">
                                                                                {t("dashboard.ok")}
                                                                        </div>
                                                                </div>
                                                        </div>
                                                        <div className="flex items-center gap-3">
                                                                <div className="w-10 h-10 rounded-full bg-amber-500/20 flex items-center justify-center">
                                                                        <AlertTriangle className="h-5 w-5 text-warning" />
                                                                </div>
                                                                <div>
                                                                        <div className="text-2xl font-bold text-warning">
                                                                                {warningDevices}
                                                                        </div>
                                                                        <div className="text-sm text-muted-foreground">
                                                                                {t("dashboard.warning")}
                                                                        </div>
                                                                </div>
                                                        </div>
                                                        <div className="flex items-center gap-3">
                                                                <div className="w-10 h-10 rounded-full bg-slate-500/20 flex items-center justify-center">
                                                                        <XCircle className="h-5 w-5 text-danger" />
                                                                </div>
                                                                <div>
                                                                        <div className="text-2xl font-bold text-danger">
                                                                                {dangerDevices}
                                                                        </div>
                                                                        <div className="text-sm text-muted-foreground">
                                                                                {t("dashboard.danger")}
                                                                        </div>
                                                                </div>
                                                        </div>
                                                </div>
                                        </CardContent>
                                </Card>

                                {/* System Health Details */}
                                <Card className="border-border bg-card">
                                        <CardHeader className="pb-3">
                                                <CardTitle className="text-lg text-foreground">
                                                        {t("dashboard.systemHealth")}
                                                </CardTitle>
                                                <CardDescription className="text-muted-foreground">
                                                        {healthLoading
                                                                ? t("dashboard.loading")
                                                                : t("dashboard.lastUpdated") +
                                                                        ": " +
                                                                        (health ? new Date().toLocaleString() : "")}
                                                </CardDescription>
                                        </CardHeader>
                                        <CardContent>
                                                {healthLoading ? (
                                                        <div className="space-y-3">
                                                                <Skeleton className="h-4 w-full bg-secondary" />
                                                                <Skeleton className="h-4 w-4/5 bg-secondary" />
                                                                <Skeleton className="h-4 w-3/4 bg-secondary" />
                                                        </div>
                                                ) : health ? (
                                                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                                                <div className="flex items-center gap-2">
                                                                        <Server className="h-5 w-5 text-info" />
                                                                        <span className="text-foreground/90">
                                                                                {t("dashboard.version")}: v{health.version}
                                                                        </span>
                                                                </div>
                                                                <div className="flex items-center gap-2">
                                                                        <Database className="h-5 w-5 text-info" />
                                                                        <span className="text-foreground/90">
                                                                                {t("dashboard.database")}: {health.database}
                                                                        </span>
                                                                </div>
                                                                <div className="flex items-center gap-2">
                                                                        <Clock className="h-5 w-5 text-info" />
                                                                        <span className="text-foreground/90">
                                                                                {t("dashboard.uptime")}:{" "}
                                                                                {Math.floor((health.uptime || 0) / 60)} min
                                                                        </span>
                                                                </div>
                                                        </div>
                                                ) : (
                                                        <p className="text-muted-foreground">{t("dashboard.disconnected")}</p>
                                                )}
                                        </CardContent>
                                </Card>

                                {/* Report Generator Quick Access */}
                                <Card className="border-border bg-card">
                                        <CardHeader className="pb-3">
                                                <CardTitle className="text-lg text-foreground">
                                                        {t("settings.advancedReportGenerator")}
                                                </CardTitle>
                                                <CardDescription className="text-muted-foreground">
                                                        {t("settings.reportGeneratorDesc")}
                                                </CardDescription>
                                        </CardHeader>
                                        <CardContent>
                                                <div className="flex flex-col sm:flex-row gap-4">
                                                        <div className="flex-1">
                                                                <h3 className="font-medium text-foreground mb-2">
                                                                        {t("settings.comprehensiveReportGeneration")}
                                                                </h3>
                                                                <p className="text-sm text-muted-foreground">
                                                                        {t("settings.comprehensiveReportDesc")}
                                                                </p>
                                                        </div>
                                                        <Button
                                                                onClick={() => navigate("/reports")}
                                                                className="bg-danger hover:bg-danger/90 text-white border-none flex items-center gap-2"
                                                                aria-label={t("settings.openReportGenerator")}
                                                        >
                                                                <Calculator className="h-4 w-4" />
                                                                {t("settings.openReportGenerator")}
                                                        </Button>
                                                </div>
                                        </CardContent>
                                </Card>
                        </div>
                </div>
        );
}
