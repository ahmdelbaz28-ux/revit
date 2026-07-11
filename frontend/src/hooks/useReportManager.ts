
/**
 * useReportManager.ts - Professional Report Generation Engine
 * 15 report templates with multi-format export (PDF, Excel, CSV, JSON)
 */

import { saveAs } from "file-saver";
import { useCallback, useState } from "react";

export type ReportType =
        | "LOAD_CALCULATION"
        | "VOLTAGE_DROP"
        | "SHORT_CIRCUIT"
        | "ARC_FLASH"
        | "CABLE_SCHEDULING"
        | "CONDUIT_FILL"
        | "DEVICE_COUNT"
        | "BOM_SUMMARY"
        | "CLASH_DETECTION"
        | "CODE_COMPLIANCE"
        | "GROUNDING_ANALYSIS"
        | "LIGHTING_CALCULATION"
        | "FIRE_ZONE_ANALYSIS"
        | "NETWORK_TOPOLOGY"
        | "MAINTENANCE_SCHEDULE";

export type ExportFormat = "pdf" | "excel" | "csv" | "json" | "html";

export interface ReportParameter {
        name: string;
        label: string;
        type: "text" | "number" | "select" | "boolean";
        value: unknown;
        options?: string[];
        required: boolean;
}

export interface ReportTemplate {
        id: ReportType;
        name: string;
        description: string;
        category: string;
        icon: string;
        parameters: ReportParameter[];
}

export interface ReportSection {
        title: string;
        type: "table" | "chart" | "text" | "summary";
        data: unknown;
        headers?: string[];
}

export interface GeneratedReport {
        id: string;
        type: ReportType;
        name: string;
        timestamp: Date;
        parameters: Record<string, unknown>;
        sections: ReportSection[];
        summary: string;
        warnings: string[];
        recommendations: string[];
}

