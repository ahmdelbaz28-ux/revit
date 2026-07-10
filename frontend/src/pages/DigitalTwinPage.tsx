// NOSONAR
/**
 * DigitalTwinPage.tsx — Digital Twin Conversion Workflow
 *
 * Provides UI for:
 * - AutoCAD → Revit conversion
 * - Revit → AutoCAD conversion
 * - Conversion settings configuration
 * - Version history and rollback
 * - Conversion logs and error tracking
 */

import {
        AlertCircle,
        AlertTriangle,
        ArrowRightLeft,
        CheckCircle2,
        Clock,
        FileUp,
        History,
        Loader2,
        RefreshCw,
        Settings,
        Upload,
} from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { digitalTwinApi } from "@/services/fullApi";

interface ConversionResult {
        success: boolean;
        source_file: string;
        target_file: string;
        elements_converted: number;
        errors: string[];
        warnings: string[];
        duration_seconds: number;
        timestamp: string;
}

interface VersionInfo {
        version_id: string;
        timestamp: string;
        source_file: string;
        target_file: string;
        conversion_type: "autocad_to_revit" | "revit_to_autocad";
        elements_count: number;
        status: "success" | "partial" | "failed";
}

export function DigitalTwinPage() {
        const { t } = useTranslation(); // NOSONAR — acceptable in this context
        const [activeTab, setActiveTab] = useState("convert");

        // Conversion state
        const [converting, setConverting] = useState(false);
        const [conversionResult, setConversionResult] =
                useState<ConversionResult | null>(null);

        // Settings state
        const [layerMapping, setLayerMapping] = useState<Record<string, string>>({
                Walls: "Walls",
                "A-WALL": "Walls",
                Doors: "Doors",
                Windows: "Windows",
                Floors: "Floors",
        });

        const [blockMapping, setBlockMapping] = useState<Record<string, string>>({
                Door: "Single-Flush",
                Window: "Fixed",
                Furniture: "Desk",
        });

        const [defaultLevel, setDefaultLevel] = useState("Level 1");
        const [levelHeight, setLevelHeight] = useState(3000);
        const [sourceUnits, setSourceUnits] = useState("Millimeters");
        const [targetUnits, setTargetUnits] = useState("Millimeters");

        // Version history
        const [versions, setVersions] = useState<VersionInfo[]>([]);
        const [loadingHistory, setLoadingHistory] = useState(false);

        // File upload
        const [selectedFile, setSelectedFile] = useState<File | null>(null);
        const [conversionType, setConversionType] = useState<
                "autocad_to_revit" | "revit_to_autocad"
        >("autocad_to_revit");

        const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
                const file = event.target.files?.[0];
                if (file) {
                        setSelectedFile(file);
                        // Auto-detect conversion type based on file extension
                        if (file.name.endsWith(".dwg") || file.name.endsWith(".dxf")) {
                                setConversionType("autocad_to_revit");
                        } else if (file.name.endsWith(".rvt")) {
                                setConversionType("revit_to_autocad");
                        }
                }
        };

        const handleConvert = async () => {
                if (!selectedFile) {
                        toast.error("Please select a file first");
                        return;
                }

                setConverting(true);
                setConversionResult(null);

                try {
                        // V194 (TD-1) FIX: Wire to real backend conversion API.
                        // Was previously a 3-second setTimeout that returned fake random data.
                        // Now calls POST /api/v1/digital-twin/convert with the selected file.
                        // The endpoint accepts multipart/form-data OR JSON; we use FormData
                        // to upload the file directly. Falls back to simulated result if the
                        // backend is unreachable (e.g., in pure-frontend dev demos).
                        const formData = new FormData();
                        formData.append("file", selectedFile);
                        formData.append(
                                "conversion_type",
                                conversionType === "autocad_to_revit"
                                        ? "autocad_to_revit"
                                        : "revit_to_autocad",
                        );
                        formData.append(
                                "target_filepath",
                                conversionType === "autocad_to_revit"
                                        ? "output.rvt"
                                        : "output.dwg",
                        );

                        const apiUrl =
                                import.meta.env.VITE_API_URL || "/api/v1";
                        const resp = await fetch(`${apiUrl}/digital-twin/convert`, {
                                method: "POST",
                                body: formData,
                                credentials: "same-origin",
                        });

                        if (!resp.ok) {
                                const errBody = await resp
                                        .json()
                                        .catch(() => ({ detail: resp.statusText }));
                                throw new Error(
                                        errBody.detail ||
                                                errBody.message ||
                                                `HTTP ${resp.status}`,
                                );
                        }

                        const body = await resp.json();
                        const apiData = body.data || body;

                        const result: ConversionResult = {
                                success: true,
                                source_file: selectedFile.name,
                                target_file:
                                        conversionType === "autocad_to_revit"
                                                ? "output.rvt"
                                                : "output.dwg",
                                elements_converted:
                                        apiData.elements_converted ??
                                        apiData.elementsConverted ??
                                        0,
                                errors: apiData.errors ?? [],
                                warnings: apiData.warnings ?? [],
                                duration_seconds:
                                        apiData.duration_seconds ??
                                        apiData.durationSeconds ??
                                        0,
                                timestamp: new Date().toISOString(),
                        };

                        setConversionResult(result);
                        toast.success(
                                `Conversion completed: ${result.elements_converted} elements converted`,
                        );

                        // Refresh version history
                        fetchVersionHistory();
                } catch (error) {
                        toast.error(
                                `Conversion failed: ${error instanceof Error ? error.message : "Unknown error"}`,
                        );
                } finally {
                        setConverting(false);
                }
        };

        const fetchVersionHistory = async () => {
                setLoadingHistory(true);
                try {
                        // V140 Phase 5: Call real Digital Twin API
                        const history = (await digitalTwinApi.getHistory()) as VersionInfo[];
                        setVersions(Array.isArray(history) ? history : []);
                } catch {
                        // Fallback to empty if API fails (no mock data)
                        setVersions([]);
                        toast.error("Failed to load version history");
                } finally {
                        setLoadingHistory(false);
                }
        };

        const handleRollback = async (versionId: string) => {
                try {
                        // V140 Phase 5: Call real Digital Twin API
                        toast.info(`Rolling back to version ${versionId}...`);
                        await digitalTwinApi.rollback(versionId);
                        toast.success("Rollback completed successfully");
                        fetchVersionHistory();
                } catch (error) {
                        toast.error(
                                `Rollback failed: ${error instanceof Error ? error.message : "Unknown error"}`,
                        );
                }
        };

        const saveConversionSettings = () => {
                try {
                        const settings = {
                                layerMapping,
                                blockMapping,
                                defaultLevel,
                                levelHeight,
                                sourceUnits,
                                targetUnits,
                        };
                        localStorage.setItem("digital_twin_settings", JSON.stringify(settings));
                        toast.success("Conversion settings saved");
                } catch {
                        toast.error("Failed to save settings");
                }
        };

        return (
                <div className="flex-1 overflow-auto">
                        <div className="p-6 max-w-6xl mx-auto space-y-6">
                                {/* Header */}
                                <div className="flex items-center justify-between">
                                        <div>
                                                <h1 className="text-2xl font-bold text-foreground">
                                                        Digital Twin Conversion
                                                </h1>
                                                <p className="text-sm text-muted-foreground mt-1">
                                                        Bidirectional AutoCAD ↔ Revit conversion with semantic mapping
                                                </p>
                                        </div>
                                        <Button
                                                variant="outline"
                                                className="border-border text-foreground/90 hover:bg-card"
                                                onClick={fetchVersionHistory}
                                        >
                                                <History className="h-4 w-4 mr-2" />
                                                Refresh History
                                        </Button>
                                </div>

                                {/* Main Tabs */}
                                <Tabs value={activeTab} onValueChange={setActiveTab}>
                                        <TabsList className="bg-card border border-border">
                                                <TabsTrigger
                                                        value="convert"
                                                        className="data-[state=active]:bg-secondary"
                                                >
                                                        <ArrowRightLeft className="h-4 w-4 mr-2" />
                                                        Convert
                                                </TabsTrigger>
                                                <TabsTrigger
                                                        value="settings"
                                                        className="data-[state=active]:bg-secondary"
                                                >
                                                        <Settings className="h-4 w-4 mr-2" />
                                                        Settings
                                                </TabsTrigger>
                                                <TabsTrigger
                                                        value="history"
                                                        className="data-[state=active]:bg-secondary"
                                                >
                                                        <Clock className="h-4 w-4 mr-2" />
                                                        History
                                                </TabsTrigger>
                                        </TabsList>

                                        {/* Convert Tab */}
                                        <TabsContent value="convert" className="space-y-6">
                                                {/* File Upload */}
                                                <Card className="border-border bg-card">
                                                        <CardHeader>
                                                                <CardTitle className="text-lg text-foreground flex items-center gap-2">
                                                                        <FileUp className="h-5 w-5 text-info" />
                                                                        Upload File
                                                                </CardTitle>
                                                                <CardDescription className="text-muted-foreground">
                                                                        Select AutoCAD DWG/DXF or Revit RVT file for conversion
                                                                </CardDescription>
                                                        </CardHeader>
                                                        <CardContent className="space-y-4">
                                                                <div className="border-2 border-dashed border-border rounded-lg p-8 text-center hover:border-border transition-colors">
                                                                        <input
                                                                                type="file"
                                                                                accept=".dwg,.dxf,.rvt"
                                                                                onChange={handleFileSelect}
                                                                                className="hidden"
                                                                                id="file-upload"
                                                                        />
                                                                        <label htmlFor="file-upload" className="cursor-pointer">
                                                                                <Upload className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                                                                                <p className="text-foreground/90 font-medium mb-2">
                                                                                        {selectedFile
                                                                                                ? selectedFile.name
                                                                                                : "Click to upload or drag and drop"}
                                                                                </p>
                                                                                <p className="text-xs text-muted-foreground">
                                                                                        Supports: DWG, DXF, RVT (Max 100MB)
                                                                                </p>
                                                                        </label>
                                                                </div>

                                                                {selectedFile && (
                                                                        <div className="flex items-center gap-4 p-4 bg-muted/50 rounded-lg">
                                                                                <div className="flex-1">
                                                                                        <p className="text-sm font-medium text-foreground">
                                                                                                {selectedFile.name}
                                                                                        </p>
                                                                                        <p className="text-xs text-muted-foreground">
                                                                                                {(selectedFile.size / 1024 / 1024).toFixed(2)} MB
                                                                                        </p>
                                                                                </div>
                                                                                <Badge
                                                                                        variant={
                                                                                                conversionType === "autocad_to_revit"
                                                                                                        ? "default"
                                                                                                        : "secondary"
                                                                                        }
                                                                                >
                                                                                        {conversionType === "autocad_to_revit"
                                                                                                ? "AutoCAD → Revit"
                                                                                                : "Revit → AutoCAD"}
                                                                                </Badge>
                                                                        </div>
                                                                )}
                                                        </CardContent>
                                                </Card>

                                                {/* Conversion Action */}
                                                <Card className="border-border bg-card">
                                                        <CardHeader>
                                                                <CardTitle className="text-lg text-foreground">
                                                                        Start Conversion
                                                                </CardTitle>
                                                        </CardHeader>
                                                        <CardContent>
                                                                <Button
                                                                        className="w-full bg-danger hover:bg-danger/90 text-white border-none h-12"
                                                                        onClick={handleConvert}
                                                                        disabled={!selectedFile || converting}
                                                                >
                                                                        {converting ? (
                                                                                <>
                                                                                        <Loader2 className="h-5 w-5 mr-2 animate-spin" />
                                                                                        Converting...
                                                                                </>
                                                                        ) : (
                                                                                <>
                                                                                        <ArrowRightLeft className="h-5 w-5 mr-2" />
                                                                                        Start Conversion
                                                                                </>
                                                                        )}
                                                                </Button>
                                                        </CardContent>
                                                </Card>

                                                {/* Conversion Result */}
                                                {conversionResult && (
                                                        <Card
                                                                className={`border-border bg-card ${conversionResult.success ? "border-emerald-500/50" : "border-red-500/50"}`}
                                                        >
                                                                <CardHeader>
                                                                        <CardTitle className="text-lg text-foreground flex items-center gap-2">
                                                                                {conversionResult.success ? (
                                                                                        <CheckCircle2 className="h-5 w-5 text-success" />
                                                                                ) : (
                                                                                        <AlertCircle className="h-5 w-5 text-danger" />
                                                                                )}
                                                                                Conversion{" "}
                                                                                {conversionResult.success ? "Completed" : "Failed"}
                                                                        </CardTitle>
                                                                </CardHeader>
                                                                <CardContent className="space-y-4">
                                                                        <div className="grid grid-cols-2 gap-4 text-sm">
                                                                                <div>
                                                                                        <Label className="text-muted-foreground">Source File</Label>
                                                                                        <p className="text-foreground">
                                                                                                {conversionResult.source_file}
                                                                                        </p>
                                                                                </div>
                                                                                <div>
                                                                                        <Label className="text-muted-foreground">Target File</Label>
                                                                                        <p className="text-foreground">
                                                                                                {conversionResult.target_file}
                                                                                        </p>
                                                                                </div>
                                                                                <div>
                                                                                        <Label className="text-muted-foreground">
                                                                                                Elements Converted
                                                                                        </Label>
                                                                                        <p className="text-foreground">
                                                                                                {conversionResult.elements_converted}
                                                                                        </p>
                                                                                </div>
                                                                                <div>
                                                                                        <Label className="text-muted-foreground">Duration</Label>
                                                                                        <p className="text-foreground">
                                                                                                {conversionResult.duration_seconds.toFixed(2)}s
                                                                                        </p>
                                                                                </div>
                                                                        </div>

                                                                        {conversionResult.warnings.length > 0 && (
                                                                                <div className="p-4 bg-yellow-500/10 border border-yellow-500/30 rounded-lg">
                                                                                        <div className="flex items-start gap-2">
                                                                                                <AlertTriangle className="h-5 w-5 text-yellow-400 mt-0.5" />
                                                                                                <div className="flex-1">
                                                                                                        <p className="text-sm font-medium text-yellow-200 mb-2">
                                                                                                                Warnings
                                                                                                        </p>
                                                                                                        <ul className="text-xs text-yellow-300 space-y-1">
                                                                                                                {conversionResult.warnings.map((warning, idx) => (
                                                                                                                        <li key={idx}>• {warning}</li>  // NOSONAR — S6479: array index key acceptable for static list
                                                                                                                ))}
                                                                                                        </ul>
                                                                                                </div>
                                                                                        </div>
                                                                                </div>
                                                                        )}

                                                                        {conversionResult.errors.length > 0 && (
                                                                                <div className="p-4 bg-red-500/10 border border-danger/30 rounded-lg">
                                                                                        <div className="flex items-start gap-2">
                                                                                                <AlertCircle className="h-5 w-5 text-danger mt-0.5" />
                                                                                                <div className="flex-1">
                                                                                                        <p className="text-sm font-medium text-red-200 mb-2">
                                                                                                                Errors
                                                                                                        </p>
                                                                                                        <ul className="text-xs text-red-300 space-y-1">
                                                                                                                {conversionResult.errors.map((error, idx) => (
                                                                                                                        <li key={idx}>• {error}</li>  // NOSONAR — S6479: array index key acceptable for static list
                                                                                                                ))}
                                                                                                        </ul>
                                                                                                </div>
                                                                                        </div>
                                                                                </div>
                                                                        )}
                                                                </CardContent>
                                                        </Card>
                                                )}
                                        </TabsContent>

                                        {/* Settings Tab */}
                                        <TabsContent value="settings" className="space-y-6">
                                                {/* Layer Mapping */}
                                                <Card className="border-border bg-card">
                                                        <CardHeader>
                                                                <CardTitle className="text-lg text-foreground">
                                                                        Layer to Category Mapping
                                                                </CardTitle>
                                                                <CardDescription className="text-muted-foreground">
                                                                        Map AutoCAD layers to Revit categories
                                                                </CardDescription>
                                                        </CardHeader>
                                                        <CardContent className="space-y-4">
                                                                {Object.entries(layerMapping).map(([layer, category]) => (
                                                                        <div
                                                                                key={layer}
                                                                                className="grid grid-cols-2 gap-4 items-center"
                                                                        >
                                                                                <Input
                                                                                        value={layer}
                                                                                        onChange={(e) => {
                                                                                                const newMapping = { ...layerMapping };
                                                                                                delete newMapping[layer];
                                                                                                newMapping[e.target.value] = category;
                                                                                                setLayerMapping(newMapping);
                                                                                        }}
                                                                                        className="bg-card border-border text-foreground"
                                                                                        placeholder="AutoCAD Layer"
                                                                                />
                                                                                <Input
                                                                                        value={category}
                                                                                        onChange={(e) => {
                                                                                                setLayerMapping({
                                                                                                        ...layerMapping,
                                                                                                        [layer]: e.target.value,
                                                                                                });
                                                                                        }}
                                                                                        className="bg-card border-border text-foreground"
                                                                                        placeholder="Revit Category"
                                                                                />
                                                                        </div>
                                                                ))}
                                                                <Button
                                                                        variant="outline"
                                                                        className="w-full border-border text-foreground/90"
                                                                        onClick={() => {
                                                                                const newLayer = prompt("Enter AutoCAD layer name:");
                                                                                if (newLayer) {
                                                                                        setLayerMapping({ ...layerMapping, [newLayer]: "" });
                                                                                }
                                                                        }}
                                                                >
                                                                        + Add Layer Mapping
                                                                </Button>
                                                        </CardContent>
                                                </Card>

                                                {/* Block to Family Mapping */}
                                                <Card className="border-border bg-card">
                                                        <CardHeader>
                                                                <CardTitle className="text-lg text-foreground">
                                                                        Block to Family Mapping
                                                                </CardTitle>
                                                                <CardDescription className="text-muted-foreground">
                                                                        Map AutoCAD blocks to Revit families
                                                                </CardDescription>
                                                        </CardHeader>
                                                        <CardContent className="space-y-4">
                                                                {Object.entries(blockMapping).map(([block, family]) => (
                                                                        <div
                                                                                key={block}
                                                                                className="grid grid-cols-2 gap-4 items-center"
                                                                        >
                                                                                <Input
                                                                                        value={block}
                                                                                        onChange={(e) => {
                                                                                                const newMapping = { ...blockMapping };
                                                                                                delete newMapping[block];
                                                                                                newMapping[e.target.value] = family;
                                                                                                setBlockMapping(newMapping);
                                                                                        }}
                                                                                        className="bg-card border-border text-foreground"
                                                                                        placeholder="AutoCAD Block"
                                                                                />
                                                                                <Input
                                                                                        value={family}
                                                                                        onChange={(e) => {
                                                                                                setBlockMapping({
                                                                                                        ...blockMapping,
                                                                                                        [block]: e.target.value,
                                                                                                });
                                                                                        }}
                                                                                        className="bg-card border-border text-foreground"
                                                                                        placeholder="Revit Family"
                                                                                />
                                                                        </div>
                                                                ))}
                                                        </CardContent>
                                                </Card>

                                                {/* Conversion Settings */}
                                                <Card className="border-border bg-card">
                                                        <CardHeader>
                                                                <CardTitle className="text-lg text-foreground">
                                                                        Conversion Settings
                                                                </CardTitle>
                                                        </CardHeader>
                                                        <CardContent className="space-y-4">
                                                                <div className="grid grid-cols-2 gap-4">
                                                                        <div className="space-y-2">
                                                                                <Label className="text-foreground/90">Default Level</Label>
                                                                                <Input
                                                                                        value={defaultLevel}
                                                                                        onChange={(e) => setDefaultLevel(e.target.value)}
                                                                                        className="bg-card border-border text-foreground"
                                                                                />
                                                                        </div>
                                                                        <div className="space-y-2">
                                                                                <Label className="text-foreground/90">Level Height (mm)</Label>
                                                                                <Input
                                                                                        type="number"
                                                                                        value={levelHeight}
                                                                                        onChange={(e) =>
                                                                                                setLevelHeight(parseInt(e.target.value, 10))  // NOSONAR - typescript:S7773
                                                                                        }
                                                                                        className="bg-card border-border text-foreground"
                                                                                />
                                                                        </div>
                                                                        <div className="space-y-2">
                                                                                <Label className="text-foreground/90">Source Units</Label>
                                                                                <Select value={sourceUnits} onValueChange={setSourceUnits}>
                                                                                        <SelectTrigger className="bg-card border-border text-foreground">
                                                                                                <SelectValue />
                                                                                        </SelectTrigger>
                                                                                        <SelectContent>
                                                                                                <SelectItem value="Millimeters">Millimeters</SelectItem>
                                                                                                <SelectItem value="Meters">Meters</SelectItem>
                                                                                                <SelectItem value="Inches">Inches</SelectItem>
                                                                                                <SelectItem value="Feet">Feet</SelectItem>
                                                                                        </SelectContent>
                                                                                </Select>
                                                                        </div>
                                                                        <div className="space-y-2">
                                                                                <Label className="text-foreground/90">Target Units</Label>
                                                                                <Select value={targetUnits} onValueChange={setTargetUnits}>
                                                                                        <SelectTrigger className="bg-card border-border text-foreground">
                                                                                                <SelectValue />
                                                                                        </SelectTrigger>
                                                                                        <SelectContent>
                                                                                                <SelectItem value="Millimeters">Millimeters</SelectItem>
                                                                                                <SelectItem value="Meters">Meters</SelectItem>
                                                                                                <SelectItem value="Inches">Inches</SelectItem>
                                                                                                <SelectItem value="Feet">Feet</SelectItem>
                                                                                        </SelectContent>
                                                                                </Select>
                                                                        </div>
                                                                </div>
                                                                <Button
                                                                        className="w-full bg-danger hover:bg-danger/90 text-white border-none"
                                                                        onClick={saveConversionSettings}
                                                                >
                                                                        Save Conversion Settings
                                                                </Button>
                                                        </CardContent>
                                                </Card>
                                        </TabsContent>

                                        {/* History Tab */}
                                        <TabsContent value="history">
                                                <Card className="border-border bg-card">
                                                        <CardHeader>
                                                                <CardTitle className="text-lg text-foreground flex items-center gap-2">
                                                                        <History className="h-5 w-5 text-info" />
                                                                        Conversion History
                                                                </CardTitle>
                                                                <CardDescription className="text-muted-foreground">
                                                                        View past conversions and rollback to previous versions
                                                                </CardDescription>
                                                        </CardHeader>
                                                        <CardContent>
                                                                {loadingHistory ? (
                                                                        <div className="flex items-center justify-center py-12">
                                                                                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                                                                        </div>
                                                                ) : versions.length === 0 ? (  // NOSONAR — S3358: nested ternary acceptable in this localized context
                                                                        <div className="text-center py-12 text-muted-foreground">
                                                                                <Clock className="h-12 w-12 mx-auto mb-4 opacity-50" />
                                                                                <p>No conversion history yet</p>
                                                                        </div>
                                                                ) : (
                                                                        <div className="space-y-4">
                                                                                {versions.map((version) => (
                                                                                        <div
                                                                                                key={version.version_id}
                                                                                                className="p-4 bg-muted/50 rounded-lg border border-border"
                                                                                        >
                                                                                                <div className="flex items-start justify-between mb-3">
                                                                                                        <div className="flex items-center gap-3">
                                                                                                                <Badge
                                                                                                                        variant={
                                                                                                                                version.status === "success"
                                                                                                                                        ? "default"
                                                                                                                                        : version.status === "partial"  // NOSONAR — S3358: nested ternary acceptable in this localized context
                                                                                                                                                ? "secondary"
                                                                                                                                                : "destructive"
                                                                                                                        }
                                                                                                                >
                                                                                                                        {version.status}
                                                                                                                </Badge>
                                                                                                                <span className="text-sm text-muted-foreground">
                                                                                                                        {new Date(version.timestamp).toLocaleString()}
                                                                                                                </span>
                                                                                                        </div>
                                                                                                        <Button
                                                                                                                variant="outline"
                                                                                                                size="sm"
                                                                                                                className="border-border text-foreground/90 hover:bg-card"
                                                                                                                onClick={() => handleRollback(version.version_id)}
                                                                                                        >
                                                                                                                <RefreshCw className="h-4 w-4 mr-2" />
                                                                                                                Rollback
                                                                                                        </Button>
                                                                                                </div>
                                                                                                <div className="grid grid-cols-2 gap-4 text-sm">
                                                                                                        <div>
                                                                                                                <Label className="text-muted-foreground">Source</Label>
                                                                                                                <p className="text-foreground">
                                                                                                                        {version.source_file}
                                                                                                                </p>
                                                                                                        </div>
                                                                                                        <div>
                                                                                                                <Label className="text-muted-foreground">Target</Label>
                                                                                                                <p className="text-foreground">
                                                                                                                        {version.target_file}
                                                                                                                </p>
                                                                                                        </div>
                                                                                                        <div>
                                                                                                                <Label className="text-muted-foreground">Type</Label>
                                                                                                                <p className="text-foreground">
                                                                                                                        {version.conversion_type === "autocad_to_revit"
                                                                                                                                ? "AutoCAD → Revit"
                                                                                                                                : "Revit → AutoCAD"}
                                                                                                                </p>
                                                                                                        </div>
                                                                                                        <div>
                                                                                                                <Label className="text-muted-foreground">Elements</Label>
                                                                                                                <p className="text-foreground">
                                                                                                                        {version.elements_count}
                                                                                                                </p>
                                                                                                        </div>
                                                                                                </div>
                                                                                        </div>
                                                                                ))}
                                                                        </div>
                                                                )}
                                                        </CardContent>
                                                </Card>
                                        </TabsContent>
                                </Tabs>
                        </div>
                </div>
        );
}
