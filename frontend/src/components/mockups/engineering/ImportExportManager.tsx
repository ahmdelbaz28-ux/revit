
import DxfParser from "dxf-parser";
import { saveAs } from "file-saver";
import { AlertCircle, Download, Upload } from "lucide-react";
import type React from "react";
import { useRef } from "react";

export function ImportExportManager() {
        const fileInputRef = useRef<HTMLInputElement>(null);

        const handleExportJSON = () => {
                // Retrieve current state logic would go here (simplified for demo)
                // In real app, access store directly or via prop
                const projectData = localStorage.getItem("nexus_project_state") || "{}";
                const blob = new Blob([projectData], {
                        type: "application/json;charset=utf-8",
                });
                saveAs(
                        blob,
                        `NexusCAD_Project_${new Date().toISOString().split("T")[0]}.json`,
                );
        };

        const handleImportDXF = (e: React.ChangeEvent<HTMLInputElement>) => {
                const file = e.target.files?.[0];
                if (!file) return;

                const reader = new FileReader();
                reader.onload = (event) => {
                        try {
                                const parser = new DxfParser();
                                const result = event.target?.result;
                                if (typeof result !== "string") {
                                        throw new Error("Invalid file content");
                                }
                                const dxfData = parser.parseSync(result);

                                // V194 (TD-5) FIX: Convert DXF entities (LINE, CIRCLE, ARC,
                                // LWPOLYLINE, TEXT) into Nexus device/connection objects.
                                // Each LINE becomes a "cable" connection, each CIRCLE/ARC
                                // becomes a "device" (junction box / panel), each TEXT
                                // becomes a label annotation. Coordinates are preserved.
                                const converted: {
                                        devices: Array<{
                                                id: string;
                                                type: string;
                                                x: number;
                                                y: number;
                                                radius?: number;
                                                label?: string;
                                        }>;
                                        connections: Array<{
                                                id: string;
                                                from: string;
                                                to: string;
                                                type: string;
                                        }>;
                                } = { devices: [], connections: [] };

                                const entities = dxfData?.entities ?? [];
                                let deviceIdx = 0;
                                let connIdx = 0;
                                const vertexToId = new Map<string, string>();

                                const vertexId = (x: number, y: number): string => {
                                        const key = `${x.toFixed(3)},${y.toFixed(3)}`;
                                        if (!vertexToId.has(key)) {
                                                const id = `v${deviceIdx++}`;
                                                vertexToId.set(key, id);
                                                converted.devices.push({
                                                        id,
                                                        type: "vertex",
                                                        x,
                                                        y,
                                                });
                                        }
                                        return vertexToId.get(key)!;
                                };

                                for (const ent of entities) {
                                        // dxf-parser uses a discriminated union on `type`, but the
                                        // per-type interfaces (ILine, ICircle, etc.) aren't exported
                                        // in a way TypeScript can narrow here. Cast to a structural
                                        // type that covers all fields we access across cases.
                                        const e = ent as {
                                                type: string;
                                                vertices?: Array<{ x: number; y: number }>;
                                                center?: { x: number; y: number };
                                                radius?: number;
                                                text?: string;
                                                startPoint?: { x: number; y: number };
                                        };
                                        switch (e.type) {
                                                case "LINE": {
                                                        if (!e.vertices || e.vertices.length < 2) break;
                                                        const v1 = e.vertices[0];
                                                        const v2 = e.vertices[1];
                                                        const id1 = vertexId(v1.x, v1.y);
                                                        const id2 = vertexId(v2.x, v2.y);
                                                        converted.connections.push({
                                                                id: `c${connIdx++}`,
                                                                from: id1,
                                                                to: id2,
                                                                type: "cable",
                                                        });
                                                        break;
                                                }
                                                case "CIRCLE": {
                                                        if (e.center == null || e.radius == null) break;
                                                        converted.devices.push({
                                                                id: `d${deviceIdx++}`,
                                                                type: "junction",
                                                                x: e.center.x,
                                                                y: e.center.y,
                                                                radius: e.radius,
                                                        });
                                                        break;
                                                }
                                                case "ARC": {
                                                        if (e.center == null || e.radius == null) break;
                                                        converted.devices.push({
                                                                id: `d${deviceIdx++}`,
                                                                type: "device",
                                                                x: e.center.x,
                                                                y: e.center.y,
                                                                radius: e.radius,
                                                        });
                                                        break;
                                                }
                                                case "LWPOLYLINE":
                                                case "POLYLINE": {
                                                        if (!e.vertices || e.vertices.length < 2) break;
                                                        for (let i = 0; i < e.vertices.length - 1; i++) {
                                                                const v1 = e.vertices[i];
                                                                const v2 = e.vertices[i + 1];
                                                                const id1 = vertexId(v1.x, v1.y);
                                                                const id2 = vertexId(v2.x, v2.y);
                                                                converted.connections.push({
                                                                        id: `c${connIdx++}`,
                                                                        from: id1,
                                                                        to: id2,
                                                                        type: "cable",
                                                                });
                                                        }
                                                        break;
                                                }
                                                case "TEXT": {
                                                        if (e.text == null) break;
                                                        const x = e.startPoint?.x ?? 0;
                                                        const y = e.startPoint?.y ?? 0;
                                                        converted.devices.push({
                                                                id: `t${deviceIdx++}`,
                                                                type: "label",
                                                                x,
                                                                y,
                                                                label: String(e.text),
                                                        });
                                                        break;
                                                }
                                                default:
                                                        // Skip unsupported entity types (INSERT, MTEXT, etc.)
                                                        break;
                                        }
                                }

                                if (import.meta.env.DEV) {
                                        console.log(
                                                `DXF Imported: ${entities.length} entities → ${converted.devices.length} devices, ${converted.connections.length} connections`,
                                        );
                                }

                                // Persist converted data so other components can pick it up.
                                // In a full app this would dispatch a store action; here we
                                // use localStorage as the inter-component bridge.
                                try {
                                        localStorage.setItem(
                                                "nexus_imported_dxf",
                                                JSON.stringify(converted),
                                        );
                                } catch {
                                        // localStorage may be full or disabled — ignore
                                }

                                alert(
                                        `DXF Imported Successfully!\n` +
                                        `Found ${entities.length} entities.\n` +
                                        `Converted: ${converted.devices.length} devices, ${converted.connections.length} connections.`,
                                );
                        } catch (err) {
                                if (import.meta.env.DEV) console.error(err);
                                alert("Failed to parse DXF file. Ensure it is a valid ASCII DXF.");
                        }
                };
                reader.readAsText(file);
                // Reset input
                if (fileInputRef.current) fileInputRef.current.value = "";
        };

        return (
                <div className="flex items-center gap-2">
                        <button
                                onClick={handleExportJSON}
                                className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20 rounded-md transition-colors border border-emerald-500/20"
                        >
                                <Download size={14} /> Export JSON
                        </button>

                        <button
                                onClick={() => fileInputRef.current?.click()}
                                className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium bg-blue-500/10 text-blue-500 hover:bg-blue-500/20 rounded-md transition-colors border border-blue-500/20"
                        >
                                <Upload size={14} /> Import DXF
                        </button>
                        <input
                                type="file"
                                ref={fileInputRef}
                                onChange={handleImportDXF}
                                accept=".dxf"
                                className="hidden"
                        />

                        <div className="h-4 w-px bg-border mx-1" />

                        <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground bg-muted px-2 py-1 rounded">
                                <AlertCircle size={10} />
                                <span>Revit IFC Support: Coming in v1.1</span>
                        </div>
                </div>
        );
}