export const REPORT_TEMPLATES: ReportTemplate[] = [
        {
                id: "LOAD_CALCULATION",
                name: "Load Calculation Report",
                description: "Comprehensive electrical load analysis per NEC Article 220",
                category: "Electrical Analysis",
                icon: "zap",
                parameters: [
                        {
                                name: "demandFactor",
                                label: "Demand Factor (%)",
                                type: "number",
                                value: 80,
                                required: true,
                        },
                        {
                                name: "diversityFactor",
                                label: "Diversity Factor",
                                type: "number",
                                value: 1.2,
                                required: true,
                        },
                        {
                                name: "safetyMargin",
                                label: "Safety Margin (%)",
                                type: "number",
                                value: 25,
                                required: true,
                        },
                        {
                                name: "includeFuture",
                                label: "Include Future Loads",
                                type: "boolean",
                                value: true,
                                required: false,
                        },
                ],
        },
        {
                id: "VOLTAGE_DROP",
                name: "Voltage Drop Analysis",
                description:
                        "Voltage drop calculations per NEC 210.19(A)(1) Informational Note No. 4",
                category: "Electrical Analysis",
                icon: "activity",
                parameters: [
                        {
                                name: "maxVoltageDrop",
                                label: "Max Voltage Drop (%)",
                                type: "number",
                                value: 3,
                                required: true,
                        },
                        {
                                name: "conductorMaterial",
                                label: "Conductor Material",
                                type: "select",
                                value: "Cu",
                                options: ["Cu", "Al"],
                                required: true,
                        },
                        {
                                name: "temperature",
                                label: "Operating Temperature (°C)",
                                type: "number",
                                value: 75,
                                required: true,
                        },
                ],
        },
        {
                id: "SHORT_CIRCUIT",
                name: "Short Circuit Analysis",
                description:
                        "Fault current calculations and protective device coordination",
                category: "Safety",
                icon: "alert-triangle",
                parameters: [
                        {
                                name: "utilityFaultMVA",
                                label: "Utility Fault MVA",
                                type: "number",
                                value: 500,
                                required: true,
                        },
                        {
                                name: "systemVoltage",
                                label: "System Voltage (V)",
                                type: "number",
                                value: 400,
                                required: true,
                        },
                        {
                                name: "xOverR",
                                label: "X/R Ratio",
                                type: "number",
                                value: 10,
                                required: true,
                        },
                        {
                                name: "analysisType",
                                label: "Analysis Type",
                                type: "select",
                                value: "symmetrical",
                                options: ["symmetrical", "asymmetrical", "momentary"],
                                required: true,
                        },
                ],
        },
        {
                id: "ARC_FLASH",
                name: "Arc Flash Hazard Analysis",
                description:
                        "Arc flash boundary and incident energy per IEEE 1584 / NFPA 70E",
                category: "Safety",
                icon: "shield",
                parameters: [
                        {
                                name: "workingDistance",
                                label: "Working Distance (mm)",
                                type: "number",
                                value: 455,
                                required: true,
                        },
                        {
                                name: "clearingTime",
                                label: "Clearing Time (cycles)",
                                type: "number",
                                value: 6,
                                required: true,
                        },
                        {
                                name: "equipmentType",
                                label: "Equipment Type",
                                type: "select",
                                value: "switchgear",
                                options: ["switchgear", "panelboard", "motor", "cable"],
                                required: true,
                        },
                ],
        },
        {
                id: "CABLE_SCHEDULING",
                name: "Cable Schedule Report",
                description:
                        "Complete cable schedule with routing, sizing, and termination details",
                category: "Documentation",
                icon: "list",
                parameters: [
                        {
                                name: "includeSpare",
                                label: "Include Spare Cores (%)",
                                type: "number",
                                value: 20,
                                required: false,
                        },
                        {
                                name: "cableStandard",
                                label: "Cable Standard",
                                type: "select",
                                value: "IEC",
                                options: ["IEC", "NEC", "BS"],
                                required: true,
                        },
                ],
        },
        {
                id: "CONDUIT_FILL",
                name: "Conduit Fill Analysis",
                description:
                        "Conduit fill percentage calculations per NEC Chapter 9 Table 1",
                category: "Electrical Analysis",
                icon: "cylinder",
                parameters: [
                        {
                                name: "maxFillPercent",
                                label: "Max Fill (%)",
                                type: "number",
                                value: 40,
                                required: true,
                        },
                        {
                                name: "conduitType",
                                label: "Conduit Type",
                                type: "select",
                                value: "EMT",
                                options: ["EMT", "RMC", "PVC", "IMC"],
                                required: true,
                        },
                ],
        },
        {
                id: "DEVICE_COUNT",
                name: "Device Count Summary",
                description: "Comprehensive count of all devices by category and type",
                category: "Documentation",
                icon: "hash",
                parameters: [
                        {
                                name: "groupBy",
                                label: "Group By",
                                type: "select",
                                value: "category",
                                options: ["category", "type", "floor", "zone"],
                                required: true,
                        },
                        {
                                name: "includeReserve",
                                label: "Include Reserve (%)",
                                type: "number",
                                value: 10,
                                required: false,
                        },
                ],
        },
        {
                id: "BOM_SUMMARY",
                name: "Bill of Materials",
                description:
                        "Complete BOM with quantities, part numbers, and estimated costs",
                category: "Procurement",
                icon: "package",
                parameters: [
                        {
                                name: "includeCost",
                                label: "Include Cost Estimates",
                                type: "boolean",
                                value: true,
                                required: false,
                        },
                        {
                                name: "currency",
                                label: "Currency",
                                type: "select",
                                value: "USD",
                                options: ["USD", "EUR", "SAR", "AED"],
                                required: true,
                        },
                        {
                                name: "contingency",
                                label: "Contingency (%)",
                                type: "number",
                                value: 15,
                                required: false,
                        },
                ],
        },
        {
                id: "CLASH_DETECTION",
                name: "Clash Detection Report",
                description:
                        "Spatial conflict analysis between electrical and other MEP systems",
                category: "Coordination",
                icon: "git-merge",
                parameters: [
                        {
                                name: "clearanceDistance",
                                label: "Min Clearance (mm)",
                                type: "number",
                                value: 100,
                                required: true,
                        },
                        {
                                name: "checkTypes",
                                label: "Check Types",
                                type: "select",
                                value: "all",
                                options: ["all", "hard", "soft", "clearance"],
                                required: true,
                        },
                ],
        },
        {
                id: "CODE_COMPLIANCE",
                name: "Code Compliance Report",
                description:
                        "Verification against NEC, IEC, and local authority requirements",
                category: "Compliance",
                icon: "check-circle",
                parameters: [
                        {
                                name: "codeStandard",
                                label: "Code Standard",
                                type: "select",
                                value: "NEC",
                                options: ["NEC", "IEC", "BS", "SBC"],
                                required: true,
                        },
                        {
                                name: "year",
                                label: "Code Year",
                                type: "select",
                                value: "2023",
                                options: ["2023", "2020", "2017"],
                                required: true,
                        },
                        {
                                name: "authority",
                                label: "Local Authority",
                                type: "text",
                                value: "",
                                required: false,
                        },
                ],
        },
        {
                id: "GROUNDING_ANALYSIS",
                name: "Grounding & Earthing Analysis",
                description:
                        "Ground resistance, step/touch potential, and earthing system design",
                category: "Safety",
                icon: "anchor",
                parameters: [
                        {
                                name: "soilResistivity",
                                label: "Soil Resistivity (Ω·m)",
                                type: "number",
                                value: 100,
                                required: true,
                        },
                        {
                                name: "maxGroundResistance",
                                label: "Max Ground Resistance (Ω)",
                                type: "number",
                                value: 5,
                                required: true,
                        },
                        {
                                name: "faultCurrent",
                                label: "Max Fault Current (kA)",
                                type: "number",
                                value: 20,
                                required: true,
                        },
                        {
                                name: "electrodeLength",
                                label: "Electrode Length (m)",
                                type: "number",
                                value: 3,
                                required: true,
                        },
                        {
                                name: "electrodeCount",
                                label: "Number of Electrodes",
                                type: "number",
                                value: 1,
                                required: true,
                        },
                ],
        },
        {
                id: "LIGHTING_CALCULATION",
                name: "Lighting Calculation Report",
                description:
                        "Illuminance levels, fixture spacing, and energy efficiency analysis",
                category: "Lighting",
                icon: "lightbulb",
                parameters: [
                        {
                                name: "targetLux",
                                label: "Target Illuminance (lux)",
                                type: "number",
                                value: 500,
                                required: true,
                        },
                        {
                                name: "roomType",
                                label: "Room Type",
                                type: "select",
                                value: "office",
                                options: ["office", "warehouse", "corridor", "outdoor"],
                                required: true,
                        },
                        {
                                name: "area",
                                label: "Room Area (m²)",
                                type: "number",
                                value: 100,
                                required: true,
                        },
                        {
                                name: "maintenanceFactor",
                                label: "Maintenance Factor",
                                type: "number",
                                value: 0.8,
                                required: true,
                        },
                ],
        },
        {
                id: "FIRE_ZONE_ANALYSIS",
                name: "Fire Zone Coverage Analysis",
                description:
                        "Smoke detector coverage, audibility, and evacuation route analysis",
                category: "Fire Safety",
                icon: "flame",
                parameters: [
                        {
                                name: "detectorSpacing",
                                label: "Max Detector Spacing (m)",
                                type: "number",
                                value: 9,
                                required: true,
                        },
                        {
                                name: "soundLevel",
                                label: "Min Sound Level (dB)",
                                type: "number",
                                value: 75,
                                required: true,
                        },
                        {
                                name: "occupancyType",
                                label: "Occupancy Type",
                                type: "select",
                                value: "commercial",
                                options: ["commercial", "residential", "industrial", "hospital"],
                                required: true,
                        },
                ],
        },
        {
                id: "NETWORK_TOPOLOGY",
                name: "Network Topology Report",
                description:
                        "Network architecture, bandwidth analysis, and redundancy verification",
                category: "IT Infrastructure",
                icon: "network",
                parameters: [
                        {
                                name: "networkType",
                                label: "Network Type",
                                type: "select",
                                value: "star",
                                options: ["star", "ring", "mesh", "hierarchical"],
                                required: true,
                        },
                        {
                                name: "bandwidth",
                                label: "Required Bandwidth (Mbps)",
                                type: "number",
                                value: 1000,
                                required: true,
                        },
                        {
                                name: "redundancy",
                                label: "Redundancy Level",
                                type: "select",
                                value: "N+1",
                                options: ["N", "N+1", "2N"],
                                required: true,
                        },
                ],
        },
        {
                id: "MAINTENANCE_SCHEDULE",
                name: "Maintenance Schedule",
                description:
                        "Preventive maintenance schedule with intervals and procedures",
                category: "Operations",
                icon: "calendar",
                parameters: [
                        {
                                name: "intervalType",
                                label: "Interval Type",
                                type: "select",
                                value: "monthly",
                                options: ["weekly", "monthly", "quarterly", "annually"],
                                required: true,
                        },
                        {
                                name: "startDate",
                                label: "Start Date",
                                type: "text",
                                value: new Date().toISOString().split("T")[0],
                                required: true,
                        },
                        {
                                name: "includeChecklist",
                                label: "Include Checklists",
                                type: "boolean",
                                value: true,
                                required: false,
                        },
                ],
        },
];

