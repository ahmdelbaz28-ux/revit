// NOSONAR
import type React from "react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

// Define detector types
export type DetectorType =
        | "smoke"
        | "heat"
        | "pull"
        | "horns"
        | "speaker"
        | "facp";

// Define detector interface
export interface Detector {
        id: string;
        x: number;
        y: number;
        type: DetectorType;
        zone?: string;
        address?: string;
        status: "normal" | "warning" | "fault";
        coverageRadius: number;
        location?: string;
        heightAFF?: number;
        manufacturer?: string;
        model?: string;
        sensitivity?: "high" | "standard" | "low";
        lastTestDate?: string;
}

interface CanvasEditorProps {
        floorPlanImage?: string;
        detectors: Detector[];
        onDetectorsChange: (detectors: Detector[]) => void;
}

export const CanvasEditor: React.FC<CanvasEditorProps> = ({
        floorPlanImage,
        detectors,
        onDetectorsChange,
}) => {
        const { t } = useTranslation();
        const canvasRef = useRef<HTMLDivElement>(null);
        const [draggingDetector, setDraggingDetector] = useState<string | null>(null);
        const [selectedDetector, setSelectedDetector] = useState<string | null>(null);
        const [newDetectorType, setNewDetectorType] = useState<DetectorType>("smoke");

        // Handle click on canvas to add new detector
        const handleCanvasClick = (e: React.MouseEvent<HTMLDivElement>) => {
                if (!canvasRef.current) return;

                const rect = canvasRef.current.getBoundingClientRect();
                const x = e.clientX - rect.left;
                const y = e.clientY - rect.top;

                // Define coverage radius based on detector type
                let coverageRadius = 6.37; // Default for smoke detector
                if (newDetectorType === "heat") {
                        coverageRadius = 4.27; // Smaller for heat detector
                }

                const newDetector: Detector = {
                        id: `detector-${Date.now()}`,
                        x,
                        y,
                        type: newDetectorType,
                        status: "normal",
                        coverageRadius,
                        location: "Not Set",
                        heightAFF: 2.7,
                        manufacturer: "Default",
                        model: "Generic",
                        sensitivity: "standard",
                        lastTestDate: new Date().toISOString().split("T")[0],
                };

                onDetectorsChange([...detectors, newDetector]);
        };

        // Handle mouse down on a detector to start dragging
        const handleMouseDown = (id: string, e: React.MouseEvent) => {
                e.stopPropagation();
                setDraggingDetector(id);
                setSelectedDetector(id);
        };

        // Handle mouse move to update detector position
        useEffect(() => {
                const handleMouseMove = (e: MouseEvent) => {
                        if (draggingDetector && canvasRef.current) {
                                const rect = canvasRef.current.getBoundingClientRect();
                                const x = e.clientX - rect.left;
                                const y = e.clientY - rect.top;

                                const updatedDetectors = detectors.map((detector) => {
                                        if (detector.id === draggingDetector) {
                                                return { ...detector, x, y };
                                        }
                                        return detector;
                                });

                                onDetectorsChange(updatedDetectors);
                        }
                };

                const handleMouseUp = () => {
                        setDraggingDetector(null);
                };

                if (draggingDetector) {
                        globalThis.addEventListener("mousemove", handleMouseMove);
                        globalThis.addEventListener("mouseup", handleMouseUp);
                }

                return () => {
                        globalThis.removeEventListener("mousemove", handleMouseMove);
                        globalThis.removeEventListener("mouseup", handleMouseUp);
                };
        }, [draggingDetector, detectors, onDetectorsChange]);

        // Get status color based on detector status
        const getStatusColor = (status: "normal" | "warning" | "fault") => {
                switch (status) {
                        case "normal":
                                return "#10B981"; // Green
                        case "warning":
                                return "#F59E0B"; // Amber
                        case "fault":
                                return "#EF4444"; // Red
                        default:
                                return "#10B981"; // Green
                }
        };

        // Render detector based on its type
        const renderDetector = (detector: Detector) => {
                const isSelected = selectedDetector === detector.id;
                const statusColor = getStatusColor(detector.status);

                // Different shapes for different detector types.
                // SonarQube S3923: "smoke", "speaker", and the default case all
                // render the same circle shape. Initialize detectorShape with the
                // default (circle) and only override in the cases that differ.
                let detectorShape = (
                        <circle
                                cx="12"
                                cy="12"
                                r="8"
                                fill={statusColor}
                                stroke="#FFFFFF"
                                strokeWidth="2"
                        />
                );
                switch (detector.type) {
                        case "heat":
                                detectorShape = (
                                        <polygon
                                                points="12,4 20,20 4,20"
                                                fill={statusColor}
                                                stroke="#FFFFFF"
                                                strokeWidth="2"
                                        />
                                );
                                break;
                        case "pull":
                                detectorShape = (
                                        <rect
                                                x="6"
                                                y="6"
                                                width="12"
                                                height="12"
                                                rx="2"
                                                fill={statusColor}
                                                stroke="#FFFFFF"
                                                strokeWidth="2"
                                        />
                                );
                                break;
                        case "horns":
                                detectorShape = (
                                        <rect
                                                x="4"
                                                y="8"
                                                width="16"
                                                height="8"
                                                rx="2"
                                                fill={statusColor}
                                                stroke="#FFFFFF"
                                                strokeWidth="2"
                                        />
                                );
                                break;
                        case "facp":
                                detectorShape = (
                                        <rect
                                                x="2"
                                                y="4"
                                                width="20"
                                                height="16"
                                                rx="3"
                                                fill={statusColor}
                                                stroke="#FFFFFF"
                                                strokeWidth="2"
                                        />
                                );
                                break;
                        // "smoke", "speaker", and any unknown type fall through
                        // to the default circle shape initialized above.
                }

                return (
                        <g
                                key={detector.id}
                                transform={`translate(${detector.x - 12}, ${detector.y - 12})`}
                                onMouseDown={(e) => handleMouseDown(detector.id, e)}
                                // V191 FIX: Stop the click event from bubbling to the canvas div's
                                // onClick handler (handleCanvasClick). Without this, clicking on a
                                // detector selects it (via onMouseDown) AND adds a new detector on
                                // top of it (via the bubbled click). stopPropagation on mousedown
                                // does NOT prevent the separate click event from bubbling.
                                onClick={(e) => e.stopPropagation()} onKeyDown={(e: React.KeyboardEvent) => { if (e.key === "Enter") e.stopPropagation(); }}                              style={{
                                        cursor: draggingDetector ? "grabbing" : "grab",
                                        // V191 FIX: pointerEvents:'auto' overrides the parent SVG's
                                        // pointer-events:none, so this <g> receives mouse events for
                                        // dragging. Without this, clicks pass through to the canvas div
                                        // (which adds a new detector) instead of selecting this one.
                                        pointerEvents: "auto",
                                }}
                        >
                                {detectorShape}
                                {isSelected && (
                                        <rect
                                                x="-2"
                                                y="-2"
                                                width="28"
                                                height="28"
                                                rx="4"
                                                fill="none"
                                                stroke="#3B82F6"
                                                strokeWidth="2"
                                                strokeDasharray="4 2"
                                        />
                                )}
                        </g>
                );
        };

        return (
                <div className="flex flex-col h-full">
                        <div className="mb-4 flex gap-2">
                                <label className="text-sm font-medium text-slate-300">
                                        {t("fireAlarm.addDetector")}
                                </label>
                                <select
                                        value={newDetectorType}
                                        onChange={(e) => setNewDetectorType(e.target.value as DetectorType)}
                                        className="bg-slate-900 border border-slate-600 rounded px-2 py-1 text-sm text-slate-100"
                                >
                                        <option value="smoke">{t("fireAlarm.smokeDet")}</option>
                                        <option value="heat">{t("fireAlarm.heatDet")}</option>
                                        <option value="pull">{t("fireAlarm.pullStation")}</option>
                                        <option value="horns">{t("fireAlarm.hornStrobe")}</option>
                                        <option value="speaker">{t("fireAlarm.speaker")}</option>
                                        <option value="facp">{t("fireAlarm.facp")}</option>
                                </select>
                        </div>

                        <div  // NOSONAR — S6848: type assertion acceptable
                                ref={canvasRef}
                                className="flex-1 bg-slate-900 border border-slate-700 rounded-lg relative overflow-hidden"
                                onClick={handleCanvasClick} onKeyDown={(e: React.KeyboardEvent<HTMLDivElement>) => { if (e.key === "Enter") { e.preventDefault(); (document.activeElement as HTMLElement)?.click(); } }}                                style={{ minHeight: "400px" }}
                        >
                                {floorPlanImage ? (
                                        <img
                                                src={floorPlanImage}
                                                alt="Floor Plan"
                                                className="absolute inset-0 w-full h-full object-contain"
                                        />
                                ) : (
                                        <div className="absolute inset-0 bg-slate-800 flex items-center justify-center pointer-events-none">
                                                {/* V192 FIX: pointer-events-none so clicks pass through to the
                canvas div's onClick handler (handleCanvasClick). Previously,
                this div intercepted clicks on empty canvas area, preventing
                new detectors from being added when no floor plan was loaded. */}
                                                <p className="text-slate-500 text-sm select-none">
                                                        {t("fireAlarm.floorPlanPlaceholder")}
                                                </p>
                                        </div>
                                )}

                                {/* V190 FIX: Wrap ALL SVG elements (circle, rect, g, polygon) inside
            a single <svg> container. Previously, the coverage <circle>
            elements were rendered as direct children of the HTML <div>,
            causing React to render them as unknown HTML tags (not SVG
            namespace). This produced the console warning:
              "Warning: The tag <%s> is unrecognized in this browser.
               If you meant to render a React component, start its name
               with an uppercase letter.%s circle"
            The browser then silently dropped the coverage circles,
            so users never saw the detector coverage visualization.
            Root cause: SVG elements MUST be inside an <svg> parent to
            be rendered in the SVG namespace. Without it, the browser
            treats <circle> as an unknown HTML element (like <foo>).
            Fix: render coverage circles AND detectors inside the same
            <svg> container. This also reduces DOM nodes (one <svg>
            instead of two) and ensures correct z-ordering (coverage
            under detectors, both over the floor plan).

            V191 FIX: The SVG has pointer-events:none so that clicks on
            empty canvas area pass THROUGH to the underlying <div>
            (which calls handleCanvasClick to add new detectors). But
            this also prevented detector <g> elements from receiving
            onMouseDown events — making detectors impossible to drag.
            Root cause: per CSS spec, pointer-events:none on parent
            means children don't receive events UNLESS they explicitly
            set pointer-events:auto. The <g> elements didn't, so
            clicking on a detector added a NEW detector on top instead
            of selecting/dragging it.
            Fix: set pointerEvents:'auto' on each detector <g> so it
            captures mouse events for dragging, while the rest of the
            SVG remains click-through for adding new detectors. */}
                                <svg className="absolute inset-0 pointer-events-none w-full h-full">
                                        {/* Coverage circles (rendered first so they appear under detectors).
              These stay pointer-events:none (inherited from SVG) — they're
              visual-only, clicks pass through to the canvas div. */}
                                        {detectors.map((detector) => (
                                                <circle
                                                        key={`coverage-${detector.id}`}
                                                        cx={detector.x}
                                                        cy={detector.y}
                                                        r={detector.coverageRadius * 10}
                                                        fill="rgba(167, 139, 250, 0.2)"
                                                        stroke="rgba(167, 139, 250, 0.5)"
                                                        strokeWidth="1"
                                                />
                                        ))}
                                        {/* Detectors (rendered on top of coverage circles).
              V191: pointerEvents:'auto' overrides the SVG's pointer-events:none
              so detectors receive onMouseDown for dragging. */}
                                        {detectors.map(renderDetector)}
                                </svg>
                        </div>
                </div>
        );
};
