
/**
 * ConversionPanel.tsx — Conversion panel with progress bar
 *
 * V213 FIX (schema mismatch): Previously this component passed the target
 * format ("revit" / "autocad" / "ifc") directly as `conversionType` to
 * `digitalTwinService.convert()`, but the backend's ConvertRequest schema
 * (backend/routers/digital_twin.py) only accepts "autocad_to_revit" or
 * "revit_to_autocad" — so EVERY conversion request returned HTTP 400.
 *
 * Now the component:
 *   1. Detects the source format from the file extension (.dwg / .rvt / .ifc)
 *   2. Maps (source → target) to the backend's conversion_type string
 *   3. Surfaces a clear error if the combination is unsupported (e.g. IFC
 *      source is not supported by this endpoint — use the IFC pipeline instead)
 */

import { ArrowRightLeft, CheckCircle2, Loader2, XCircle } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
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
import { digitalTwinService } from "@/services/digitalTwinService";

type ConvertState = "idle" | "converting" | "success" | "error";

/**
 * V213: Detect the source format from the file extension.
 * Returns "autocad" for .dwg/.dxf, "revit" for .rvt, "ifc" for .ifc,
 * or null if the extension is unrecognized.
 */
function detectSourceFormat(filePath: string): "autocad" | "revit" | "ifc" | null {
        const lower = filePath.toLowerCase().trim();
        if (lower.endsWith(".dwg") || lower.endsWith(".dxf")) return "autocad";
        if (lower.endsWith(".rvt")) return "revit";
        if (lower.endsWith(".ifc")) return "ifc";
        return null;
}

/**
 * V213: Map (sourceFormat, targetFormat) to the backend's conversion_type
 * string. Returns null if the combination is unsupported.
 */
function resolveConversionType(
        sourceFormat: "autocad" | "revit" | "ifc",
        targetFormat: "autocad" | "revit" | "ifc",
): "autocad_to_revit" | "revit_to_autocad" | null {
        if (sourceFormat === "autocad" && targetFormat === "revit") return "autocad_to_revit";
        if (sourceFormat === "revit" && targetFormat === "autocad") return "revit_to_autocad";
        // IFC source is not supported by this endpoint — the IFC pipeline
        // (fireai/bridges/ifc_pipeline.py) handles IFC separately.
        // Same-format conversions are no-ops.
        return null;
}

export function ConversionPanel() {
        const [sourceFile, setSourceFile] = useState("");
        const [targetFormat, setTargetFormat] = useState<"revit" | "autocad" | "ifc">("revit");
        const [state, setState] = useState<ConvertState>("idle");
        const [result, setResult] = useState<Record<string, unknown> | null>(null);

        const handleConvert = async () => {
                if (!sourceFile.trim()) {
                        toast.error("Please enter a source file path");
                        return;
                }

                // V213: Detect source format and resolve the backend conversion_type
                const sourceFormat = detectSourceFormat(sourceFile);
                if (!sourceFormat) {
                        toast.error(
                                "Could not detect source format from file extension. " +
                                "Supported: .dwg, .dxf, .rvt, .ifc",
                        );
                        setState("error");
                        return;
                }

                const conversionType = resolveConversionType(sourceFormat, targetFormat);
                if (!conversionType) {
                        toast.error(
                                `Conversion from ${sourceFormat} to ${targetFormat} is not supported ` +
                                "by this endpoint. Use the IFC pipeline endpoint for IFC conversions, " +
                                "or pick a different target format.",
                        );
                        setState("error");
                        return;
                }

                setState("converting");
                try {
                        const res = await digitalTwinService.convert(sourceFile, conversionType);
                        setResult(res as Record<string, unknown>);
                        setState("success");
                        toast.success("Conversion completed successfully");
                } catch (err) {
                        setState("error");
                        toast.error(
                                `Conversion failed: ${err instanceof Error ? err.message : "Unknown error"}`,
                        );
                }
        };

        return (
                <Card className="border-border bg-card">
                        <CardHeader>
                                <CardTitle className="flex items-center gap-2 text-foreground">
                                        <ArrowRightLeft className="h-5 w-5 text-primary" />
                                        Bidirectional Conversion
                                </CardTitle>
                                <CardDescription className="text-muted-foreground">
                                        Convert between AutoCAD (DWG) and Revit (RVT) formats
                                </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-4">
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                        <div className="space-y-2">
                                                <Label className="text-foreground/90">Source File</Label>
                                                <Input
                                                        placeholder="/path/to/file.dwg or /path/to/file.rvt"
                                                        value={sourceFile}
                                                        onChange={(e) => setSourceFile(e.target.value)}
                                                        className="bg-card border-border text-foreground"
                                                />
                                                {sourceFile && (
                                                        <p className="text-xs text-muted-foreground">
                                                                Detected source:{" "}
                                                                <span className="font-medium">
                                                                        {detectSourceFormat(sourceFile) ?? "unknown"}
                                                                </span>
                                                        </p>
                                                )}
                                        </div>
                                        <div className="space-y-2">
                                                <Label className="text-foreground/90">Target Format</Label>
                                                <select
                                                        value={targetFormat}
                                                        onChange={(e) =>
                                                                setTargetFormat(e.target.value as "revit" | "autocad" | "ifc")
                                                        }
                                                        className="w-full bg-card border border-border text-foreground rounded-md px-3 py-2 text-sm"
                                                >
                                                        <option value="revit">Revit (RVT)</option>
                                                        <option value="autocad">AutoCAD (DWG)</option>
                                                        <option value="ifc">IFC (via IFC pipeline)</option>
                                                </select>
                                        </div>
                                </div>
                                <Button
                                        onClick={handleConvert}
                                        disabled={state === "converting"}
                                        className="w-full bg-primary hover:bg-orange-700 text-white"
                                >
                                        {state === "converting" ? (
                                                <>
                                                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                                        Converting...
                                                </>
                                        ) : (
                                                <>
                                                        <ArrowRightLeft className="h-4 w-4 mr-2" />
                                                        Convert
                                                </>
                                        )}
                                </Button>
                                {state === "success" && result && (
                                        <div className="p-3 bg-emerald-600/10 border border-emerald-600/30 rounded-lg">
                                                <div className="flex items-center gap-2 mb-2">
                                                        <CheckCircle2 className="h-5 w-5 text-success" />
                                                        <span className="text-sm text-emerald-300">
                                                                Conversion Successful
                                                        </span>
                                                </div>
                                                <pre className="text-xs text-muted-foreground overflow-auto">
                                                        {JSON.stringify(result, null, 2)}
                                                </pre>
                                        </div>
                                )}
                                {state === "error" && (
                                        <div className="p-3 bg-danger/10 border border-slate-600/30 rounded-lg">
                                                <div className="flex items-center gap-2">
                                                        <XCircle className="h-5 w-5 text-danger" />
                                                        <span className="text-sm text-slate-400">Conversion Failed</span>
                                                </div>
                                        </div>
                                )}
                        </CardContent>
                </Card>
        );
}