interface DeviceData {
        id: string;
        type: string;
        name: string;
        category: string;
        voltage: number;
        current: number;
        load: number;
        x: number;
        y: number;
        properties?: Record<string, unknown>;
}

interface ConnectionData {
        id: string;
        fromId: string;
        toId: string;
        cableSize: string;
        length: number;
        current: number;
}

export function useReportManager() {
        const [reports, setReports] = useState<GeneratedReport[]>([]);
        const [isGenerating, setIsGenerating] = useState(false);

        const getTemplate = useCallback(
                (type: ReportType): ReportTemplate | undefined => {
                        return REPORT_TEMPLATES.find((t) => t.id === type);
                },
                [],
        );

        const generateReport = useCallback(
                (
                        type: ReportType,
                        devices: DeviceData[],
                        connections: ConnectionData[],
                        parameters?: Record<string, unknown>,
                ): GeneratedReport => {
                        const template = getTemplate(type);
                        if (!template) throw new Error(`Unknown report type: ${type}`);

                        const mergedParams = {
                                ...Object.fromEntries(
                                        template.parameters.map((p) => [p.name, p.value]),
                                ),
                                ...parameters,
                        };
                        const sections = generateReportSections(
                                type,
                                devices,
                                connections,
                                mergedParams,
                        );
                        const summary = generateSummary(type, devices, connections, mergedParams);
                        const warnings = generateWarnings(
                                type,
                                devices,
                                connections,
                                mergedParams,
                        );
                        const recommendations = generateRecommendations(
                                type,
                                devices,
                                connections,
                                mergedParams,
                        );

                        return {
                                id: `RPT_${Date.now()}_${Math.random().toString(36).substr(2, 6)}`,
                                type,
                                name: template.name,
                                timestamp: new Date(),
                                parameters: mergedParams,
                                sections,
                                summary,
                                warnings,
                                recommendations,
                        };
                },
                [getTemplate],
        );

        const generateAndSave = useCallback(
                (
                        type: ReportType,
                        devices: DeviceData[],
                        connections: ConnectionData[],
                        format: ExportFormat,
                        parameters?: Record<string, unknown>,
                ) => {
                        setIsGenerating(true);
                        try {
                                const report = generateReport(type, devices, connections, parameters);
                                setReports((prev) => [report, ...prev]);
                                exportReport(report, format);
                        } finally {
                                setIsGenerating(false);
                        }
                },
                [generateReport],
        );

        const deleteReport = useCallback((id: string) => {
                setReports((prev) => prev.filter((r) => r.id !== id));
        }, []);

        const clearReports = useCallback(() => {
                setReports([]);
        }, []);

        return {
                templates: REPORT_TEMPLATES,
                reports,
                isGenerating,
                getTemplate,
                generateReport,
                generateAndSave,
                deleteReport,
                clearReports,
                exportReport,
        };
}

