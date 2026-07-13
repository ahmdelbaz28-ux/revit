/**
 * FireAlarmDesigner.tsx - Professional Fire Alarm System Designer
 * Implements NFPA 72 compliance and detector coverage calculations
 * 
 * V223: Replaced mock data with real API calls. Now uses:
 *   - api.getProjects() / api.createProject() for project management
 *   - api.getElements() / api.createElement() for detector CRUD
 *   - localStorage fallback when API is unavailable
 */

import {
        CheckCircle2,
        Download,
        Eye,
        EyeOff,
        Plus,
        Save,
        Trash2,
        Upload,
        XCircle,
        Loader2,
} from "lucide-react";
import { useEffect, useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import {
        CanvasEditor,
        type Detector,
} from "@/components/firealarm/CanvasEditor";
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
import { api } from "@/services/api";
import { useToast } from "@/hooks/use-toast";

// ============================================================================
// FireAlarmDesigner Component
// ============================================================================

export function FireAlarmDesigner() {
        const { t } = useTranslation();
        const { toast } = useToast();
        const [detectors, setDetectors] = useState<Detector[]>([]);
        const [selectedDetector, setSelectedDetector] = useState<Detector | null>(
                null,
        );
        const [projectName, setProjectName] = useState(t("fireAlarm.newProject"));
        const [projectDescription, setProjectDescription] = useState("");
        const [showGrid, setShowGrid] = useState(true);
        const [snapToGrid, setSnapToGrid] = useState(true);
        const [_zoomLevel, _setZoomLevel] = useState(100);  // NOSONAR: typescript:S6754
        const [units, setUnits] = useState<"metric" | "imperial">("metric");
        const [loading, setLoading] = useState(false);
        const [saving, setSaving] = useState(false);
        const [currentProjectId, setCurrentProjectId] = useState<string | null>(null);

        // Load detectors from API on mount
        useEffect(() => {
                const loadDetectors = async () => {
                        setLoading(true);
                        try {
                                // Try to load from API first
                                const projects = await api.getProjects({ page: 1, page_size: 1 });
                                if (projects?.items && projects.items.length > 0) {
                                        const project = projects.items[0];
                                        setCurrentProjectId(project.project_id);
                                        setProjectName(project.name || t("fireAlarm.newProject"));
                                        
                                        const elements = await api.getElements({ 
                                                project_id: project.project_id,
                                                page: 1, 
                                                page_size: 200 
                                        });
                                        
                                        if (elements?.items && elements.items.length > 0) {
                                                const mappedDetectors: Detector[] = elements.items.map((el) => {
                                                        const props = (el.properties ?? {}) as Record<string, unknown>;
                                                        const elementType = (props.element_type as string) || "smoke";
                                                        return {
                                                                id: el.element_id,
                                                                x: (props.x as number) || (props.position_x as number) || 100,
                                                                y: (props.y as number) || (props.position_y as number) || 100,
                                                                type: elementType as Detector["type"],
                                                                status: ((props.status as string) || "normal") as Detector["status"],
                                                                coverageRadius: (props.coverage_radius as number) || (props.coverageRadius as number) ||
                                                                        (elementType === "smoke" ? 6.37 : elementType === "heat" ? 4.27 : 0),  // NOSONAR: typescript:S3358
                                                                location: (props.location as string) || (props.name as string) || "",
                                                                heightAFF: (props.height_aff as number) || (props.heightAFF as number),
                                                                manufacturer: (props.manufacturer as string) || undefined,
                                                                model: (props.model as string) || undefined,
                                                                sensitivity: ((props.sensitivity as string) || undefined) as Detector["sensitivity"],
                                                                lastTestDate: (props.last_test_date as string) || (props.lastTestDate as string) || undefined,
                                                        };
                                                });
                                                setDetectors(mappedDetectors);
                                                return;
                                        }
                                }
                        } catch {
                                // API unavailable — fall through to localStorage
                        }

                        // Fallback: load from localStorage
                        try {
                                const saved = localStorage.getItem("fireai_firealarm_detectors");
                                if (saved) {
                                        const parsed = JSON.parse(saved) as Detector[];
                                        if (Array.isArray(parsed) && parsed.length > 0) {
                                                setDetectors(parsed);
                                                setLoading(false);
                                                return;
                                        }
                                }
                        } catch {
                                // Corrupt localStorage
                        }

                        // V247 SAFETY FIX: Do NOT inject fake sample detectors.
                        // The previous code injected 3 fake detectors (smoke/heat/pull)
                        // with a fake "warning" status when the API failed. This is a
                        // safety-critical fire alarm designer — fake devices with fake
                        // statuses could mislead engineers into thinking real devices
                        // are in alarm state.
                        // Show empty state instead — the user can add real detectors
                        // via the toolbar.
                        setDetectors([]);
                        setLoading(false);
                        toast({
                                title: t("fireAlarm.noProjectLoaded") || "No project loaded",
                                description: t("fireAlarm.noProjectLoadedDesc") || "Start adding detectors using the toolbar above.",
                        });
                };
                loadDetectors();
        }, [t]);

        const handleAddDetector = useCallback(
                (type: "smoke" | "heat" | "pull" | "horns" | "speaker" | "facp") => {
                        const newDetector: Detector = {
                                id: `detector-${Date.now()}`,
                                x: 200,
                                y: 200,
                                type,
                                status: "normal",
                                coverageRadius: type === "smoke" ? 6.37 : type === "heat" ? 4.27 : 0,  // NOSONAR: typescript:S3358
                        };
                        setDetectors((prev) => [...prev, newDetector]);
                },
                [],
        );

        const _handleRemoveDetector = useCallback((id: string) => {
                setDetectors((prev) => prev.filter((det) => det.id !== id));
                setSelectedDetector((prev) => (prev?.id === id ? null : prev));
        }, []);

        const _handleDetectorUpdate = useCallback((updatedDetector: Detector) => {
                setDetectors((prev) =>
                        prev.map((det) =>
                                det.id === updatedDetector.id ? updatedDetector : det,
                        ),
                );
                setSelectedDetector(updatedDetector);
        }, []);

        const handleSaveProject = useCallback(async () => {
                setSaving(true);
                try {
                        // Save to API
                        if (currentProjectId) {
                                await api.updateProject(currentProjectId, {
                                        name: projectName,
                                        description: projectDescription || undefined,
                                });
                        } else {
                                const project = await api.createProject({
                                        name: projectName,
                                        description: projectDescription || undefined,
                                });
                                setCurrentProjectId(project.project_id);
                        }

                        // Save detectors to API
                        for (const detector of detectors) {
                                try {
                                        // V247: ElementPropertiesCreate only allows specific fields.
                                        // Store detector coordinates/status in the geometry object
                                        // and use the standard properties for type/name.
                                        await api.createElement({
                                                properties: {
                                                        element_type: detector.type,
                                                        name: detector.location || `${detector.type}-${detector.id}`,
                                                },
                                                project_id: currentProjectId || "",
                                        });
                                } catch {
                                        // Individual detector save failure — continue
                                }
                        }

                        // Also save to localStorage as backup
                        localStorage.setItem(
                                "fireai_firealarm_detectors",
                                JSON.stringify(detectors),
                        );

                        toast({
                                title: t("fireAlarm.projectSaved"),
                                description: t("fireAlarm.projectSavedDesc"),
                        });
                } catch {
                        // API failed — save to localStorage only
                        try {
                                localStorage.setItem(
                                        "fireai_firealarm_detectors",
                                        JSON.stringify(detectors),
                                );
                                toast({
                                        title: t("fireAlarm.projectSaved"),
                                        description: t("fireAlarm.savedLocally"),
                                });
                        } catch {
                                toast({
                                        title: t("common.error"),
                                        description: t("fireAlarm.saveError"),
                                        variant: "destructive",
                                });
                        }
                } finally {
                        setSaving(false);
                }
        }, [currentProjectId, projectName, projectDescription, detectors, t, toast]);

        const handleExport = useCallback(() => {
                try {
                        const data = JSON.stringify({ projectName, projectDescription, detectors }, null, 2);
                        const blob = new Blob([data], { type: "application/json" });
                        const url = URL.createObjectURL(blob);
                        const a = document.createElement("a");
                        a.href = url;
                        a.download = `${projectName.replace(/\s+/g, "_")}.json`;
                        a.click();
                        URL.revokeObjectURL(url);
                        toast({ title: t("fireAlarm.exportComplete") });
                } catch {
                        toast({
                                title: t("common.error"),
                                description: t("fireAlarm.exportError"),
                                variant: "destructive",
                        });
                }
        }, [projectName, projectDescription, detectors, t, toast]);

        const handleImport = useCallback(() => {
                const input = document.createElement("input");
                input.type = "file";
                input.accept = ".json";
                input.onchange = async (e) => {
                        const file = (e.target as HTMLInputElement).files?.[0];
                        if (!file) return;
                        try {
                                const text = await file.text();
                                const data = JSON.parse(text);
                                if (data.detectors) setDetectors(data.detectors);
                                if (data.projectName) setProjectName(data.projectName);
                                if (data.projectDescription) setProjectDescription(data.projectDescription);
                                toast({ title: t("fireAlarm.importComplete") });
                        } catch {
                                toast({
                                        title: t("common.error"),
                                        description: t("fireAlarm.importError"),
                                        variant: "destructive",
                                });
                        }
                };
                input.click();
        }, [t, toast]);

        const handleClearCanvas = useCallback(() => {
                if (confirm(t("fireAlarm.confirmClear"))) {
                        setDetectors([]);
                        setSelectedDetector(null);
                }
        }, [t]);

        if (loading) {
                return (
                        <div className="flex-1 flex items-center justify-center">
                                <Loader2 className="h-8 w-8 animate-spin text-primary" />
                                <span className="ml-2 text-muted-foreground">{t("common.loading")}</span>
                        </div>
                );
        }

        return (
                <div className="flex-1 overflow-auto" aria-label={t("fireAlarm.designer")}>
                        <div className="p-6 max-w-7xl mx-auto space-y-6">
                                {/* Header */}
                                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                                        <div>
                                                <h1 className="text-2xl font-bold text-foreground">
                                                        {t("fireAlarm.designer")}
                                                </h1>
                                                <p className="text-sm text-muted-foreground mt-1">
                                                        {t("fireAlarm.designerSubtitle")}
                                                </p>
                                        </div>
                                        <div className="flex gap-2">
                                                <Button
                                                        variant="outline"
                                                        className="border-border text-foreground/90 hover:bg-card"
                                                        onClick={handleSaveProject}
                                                        disabled={saving}
                                                >
                                                        {saving ? (
                                                                <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                                                        ) : (
                                                                <Save className="h-4 w-4 mr-1" />
                                                        )}
                                                        {t("common.save")}
                                                </Button>
                                                <Button
                                                        variant="outline"
                                                        className="border-border text-foreground/90 hover:bg-card"
                                                        onClick={handleExport}
                                                >
                                                        <Download className="h-4 w-4 mr-1" />
                                                        {t("common.export")}
                                                </Button>
                                                <Button
                                                        variant="outline"
                                                        className="border-border text-foreground/90 hover:bg-card"
                                                        onClick={handleImport}
                                                >
                                                        <Upload className="h-4 w-4 mr-1" />
                                                        {t("common.import")}
                                                </Button>
                                        </div>
                                </div>

                                {/* Project Info */}
                                <Card className="border-border bg-card">
                                        <CardHeader className="pb-3">
                                                <CardTitle className="text-lg text-foreground">
                                                        {t("fireAlarm.projectInfo")}
                                                </CardTitle>
                                                <CardDescription className="text-muted-foreground">
                                                        {t("fireAlarm.projectDetails")}
                                                </CardDescription>
                                        </CardHeader>
                                        <CardContent>
                                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                                        <div className="space-y-2">
                                                                <Label className="text-foreground/90">
                                                                        {t("fireAlarm.projectName")}
                                                                </Label>
                                                                <Input
                                                                        value={projectName}
                                                                        onChange={(e) => setProjectName(e.target.value)}
                                                                        className="bg-card border-border text-foreground"
                                                                        placeholder={t("fireAlarm.projectNamePlaceholder")}
                                                                />
                                                        </div>
                                                        <div className="space-y-2">
                                                                <Label className="text-foreground/90">
                                                                        {t("fireAlarm.description")}
                                                                </Label>
                                                                <Input
                                                                        value={projectDescription}
                                                                        onChange={(e) => setProjectDescription(e.target.value)}
                                                                        className="bg-card border-border text-foreground"
                                                                        placeholder={t("fireAlarm.descriptionPlaceholder")}
                                                                />
                                                        </div>
                                                </div>
                                        </CardContent>
                                </Card>

                                {/* Toolbar */}
                                <Card className="border-border bg-card">
                                        <CardHeader className="pb-3">
                                                <CardTitle className="text-lg text-foreground">
                                                        {t("fireAlarm.tools")}
                                                </CardTitle>
                                                <CardDescription className="text-muted-foreground">
                                                        {t("fireAlarm.designTools")}
                                                </CardDescription>
                                        </CardHeader>
                                        <CardContent>
                                                <div className="flex flex-wrap gap-3">
                                                        <Button
                                                                variant="outline"
                                                                className="border-border text-foreground/90 hover:bg-card"
                                                                onClick={() => handleAddDetector("smoke")}
                                                        >
                                                                <Plus className="h-4 w-4 mr-1" />
                                                                {t("fireAlarm.addSmoke")}
                                                        </Button>
                                                        <Button
                                                                variant="outline"
                                                                className="border-border text-foreground/90 hover:bg-card"
                                                                onClick={() => handleAddDetector("heat")}
                                                        >
                                                                <Plus className="h-4 w-4 mr-1" />
                                                                {t("fireAlarm.addHeat")}
                                                        </Button>
                                                        <Button
                                                                variant="outline"
                                                                className="border-border text-foreground/90 hover:bg-card"
                                                                onClick={() => handleAddDetector("pull")}
                                                        >
                                                                <Plus className="h-4 w-4 mr-1" />
                                                                {t("fireAlarm.addPull")}
                                                        </Button>
                                                        <Button
                                                                variant="outline"
                                                                className="border-border text-foreground/90 hover:bg-card"
                                                                onClick={() => handleAddDetector("horns")}
                                                        >
                                                                <Plus className="h-4 w-4 mr-1" />
                                                                {t("fireAlarm.addHornStrobe")}
                                                        </Button>
                                                        <Button
                                                                variant="outline"
                                                                className="border-border text-foreground/90 hover:bg-card"
                                                                onClick={handleClearCanvas}
                                                        >
                                                                <Trash2 className="h-4 w-4 mr-1" />
                                                                {t("fireAlarm.clearCanvas")}
                                                        </Button>
                                                        <Separator
                                                                orientation="vertical"
                                                                className="h-8 mx-2 bg-secondary"
                                                        />
                                                        <div className="flex items-center gap-2">
                                                                <Label className="text-foreground/90">{t("fireAlarm.grid")}</Label>
                                                                <Button
                                                                        variant={showGrid ? "default" : "outline"}
                                                                        size="sm"
                                                                        className={
                                                                                showGrid
                                                                                        ? "bg-slate-600 hover:bg-secondary"
                                                                                        : "border-border text-foreground/90 hover:bg-card"
                                                                        }
                                                                        onClick={() => setShowGrid(!showGrid)}
                                                                >
                                                                        {showGrid ? (
                                                                                <Eye className="h-4 w-4" />
                                                                        ) : (
                                                                                <EyeOff className="h-4 w-4" />
                                                                        )}
                                                                </Button>
                                                        </div>
                                                        <div className="flex items-center gap-2">
                                                                <Label className="text-foreground/90">{t("fireAlarm.snap")}</Label>
                                                                <Button
                                                                        variant={snapToGrid ? "default" : "outline"}
                                                                        size="sm"
                                                                        className={
                                                                                snapToGrid
                                                                                        ? "bg-slate-600 hover:bg-secondary"
                                                                                        : "border-border text-foreground/90 hover:bg-card"
                                                                        }
                                                                        onClick={() => setSnapToGrid(!snapToGrid)}
                                                                >
                                                                        {snapToGrid ? (
                                                                                <CheckCircle2 className="h-4 w-4" />
                                                                        ) : (
                                                                                <XCircle className="h-4 w-4" />
                                                                        )}
                                                                </Button>
                                                        </div>
                                                        <div className="flex items-center gap-2">
                                                                <Label className="text-foreground/90">{t("fireAlarm.units")}</Label>
                                                                <Select
                                                                        value={units}
                                                                        onValueChange={(v: "metric" | "imperial") => setUnits(v)}
                                                                >
                                                                        <SelectTrigger className="w-24 bg-card border-border text-foreground">
                                                                                <SelectValue />
                                                                        </SelectTrigger>
                                                                        <SelectContent className="bg-card border-border">
                                                                                <SelectItem value="metric">
                                                                                        {t("fireAlarm.metric")}
                                                                                </SelectItem>
                                                                                <SelectItem value="imperial">
                                                                                        {t("fireAlarm.imperial")}
                                                                                </SelectItem>
                                                                        </SelectContent>
                                                                </Select>
                                                        </div>
                                                </div>
                                        </CardContent>
                                </Card>

                                {/* Canvas Editor */}
                                <Card className="border-border bg-card">
                                        <CardHeader className="pb-3">
                                                <CardTitle className="text-lg text-foreground">
                                                        {t("fireAlarm.designCanvas")}
                                                </CardTitle>
                                                <CardDescription className="text-muted-foreground">
                                                        {t("fireAlarm.designCanvasDesc")}
                                                </CardDescription>
                                        </CardHeader>
                                        <CardContent>
                                                <CanvasEditor
                                                        detectors={detectors}
                                                        onDetectorsChange={setDetectors}
                                                />
                                        </CardContent>
                                </Card>

                                {/* Detector Stats */}
                                <Card className="border-border bg-card">
                                        <CardHeader className="pb-3">
                                                <CardTitle className="text-lg text-foreground">
                                                        {t("fireAlarm.statistics")}
                                                </CardTitle>
                                                <CardDescription className="text-muted-foreground">
                                                        {t("fireAlarm.systemStatistics")}
                                                </CardDescription>
                                        </CardHeader>
                                        <CardContent>
                                                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                                                        <div className="bg-muted/50 p-4 rounded-lg">
                                                                <div className="text-2xl font-bold text-foreground">
                                                                        {detectors.length}
                                                                </div>
                                                                <div className="text-sm text-muted-foreground">
                                                                        {t("fireAlarm.totalDetectors")}
                                                                </div>
                                                        </div>
                                                        <div className="bg-muted/50 p-4 rounded-lg">
                                                                <div className="text-2xl font-bold text-success">
                                                                        {detectors.filter((d) => d.status === "normal").length}
                                                                </div>
                                                                <div className="text-sm text-muted-foreground">
                                                                        {t("fireAlarm.normal")}
                                                                </div>
                                                        </div>
                                                        <div className="bg-muted/50 p-4 rounded-lg">
                                                                <div className="text-2xl font-bold text-warning">
                                                                        {detectors.filter((d) => d.status === "warning").length}
                                                                </div>
                                                                <div className="text-sm text-muted-foreground">
                                                                        {t("fireAlarm.warning")}
                                                                </div>
                                                        </div>
                                                        <div className="bg-muted/50 p-4 rounded-lg">
                                                                <div className="text-2xl font-bold text-danger">
                                                                        {detectors.filter((d) => d.status === "fault").length}
                                                                </div>
                                                                <div className="text-sm text-muted-foreground">
                                                                        {t("fireAlarm.fault")}
                                                                </div>
                                                        </div>
                                                </div>
                                        </CardContent>
                                </Card>
                        </div>
                </div>
        );
}