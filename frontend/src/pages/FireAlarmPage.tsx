
/**
 * FireAlarmPage.tsx - Main Fire Alarm System Dashboard
 *
 * V140 Phase 5: Connected to real devices API. Falls back to empty zones
 * when no project is selected or API is unavailable.
 */
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { ExplainButton } from "@/components/ai/ExplainButton";
import {
        CanvasEditor,
        type Detector,
} from "@/components/firealarm/CanvasEditor";
import { DeviceProperties } from "@/components/firealarm/DeviceProperties";
import { SymbolLibrary } from "@/components/firealarm/SymbolLibrary";
import { ZoneNavigator } from "@/components/firealarm/ZoneNavigator";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
        Card,
        CardContent,
        CardDescription,
        CardHeader,
        CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/services/api";

// Mock data for the navigator
const mockZones = [
        {
                id: "project-1",
                name: "Building A Fire Alarm System",
                type: "panel" as const,
                devices: [], // Add empty devices array to satisfy the Zone interface
                children: [
                        {
                                id: "facp-1",
                                name: "FACP-1 (Main Panel)",
                                type: "panel" as const,
                                devices: [],
                                children: [
                                        {
                                                id: "slc-loop-1",
                                                name: "SLC Loop 1",
                                                type: "loop" as const,
                                                devices: [],
                                                children: [
                                                        {
                                                                id: "zone-1-01",
                                                                name: "Zone 1-01: Basement (12 devices)",
                                                                type: "zone" as const,
                                                                devices: [
                                                                        {
                                                                                id: "dev-1",
                                                                                name: "Basement Smoke 01",
                                                                                type: "smoke",
                                                                                zone: "zone-1-01",
                                                                                status: "normal" as const,
                                                                                address: "001",
                                                                        },
                                                                        {
                                                                                id: "dev-2",
                                                                                name: "Basement Heat 01",
                                                                                type: "heat",
                                                                                zone: "zone-1-01",
                                                                                status: "warning" as const,
                                                                                address: "002",
                                                                        },
                                                                ],
                                                        },
                                                        {
                                                                id: "zone-1-02",
                                                                name: "Zone 1-02: Ground Floor (24 devices)",
                                                                type: "zone" as const,
                                                                devices: [
                                                                        {
                                                                                id: "dev-3",
                                                                                name: "GF Smoke 01",
                                                                                type: "smoke",
                                                                                zone: "zone-1-02",
                                                                                status: "normal" as const,
                                                                                address: "003",
                                                                        },
                                                                        {
                                                                                id: "dev-4",
                                                                                name: "GF Pull 01",
                                                                                type: "pull",
                                                                                zone: "zone-1-02",
                                                                                status: "normal" as const,
                                                                                address: "004",
                                                                        },
                                                                ],
                                                        },
                                                ],
                                        },
                                        {
                                                id: "nac-circuit-1",
                                                name: "NAC Circuit 1 (General)",
                                                type: "circuit" as const,
                                                devices: [
                                                        {
                                                                id: "dev-5",
                                                                name: "GF Horn/Strobe 01",
                                                                type: "horns",
                                                                zone: "nac-circuit-1",
                                                                status: "normal" as const,
                                                                address: "005",
                                                        },
                                                ],
                                        },
                                ],
                        },
                        {
                                id: "facp-2",
                                name: "FACP-2 (Annunciator)",
                                type: "panel" as const,
                                devices: [
                                        {
                                                id: "dev-6",
                                                name: "Annunciator Panel",
                                                type: "facp",
                                                zone: "facp-2",
                                                status: "normal" as const,
                                                address: "006",
                                        },
                                ],
                        },
                ],
        },
];