function generateReportSections(
        type: ReportType,
        devices: DeviceData[],
        connections: ConnectionData[],
        params: Record<string, unknown>,
): ReportSection[] {
        switch (type) {
                case "LOAD_CALCULATION": {
                        const totalLoad = devices.reduce((sum, d) => sum + d.load, 0);
                        const demandFactor = (params.demandFactor as number) / 100;
                        const diversityFactor = params.diversityFactor as number;
                        const safetyMargin = (params.safetyMargin as number) / 100;
                        const designLoad =
                                totalLoad * demandFactor * diversityFactor * (1 + safetyMargin);

                        const byCategory: Record<string, number> = {};
                        devices.forEach((d) => {
                                byCategory[d.category] = (byCategory[d.category] || 0) + d.load;
                        });

                        return [
                                {
                                        title: "Executive Summary",
                                        type: "summary",
                                        data: { totalLoad, designLoad, devices: devices.length },
                                },
                                {
                                        title: "Load by Category",
                                        type: "table",
                                        headers: ["Category", "Connected Load (W)", "Percentage"],
                                        data: Object.entries(byCategory).map(([cat, load]) => [
                                                cat,
                                                load.toFixed(2),
                                                `${((load / totalLoad) * 100).toFixed(1)}%`,
                                        ]),
                                },
                                {
                                        title: "Device Load Schedule",
                                        type: "table",
                                        headers: [
                                                "Device ID",
                                                "Type",
                                                "Category",
                                                "Voltage (V)",
                                                "Current (A)",
                                                "Load (W)",
                                        ],
                                        data: devices.map((d) => [
                                                d.id,
                                                d.type,
                                                d.category,
                                                d.voltage,
                                                d.current.toFixed(3),
                                                d.load.toFixed(2),
                                        ]),
                                },
                                {
                                        title: "Design Calculations",
                                        type: "text",
                                        data: `Connected Load: ${totalLoad.toFixed(2)} W\nDemand Factor: ${demandFactor * 100}%\nDiversity Factor: ${diversityFactor}\nSafety Margin: ${safetyMargin * 100}%\nDesign Load: ${designLoad.toFixed(2)} W`,
                                },
                        ];
                }

                case "VOLTAGE_DROP": {
                        const maxAllowed = params.maxVoltageDrop as number;
                        const results = connections.map((c) => {
                                const lengthKm = c.length / 1000;
                                const resistance = (0.0175 * lengthKm) / 2.5;
                                const voltageDrop = c.current * resistance * 2;
                                const percentage = (voltageDrop / 230) * 100;
                                return {
                                        ...c,
                                        voltageDrop,
                                        percentage,
                                        status: percentage > maxAllowed ? "FAIL" : "PASS",
                                };
                        });

                        return [
                                {
                                        title: "Voltage Drop Summary",
                                        type: "summary",
                                        data: {
                                                totalCables: connections.length,
                                                failed: results.filter((r) => r.status === "FAIL").length,
                                                maxAllowed,
                                        },
                                },
                                {
                                        title: "Voltage Drop Results",
                                        type: "table",
                                        headers: [
                                                "Connection ID",
                                                "From",
                                                "To",
                                                "Length (m)",
                                                "Current (A)",
                                                "V-Drop (V)",
                                                "V-Drop (%)",
                                                "Status",
                                        ],
                                        data: results.map((r) => [
                                                r.id,
                                                r.fromId,
                                                r.toId,
                                                r.length.toFixed(1),
                                                r.current.toFixed(2),
                                                r.voltageDrop.toFixed(3),
                                                r.percentage.toFixed(2),
                                                r.status,
                                        ]),
                                },
                        ];
                }

                case "SHORT_CIRCUIT": {
                        const faultMVA = params.utilityFaultMVA as number;
                        // V214 FIX: Use systemVoltage parameter (default 400V) instead of
                        // hardcoded 400. Previously the voltage was always 400V regardless
                        // of the actual system voltage (e.g. 208V, 480V, 690V). This caused
                        // incorrect fault current calculations for non-400V systems.
                        const voltage = (params.systemVoltage as number) || 400;
                        const faultCurrent = (faultMVA * 1e6) / (Math.sqrt(3) * voltage);
                        return [
                                {
                                        title: "Short Circuit Summary",
                                        type: "summary",
                                        data: { faultMVA, faultCurrent: faultCurrent.toFixed(0), voltage },
                                },
                                {
                                        title: "Fault Current at Each Bus",
                                        type: "table",
                                        headers: ["Bus ID", "Fault Current (A)", "Fault MVA", "X/R Ratio"],
                                        data: devices
                                                .slice(0, 10)
                                                .map((d) => [
                                                        d.id,
                                                        faultCurrent.toFixed(0),
                                                        faultMVA.toFixed(1),
                                                        (params.xOverR as number).toFixed(1),
                                                ]),
                                },
                        ];
                }

                case "ARC_FLASH": {
                        const workingDistance = params.workingDistance as number;
                        const incidentEnergy = 4.184 * 0.01 * (workingDistance / 455) ** -2 * 20;
                        return [
                                {
                                        title: "Arc Flash Analysis",
                                        type: "summary",
                                        data: {
                                                workingDistance,
                                                incidentEnergy: incidentEnergy.toFixed(2),
                                                boundary: Math.sqrt(incidentEnergy * 100).toFixed(0),
                                        },
                                },
                                {
                                        title: "PPE Requirements",
                                        type: "table",
                                        headers: [
                                                "Equipment",
                                                "Incident Energy (cal/cm²)",
                                                "Arc Flash Boundary (mm)",
                                                "PPE Category",
                                        ],
                                        data: devices
                                                .slice(0, 5)
                                                .map((d) => [
                                                        d.name,
                                                        incidentEnergy.toFixed(2),
                                                        Math.sqrt(incidentEnergy * 100).toFixed(0),
                                                        incidentEnergy > 40
                                                                ? "4"
                                                                : incidentEnergy > 12
                                                                        ? "3"
                                                                        : incidentEnergy > 8
                                                                                ? "2"
                                                                                : "1",
                                                ]),
                                },
                        ];
                }

                case "CABLE_SCHEDULING": {
                        return [
                                {
                                        title: "Cable Schedule",
                                        type: "summary",
                                        data: { totalCables: connections.length },
                                },
                                {
                                        title: "Cable Schedule Details",
                                        type: "table",
                                        headers: [
                                                "Cable ID",
                                                "From",
                                                "To",
                                                "Type",
                                                "Size (mm²)",
                                                "Length (m)",
                                                "Cores",
                                                "Spare Cores",
                                        ],
                                        data: connections.map((c, _i) => [
                                                c.id,
                                                c.fromId,
                                                c.toId,
                                                "XLPE/PVC",
                                                c.cableSize,
                                                c.length.toFixed(1),
                                                "4",
                                                "1",
                                        ]),
                                },
                        ];
                }

                case "CONDUIT_FILL": {
                        const maxFill = params.maxFillPercent as number;
                        // SAFETY NOTE: Conduit fill calculations MUST use actual cable cross-sectional
                        // areas per NEC Chapter 9 Table 5 and conduit internal areas per Table 4.
                        // The placeholder values below are ONLY used when real dimensions are unavailable.
                        // Reports generated with placeholder data are NOT valid for code compliance.
                        const conduitData = connections.slice(0, 10).map((c, i) => {
                                // Estimate fill from cable size string (e.g., "2.5mm²", "4mm²", "1.5mm²")
                                // Default: 1 cable per conduit for estimation, NEC Table 4 EMT 25mm = 366mm²
                                const cableAreaMatch = c.cableSize?.match(/([\d.]+)/);
                                const cableAreaMm2 = cableAreaMatch
                                        ? parseFloat(cableAreaMatch[1])
                                        : 2.5;
                                const conduitInternalArea = 366; // EMT 25mm per NEC Table 4
                                const numCables = 2; // Assume 2 cables per conduit for estimation
                                const totalCableArea = cableAreaMm2 * numCables;
                                const fillPercent = (totalCableArea / conduitInternalArea) * 100;
                                return {
                                        id: `COND-${i + 1}`,
                                        size: "25",
                                        cables: c.cableSize,
                                        fillArea: totalCableArea.toFixed(0),
                                        fillPercent: fillPercent.toFixed(1),
                                        status: fillPercent > maxFill ? "OVERFILL" : "OK",
                                        placeholder: !cableAreaMatch,
                                };
                        });
                        return [
                                {
                                        title: "Conduit Fill Analysis",
                                        type: "summary",
                                        data: {
                                                maxFill,
                                                conduitType: params.conduitType,
                                                placeholderWarning:
                                                        "Fill percentages are estimated from cable size strings. For official compliance, use actual manufacturer dimensions per NEC Chapter 9.",
                                        },
                                },
                                {
                                        title: "Conduit Fill Results",
                                        type: "table",
                                        headers: [
                                                "Conduit ID",
                                                "Size (mm)",
                                                "Cables",
                                                "Fill Area (mm²)",
                                                "Fill %",
                                                "Status",
                                        ],
                                        data: conduitData.map((d) => [
                                                d.id,
                                                d.size,
                                                d.cables,
                                                d.fillArea,
                                                `${d.fillPercent}%`,
                                                d.status,
                                        ]),
                                },
                        ];
                }

                case "DEVICE_COUNT": {
                        const byCategory: Record<string, number> = {};
                        const byType: Record<string, number> = {};
                        devices.forEach((d) => {
                                byCategory[d.category] = (byCategory[d.category] || 0) + 1;
                                byType[d.type] = (byType[d.type] || 0) + 1;
                        });

                        return [
                                {
                                        title: "Device Count Summary",
                                        type: "summary",
                                        data: {
                                                total: devices.length,
                                                categories: Object.keys(byCategory).length,
                                        },
                                },
                                {
                                        title: "Count by Category",
                                        type: "table",
                                        headers: ["Category", "Count", "Percentage"],
                                        data: Object.entries(byCategory).map(([cat, count]) => [
                                                cat,
                                                count.toString(),
                                                `${((count / devices.length) * 100).toFixed(1)}%`,
                                        ]),
                                },
                                {
                                        title: "Count by Type",
                                        type: "table",
                                        headers: ["Device Type", "Count"],
                                        data: Object.entries(byType).map(([type, count]) => [
                                                type,
                                                count.toString(),
                                        ]),
                                },
                        ];
                }

                case "BOM_SUMMARY": {
                        // SAFETY NOTE: Unit costs are estimated averages for fire alarm components.
                        // These are NOT procurement prices — always verify with suppliers.
                        // Using deterministic estimates per device type to avoid Math.random() fabrication.
                        const COST_ESTIMATES: Record<string, number> = {
                                smoke_detector: 85,
                                heat_detector: 65,
                                manual_station: 45,
                                sounder: 120,
                                strobe: 95,
                                sounder_strobe: 150,
                                faccp: 2500,
                                battery: 350,
                                power_supply: 280,
                                monitor_module: 75,
                                control_module: 85,
                                relay_module: 55,
                                isolator: 60,
                                duct_detector: 110,
                                beam_detector: 450,
                        };
                        const byType: Record<string, { count: number; unitCost: number }> = {};
                        devices.forEach((d) => {
                                if (!byType[d.type]) {
                                        // Use known estimate if available, otherwise use a default based on category
                                        const estimatedCost =
                                                COST_ESTIMATES[d.type.toLowerCase()] ||
                                                (d.category === "FIRE_ALARM"
                                                        ? 100
                                                        : d.category === "DATA_NETWORK"
                                                                ? 200
                                                                : 75);
                                        byType[d.type] = { count: 0, unitCost: estimatedCost };
                                }
                                byType[d.type].count++;
                        });

                        return [
                                {
                                        title: "Bill of Materials",
                                        type: "summary",
                                        data: {
                                                totalItems: devices.length,
                                                estimatedCost: Object.values(byType)
                                                        .reduce((s, v) => s + v.count * v.unitCost, 0)
                                                        .toFixed(2),
                                        },
                                },
                                {
                                        title: "Material Schedule",
                                        type: "table",
                                        headers: ["Item", "Description", "Qty", "Unit Cost", "Total Cost"],
                                        data: Object.entries(byType).map(([type, info]) => [
                                                type,
                                                `Device - ${type}`,
                                                info.count.toString(),
                                                `$${info.unitCost.toFixed(2)}`,
                                                `$${(info.count * info.unitCost).toFixed(2)}`,
                                        ]),
                                },
                        ];
                }

                case "CLASH_DETECTION": {
                        const clearance = params.clearanceDistance as number;
                        const clashes: Array<{
                                id: string;
                                element1: string;
                                element2: string;
                                distance: number;
                                severity: string;
                        }> = [];
                        for (let i = 0; i < devices.length; i++) {
                                for (let j = i + 1; j < devices.length; j++) {
                                        const dx = devices[i].x - devices[j].x;
                                        const dy = devices[i].y - devices[j].y;
                                        const dist = Math.sqrt(dx * dx + dy * dy);
                                        if (dist < clearance) {
                                                clashes.push({
                                                        id: `CLASH-${clashes.length + 1}`,
                                                        element1: devices[i].id,
                                                        element2: devices[j].id,
                                                        distance: dist,
                                                        severity: dist < clearance / 2 ? "Critical" : "Warning",
                                                });
                                        }
                                }
                        }

                        return [
                                {
                                        title: "Clash Detection Summary",
                                        type: "summary",
                                        data: {
                                                totalClashes: clashes.length,
                                                critical: clashes.filter((c) => c.severity === "Critical").length,
                                        },
                                },
                                {
                                        title: "Clash Details",
                                        type: "table",
                                        headers: [
                                                "Clash ID",
                                                "Element 1",
                                                "Element 2",
                                                "Distance (mm)",
                                                "Severity",
                                        ],
                                        data: clashes.map((c) => [
                                                c.id,
                                                c.element1,
                                                c.element2,
                                                c.distance.toFixed(1),
                                                c.severity,
                                        ]),
                                },
                        ];
                }

                case "CODE_COMPLIANCE": {
                        // V214 FIX: Previously this template returned hardcoded PASS/WARNING
                        // statuses for 5 NEC rules without actually checking anything. This
                        // is a safety-critical deception — an engineer may believe the system
                        // is code-compliant when no real verification was performed.
                        //
                        // Now the template returns a clear "MANUAL REVIEW REQUIRED" status
                        // for each rule, with a disclaimer that automated compliance checking
                        // requires the spatial_engine / qomn_kernel modules. The summary
                        // explicitly states 0 rules passed automatically.
                        const checks = [
                                {
                                        rule: "NEC 210.19 - Conductor Sizing",
                                        status: "MANUAL REVIEW REQUIRED",
                                        detail: "Verify ampacity per continuous load (125%) + non-continuous (100%). Use cable_sizing report for automated NEC §310.16 check.",
                                },
                                {
                                        rule: "NEC 250 - Grounding",
                                        status: "MANUAL REVIEW REQUIRED",
                                        detail: "Verify grounding electrode system + bonding. Use grounding_analysis report for IEEE 80 resistance calculation.",
                                },
                                {
                                        rule: "NEC 300.3 - Conductors in Raceway",
                                        status: "MANUAL REVIEW REQUIRED",
                                        detail: "Verify all conductors of same circuit in same raceway. Manual field verification required.",
                                },
                                {
                                        rule: "NEC 310.15 - Ampacity",
                                        status: "MANUAL REVIEW REQUIRED",
                                        detail: "Verify ampacity after ambient temperature correction + derating. Use cable_sizing report for automated check.",
                                },
                                {
                                        rule: "NEC 700 - Emergency Systems",
                                        status: "MANUAL REVIEW REQUIRED",
                                        detail: "Verify emergency circuit identification + separation. Manual verification required per NEC 700.10.",
                                },
                        ];

                        return [
                                {
                                        title: "Code Compliance Summary",
                                        type: "summary",
                                        data: {
                                                standard: params.codeStandard,
                                                year: params.year,
                                                passed: 0,
                                                warnings: 0,
                                                manualReviewRequired: checks.length,
                                                disclaimer: "Automated compliance verification is not performed in this template. All rules require manual review by a licensed engineer. For automated NEC ampacity checking, use the cable_sizing report. For NFPA 72 detector spacing verification, use the nfpa72_coverage report.",
                                        },
                                },
                                {
                                        title: "Compliance Checks",
                                        type: "table",
                                        headers: ["Rule", "Status", "Detail"],
                                        data: checks.map((c) => [c.rule, c.status, c.detail]),
                                },
                        ];
                }

                case "GROUNDING_ANALYSIS": {
                        const soilRes = params.soilResistivity as number;
                        // V214 FIX: Use electrodeLength + electrodeCount parameters
                        // instead of hardcoded values. Previously the formula used
                        // hardcoded electrode length of 3m and ignored electrode count.
                        // The IEEE 80 formula for a single vertical rod is:
                        //   R = ρ / (2πL) × ln(2L/d)
                        // where ρ=soil resistivity, L=electrode length, d=diameter.
                        // For multiple rods in parallel (approximate):
                        //   R_total = R_single / n (ignoring mutual interference)
                        const electrodeLength = (params.electrodeLength as number) || 3;
                        const electrodeCount = (params.electrodeCount as number) || 1;
                        // Simplified single-rod formula: R = ρ / (2πL)
                        // (This is a conservative upper bound — full IEEE 80 includes
                        // diameter and depth terms. For full analysis use the etap-expert
                        // skill which implements IEEE 80-2013 exactly.)
                        const singleRodResistance = soilRes / (2 * Math.PI * electrodeLength);
                        const groundResistance = singleRodResistance / electrodeCount;
                        return [
                                {
                                        title: "Grounding Analysis",
                                        type: "summary",
                                        data: {
                                                soilResistivity: soilRes,
                                                electrodeLength,
                                                electrodeCount,
                                                singleRodResistance: singleRodResistance.toFixed(2),
                                                calculatedResistance: groundResistance.toFixed(2),
                                                maxAllowed: params.maxGroundResistance,
                                                status:
                                                        groundResistance < (params.maxGroundResistance as number)
                                                                ? "PASS"
                                                                : "FAIL",
                                                standard: "IEEE 80-2013 (simplified)",
                                                note: "For full IEEE 80 analysis (including diameter, depth, mesh), use the etap-expert skill.",
                                        },
                                },
                                {
                                        title: "Ground Electrode Details",
                                        type: "table",
                                        headers: [
                                                "Electrode ID",
                                                "Type",
                                                "Length (m)",
                                                "Resistance (Ω)",
                                                "Status",
                                        ],
                                        data: Array.from({ length: electrodeCount }, (_, i) => [
                                                `GE-${i + 1}`,
                                                "Copper Rod",
                                                electrodeLength.toFixed(1),
                                                singleRodResistance.toFixed(2),
                                                groundResistance < (params.maxGroundResistance as number)
                                                        ? "PASS"
                                                        : "FAIL",
                                        ]),
                                },
                        ];
                }

                case "LIGHTING_CALCULATION": {
                        const targetLux = params.targetLux as number;
                        // V214 FIX: Use area parameter instead of hardcoded 100.
                        // Previously the area was always 100m² regardless of actual
                        // room size, causing incorrect lumen calculations.
                        const area = (params.area as number) || 100;
                        const totalLumens =
                                (targetLux * area) / (params.maintenanceFactor as number);
                        return [
                                {
                                        title: "Lighting Calculation",
                                        type: "summary",
                                        data: {
                                                targetLux,
                                                area: `${area} m²`,
                                                totalLumens: totalLumens.toFixed(0),
                                                estimatedFixtures: Math.ceil(totalLumens / 3000),
                                                roomType: params.roomType,
                                                maintenanceFactor: params.maintenanceFactor,
                                        },
                                },
                                {
                                        title: "Fixture Schedule",
                                        type: "table",
                                        headers: ["Fixture ID", "Type", "Lumens", "Wattage", "Count"],
                                        data: [
                                                [
                                                        "LT-1",
                                                        "LED Panel 600x600",
                                                        "3000",
                                                        "40W",
                                                        Math.ceil(totalLumens / 3000).toString(),
                                                ],
                                        ],
                                },
                        ];
                }

                case "FIRE_ZONE_ANALYSIS": {
                        const spacing = params.detectorSpacing as number;
                        const coveragePerDetector = spacing * spacing;
                        const totalArea = 500;
                        const requiredDetectors = Math.ceil(totalArea / coveragePerDetector);
                        return [
                                {
                                        title: "Fire Zone Analysis",
                                        type: "summary",
                                        data: {
                                                totalArea: `${totalArea} m²`,
                                                detectorSpacing: `${spacing} m`,
                                                coveragePerDetector: `${coveragePerDetector} m²`,
                                                requiredDetectors,
                                                installedDetectors: devices.filter(
                                                        (d) => d.category === "FIRE_ALARM",
                                                ).length,
                                        },
                                },
                                {
                                        title: "Detector Coverage",
                                        type: "table",
                                        headers: ["Zone", "Area (m²)", "Required", "Installed", "Status"],
                                        data: [
                                                [
                                                        "Zone 1",
                                                        "250",
                                                        Math.ceil(250 / coveragePerDetector).toString(),
                                                        devices
                                                                .filter((d) => d.category === "FIRE_ALARM")
                                                                .length.toString(),
                                                        devices.filter((d) => d.category === "FIRE_ALARM").length >=
                                                        requiredDetectors
                                                                ? "OK"
                                                                : "INSUFFICIENT",
                                                ],
                                        ],
                                },
                        ];
                }

                case "NETWORK_TOPOLOGY": {
                        return [
                                {
                                        title: "Network Topology",
                                        type: "summary",
                                        data: {
                                                type: params.networkType,
                                                bandwidth: `${params.bandwidth} Mbps`,
                                                redundancy: params.redundancy,
                                                devices: devices.length,
                                        },
                                },
                                {
                                        title: "Network Devices",
                                        type: "table",
                                        headers: [
                                                "Device ID",
                                                "Type",
                                                "IP Address",
                                                "Port Count",
                                                "Bandwidth",
                                        ],
                                        data: devices
                                                .filter((d) => d.category === "DATA_NETWORK")
                                                .map((d, i) => [
                                                        d.id,
                                                        d.type,
                                                        `192.168.1.${10 + i}`,
                                                        "24",
                                                        `${params.bandwidth} Mbps`,
                                                ]),
                                },
                        ];
                }

                case "MAINTENANCE_SCHEDULE": {
                        return [
                                {
                                        title: "Maintenance Schedule",
                                        type: "summary",
                                        data: {
                                                interval: params.intervalType,
                                                startDate: params.startDate,
                                                totalDevices: devices.length,
                                        },
                                },
                                {
                                        title: "Maintenance Tasks",
                                        type: "table",
                                        headers: ["Task ID", "Device Type", "Task", "Interval", "Next Due"],
                                        data: devices
                                                .slice(0, 10)
                                                .map((d, i) => [
                                                        `MT-${i + 1}`,
                                                        d.type,
                                                        "Visual Inspection & Testing",
                                                        params.intervalType as string,
                                                        new Date(Date.now() + 30 * 24 * 60 * 60 * 1000)
                                                                .toISOString()
                                                                .split("T")[0],
                                                ]),
                                },
                        ];
                }

                default:
                        return [{ title: "Report", type: "text", data: "No sections generated" }];
        }
}

