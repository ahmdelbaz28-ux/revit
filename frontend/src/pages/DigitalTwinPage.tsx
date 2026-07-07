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
        const { t } = useTranslation();
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
                } catch (_error) {
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
                } catch (_error) {
                        toast.error("Failed to save settings");
                }
        };

        return (
                <div className="flex-1 overflow-auto">
                        <div className="p-6 max-w-6xl mx-auto space-y-6">
                                {/* Header */}
                                <div className="flex items-center justify-between">
                                        <div>
                                                <h1 className="text-2xl font-bold text-slate-100">
                                                        Digital Twin Conversion
                                                </h1>
                                                <p className="text-sm text-slate-400 mt-1">
                                                        Bidirectional AutoCAD ↔ Revit conversion with semantic mapping
                                                </p>
                                        </div>
                                        <Button
                                                variant="outline"
                                                className="border-slate-600 text-slate-300 hover:bg-slate-800"
                                                onClick={fetchVersionHistory}
                                        >
                                                <History className="h-4 w-4 mr-2" />
                                                Refresh History
                                        </Button>
                                </div>

                                {/* Main Tabs */}
                                <Tabs value={activeTab} onValueChange={setActiveTab}>
                                        <TabsList className="bg-slate-800 border border-slate-700">
                                                <TabsTrigger
                                                        value="convert"
                                                        className="data-[state=active]:bg-slate-700"
                                                >
                                                        <ArrowRightLeft className="h-4 w-4 mr-2" />
                                                        Convert
                                                </TabsTrigger>
                                                <TabsTrigger
                                                        value="settings"
                                                        className="data-[state=active]:bg-slate-700"
                                                >
                                                        <Settings className="h-4 w-4 mr-2" />
                                                        Settings
                                                </TabsTrigger>
                                                <TabsTrigger
                                                        value="history"
                                                        className="data-[state=active]:bg-slate-700"
                                                >
                                                        <Clock className="h-4 w-4 mr-2" />
                                                        History
                                                </TabsTrigger>
                                        </TabsList>

                                        {/* Convert Tab */}
                                        <TabsContent value="convert" className="space-y-6">
                                                {/* File Upload */}
                                                <Card className="border-slate-700 bg-slate-800">
                                                        <CardHeader>
                                                                <CardTitle className="text-lg text-slate-100 flex items-center gap-2">
                                                                        <FileUp className="h-5 w-5 text-blue-400" />
                                                                        Upload File
                                                                </CardTitle>
                                                                <CardDescription className="text-slate-400">
                                                                        Select AutoCAD DWG/DXF or Revit RVT file for conversion
                                                                </CardDescription>
                                                        </CardHeader>
                                                        <CardContent className="space-y-4">
                                                                <div className="border-2 border-dashed border-slate-600 rounded-lg p-8 text-center hover:border-slate-500 transition-colors">
                                                                        <input
                                                                                type="file"
                                                                                accept=".dwg,.dxf,.rvt"
                                                                                onChange={handleFileSelect}
                                                                                className="hidden"
                                                                                id="file-upload"
                                                                        />
                                                                        <label htmlFor="file-upload" className="cursor-pointer">
                                                                                <Upload className="h-12 w-12 mx-auto text-slate-400 mb-4" />
                                                                                <p className="text-slate-300 font-medium mb-2">
                                                                                        {selectedFile
                                                                                                ? selectedFile.name
                                                                                                : "Click to upload or drag and drop"}
                                                                                </p>
                                                                                <p className="text-xs text-slate-500">
                                                                                        Supports: DWG, DXF, RVT (Max 100MB)
                                                                                </p>
                                                                        </label>
                                                                </div>

                                                                {selectedFile && (
                                                                        <div className="flex items-center gap-4 p-4 bg-slate-900/50 rounded-lg">
                                                                                <div className="flex-1">
                                                                                        <p className="text-sm font-medium text-slate-200">
                                                                                                {selectedFile.name}
                                                                                        </p>
                                                                                        <p className="text-xs text-slate-400">
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
                                                <Card className="border-slate-700 bg-slate-800">
                                                        <CardHeader>
                                                                <CardTitle className="text-lg text-slate-100">
                                                                        Start Conversion
                                                                </CardTitle>
                                                        </CardHeader>
                                                        <CardContent>
                                                                <Button
                                                                        className="w-full bg-red-600 hover:bg-red-700 text-white border-none h-12"
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
                                                                className={`border-slate-700 bg-slate-800 ${conversionResult.success ? "border-emerald-500/50" : "border-red-500/50"}`}
                                                        >
                                                                <CardHeader>
                                                                        <CardTitle className="text-lg text-slate-100 flex items-center gap-2">
                                                                                {conversionResult.success ? (
                                                                                        <CheckCircle2 className="h-5 w-5 text-emerald-400" />
                                                                                ) : (
                                                                                        <AlertCircle className="h-5 w-5 text-red-400" />
                                                                                )}
                                                                                Conversion{" "}
                                                                                {conversionResult.success ? "Completed" : "Failed"}
                                                                        </CardTitle>
                                                                </CardHeader>
                                                                <CardContent className="space-y-4">
                                                                        <div className="grid grid-cols-2 gap-4 text-sm">
                                                                                <div>
                                                                                        <Label className="text-slate-400">Source File</Label>
                                                                                        <p className="text-slate-200">
                                                                                                {conversionResult.source_file}
                                                                                        </p>
                                                                                </div>
                                                                                <div>
                                                                                        <Label className="text-slate-400">Target File</Label>
                                                                                        <p className="text-slate-200">
                                                                                                {conversionResult.target_file}
                                                                                        </p>
                                                                                </div>
                                                                                <div>
                                                                                        <Label className="text-slate-400">
                                                                                                Elements Converted
                                                                                        </Label>
                                                                                        <p className="text-slate-200">
                                                                                                {conversionResult.elements_converted}
                                                                                        </p>
                                                                                </div>
                                                                                <div>
                                                                                        <Label className="text-slate-400">Duration</Label>
                                                                                        <p className="text-slate-200">
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
                                                                                                                        <li key={idx}>• {warning}</li>
                                                                                                                ))}
                                                                                                        </ul>
                                                                                                </div>
                                                                                        </div>
                                                                                </div>
                                                                        )}

                                                                        {conversionResult.errors.length > 0 && (
                                                                                <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-lg">
                                                                                        <div className="flex items-start gap-2">
                                                                                                <AlertCircle className="h-5 w-5 text-red-400 mt-0.5" />
                                                                                                <div className="flex-1">
                                                                                                        <p className="text-sm font-medium text-red-200 mb-2">
                                                                                                                Errors
                                                                                                        </p>
                                                                                                        <ul className="text-xs text-red-300 space-y-1">
                                                                                                                {conversionResult.errors.map((error, idx) => (
                                                                                                                        <li key={idx}>• {error}</li>
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
                                                <Card className="border-slate-700 bg-slate-800">
                                                        <CardHeader>
                                                                <CardTitle className="text-lg text-slate-100">
                                                                        Layer to Category Mapping
                                                                </CardTitle>
                                                                <CardDescription className="text-slate-400">
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
                                                                                        className="bg-slate-900 border-slate-600 text-slate-100"
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
                                                                                        className="bg-slate-900 border-slate-600 text-slate-100"
                                                                                        placeholder="Revit Category"
                                                                                />
                                                                        </div>
                                                                ))}
                                                                <Button
                                                                        variant="outline"
                                                                        className="w-full border-slate-600 text-slate-300"
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
                                                <Card className="border-slate-700 bg-slate-800">
                                                        <CardHeader>
                                                                <CardTitle className="text-lg text-slate-100">
                                                                        Block to Family Mapping
                                                                </CardTitle>
                                                                <CardDescription className="text-slate-400">
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
                                                                                        className="bg-slate-900 border-slate-600 text-slate-100"
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
                                                                                        className="bg-slate-900 border-slate-600 text-slate-100"
                                                                                        placeholder="Revit Family"
                                                                                />
                                                                        </div>
                                                                ))}
                                                        </CardContent>
                                                </Card>

                                                {/* Conversion Settings */}
                                                <Card className="border-slate-700 bg-slate-800">
                                                        <CardHeader>
                                                                <CardTitle className="text-lg text-slate-100">
                                                                        Conversion Settings
                                                                </CardTitle>
                                                        </CardHeader>
                                                        <CardContent className="space-y-4">
                                                                <div className="grid grid-cols-2 gap-4">
                                                                        <div className="space-y-2">
                                                                                <Label className="text-slate-300">Default Level</Label>
                                                                                <Input
                                                                                        value={defaultLevel}
                                                                                        onChange={(e) => setDefaultLevel(e.target.value)}
                                                                                        className="bg-slate-900 border-slate-600 text-slate-100"
                                                                                />
                                                                        </div>
                                                                        <div className="space-y-2">
                                                                                <Label className="text-slate-300">Level Height (mm)</Label>
                                                                                <Input
                                                                                        type="number"
                                                                                        value={levelHeight}
                                                                                        onChange={(e) =>
                                                                                                setLevelHeight(parseInt(e.target.value, 10))
                                                                                        }
                                                                                        className="bg-slate-900 border-slate-600 text-slate-100"
                                                                                />
                                                                        </div>
                                                                        <div className="space-y-2">
                                                                                <Label className="text-slate-300">Source Units</Label>
                                                                                <Select value={sourceUnits} onValueChange={setSourceUnits}>
                                                                                        <SelectTrigger className="bg-slate-900 border-slate-600 text-slate-100">
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
                                                                                <Label className="text-slate-300">Target Units</Label>
                                                                                <Select value={targetUnits} onValueChange={setTargetUnits}>
                                                                                        <SelectTrigger className="bg-slate-900 border-slate-600 text-slate-100">
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
                                                                        className="w-full bg-red-600 hover:bg-red-700 text-white border-none"
                                                                        onClick={saveConversionSettings}
                                                                >
                                                                        Save Conversion Settings
                                                                </Button>
                                                        </CardContent>
                                                </Card>
                                        </TabsContent>

                                        {/* History Tab */}
                                        <TabsContent value="history">
                                                <Card className="border-slate-700 bg-slate-800">
                                                        <CardHeader>
                                                                <CardTitle className="text-lg text-slate-100 flex items-center gap-2">
                                                                        <History className="h-5 w-5 text-blue-400" />
                                                                        Conversion History
                                                                </CardTitle>
                                                                <CardDescription className="text-slate-400">
                                                                        View past conversions and rollback to previous versions
                                                                </CardDescription>
                                                        </CardHeader>
                                                        <CardContent>
                                                                {loadingHistory ? (
                                                                        <div className="flex items-center justify-center py-12">
                                                                                <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
                                                                        </div>
                                                                ) : versions.length === 0 ? (
                                                                        <div className="text-center py-12 text-slate-400">
                                                                                <Clock className="h-12 w-12 mx-auto mb-4 opacity-50" />
                                                                                <p>No conversion history yet</p>
                                                                        </div>
                                                                ) : (
                                                                        <div className="space-y-4">
                                                                                {versions.map((version) => (
                                                                                        <div
                                                                                                key={version.version_id}
                                                                                                className="p-4 bg-slate-900/50 rounded-lg border border-slate-700"
                                                                                        >
                                                                                                <div className="flex items-start justify-between mb-3">
                                                                                                        <div className="flex items-center gap-3">
                                                                                                                <Badge
                                                                                                                        variant={
                                                                                                                                version.status === "success"
                                                                                                                                        ? "default"
                                                                                                                                        : version.status === "partial"
                                                                                                                                                ? "secondary"
                                                                                                                                                : "destructive"
                                                                                                                        }
                                                                                                                >
                                                                                                                        {version.status}
                                                                                                                </Badge>
                                                                                                                <span className="text-sm text-slate-400">
                                                                                                                        {new Date(version.timestamp).toLocaleString()}
                                                                                                                </span>
                                                                                                        </div>
                                                                                                        <Button
                                                                                                                variant="outline"
                                                                                                                size="sm"
                                                                                                                className="border-slate-600 text-slate-300 hover:bg-slate-800"
                                                                                                                onClick={() => handleRollback(version.version_id)}
                                                                                                        >
                                                                                                                <RefreshCw className="h-4 w-4 mr-2" />
                                                                                                                Rollback
                                                                                                        </Button>
                                                                                                </div>
                                                                                                <div className="grid grid-cols-2 gap-4 text-sm">
                                                                                                        <div>
                                                                                                                <Label className="text-slate-400">Source</Label>
                                                                                                                <p className="text-slate-200">
                                                                                                                        {version.source_file}
                                                                                                                </p>
                                                                                                        </div>
                                                                                                        <div>
                                                                                                                <Label className="text-slate-400">Target</Label>
                                                                                                                <p className="text-slate-200">
                                                                                                                        {version.target_file}
                                                                                                                </p>
                                                                                                        </div>
                                                                                                        <div>
                                                                                                                <Label className="text-slate-400">Type</Label>
                                                                                                                <p className="text-slate-200">
                                                                                                                        {version.conversion_type === "autocad_to_revit"
                                                                                                                                ? "AutoCAD → Revit"
                                                                                                                                : "Revit → AutoCAD"}
                                                                                                                </p>
                                                                                                        </div>
                                                                                                        <div>
                                                                                                                <Label className="text-slate-400">Elements</Label>
                                                                                                                <p className="text-slate-200">
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