export function FireAlarmPage() {
        const { t } = useTranslation();
        const [detectors, setDetectors] = useState<Detector[]>([
                {
                        id: "det-1",
                        x: 100,
                        y: 150,
                        type: "smoke",
                        status: "normal",
                        coverageRadius: 6.37,
                        location: "Room 101",
                        heightAFF: 2.7,
                        manufacturer: "Hochiki",
                        model: "LT-1",
                        sensitivity: "standard",
                        lastTestDate: "2023-05-15",
                },
                {
                        id: "det-2",
                        x: 250,
                        y: 200,
                        type: "heat",
                        status: "warning",
                        coverageRadius: 4.27,
                        location: "Room 102",
                        heightAFF: 2.7,
                        manufacturer: "System Sensor",
                        model: "LSH-1",
                        sensitivity: "standard",
                        lastTestDate: "2023-05-10",
                },
                {
                        id: "det-3",
                        x: 400,
                        y: 100,
                        type: "pull",
                        status: "normal",
                        coverageRadius: 0,
                        location: "Hallway",
                        heightAFF: 1.2,
                        manufacturer: "Honeywell",
                        model: "PSS-1",
                        sensitivity: "standard",
                        lastTestDate: "2023-05-12",
                },
        ]);
        const [selectedDevice, setSelectedDevice] = useState<string | null>(null);
        const [showProperties, setShowProperties] = useState(false);

        // V187 FIX: Undo/Redo/Save with proper state management.
        // V186 had a stale state bug: pushHistory(detectors) captured the render-time
        // value of `detectors`, not the actual previous state. If multiple changes
        // happened in one tick, history captured wrong snapshots.
        // V187 fix: use a ref to always have the latest detectors value, and
        // capture history INSIDE setDetectors so we get the actual previous state.
        // Also: Save now LOADS from localStorage on mount (V186 only saved, never loaded).
        const [history, setHistory] = useState<Detector[][]>([]);
        const [redoStack, setRedoStack] = useState<Detector[][]>([]);
        const [saveStatus, setSaveStatus] = useState<string | null>(null);
        const detectorsRef = useRef<Detector[]>(detectors);
        detectorsRef.current = detectors;

        const pushHistory = (snapshot: Detector[]) => {
                setHistory((prev) => [...prev.slice(-19), snapshot]);
                setRedoStack([]);
        };

        // V187: setDetectorsWithHistory captures the ACTUAL previous state using
        // the functional updater pattern, avoiding the stale closure bug.
        const setDetectorsWithHistory = (
                next: Detector[] | ((prev: Detector[]) => Detector[]),
        ) => {
                setDetectors((prev) => {
                        pushHistory(prev); // capture actual previous state, not stale closure
                        return typeof next === "function" ? next(prev) : next;
                });
        };

        const handleUndo = () => {
                setHistory((prevHistory) => {
                        if (prevHistory.length === 0) return prevHistory;
                        const last = prevHistory[prevHistory.length - 1];
                        setRedoStack((r) => [...r, detectorsRef.current]);
                        setDetectors(last);
                        return prevHistory.slice(0, -1);
                });
        };

        const handleRedo = () => {
                setRedoStack((prevRedo) => {
                        if (prevRedo.length === 0) return prevRedo;
                        const next = prevRedo[prevRedo.length - 1];
                        setHistory((h) => [...h, detectorsRef.current]);
                        setDetectors(next);
                        return prevRedo.slice(0, -1);
                });
        };

        const handleSave = () => {
                try {
                        localStorage.setItem(
                                "fireai_firealarm_detectors",
                                JSON.stringify(detectors),
                        );
                        setSaveStatus(t("fireAlarm.projectSaved"));
                        setTimeout(() => setSaveStatus(null), 2500);
                } catch {
                        setSaveStatus(t("common.error"));
                        setTimeout(() => setSaveStatus(null), 2500);
                }
        };

        // V187: Load saved detectors from localStorage on mount
        useEffect(() => {
                try {
                        const saved = localStorage.getItem("fireai_firealarm_detectors");
                        if (saved) {
                                const parsed = JSON.parse(saved) as Detector[];
                                if (Array.isArray(parsed) && parsed.length > 0) {
                                        setDetectors(parsed);
                                }
                        }
                } catch {
                        // Corrupt localStorage - ignore, use default detectors
                }
        }, []);

        // V140 Phase 5: Fetch zones from API
        const [zones, setZones] = useState<typeof mockZones>([]);
        const [zonesLoading, setZonesLoading] = useState(false);

        useEffect(() => {
                const fetchZones = async () => {
                        setZonesLoading(true);
                        try {
                                const projects = await api.getProjects({ page: 1, page_size: 1 });
                                if (projects?.items && projects.items.length > 0) {
                                        const devices = await api.getElements({ page: 1, page_size: 100 });
                                        if (devices?.items && devices.items.length > 0) {
                                                // Transform devices into zone structure
                                                const zoneMap: Record<
                                                        string,
                                                        { id: string; name: string; type: string; devices: unknown[] }
                                                > = {};
                                                for (const device of devices.items) {
                                                        const d = device as unknown as Record<string, unknown>;
                                                        const zoneId = (d?.zone_id as string) || "default-zone";
                                                        if (!zoneMap[zoneId]) {
                                                                zoneMap[zoneId] = {
                                                                        id: zoneId,
                                                                        name: `Zone ${zoneId}`,
                                                                        type: "zone",
                                                                        devices: [],
                                                                };
                                                        }
                                                        zoneMap[zoneId].devices.push(device);
                                                }
                                                if (Object.keys(zoneMap).length > 0) {
                                                        setZones([
                                                                {
                                                                        id: "project-1",
                                                                        name: projects.items[0].name || "Fire Alarm System",
                                                                        type: "panel",
                                                                        devices: [],
                                                                        children: Object.values(zoneMap),
                                                                },
                                                        ] as unknown as typeof mockZones);
                                                } else {
                                                        // V246 SAFETY FIX: Show empty state instead of mock data
                                                        setZones([]);
                                                }
                                        } else {
                                                // V246 SAFETY FIX: Show empty state instead of mock data
                                                setZones([]);
                                        }
                                } else {
                                        // V246 SAFETY FIX: Show empty state instead of mock data
                                        setZones([]);
                                }
                        } catch {
                                // V246 SAFETY FIX: Show empty state instead of mock data
                                setZones([]);
                        } finally {
                                setZonesLoading(false);
                        }
                };
                fetchZones();
        }, []);

        const handleDeviceSelect = (deviceId: string) => {
                setSelectedDevice(deviceId);
                setShowProperties(true);
        };

        const handleZoomToZone = (zoneId: string) => {
                // V247 FIX: Replaced alert() with toast notification.
                // The zoom functionality would require a canvas ref + scrollIntoView;
                // for now, show a non-blocking toast instead of a blocking alert().
                toast.info(`Zone selected: ${zoneId}`);
        };

        const handleSaveDevice = (updatedDevice: Partial<{ id: string } & Record<string, unknown>>) => {
                // V187: use setDetectorsWithHistory to capture actual previous state
                if (!updatedDevice.id) return;
                setDetectorsWithHistory((prev) =>
                        prev.map((det) => (det.id === updatedDevice.id ? { ...det, ...updatedDevice } : det)),
                );
                setShowProperties(false);
        };

        return (
                <div
                        className="flex flex-1 overflow-auto"
                        aria-label={t("fireAlarm.dashboard")}
                >
                        {/* Zone Navigator - Left sidebar */}
                        <div className="w-64 h-full bg-card border-r border-border p-2">
                                {zonesLoading ? (
                                        <Skeleton className="h-full w-full bg-card" />
                                ) : (
                                        <ZoneNavigator
                                                zones={zones}
                                                selectedDevice={selectedDevice}
                                                onDeviceSelect={handleDeviceSelect}
                                                onZoomToZone={handleZoomToZone}
                                        />
                                )}
                        </div>

                        {/* Main Content Area */}
                        <div className="flex-1 flex flex-col">
                                {/* Top Toolbar */}
                                <div className="h-14 flex items-center px-4 border-b border-border bg-card">
                                        <h1 className="text-lg font-semibold text-foreground">
                                                {t("fireAlarm.designer")}
                                        </h1>
                                        <div className="ml-auto flex gap-2 items-center">
                                                {/* V192 FIX: Consistent button styling for Undo/Redo/Save.
                Previously Save was red (looked destructive) while Undo/Redo
                were outline. Now all three use the same size/padding, with
                Save using the primary orange accent (BAZSpark brand color)
                to distinguish it as the main action. Undo/Redo stay outline
                to indicate they're secondary actions. */}
                                                <Button
                                                        variant="outline"
                                                        size="sm"
                                                        className="border-border text-foreground/90 hover:bg-secondary hover:text-foreground transition-colors"
                                                        onClick={handleUndo}
                                                        disabled={history.length === 0}
                                                        aria-label={t("common.undo")}
                                                >
                                                        <svg
                                                                className="h-4 w-4 mr-1.5"
                                                                viewBox="0 0 24 24"
                                                                fill="none"
                                                                stroke="currentColor"
                                                                strokeWidth="2"
                                                                strokeLinecap="round"
                                                                strokeLinejoin="round"
                                                        >
                                                                <path d="M3 7v6h6" />
                                                                <path d="M21 17a9 9 0 0 0-15-6.7L3 13" />
                                                        </svg>
                                                        {t("common.undo")}
                                                </Button>
                                                <Button
                                                        variant="outline"
                                                        size="sm"
                                                        className="border-border text-foreground/90 hover:bg-secondary hover:text-foreground transition-colors"
                                                        onClick={handleRedo}
                                                        disabled={redoStack.length === 0}
                                                        aria-label={t("common.redo")}
                                                >
                                                        <svg
                                                                className="h-4 w-4 mr-1.5"
                                                                viewBox="0 0 24 24"
                                                                fill="none"
                                                                stroke="currentColor"
                                                                strokeWidth="2"
                                                                strokeLinecap="round"
                                                                strokeLinejoin="round"
                                                        >
                                                                <path d="M21 7v6h-6" />
                                                                <path d="M3 17a9 9 0 0 1 15-6.7L21 13" />
                                                        </svg>
                                                        {t("common.redo")}
                                                </Button>
                                                <Button
                                                        size="sm"
                                                        className="bg-primary hover:bg-orange-700 text-white border-none transition-colors"
                                                        onClick={handleSave}
                                                        aria-label={t("common.save")}
                                                >
                                                        <svg
                                                                className="h-4 w-4 mr-1.5"
                                                                viewBox="0 0 24 24"
                                                                fill="none"
                                                                stroke="currentColor"
                                                                strokeWidth="2"
                                                                strokeLinecap="round"
                                                                strokeLinejoin="round"
                                                        >
                                                                <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" />
                                                                <polyline points="17 21 17 13 7 13 7 21" />
                                                                <polyline points="7 3 7 8 15 8" />
                                                        </svg>
                                                        {t("common.save")}
                                                </Button>
                                                {saveStatus && (
                                                        <span
                                                                className="text-xs text-success ml-2"
                                                                role="status"
                                                                aria-live="polite"
                                                        >
                                                                {saveStatus}
                                                        </span>
                                                )}
                                        </div>
                                </div>

                                {/* Canvas Area */}
                                <div className="flex-1 flex overflow-hidden">
                                        <div className="flex-1 p-4">
                                                <CanvasEditor
                                                        detectors={detectors}
                                                        onDetectorsChange={setDetectorsWithHistory}
                                                />
                                        </div>

                                        {/* Symbol Library - Right sidebar */}
                                        <div className="w-80 border-l border-border p-4 bg-card">
                                                <SymbolLibrary />

                                                <div className="mt-6">
                                                        <Card className="border-border bg-card">
                                                                <CardHeader>
                                                                        <div className="flex items-center justify-between">
                                                                                <CardTitle className="text-lg text-foreground">
                                                                                        {t("fireAlarm.projectInfo")}
                                                                                </CardTitle>
                                                                                <ExplainButton
                                                                                        calculationType="device_summary"
                                                                                        result={{
                                                                                                total_detectors: detectors.length,
                                                                                                smoke_detectors: detectors.filter((d: Detector) => d.type === "smoke").length,
                                                                                                heat_detectors: detectors.filter((d: Detector) => d.type === "heat").length,
                                                                                                pull_stations: detectors.filter((d: Detector) => d.type === "pull").length,
                                                                                                normal: detectors.filter((d: Detector) => d.status === "normal").length,
                                                                                                warning: detectors.filter((d: Detector) => d.status === "warning").length,
                                                                                        }}
                                                                                />
                                                                        </div>
                                                                        <CardDescription className="text-muted-foreground">
                                                                                {t("fireAlarm.projectDetails")}
                                                                        </CardDescription>
                                                                </CardHeader>
                                                                <CardContent>
                                                                        <div className="space-y-3">
                                                                                <div className="flex justify-between">
                                                                                        <span className="text-muted-foreground">
                                                                                                {t("fireAlarm.totalDetectors")}
                                                                                        </span>
                                                                                        <span className="text-foreground">{detectors.length}</span>
                                                                                </div>
                                                                                <div className="flex justify-between">
                                                                                        <span className="text-muted-foreground">
                                                                                                {t("fireAlarm.smokeDetectors")}
                                                                                        </span>
                                                                                        <span className="text-foreground">
                                                                                                {detectors.filter((d) => d.type === "smoke").length}
                                                                                        </span>
                                                                                </div>
                                                                                <div className="flex justify-between">
                                                                                        <span className="text-muted-foreground">
                                                                                                {t("fireAlarm.heatDetectors")}
                                                                                        </span>
                                                                                        <span className="text-foreground">
                                                                                                {detectors.filter((d) => d.type === "heat").length}
                                                                                        </span>
                                                                                </div>
                                                                                <div className="flex justify-between">
                                                                                        <span className="text-muted-foreground">
                                                                                                {t("fireAlarm.normal")}
                                                                                        </span>
                                                                                        <Badge
                                                                                                variant="secondary"
                                                                                                className="bg-success/10 text-success border-success/30"
                                                                                        >
                                                                                                {detectors.filter((d) => d.status === "normal").length}
                                                                                        </Badge>
                                                                                </div>
                                                                                <div className="flex justify-between">
                                                                                        <span className="text-muted-foreground">
                                                                                                {t("fireAlarm.warning")}
                                                                                        </span>
                                                                                        <Badge
                                                                                                variant="secondary"
                                                                                                className="bg-warning/10 text-warning border-warning/30"
                                                                                        >
                                                                                                {detectors.filter((d) => d.status === "warning").length}
                                                                                        </Badge>
                                                                                </div>
                                                                        </div>
                                                                </CardContent>
                                                        </Card>
                                                </div>
                                        </div>
                                </div>
                        </div>

                        {/* Device Properties Panel - Appears when device is selected */}
                        {showProperties && selectedDevice && (
                                <DeviceProperties
                                        device={detectors.find((d) => d.id === selectedDevice) || null}
                                        onSave={handleSaveDevice}
                                        onClose={() => setShowProperties(false)}
                                />
                        )}
                </div>
        );
}