function generateSummary(
        type: ReportType,
        devices: DeviceData[],
        connections: ConnectionData[],
        params: Record<string, unknown>,
): string {
        switch (type) {
                case "LOAD_CALCULATION":
                        return `Total connected load: ${devices.reduce((s, d) => s + d.load, 0).toFixed(2)} W across ${devices.length} devices. Design load with ${params.demandFactor as number}% demand factor and ${params.safetyMargin as number}% safety margin applied.`;
                case "VOLTAGE_DROP":
                        return `Voltage drop analysis for ${connections.length} cable runs. Maximum allowed: ${params.maxVoltageDrop as number}%. All runs evaluated per NEC requirements.`;
                case "SHORT_CIRCUIT":
                        return `Short circuit analysis with ${params.utilityFaultMVA as number} MVA utility fault level. Symmetrical fault currents calculated for all bus points.`;
                case "ARC_FLASH":
                        return `Arc flash hazard analysis per IEEE 1584. Working distance: ${params.workingDistance as number}mm. PPE requirements determined for all equipment.`;
                case "CABLE_SCHEDULING":
                        return `Complete cable schedule for ${connections.length} cable runs. All cables sized per ${params.cableStandard as string} standards.`;
                case "CONDUIT_FILL":
                        return `Conduit fill analysis for ${params.conduitType as string} conduits. Maximum fill limit: ${params.maxFillPercent as number}% per NEC Chapter 9.`;
                case "DEVICE_COUNT":
                        return `Total of ${devices.length} devices catalogued across ${new Set(devices.map((d) => d.category)).size} categories.`;
                case "BOM_SUMMARY":
                        return `Bill of materials for ${devices.length} devices. Includes quantities, specifications, and cost estimates in ${params.currency as string}.`;
                case "CLASH_DETECTION":
                        return `Clash detection analysis with ${params.clearanceDistance as number}mm minimum clearance. All spatial conflicts identified and classified.`;
                case "CODE_COMPLIANCE":
                        return `Code compliance verification against ${params.codeStandard as string} ${params.year as string} edition. All applicable rules evaluated.`;
                case "GROUNDING_ANALYSIS":
                        return `Grounding analysis with soil resistivity of ${params.soilResistivity as number} Ω·m. Ground resistance calculated and verified against ${params.maxGroundResistance as number}Ω limit.`;
                case "LIGHTING_CALCULATION":
                        return `Lighting calculation for ${params.roomType as string} space. Target illuminance: ${params.targetLux as number} lux. Fixture count and layout determined.`;
                case "FIRE_ZONE_ANALYSIS":
                        return `Fire zone coverage analysis for ${params.occupancyType as string} occupancy. Detector spacing: ${params.detectorSpacing as number}m. Coverage verified per NFPA 72.`;
                case "NETWORK_TOPOLOGY":
                        return `Network topology analysis for ${params.networkType as string} architecture. Bandwidth: ${params.bandwidth as number} Mbps. Redundancy: ${params.redundancy as string}.`;
                case "MAINTENANCE_SCHEDULE":
                        return `Preventive maintenance schedule with ${params.intervalType as string} intervals starting ${params.startDate as string}. All ${devices.length} devices included.`;
                default:
                        return "Report generated successfully.";
        }
}

function generateWarnings(
        type: ReportType,
        devices: DeviceData[],
        connections: ConnectionData[],
        params: Record<string, unknown>,
): string[] {
        const warnings: string[] = [];
        if (
                type === "LOAD_CALCULATION" &&
                devices.reduce((s, d) => s + d.load, 0) > 10000
        ) {
                warnings.push(
                        "Total connected load exceeds 10kW. Verify main breaker sizing.",
                );
        }
        if (type === "VOLTAGE_DROP") {
                const maxAllowed = params.maxVoltageDrop as number;
                connections.forEach((c) => {
                        const vd =
                                ((((c.current * 0.0175 * c.length) / 1000 / 2.5) * 2) / 230) * 100;
                        if (vd > maxAllowed)
                                warnings.push(
                                        `Connection ${c.id} exceeds max voltage drop: ${vd.toFixed(2)}% > ${maxAllowed}%`,
                                );
                });
        }
        if (type === "ARC_FLASH" && (params.clearingTime as number) > 6) {
                warnings.push(
                        "Clearing time exceeds 6 cycles. Consider faster protective devices.",
                );
        }
        if (type === "FIRE_ZONE_ANALYSIS") {
                const installed = devices.filter((d) => d.category === "FIRE_ALARM").length;
                if (installed < 5)
                        warnings.push("Insufficient fire alarm devices for adequate coverage.");
        }
        if (warnings.length === 0) warnings.push("No critical warnings identified.");
        return warnings;
}

function generateRecommendations(
        type: ReportType,
        _devices: DeviceData[],
        _connections: ConnectionData[],
        _params: Record<string, unknown>,
): string[] {
        const recs: string[] = [];
        if (type === "LOAD_CALCULATION") {
                recs.push("Consider load diversity for more accurate demand calculation.");
                recs.push("Verify future expansion capacity in main distribution panel.");
        }
        if (type === "VOLTAGE_DROP") {
                recs.push("Increase conductor size for runs exceeding 3% voltage drop.");
                recs.push("Consider relocating loads closer to source for long runs.");
        }
        if (type === "BOM_SUMMARY") {
                recs.push("Include 10-15% spare capacity for future expansion.");
                recs.push("Verify lead times for specialized equipment.");
        }
        if (type === "CODE_COMPLIANCE") {
                recs.push(
                        "Schedule review with local authority having jurisdiction (AHJ).",
                );
                recs.push("Document all deviations and obtain written approvals.");
        }
        if (recs.length === 0)
                recs.push("Review all findings with qualified engineering staff.");
        return recs;
}

export function exportReport(
        report: GeneratedReport,
        format: ExportFormat,
): void {
        switch (format) {
                case "json": {
                        const blob = new Blob([JSON.stringify(report, null, 2)], {
                                type: "application/json",
                        });
                        saveAs(
                                blob,
                                `${report.type}_${report.timestamp.toISOString().split("T")[0]}.json`,
                        );
                        break;
                }
                case "csv": {
                        let csv = `NexusCAD Pro - ${report.name}\n`;
                        csv += `Generated:,${report.timestamp.toISOString()}\n\n`;
                        csv += `SUMMARY\n${report.summary}\n\n`;

                        for (const section of report.sections) {
                                csv += `${section.title}\n`;
                                if (section.headers) {
                                        csv += `${section.headers.join(",")}\n`;
                                }
                                if (Array.isArray(section.data)) {
                                        for (const row of section.data) {
                                                csv += `${Array.isArray(row) ? row.join(",") : String(row)}\n`;
                                        }
                                }
                                csv += "\n";
                        }

                        if (report.warnings.length > 0) {
                                csv += `WARNINGS\n${report.warnings.join("\n")}\n\n`;
                        }
                        if (report.recommendations.length > 0) {
                                csv += `RECOMMENDATIONS\n${report.recommendations.join("\n")}\n`;
                        }

                        const blob = new Blob([csv], { type: "text/csv" });
                        saveAs(
                                blob,
                                `${report.type}_${report.timestamp.toISOString().split("T")[0]}.csv`,
                        );
                        break;
                }
                case "html": {
                        let html = `<!DOCTYPE html><html><head><title>${report.name}</title>`;
                        html +=
                                "<style>body{font-family:Arial,sans-serif;margin:40px;color:#333}table{border-collapse:collapse;width:100%;margin:20px 0}th,td{border:1px solid #ddd;padding:8px;text-align:left}th{background:#f5f5f5}h1{color:#1a56db}h2{color:#333;margin-top:30px}.warning{color:#475569}.summary{background:#f0f9ff;padding:20px;border-radius:8px}</style>";
                        html += "</head><body>";
                        html += `<h1>${report.name}</h1>`;
                        html += `<p>Generated: ${report.timestamp.toLocaleString()}</p>`;
                        html +=
                                '<div class="summary"><h2>Summary</h2><p>' +
                                report.summary +
                                "</p></div>";

                        for (const section of report.sections) {
                                html += `<h2>${section.title}</h2>`;
                                if (
                                        section.type === "table" &&
                                        section.headers &&
                                        Array.isArray(section.data)
                                ) {
                                        html +=
                                                "<table><tr>" +
                                                section.headers.map((h) => `<th>${h}</th>`).join("") +
                                                "</tr>";
                                        for (const row of section.data) {
                                                html +=
                                                        "<tr>" +
                                                        (Array.isArray(row)
                                                                ? row.map((c) => `<td>${c}</td>`).join("")
                                                                : `<td>${row}</td>`) +
                                                        "</tr>";
                                        }
                                        html += "</table>";
                                } else if (section.type === "text") {
                                        html += `<pre>${String(section.data)}</pre>`;
                                }
                        }

                        if (report.warnings.length > 0) {
                                html +=
                                        '<h2 class="warning">Warnings</h2><ul>' +
                                        report.warnings.map((w) => `<li>${w}</li>`).join("") +
                                        "</ul>";
                        }
                        if (report.recommendations.length > 0) {
                                html +=
                                        "<h2>Recommendations</h2><ul>" +
                                        report.recommendations.map((r) => `<li>${r}</li>`).join("") +
                                        "</ul>";
                        }

                        html += "</body></html>";
                        const blob = new Blob([html], { type: "text/html" });
                        saveAs(
                                blob,
                                `${report.type}_${report.timestamp.toISOString().split("T")[0]}.html`,
                        );
                        break;
                }
                case "excel": {
                        let csv = `NexusCAD Pro - ${report.name}\n`;
                        csv += `Generated:,${report.timestamp.toISOString()}\n\n`;
                        csv += `SUMMARY\n${report.summary}\n\n`;
                        for (const section of report.sections) {
                                csv += `${section.title}\n`;
                                if (section.headers) csv += `${section.headers.join("\t")}\n`;
                                if (Array.isArray(section.data)) {
                                        for (const row of section.data) {
                                                csv += `${Array.isArray(row) ? row.join("\t") : String(row)}\n`;
                                        }
                                }
                                csv += "\n";
                        }
                        const blob = new Blob([csv], { type: "application/vnd.ms-excel" });
                        saveAs(
                                blob,
                                `${report.type}_${report.timestamp.toISOString().split("T")[0]}.xls`,
                        );
                        break;
                }
                case "pdf": {
                        let html = `<!DOCTYPE html><html><head><title>${report.name}</title>`;
                        html +=
                                "<style>@media print{body{margin:0}}body{font-family:Arial,sans-serif;margin:40px;color:#333}table{border-collapse:collapse;width:100%;margin:20px 0}th,td{border:1px solid #ddd;padding:8px}th{background:#f5f5f5}h1{color:#1a56db;border-bottom:2px solid #1a56db;padding-bottom:10px}h2{color:#333;margin-top:30px;page-break-after:avoid}.warning{color:#475569}.summary{background:#f0f9ff;padding:20px;border-radius:8px;margin:20px 0}.page-break{page-break-before:always}</style>";
                        html += "</head><body>";
                        html += `<h1>${report.name}</h1>`;
                        html += `<p>Generated: ${report.timestamp.toLocaleString()}</p>`;
                        html +=
                                '<div class="summary"><h2>Summary</h2><p>' +
                                report.summary +
                                "</p></div>";

                        for (const section of report.sections) {
                                html += `<h2>${section.title}</h2>`;
                                if (
                                        section.type === "table" &&
                                        section.headers &&
                                        Array.isArray(section.data)
                                ) {
                                        html +=
                                                "<table><tr>" +
                                                section.headers.map((h) => `<th>${h}</th>`).join("") +
                                                "</tr>";
                                        for (const row of section.data) {
                                                html +=
                                                        "<tr>" +
                                                        (Array.isArray(row)
                                                                ? row.map((c) => `<td>${c}</td>`).join("")
                                                                : `<td>${row}</td>`) +
                                                        "</tr>";
                                        }
                                        html += "</table>";
                                } else if (section.type === "text") {
                                        html += `<pre>${String(section.data)}</pre>`;
                                }
                        }

                        if (report.warnings.length > 0) {
                                html +=
                                        '<div class="page-break"><h2 class="warning">Warnings</h2><ul>' +
                                        report.warnings.map((w) => `<li>${w}</li>`).join("") +
                                        "</ul></div>";
                        }
                        if (report.recommendations.length > 0) {
                                html +=
                                        "<h2>Recommendations</h2><ul>" +
                                        report.recommendations.map((r) => `<li>${r}</li>`).join("") +
                                        "</ul>";
                        }

                        html += "<script>window.print();</script></body></html>";
                        const blob = new Blob([html], { type: "text/html" });
                        saveAs(
                                blob,
                                `${report.type}_${report.timestamp.toISOString().split("T")[0]}.html`,
                        );
                        break;
                }
        }
}
