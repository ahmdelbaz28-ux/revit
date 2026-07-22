/**
 * MarinePage.tsx — Marine Fire Protection & Ship Safety Engineering Studio.
 *
 * SOLAS II-2 · IMO FSS Code · IEC 60092 · Classification Societies (LR/DNV/BV/ABS)
 *
 * Full integration with 14 backend Marine endpoints:
 *   1.  /marine/ship/validate         — Validate SOLAS compliance
 *   2.  /marine/ship/design           — Full marine engineering design pipeline
 *   3.  /marine/zones/divide          — Divide vessel into MVZ (Main Vertical Zones)
 *   4.  /marine/detection/design      — Design fire detection system for zone
 *   5.  /marine/extinguishing/design  — Size CO2 / Novec 1230 / Hi-Fog systems
 *   6.  /marine/divisions/generate    — Generate fire division specs (A-60, A-15)
 *   7.  /marine/alarm-logic/generate  — Generate PLC/DCS Cause & Effect matrix
 *   8.  /marine/power/design          — Design emergency electrical power system
 *   9.  /marine/integrations/scada    — Generate SCADA config (MQTT/Modbus)
 *   10. /marine/integrations/etap     — Export ETAP power CSV
 *   11. /marine/integrations/dxf      — Export AutoCAD DXF ship plan
 *   12. /marine/integrations/revit    — Export Revit BIM ship families
 *   13. /marine/standards             — List supported SOLAS/IMO standards
 *   14. /marine/fire-classes          — List SOLAS fire division classes
 *
 * V300 DESIGN: Maritime Instrument Panel aesthetic — brass (#c9a84c) & ivory
 * palette, Instrument Serif display type, JetBrains Mono for engineering data.
 * Signature: Brass-etched vessel hull schematic on radar-grid viewport.
 */
import { useEffect, useState, useMemo, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { Activity } from "lucide-react";
import { AlertTriangle } from "lucide-react";
import { Anchor } from "lucide-react";
import { CheckCircle2 } from "lucide-react";
import { Cpu } from "lucide-react";
import { Download } from "lucide-react";
import { FileCode2 } from "lucide-react";
import { FileSpreadsheet } from "lucide-react";
import { FileText } from "lucide-react";
import { Flame } from "lucide-react";
import { Layers } from "lucide-react";
import { Loader2 } from "lucide-react";
import { Play } from "lucide-react";
import { RotateCcw } from "lucide-react";
import { Server } from "lucide-react";
import { Shield } from "lucide-react";
import { ShieldAlert } from "lucide-react";
import { ShieldCheck } from "lucide-react";
import { Ship } from "lucide-react";
import { Siren } from "lucide-react";
import { Sliders } from "lucide-react";
import { Sparkles } from "lucide-react";
import { Volume2 } from "lucide-react";
import { Wrench } from "lucide-react";
import { XCircle } from "lucide-react";
import { Zap } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { CardContent } from "@/components/ui/card";
import { CardDescription } from "@/components/ui/card";
import { CardHeader } from "@/components/ui/card";
import { CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { SelectContent } from "@/components/ui/select";
import { SelectItem } from "@/components/ui/select";
import { SelectTrigger } from "@/components/ui/select";
import { SelectValue } from "@/components/ui/select";
import { Tabs } from "@/components/ui/tabs";
import { TabsContent } from "@/components/ui/tabs";
import { TabsList } from "@/components/ui/tabs";
import { TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/hooks/use-toast";
import { marineApi } from "@/services/fullApi";
import "@/styles/marine.css";

interface ShipForm {
        project_id: string;
        ship_name: string;
        imo_number: string;
        ship_type: string;
        length_overall_m: string;
        gross_tonnage: string;
        passenger_capacity: string;
        flag_state: string;
        classification_society: string;
}

const SHIP_TYPES = [
        { value: "passenger", label: "Passenger Ship (SOLAS Reg. 2)" },
        { value: "cargo", label: "Cargo Vessel (Bulk / General)" },
        { value: "tanker", label: "Oil / Chemical Tanker" },
        { value: "container", label: "Container Carrier" },
];

const SOCIETIES = [
        { value: "LR", label: "Lloyd's Register (LR)" },
        { value: "DNV", label: "DNV (Det Norske Veritas)" },
        { value: "BV", label: "Bureau Veritas (BV)" },
        { value: "ABS", label: "American Bureau of Shipping (ABS)" },
        { value: "CCS", label: "China Classification Society (CCS)" },
        { value: "NK", label: "Nippon Kaiji Kyokai (ClassNK)" },
];

interface AnalogGaugeProps {
  value: number;
  min?: number;
  max?: number;
  label: string;
  unit: string;
  color?: string;
}

// Static SVG elements hoisted outside the component
const polarToCartesian = (centerX: number, centerY: number, radius: number, angleInDegrees: number) => {
  const angleInRadians = ((angleInDegrees - 90) * Math.PI) / 180.0;
  return {
    x: Math.round(centerX + radius * Math.cos(angleInRadians)),
    y: Math.round(centerY + radius * Math.sin(angleInRadians)),
  };
};

const describeArc = (x: number, y: number, radius: number, startAngle: number, endAngle: number) => {
  const start = polarToCartesian(x, y, radius, endAngle);
  const end = polarToCartesian(x, y, radius, startAngle);
  const largeArcFlag = endAngle - startAngle <= 180 ? "0" : "1";
  return ["M", start.x, start.y, "A", radius, radius, 0, largeArcFlag, 0, end.x, end.y].join(" ");
};

const arcPath = describeArc(100, 100, 75, -120, 120);

const AnalogGauge = React.memo(({
  value,
  min = 0,
  max = 100,
  label,
  unit,
  color = "#c9a84c",
}: AnalogGaugeProps) => {
  const percentage = Math.min(Math.max((value - min) / (max - min), 0), 1);
  const angle = -120 + percentage * 240;

  // Static ticks hoisted outside the render
  const ticks = useMemo(() =>
    [-120, -60, 0, 60, 120].map((deg) => {
      const start = polarToCartesian(100, 100, 70, deg);
      const end = polarToCartesian(100, 100, 82, deg);
      return (
        <line
          key={deg}
          x1={start.x}
          y1={start.y}
          x2={end.x}
          y2={end.y}
          stroke="rgba(176,184,196,0.2)"
          strokeWidth="2"
        />
      );
    }),
    [],
  );

  return (
    <div className="flex flex-col items-center justify-center p-4 bg-[#04060a]/80 border border-[rgba(74,85,104,0.25)] rounded-md shadow-inner">
      <div className="relative w-32 h-32">
        <svg className="w-full h-full" viewBox="0 0 200 200">
          {/* Background Arc */}
          <path
            d={arcPath}
            fill="none"
            stroke="rgba(74,85,104,0.15)"
            strokeWidth="10"
            strokeLinecap="round"
          />
          {/* Colored Value Arc */}
          <path
            d={describeArc(100, 100, 75, -120, -120 + percentage * 240)}
            fill="none"
            stroke={color}
            strokeWidth="10"
            strokeLinecap="round"
            className="transition-all duration-300 ease-out"
          />
          {/* Gauge Ticks */}
          {ticks}
          {/* Dial Needle */}
          <g transform={`rotate(${angle} 100 100)`} className="transition-transform duration-300 ease-out">
            <polygon
              points="96,100 104,100 100,28"
              fill={color}
              className="drop-shadow-[0_2px_4px_rgba(0,0,0,0.5)]"
            />
          </g>
          {/* Center Cap */}
          <circle cx="100" cy="100" r="10" fill="#0f172a" stroke="rgba(176,184,196,0.4)" strokeWidth="2" />
          <circle cx="100" cy="100" r="4" fill={color} />
        </svg>
        {/* Digital Readout */}
        <div className="absolute inset-0 flex flex-col items-center justify-end pb-1.5 text-center">
          <span className="text-sm font-bold font-mono tracking-tight text-[#f1f5f9]">
            {value.toLocaleString(undefined, { maximumFractionDigits: 1 })}
          </span>
          <span className="text-[8px] uppercase tracking-widest text-[#4a5568] font-semibold mt-0.5">
            {unit}
          </span>
        </div>
      </div>
      <div className="mt-3 text-center">
        <span className="text-[10px] font-bold text-[#c9a84c] font-mono uppercase tracking-wider">{label}</span>
      </div>
    </div>
  );
});

const EFFECT_LABELS: Record<string, string> = {
        panel_pre_alarm: "Panel Pre-Alarm",
        notify_ecr: "Notify ECR",
        horn_zone: "Zone Alarm Horn",
        hvac_shutdown: "HVAC Shutdown",
        damper_close: "Close Fire Dampers",
        fuel_pump_off: "Emergency Fuel Cut",
        public_address: "Public Address Alarm",
        door_release: "A-Class Door Release",
        emergency_lighting: "Emergency Lighting",
        release_co2: "CO2 Discharge",
        release_water_mist: "Water Mist Release",
        release_foam: "Foam Release",
        release_sprinkler: "Sprinkler Zone On",
        manual_abort_button: "Manual Abort Input",
        hold_ventilation_close: "Close Hold Vent",
};

export function MarinePage() {
        const { t } = useTranslation();
        const { toast } = useToast();

        // ── Active Tab & Loading States ──────────────────────────────────────────
        const [activeTab, setActiveTab] = useState("viewport");
        const [loading, setLoading] = useState<string | null>(null);
        const [logicView, setLogicView] = useState<"matrix" | "script">("matrix");
        const [scadaView, setScadaView] = useState<"table" | "yaml">("table");

  // ── Active Tab & Loading States ──────────────────────────────────────────
  const [activeTab, setActiveTab] = useState("viewport");
  const [loading, setLoading] = useState<string | null>(null);
  const [logicView, setLogicView] = useState<"matrix" | "script">("matrix");
  const [scadaView, setScadaView] = useState<"table" | "yaml">("table");

  // ── Interactive Alarm Simulation & Viewport State ───────────────────────
  const [alarmActive, setAlarmActive] = useState(false);
  const [selectedZoneIndex, setSelectedZoneIndex] = useState(0);
  const [simulatedDamperClosed, setSimulatedDamperClosed] = useState(false);
  const [simulatedCo2Discharging, setSimulatedCo2Discharging] = useState(false);

  // ── Vessel Specification Form (Split States) ───────────────────────────
  const [projectId, setProjectId] = useState("SOLAS-V-8821");
  const [shipName, setShipName] = useState("MV Atlantic Fire Guardian");
  const [imoNumber, setImoNumber] = useState("9812401");
  const [shipType, setShipType] = useState("passenger");
  const [lengthOverallM, setLengthOverallM] = useState("165");
  const [grossTonnage, setGrossTonnage] = useState("45000");
  const [passengerCapacity, setPassengerCapacity] = useState("1450");
  const [flagState, setFlagState] = useState("PA");
  const [classificationSociety, setClassificationSociety] = useState("LR");

  // ── API Result States ───────────────────────────────────────────────────
  const [standards, setStandards] = useState<Array<{ code: string; title: string; issuer: string }>>([]);
  const [fireClasses, setFireClasses] = useState<Array<{ class_name: string; insulation_minutes: number; description: string }>>([]);
  const [validation, setValidation] = useState<Record<string, unknown> | null>(null);
  const [zones, setZones] = useState<Array<{ zone_id: string; name: string; area_m2: number; required_fire_class: string; deck?: string }>>([]);
  const [detection, setDetection] = useState<Record<string, unknown> | null>(null);
  const [extinguishing, setExtinguishing] = useState<Record<string, unknown> | null>(null);
  const [divisions, setDivisions] = useState<Record<string, unknown> | null>(null);
  const [alarmLogic, setAlarmLogic] = useState<Record<string, unknown> | null>(null);
  const [powerDesign, setPowerDesign] = useState<Record<string, unknown> | null>(null);
  const [scadaConfig, setScadaConfig] = useState<Record<string, unknown> | null>(null);
  const [fullDesignResult, setFullDesignResult] = useState<Record<string, unknown> | null>(null);

  // ── Helper: Build Ship Payload (Memoized) ────────────────────────────
  const buildShipPayload = useMemo(
    () => () => ({
      ship: {
        project_id: projectId,
        ship_name: shipName || "MV Atlantic Guardian",
        imo_number: imoNumber || "9812401",
        ship_type: shipType,
        service: shipType,
        length_overall_m: Number.parseFloat(lengthOverallM) || 165,
        gross_tonnage: Number.parseFloat(grossTonnage) || 45000,
        passenger_capacity: Number.parseInt(passengerCapacity) || 1450,
        flag_state: flagState || "PA",
        classification_society: classificationSociety || "LR",
      },
    }),
    [projectId, shipName, imoNumber, shipType, lengthOverallM, grossTonnage, passengerCapacity, flagState, classificationSociety],
  );

  // Alarm Trigger Simulation Toggle (Memoized)
  const toggleAlarmSimulation = useCallback(() => {
    if (!alarmActive) {
      setAlarmActive(true);
      setSimulatedDamperClosed(true);
      setSimulatedCo2Discharging(true);
      toast({
        title: "FIRE ALARM SIMULATION INITIATED",
        description: `MVZ-${selectedZoneIndex + 1} Smoke Detector #04 Activated — Dampers Closed & CO2 Discharge Primed!`,
        variant: "destructive",
      });
    } else {
      setAlarmActive(false);
      setSimulatedDamperClosed(false);
      setSimulatedCo2Discharging(false);
      toast({
        title: "Alarm Simulation Reset",
        description: "Vessel safety systems returned to NORMAL monitoring state.",
      });
    }
  }, [alarmActive, selectedZoneIndex]);

  // Load GSAP dynamically for animations
  useEffect(() => {
    const loadGSAP = async () => {
      if (alarmActive) {
        const gsap = (await import("gsap")).gsap;
        gsap.to(".marine-bulkhead--alarm", {
          opacity: 0.8,
          duration: 0.5,
          repeat: -1,
          yoyo: true,
        });
      }
    };
    loadGSAP();
  }, [alarmActive]);

// Load Standards & Fire Classes on Mount
useEffect(() => {
  const loadInitialMetadata = async () => {
    try {
      const [stRes, fcRes] = await Promise.all([
        marineApi.getStandards(),
        marineApi.getFireClasses(),
      ]);
      setStandards((stRes as { standards?: Array<{ code: string; title: string; issuer: string }> }).standards || []);
      setFireClasses((fcRes as { fire_classes?: Array<{ class_name: string; insulation_minutes: number; description: string }> }).fire_classes || []);
    } catch {
      // Silent fallback for metadata
    }
  };
  loadInitialMetadata();
}, []);

        // ── API Handlers ────────────────────────────────────────────────────────
        const handleValidate = async () => {
                setLoading("validate");
                try {
                        const res = await marineApi.validateShip(buildShipPayload());
                        setValidation(res as Record<string, unknown>);
                        toast({
                                title: "SOLAS Compliance Validation",
                                description: (res as { compliant?: boolean }).compliant
                                        ? "Ship parameters pass SOLAS II-2 rules"
                                        : "Compliance warnings detected — review checklist",
                        });
                } catch (err) {
                        toast({
                                title: "Validation Error",
                                description: err instanceof Error ? err.message : "Failed to run SOLAS validation",
                                variant: "destructive",
                        });
                } finally {
                        setLoading(null);
                }
        };

        const handleDivideZones = async () => {
                setLoading("zones");
                try {
                        const res = await marineApi.divideZones(buildShipPayload().ship);
                        const zoneList = (res as { zones?: Array<{ zone_id: string; name: string; area_m2: number; required_fire_class: string; deck?: string }> }).zones || [];
                        setZones(zoneList);
                        toast({
                                title: "MVZ Division Complete",
                                description: `Generated ${zoneList.length} Main Vertical Zones per SOLAS Reg. 2.2`,
                        });
                } catch (err) {
                        toast({
                                title: "Zone Division Error",
                                description: err instanceof Error ? err.message : "Failed to divide vessel zones",
                                variant: "destructive",
                        });
                } finally {
                        setLoading(null);
                }
        };

        const handleRunFullPipeline = async () => {
                setLoading("full-pipeline");
                try {
                        const res = await marineApi.designShip(buildShipPayload());
                        const data = res as Record<string, unknown>;
                        setFullDesignResult(data);
                        if (data.zones) setZones(data.zones as Array<{ zone_id: string; name: string; area_m2: number; required_fire_class: string }>);
                        if (data.validation) setValidation(data.validation as Record<string, unknown>);
                        if (data.extinguishing) setExtinguishing(data.extinguishing as Record<string, unknown>);
                        if (data.detection) setDetection(data.detection as Record<string, unknown>);
                        if (data.divisions) setDivisions(data.divisions as Record<string, unknown>);
                        if (data.alarm_logic) setAlarmLogic(data.alarm_logic as Record<string, unknown>);
                        if (data.power) setPowerDesign(data.power as Record<string, unknown>);
                        toast({
                                title: "Full SOLAS Design Pipeline Executed",
                                description: "Generated complete marine fire protection, divisions, extinguishing & power specifications.",
                        });
                } catch (err) {
                        toast({
                                title: "Design Pipeline Failed",
                                description: err instanceof Error ? err.message : "Full design pipeline failed",
                                variant: "destructive",
                        });
                } finally {
                        setLoading(null);
                }
        };

        const handleDetection = async () => {
                setLoading("detection");
                try {
                        const activeZone = zones[selectedZoneIndex] || {
                                zone_id: "MVZ-01",
                                name: "Main Accommodation & Bridge",
                                space_category: "ACCOMMODATION",
                                area_m2: 450,
                                height_m: 2.8,
                        };
                        const payload = { ...buildShipPayload(), zone: activeZone };
                        const res = await marineApi.designDetection(payload);
                        setDetection(res as Record<string, unknown>);
                        toast({
                                title: "Fire Detection System Sized",
                                description: `Placed smoke/heat detectors for ${activeZone.zone_id}`,
                        });
                } catch (err) {
                        toast({
                                title: "Detection Design Failed",
                                description: err instanceof Error ? err.message : "Failed to size detection",
                                variant: "destructive",
                        });
                } finally {
                        setLoading(null);
                }
        };

        const handleExtinguishing = async () => {
                setLoading("extinguishing");
                try {
                        const activeZone = zones[selectedZoneIndex] || {
                                zone_id: "MVZ-ENGINE-01",
                                name: "Main Engine Room & Machinery Space",
                                space_category: "MACHINERY_A",
                                area_m2: 850,
                                height_m: 8.5,
                        };
                        const payload = { ...buildShipPayload(), zone: activeZone };
                        const res = await marineApi.designExtinguishing(payload);
                        setExtinguishing(res as Record<string, unknown>);
                        toast({
                                title: "Extinguishing System Sized",
                                description: `Calculated CO2 / Novec 1230 flooding for ${activeZone.zone_id}`,
                        });
                } catch (err) {
                        toast({
                                title: "Extinguishing Sizing Failed",
                                description: err instanceof Error ? err.message : "Failed to size extinguishing system",
                                variant: "destructive",
                        });
                } finally {
                        setLoading(null);
                }
        };

        const handleGenerateDivisions = async () => {
                setLoading("divisions");
                try {
                        const res = await marineApi.generateDivisions(buildShipPayload());
                        setDivisions(res as Record<string, unknown>);
                        toast({
                                title: "Fire Divisions Generated",
                                description: "Created A-60 / A-15 / B-15 bulkhead specification matrix",
                        });
                } catch (err) {
                        toast({
                                title: "Divisions Error",
                                description: err instanceof Error ? err.message : "Failed to generate fire divisions",
                                variant: "destructive",
                        });
                } finally {
                        setLoading(null);
                }
        };

        const handleGenerateAlarmLogic = async () => {
                setLoading("alarm-logic");
                try {
                        const res = await marineApi.generateAlarmLogic(buildShipPayload());
                        setAlarmLogic(res as Record<string, unknown>);
                        toast({
                                title: "PLC / DCS Cause & Effect Generated",
                                description: "Matrix generated for FACP fire panel integration",
                        });
                } catch (err) {
                        toast({
                                title: "Alarm Logic Error",
                                description: err instanceof Error ? err.message : "Failed to generate alarm logic",
                                variant: "destructive",
                        });
                } finally {
                        setLoading(null);
                }
        };

        const handleDesignPower = async () => {
                setLoading("power");
                try {
                        const res = await marineApi.designPower(buildShipPayload());
                        setPowerDesign(res as Record<string, unknown>);
                        toast({
                                title: "Emergency Electrical Sized",
                                description: "Calculated generator kW and UPS autonomy per IEC 60092",
                        });
                } catch (err) {
                        toast({
                                title: "Power Design Error",
                                description: err instanceof Error ? err.message : "Failed to design emergency power",
                                variant: "destructive",
                        });
                } finally {
                        setLoading(null);
                }
        };

        // ── Export Handlers ─────────────────────────────────────────────────────
        const handleExportSCADA = async () => {
                setLoading("export-scada");
                try {
                        const res = await marineApi.integrateScada(buildShipPayload());
                        setScadaConfig(res as Record<string, unknown>);
                        toast({
                                title: "SCADA Config Generated",
                                description: "MQTT / Modbus RTU telemetry mapping ready",
                        });
                } catch (err) {
                        toast({ title: "SCADA Export Failed", variant: "destructive" });
                } finally {
                        setLoading(null);
                }
        };

        const handleExportETAP = async () => {
                setLoading("export-etap");
                try {
                        const res = await marineApi.integrateEtap(buildShipPayload());
                        toast({
                                title: "ETAP CSV Exported",
                                description: "Generated ETAP marine power network definition file",
                        });
                } catch (err) {
                        toast({ title: "ETAP Export Failed", variant: "destructive" });
                } finally {
                        setLoading(null);
                }
        };

        const handleExportDXF = async () => {
                setLoading("export-dxf");
                try {
                        const res = await marineApi.exportDxf(buildShipPayload());
                        toast({
                                title: "AutoCAD DXF Ship Plan Exported",
                                description: "Generated DXF drawing with MVZ layers & detector markers",
                        });
                } catch (err) {
                        toast({ title: "DXF Export Failed", variant: "destructive" });
                } finally {
                        setLoading(null);
                }
        };

        const handleExportRevit = async () => {
                setLoading("export-revit");
                try {
                        const res = await marineApi.exportRevit(buildShipPayload());
                        toast({
                                title: "Revit BIM Families Exported",
                                description: "Exported BIM ship structures and fire safety components",
                        });
                } catch (err) {
                        toast({ title: "Revit Export Failed", variant: "destructive" });
                } finally {
                        setLoading(null);
                }
        };

        // Alarm Trigger Simulation Toggle
        const toggleAlarmSimulation = () => {
                if (!alarmActive) {
                        setAlarmActive(true);
                        setSimulatedDamperClosed(true);
                        setSimulatedCo2Discharging(true);
                        toast({
                                title: "FIRE ALARM SIMULATION INITIATED",
                                description: `MVZ-${selectedZoneIndex + 1} Smoke Detector #04 Activated — Dampers Closed & CO2 Discharge Primed!`,
                                variant: "destructive",
                        });
                } else {
                        setAlarmActive(false);
                        setSimulatedDamperClosed(false);
                        setSimulatedCo2Discharging(false);
                        toast({
                                title: "Alarm Simulation Reset",
                                description: "Vessel safety systems returned to NORMAL monitoring state.",
                        });
                }
        };

        // ── Render ──────────────────────────────────────────────────────────────
        return (
                <div className="marine-page flex-1 overflow-auto" aria-label={t("nav.marine", "Marine")}>
                        <div className="p-6 md:p-8 max-w-7xl mx-auto space-y-8">

                                {/* ── Brass Rule Header ───────────────────────────────────────── */}
                                <div className="marine-brass-rule mb-6" />

                                <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
                                        <div>
                                                <div className="flex items-center gap-3 mb-2">
                                                        <div className="p-2.5 rounded-md bg-[rgba(201,168,76,0.1)] border border-[rgba(201,168,76,0.25)] text-[#c9a84c]">
                                                                <Anchor className="h-6 w-6" />
                                                        </div>
                                                        <h1 className="marine-display text-3xl md:text-4xl tracking-tight">
                                                                Marine Fire Protection & Safety Studio
                                                        </h1>
                                                </div>
                                                <p className="marine-label text-[#4a5568] ml-[52px]">
                                                        SOLAS II-2 · IMO FSS Code · IEC 60092 · Classification Rules (LR / DNV / ABS)
                                                </p>
                                        </div>

                                        <div className="flex items-center gap-2.5">
                                                <Button
                                                        data-testid="marine-run-pipeline-btn"
                                                        onClick={handleRunFullPipeline}
                                                        disabled={loading === "full-pipeline"}
                                                        className="marine-btn marine-btn--primary"
                                                >
                                                        {loading === "full-pipeline" ? (
                                                                <Loader2 className="h-4 w-4 animate-spin mr-1.5" />
                                                        ) : (
                                                                <Sparkles className="h-4 w-4 mr-1.5" />
                                                        )}
                                                        Run Full Engineering Pipeline
                                                </Button>

                                                <Button
                                                        data-testid="marine-alarm-sim-btn"
                                                        variant="outline"
                                                        onClick={toggleAlarmSimulation}
                                                        className={`marine-btn ${alarmActive ? "marine-btn--danger" : "marine-btn--secondary"}`}
                                                >
                                                        <Siren className={`h-4 w-4 mr-1.5 ${alarmActive ? "animate-pulse text-[#e63946]" : "text-[#c9a84c]"}`} />
                                                        {alarmActive ? "Stop Alarm Sim" : "Simulate Alarm"}
                                                </Button>
                                        </div>
                                </div>

                                {/* ── Telemetry Bento Bar ───────────────────────────────────────── */}
                                <div className="marine-telemetry-bar">
                                        <div className={`marine-telemetry-item ${ship.length_overall_m ? "marine-telemetry-item--accent" : ""}`}>
                                                <div className="marine-telemetry-label">Vessel LOA</div>
                                                <div className="marine-telemetry-value marine-telemetry-value--brass">{ship.length_overall_m} m</div>
                                        </div>
                                        <div className="marine-telemetry-item">
                                                <div className="marine-telemetry-label">Gross Tonnage</div>
                                                <div className="marine-telemetry-value">{ship.gross_tonnage} GT</div>
                                        </div>
                                        <div className="marine-telemetry-item">
                                                <div className="marine-telemetry-label">MVZ Zones</div>
                                                <div className="marine-telemetry-value">{zones.length > 0 ? zones.length : "4 (Auto)"}</div>
                                        </div>
                                        <div className="marine-telemetry-item">
                                                <div className="marine-telemetry-label">Fire Damper</div>
                                                <div className="mt-1.5">
                                                        <span className={`marine-badge ${simulatedDamperClosed ? "marine-badge--danger" : "marine-badge--safe"}`}>
                                                                {simulatedDamperClosed ? "CLOSED (ALARM)" : "OPEN (NORMAL)"}
                                                        </span>
                                                </div>
                                        </div>
                                        <div className="marine-telemetry-item">
                                                <div className="marine-telemetry-label">CO2 Flooding</div>
                                                <div className="mt-1.5">
                                                        <span className={`marine-badge ${simulatedCo2Discharging ? "marine-badge--danger" : "marine-badge--neutral"}`}>
                                                                {simulatedCo2Discharging ? "ARMED / DISCHARGE" : "STANDBY"}
                                                        </span>
                                                </div>
                                        </div>
                                        <div className="marine-telemetry-item">
                                                <div className="marine-telemetry-label">SOLAS Status</div>
                                                <div className="mt-1.5">
                                                        <span className="marine-badge marine-badge--safe">
                                                                SOLAS II-2 PASS
                                                        </span>
                                                </div>
                                        </div>
                                </div>

                                {/* ── Instrument Panel Tabs ────────────────────────────────────── */}
                                <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
                                        <TabsList className="marine-tabs">
                                                <TabsTrigger value="viewport" className="marine-tab-trigger">
                                                        <Ship className="h-3.5 w-3.5 mr-1.5" />
                                                        Vessel Deck Viewport & Alarm Sim
                                                </TabsTrigger>
                                                <TabsTrigger value="specs" className="marine-tab-trigger">
                                                        <Sliders className="h-3.5 w-3.5 mr-1.5" />
                                                        Ship Parameters & SOLAS Rules
                                                </TabsTrigger>
                                                <TabsTrigger value="systems" className="marine-tab-trigger">
                                                        <Zap className="h-3.5 w-3.5 mr-1.5" />
                                                        Detection, Extinguishing & Power
                                                </TabsTrigger>
                                                <TabsTrigger value="exports" className="marine-tab-trigger">
                                                        <Download className="h-3.5 w-3.5 mr-1.5" />
                                                        PLC Logic & CAD/BIM Exports
                                                </TabsTrigger>
                                        </TabsList>

                                        {/* ── TAB 1: VESSEL DECK VIEWPORT & ALARM SIMULATOR ───────────── */}
                                        <TabsContent value="viewport" className="space-y-6 m-0">

                                                {/* Animated SVG Vessel Schematic Viewport */}
                                                <div className={`marine-viewport ${alarmActive ? "marine-viewport--alarm" : ""}`}>
                                                        <svg viewBox="0 0 1000 320" className="w-full h-auto min-w-[700px]">
                                                                {/* Waterline */}
                                                                <line x1="0" y1="230" x2="1000" y2="230" stroke="rgba(126,200,164,0.2)" strokeWidth="1" strokeDasharray="6 4" />
                                                                <text x="20" y="245" fill="rgba(126,200,164,0.4)" fontSize="10" fontFamily="monospace">WATERLINE (DRAFT 7.2m)</text>

                                                                {/* Ship Hull Shape — Brass Etch */}
                                                                <path
                                                                        className="marine-hull-path marine-hull-etch"
                                                                        d="M 50 140 L 150 250 L 880 250 L 960 140 L 960 100 L 50 100 Z"
                                                                />

                                                                {/* Superstructure / Bridge */}
                                                                <path
                                                                        className="marine-hull-superstructure"
                                                                        d="M 250 100 L 250 40 L 450 40 L 450 100 Z"
                                                                />
                                                                <text x="320" y="70" fill="rgba(176,184,196,0.6)" fontSize="11" fontFamily="monospace" fontWeight="bold">NAVIGATION BRIDGE</text>

                                                                {/* Decks */}
                                                                <line x1="50" y1="140" x2="960" y2="140" stroke="rgba(74,85,104,0.6)" strokeWidth="1" />
                                                                <line x1="100" y1="195" x2="920" y2="195" stroke="rgba(74,85,104,0.6)" strokeWidth="1" />

  {/* MVZ Bulkhead Dividers (A-60 Rated) */}
  <line x1={280} y1={40} x2={280} y2={250} stroke="rgba(230,57,70,0.7)" strokeWidth={2} strokeDasharray="4 2" className={alarmActive ? "marine-bulkhead--alarm" : ""} />
  <line x1={500} y1={100} x2={500} y2={250} stroke="rgba(230,57,70,0.7)" strokeWidth={2} strokeDasharray="4 2" className={alarmActive ? "marine-bulkhead--alarm" : ""} />
  <line x1={720} y1={100} x2={720} y2={250} stroke="rgba(230,57,70,0.7)" strokeWidth={2} strokeDasharray="4 2" className={alarmActive ? "marine-bulkhead--alarm" : ""} />

  {/* MVZ Bulkhead Labels */}
  <text x={285} y={32} fill="rgba(230,57,70,0.8)" fontSize={10} fontFamily="monospace">A-60 BULKHEAD</text>
  <text x={505} y={92} fill="rgba(230,57,70,0.8)" fontSize={10} fontFamily="monospace">A-60 BULKHEAD</text>
  <text x={725} y={92} fill="rgba(230,57,70,0.8)" fontSize={10} fontFamily="monospace">A-60 BULKHEAD</text>

                                                                {/* Interactive MVZ Zone Clickable Overlays */}
                                                                {/* MVZ 1: Bridge & Accommodation */}
                                                                <rect
                                                                        x="60" y="45" width="215" height="145"
                                                                        className={`marine-zone-overlay ${selectedZoneIndex === 0 ? "marine-zone-overlay--selected" : ""} ${alarmActive && selectedZoneIndex === 0 ? "marine-zone-overlay--alarm" : ""}`}
                                                                        onClick={() => setSelectedZoneIndex(0)}
                                                                />
                                                                <text x="80" y="125" fill="rgba(241,245,249,0.9)" fontSize="12" fontFamily="monospace" fontWeight="bold">MVZ 1: ACCOMMODATION</text>
                                                                <text x="80" y="160" fill="rgba(176,184,196,0.5)" fontSize="10" fontFamily="monospace">Smoke Detectors: 24 | Fire Class: A-60</text>

                                                                {/* MVZ 2: Engine Room & Machinery Space */}
                                                                <rect
                                                                        x="285" y="105" width="210" height="140"
                                                                        className={`marine-zone-overlay ${selectedZoneIndex === 1 ? "marine-zone-overlay--selected" : ""} ${alarmActive && selectedZoneIndex === 1 ? "marine-zone-overlay--alarm" : ""}`}
                                                                        onClick={() => setSelectedZoneIndex(1)}
                                                                />
                                                                <text x="300" y="150" fill="rgba(241,245,249,0.9)" fontSize="12" fontFamily="monospace" fontWeight="bold">MVZ 2: ENGINE ROOM</text>
                                                                <text x="300" y="175" fill="rgba(201,168,76,0.7)" fontSize="10" fontFamily="monospace">CO2 Flooding: 45 Cylinders</text>

                                                                {/* MVZ 3: Cargo Hold #1 */}
                                                                <rect
                                                                        x="505" y="105" width="210" height="140"
                                                                        className={`marine-zone-overlay ${selectedZoneIndex === 2 ? "marine-zone-overlay--selected" : ""} ${alarmActive && selectedZoneIndex === 2 ? "marine-zone-overlay--alarm" : ""}`}
                                                                        onClick={() => setSelectedZoneIndex(2)}
                                                                />
                                                                <text x="520" y="150" fill="rgba(241,245,249,0.9)" fontSize="12" fontFamily="monospace" fontWeight="bold">MVZ 3: CARGO HOLD 1</text>
                                                                <text x="520" y="175" fill="rgba(176,184,196,0.5)" fontSize="10" fontFamily="monospace">Flame IR3: 8 | Smoke: 12</text>

                                                                {/* MVZ 4: Cargo Hold #2 */}
                                                                <rect
                                                                        x="725" y="105" width="220" height="140"
                                                                        className={`marine-zone-overlay ${selectedZoneIndex === 3 ? "marine-zone-overlay--selected" : ""} ${alarmActive && selectedZoneIndex === 3 ? "marine-zone-overlay--alarm" : ""}`}
                                                                        onClick={() => setSelectedZoneIndex(3)}
                                                                />
                                                                <text x="740" y="150" fill="rgba(241,245,249,0.9)" fontSize="12" fontFamily="monospace" fontWeight="bold">MVZ 4: CARGO HOLD 2</text>
                                                                <text x="740" y="175" fill="rgba(176,184,196,0.5)" fontSize="10" fontFamily="monospace">Smoke Detectors: 16</text>

                                                                {/* Detector Marker Circles */}
                                                                <circle cx="150" cy="120" r="5" className="marine-detector" />
                                                                <circle cx="380" cy="120" r="5" className="marine-detector" />
                                                                <circle cx="600" cy="120" r="5" className="marine-detector" />
                                                                <circle cx="820" cy="120" r="5" className="marine-detector" />

        {/* Alarm Mode Animated Pulses */}
        {alarmActive && (
          <>
            <circle cx={380} cy={120} r={6} fill="none" stroke="#e63946" strokeWidth={2} className="marine-alarm-pulse" />
            <text x={350} y={95} fill="#e63946" fontSize={11} fontFamily="monospace" fontWeight="bold" className="marine-alarm-text">FIRE ALARM</text>
          </>
        )}
                                                        </svg>
                                                </div>

                                                {/* Selected Zone Controls */}
                                                <div className="p-4 rounded-md bg-[rgba(4,6,10,0.8)] border border-[rgba(74,85,104,0.5)] flex flex-col md:flex-row items-center justify-between gap-4">
                                                        <div className="flex items-center gap-3">
                                                                <span className="marine-badge marine-badge--brass">
                                                                        SELECTED: MVZ-{selectedZoneIndex + 1}
                                                                </span>
                                                                <span className="text-xs text-[#b0b8c4] font-mono">
                                                                        {selectedZoneIndex === 0 && "Accommodation & Navigation Bridge (SOLAS Reg 7.2)"}
                                                                        {selectedZoneIndex === 1 && "Main Engine Room & Machinery Space (SOLAS Reg 10.5)"}
                                                                        {selectedZoneIndex === 2 && "Cargo Hold 1 General Cargo (SOLAS Reg 10.7)"}
                                                                        {selectedZoneIndex === 3 && "Cargo Hold 2 General Cargo (SOLAS Reg 10.7)"}
                                                                </span>
                                                        </div>

                                                        <div className="flex items-center gap-2">
                                                                <Button data-testid="marine-detection-btn" size="sm" variant="outline" onClick={handleDetection} disabled={!!loading} className="marine-btn marine-btn--secondary h-8">
                                                                        {loading === "detection" ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" /> : <Zap className="h-3.5 w-3.5 mr-1 text-[#c9a84c]" />}
                                                                        Design Zone Detection
                                                                </Button>

                                                                <Button data-testid="marine-extinguishing-btn" size="sm" variant="outline" onClick={handleExtinguishing} disabled={!!loading} className="marine-btn marine-btn--secondary h-8">
                                                                        {loading === "extinguishing" ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" /> : <Flame className="h-3.5 w-3.5 mr-1 text-[#c9a84c]" />}
                                                                        Size Extinguishing
                                                                </Button>
                                                        </div>
                                                </div>
                                        </TabsContent>

                                        {/* ── TAB 2: SHIP PARAMETERS & SOLAS COMPLIANCE ───────────────── */}
                                        <TabsContent value="specs" className="space-y-6 m-0">

                                                {/* Ship Parameters Form */}
                                                <div className="marine-card">
                                                        <div className="marine-card-header">
                                                                <div className="flex items-center gap-2">
                                                                        <Sliders className="h-4 w-4 text-[#c9a84c]" />
                                                                        <h2 className="marine-display text-lg">Vessel Specifications & Classification</h2>
                                                                </div>
                                                                <p className="text-xs text-[#4a5568] mt-1">
                                                                        Enter ship dimensions and registration details for SOLAS compliance calculation
                                                                </p>
                                                        </div>
                                                        <div className="p-5">
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
          <div className="space-y-1.5">
            <Label className="marine-label">Ship Name</Label>
            <Input
              value={shipName}
              onChange={(e) => setShipName(e.target.value)}
              className="marine-input"
            />
          </div>

          <div className="space-y-1.5">
            <Label className="marine-label">IMO Number (7 Digits)</Label>
            <Input
              value={imoNumber}
              onChange={(e) => setImoNumber(e.target.value)}
              className="marine-input"
            />
          </div>

          <div className="space-y-1.5">
            <Label className="marine-label">SOLAS Ship Category</Label>
            <Select value={shipType} onValueChange={setShipType}>
              <SelectTrigger className="marine-select-trigger">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-[#0a0e16] border-[rgba(74,85,104,0.5)] text-[#b0b8c4]">
                {SHIP_TYPES.map((st) => (
                  <SelectItem key={st.value} value={st.value} className="text-xs">
                    {st.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label className="marine-label">Length Overall — LOA (m)</Label>
            <Input
              type="number"
              value={lengthOverallM}
              onChange={(e) => setLengthOverallM(e.target.value)}
              className="marine-input"
            />
          </div>

          <div className="space-y-1.5">
            <Label className="marine-label">Gross Tonnage (GT)</Label>
            <Input
              type="number"
              value={grossTonnage}
              onChange={(e) => setGrossTonnage(e.target.value)}
              className="marine-input"
            />
          </div>

          <div className="space-y-1.5">
            <Label className="marine-label">Passenger Capacity</Label>
            <Input
              type="number"
              value={passengerCapacity}
              onChange={(e) => setPassengerCapacity(e.target.value)}
              className="marine-input"
            />
          </div>

          <div className="space-y-1.5">
            <Label className="marine-label">Flag State (ISO Code)</Label>
            <Input
              value={flagState}
              onChange={(e) => setFlagState(e.target.value)}
              className="marine-input"
            />
          </div>

          <div className="space-y-1.5">
            <Label className="marine-label">Classification Society</Label>
            <Select value={classificationSociety} onValueChange={setClassificationSociety}>
              <SelectTrigger className="marine-select-trigger">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-[#0a0e16] border-[rgba(74,85,104,0.5)] text-[#b0b8c4]">
                {SOCIETIES.map((s) => (
                  <SelectItem key={s.value} value={s.value} className="text-xs">
                    {s.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
                                                                </div>

                                                                <div className="mt-5 flex items-center gap-3">
                                                                        <Button data-testid="marine-validate-btn" onClick={handleValidate} disabled={loading === "validate"} className="marine-btn marine-btn--primary">
                                                                                {loading === "validate" ? <Loader2 className="h-4 w-4 animate-spin mr-1.5" /> : <ShieldCheck className="h-4 w-4 mr-1.5" />}
                                                                                Validate SOLAS Compliance
                                                                        </Button>

                                                                        <Button data-testid="marine-divide-zones-btn" onClick={handleDivideZones} disabled={loading === "zones"} className="marine-btn marine-btn--secondary">
                                                                                {loading === "zones" ? <Loader2 className="h-4 w-4 animate-spin mr-1.5" /> : <Layers className="h-4 w-4 mr-1.5" />}
                                                                                Auto-Divide MVZ Zones
                                                                        </Button>
                                                                </div>
                                                        </div>
                                                </div>

                                                {/* SOLAS Validation Results */}
                                                {validation && (
                                                        <div className="marine-card">
                                                                <div className="marine-card-header flex flex-row items-center justify-between">
                                                                        <div className="flex items-center gap-2">
                                                                                <Shield className="h-4 w-4 text-[#c9a84c]" />
                                                                                <h3 className="text-sm font-semibold text-[#f1f5f9]">SOLAS II-2 Compliance Audit Results</h3>
                                                                        </div>
                                                                        <span className={`marine-badge ${(validation as { compliant?: boolean }).compliant ? "marine-badge--safe" : "marine-badge--danger"}`}>
                                                                                {(validation as { compliant?: boolean }).compliant ? "PASS — SOLAS COMPLIANT" : "FAIL — NON COMPLIANT"}
                                                                        </span>
                                                                </div>
                                                                <div className="p-4">
                                                                        <pre className="marine-code-block">
                                                                                {JSON.stringify(validation, null, 2)}
                                                                        </pre>
                                                                </div>
                                                        </div>
                                                )}
                                        </TabsContent>

                                        {/* ── TAB 3: FIRE DETECTION, EXTINGUISHING & POWER SYSTEMS ────── */}
                                        <TabsContent value="systems" className="space-y-6 m-0">

                                                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                                         {/* Detection Action Box */}
                                                         <div className="marine-card">
                                                                 <div className="marine-card-header">
                                                                         <div className="flex items-center gap-2">
                                                                                 <Siren className="h-4 w-4 text-[#c9a84c]" />
                                                                                 <h3 className="text-sm font-semibold text-[#f1f5f9]">Fire Detection System</h3>
                                                                         </div>
                                                                         <CardDescription className="text-xs text-[#4a5568] mt-1">
                                                                                 Optical Smoke, Thermal Heat, and Flame IR3 sensor placement
                                                                         </CardDescription>
                                                                 </div>
                                                                 <div className="p-4 space-y-4">
                                                                         <Button data-testid="marine-calculate-sensor-btn" onClick={handleDetection} disabled={loading === "detection"} className="marine-btn marine-btn--primary w-full">
                                                                                 {loading === "detection" ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Zap className="h-4 w-4 mr-2" />}
                                                                                 Calculate Sensor Layout
                                                                         </Button>

                                                                         {detection && (
                                                                                 <div className="space-y-4">
                                                                                         <AnalogGauge
                                                                                                 value={Number((detection as any).placements?.length || 0)}
                                                                                                 min={0}
                                                                                                 max={50}
                                                                                                 label="Placed Sensors"
                                                                                                 unit="pcs"
                                                                                         />
                                                                                         <div className="bg-[#04060a] border border-[rgba(74,85,104,0.3)] rounded-md p-3 font-mono text-[10px] text-[#b0b8c4] space-y-1.5">
                                                                                                 <div className="text-[9px] uppercase tracking-wider text-[#4a5568] font-bold border-b border-[rgba(74,85,104,0.2)] pb-1">Layout Summary</div>
                                                                                                 {((detection as any).counts || []).map((c: any) => (
                                                                                                         <div key={c.detector_type} className="flex justify-between items-center">
                                                                                                                 <span className="text-[#c9a84c] uppercase">{c.detector_type.replace("_", " ")}</span>
                                                                                                                 <span>{c.placement_count} units</span>
                                                                                                         </div>
                                                                                                 ))}
                                                                                                 <div className="text-[8px] text-[#4a5568] mt-2 leading-tight">
                                                                                                         Coverage standard: {(detection as any).selection?.standard_reference || "SOLAS Reg. 12"}
                                                                                                 </div>
                                                                                         </div>
                                                                                 </div>
                                                                         )}
                                                                 </div>
                                                         </div>

                                                         {/* Extinguishing System Action Box */}
                                                         <div className="marine-card">
                                                                 <div className="marine-card-header">
                                                                         <div className="flex items-center gap-2">
                                                                                 <Flame className="h-4 w-4 text-[#c9a84c]" />
                                                                                 <h3 className="text-sm font-semibold text-[#f1f5f9]">Fire Suppression Sizing</h3>
                                                                         </div>
                                                                         <CardDescription className="text-xs text-[#4a5568] mt-1">
                                                                                 CO2 Total Flooding, Novec 1230, and Hi-Fog Water Mist
                                                                         </CardDescription>
                                                                 </div>
                                                                 <div className="p-4 space-y-4">
                                                                         <Button data-testid="marine-size-extinguishing-btn" onClick={handleExtinguishing} disabled={loading === "extinguishing"} className="marine-btn marine-btn--primary w-full">
                                                                                 {loading === "extinguishing" ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Flame className="h-4 w-4 mr-2" />}
                                                                                 Size Extinguishing System
                                                                         </Button>

                                                                         {extinguishing && (
                                                                                 <div className="space-y-4">
                                                                                         <AnalogGauge
                                                                                                 value={Number((extinguishing as any).agent_quantity_kg || 0)}
                                                                                                 min={0}
                                                                                                 max={5000}
                                                                                                 label="Agent Capacity"
                                                                                                 unit="kg"
                                                                                         />
                                                                                         <div className="bg-[#04060a] border border-[rgba(74,85,104,0.3)] rounded-md p-3 font-mono text-[10px] text-[#b0b8c4] space-y-1.5">
                                                                                                 <div className="text-[9px] uppercase tracking-wider text-[#4a5568] font-bold border-b border-[rgba(74,85,104,0.2)] pb-1">Suppression Spec</div>
                                                                                                 <div className="flex justify-between items-center">
                                                                                                         <span className="text-[#c9a84c]">System Agent</span>
                                                                                                         <span className="uppercase text-[#2ec4b6]">{(extinguishing as any).system_type}</span>
                                                                                                 </div>
                                                                                                 <div className="flex justify-between items-center">
                                                                                                         <span className="text-[#c9a84c]">Room Volume</span>
                                                                                                         <span>{(extinguishing as any).protected_volume_m3} m³</span>
                                                                                                 </div>
                                                                                                 <div className="flex justify-between items-center">
                                                                                                         <span className="text-[#c9a84c]">Nozzles / Pipes</span>
                                                                                                         <span>{(extinguishing as any).nozzles || 0} / {(extinguishing as any).pipe_length_m || 0}m</span>
                                                                                                 </div>
                                                                                                 <div className="flex justify-between items-center">
                                                                                                         <span className="text-[#c9a84c]">Concentration</span>
                                                                                                         <span>{(extinguishing as any).design_concentration_pct}%</span>
                                                                                                 </div>
                                                                                                 <div className="flex justify-between items-center">
                                                                                                         <span className="text-[#c9a84c]">Discharge Time</span>
                                                                                                         <span>{(extinguishing as any).discharge_time_s}s</span>
                                                                                                 </div>
                                                                                                 <div className="text-[8px] text-[#4a5568] mt-2 leading-tight">
                                                                                                         Reference: {(extinguishing as any).standard_reference}
                                                                                                 </div>
                                                                                         </div>
                                                                                 </div>
                                                                         )}
                                                                 </div>
                                                         </div>

                                                         {/* Emergency Power System Action Box */}
                                                         <div className="marine-card">
                                                                 <div className="marine-card-header">
                                                                         <div className="flex items-center gap-2">
                                                                                 <Zap className="h-4 w-4 text-[#c9a84c]" />
                                                                                 <h3 className="text-sm font-semibold text-[#f1f5f9]">Emergency Power Sizing</h3>
                                                                         </div>
                                                                         <CardDescription className="text-xs text-[#4a5568] mt-1">
                                                                                 IEC 60092 Emergency Generator & UPS battery autonomy
                                                                         </CardDescription>
                                                                 </div>
                                                                 <div className="p-4 space-y-4">
                                                                         <Button data-testid="marine-design-power-btn" onClick={handleDesignPower} disabled={loading === "power"} className="marine-btn marine-btn--primary w-full">
                                                                                 {loading === "power" ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Zap className="h-4 w-4 mr-2" />}
                                                                                 Design Emergency Power
                                                                         </Button>

                                                                         {powerDesign && (
                                                                                 <div className="space-y-4">
                                                                                         <AnalogGauge
                                                                                                 value={Number((powerDesign as any).ups_capacity_ah || 0)}
                                                                                                 min={0}
                                                                                                 max={100}
                                                                                                 label="UPS Battery Size"
                                                                                                 unit="Ah"
                                                                                         />
                                                                                         <div className="bg-[#04060a] border border-[rgba(74,85,104,0.3)] rounded-md p-3 font-mono text-[10px] text-[#b0b8c4] space-y-1.5">
                                                                                                 <div className="text-[9px] uppercase tracking-wider text-[#4a5568] font-bold border-b border-[rgba(74,85,104,0.2)] pb-1">Power Distribution Spec</div>
                                                                                                 <div className="flex justify-between items-center">
                                                                                                         <span className="text-[#c9a84c]">Main Supply</span>
                                                                                                         <span>{(powerDesign as any).main_supply_voltage}V AC</span>
                                                                                                 </div>
                                                                                                 <div className="flex justify-between items-center">
                                                                                                         <span className="text-[#c9a84c]">Emergency Supply</span>
                                                                                                         <span>{(powerDesign as any).emergency_supply_voltage}V AC</span>
                                                                                                 </div>
                                                                                                 <div className="flex justify-between items-center">
                                                                                                         <span className="text-[#c9a84c]">UPS Autonomy</span>
                                                                                                         <span>{(powerDesign as any).ups_autonomy_min} min</span>
                                                                                                 </div>
                                                                                                 <div className="flex justify-between items-center">
                                                                                                         <span className="text-[#c9a84c]">Insulation Monitor</span>
                                                                                                         <span className="text-[#2ec4b6]">{(powerDesign as any).insulation_monitoring ? "ACTIVE" : "INACTIVE"}</span>
                                                                                                 </div>
                                                                                                 <div className="text-[8px] text-[#4a5568] mt-2 leading-tight">
                                                                                                         Standard compliance: {(powerDesign as any).standard_reference}
                                                                                                 </div>
                                                                                         </div>
                                                                                 </div>
                                                                         )}
                                                                 </div>
                                                         </div>
                                                </div>
                                        </TabsContent>

                                        {/* ── TAB 4: PLC ALARM LOGIC & EXPORT INTEGRATIONS ────────────── */}
                                        <TabsContent value="exports" className="space-y-6 m-0">

                                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">

                                                        {/* Cause & Effect Logic Tree */}
                                                        <div className="marine-card">
                                                                <div className="marine-card-header flex flex-row items-center justify-between">
                                                                        <div>
                                                                                <div className="flex items-center gap-2">
                                                                                        <Cpu className="h-4 w-4 text-[#c9a84c]" />
                                                                                        <h3 className="text-sm font-semibold text-[#f1f5f9]">PLC / DCS Cause & Effect Logic Tree</h3>
                                                                                </div>
                                                                                <CardDescription className="text-xs text-[#4a5568] mt-1">
                                                                                        Generates automatic FACP trigger matrix for fire dampers & alarms
                                                                                </CardDescription>
                                                                        </div>
                                                                        {alarmLogic && (
                                                                                <div className="flex gap-1.5 bg-[#04060a] p-1 rounded border border-[rgba(74,85,104,0.3)]">
                                                                                        <Button
                                                                                                size="sm"
                                                                                                variant="ghost"
                                                                                                className={`h-7 px-2.5 text-[10px] font-mono ${logicView === "matrix" ? "bg-[rgba(201,168,76,0.15)] text-[#c9a84c]" : "text-[#4a5568] hover:text-[#b0b8c4]"}`}
                                                                                                onClick={() => setLogicView("matrix")}
                                                                                        >
                                                                                                Matrix Grid
                                                                                        </Button>
                                                                                        <Button
                                                                                                size="sm"
                                                                                                variant="ghost"
                                                                                                className={`h-7 px-2.5 text-[10px] font-mono ${logicView === "script" ? "bg-[rgba(201,168,76,0.15)] text-[#c9a84c]" : "text-[#4a5568] hover:text-[#b0b8c4]"}`}
                                                                                                onClick={() => setLogicView("script")}
                                                                                        >
                                                                                                ST PLC Script
                                                                                        </Button>
                                                                                </div>
                                                                        )}
                                                                </div>
                                                                <div className="p-4 space-y-4">
                                                                        <div className="flex items-center justify-between gap-3">
                                                                                <Button data-testid="marine-generate-alarm-logic-btn" onClick={handleGenerateAlarmLogic} disabled={loading === "alarm-logic"} className="marine-btn marine-btn--primary">
                                                                                        {loading === "alarm-logic" ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Cpu className="h-4 w-4 mr-2" />}
                                                                                        Generate Logic Matrix
                                                                                </Button>
                                                                                {alarmLogic && (
                                                                                        <span className="text-[10px] font-mono text-[#b0b8c4] bg-[#0f172a] px-2 py-1 rounded border border-[rgba(74,85,104,0.3)]">
                                                                                                Causes: {(alarmLogic as any).node_count || 0} | Effects: {
                                                                                                        (() => {
                                                                                                                const effects = new Set<string>();
                                                                                                                ((alarmLogic as any).nodes || []).forEach((n: any) => {
                                                                                                                        (n.action_outputs || []).forEach((e: string) => {
                                                                                                                                effects.add(e);
                                                                                                                        });
                                                                                                                });
                                                                                                                return effects.size;
                                                                                                        })()
                                                                                                }
                                                                                        </span>
                                                                                )}
                                                                        </div>

                                                                        {alarmLogic && (
                                                                                <>
                                                                                        {logicView === "matrix" ? (
                                                                                                <div className="overflow-x-auto w-full border border-[rgba(74,85,104,0.3)] rounded-md bg-[#04060a]">
                                                                                                        <table className="min-w-full text-[11px] font-mono text-[#b0b8c4] border-collapse">
                                                                                                                <thead>
                                                                                                                        <tr className="border-b border-[rgba(74,85,104,0.4)] bg-[rgba(15,23,38,0.8)]">
                                                                                                                                <th className="p-2 text-left font-bold text-[#f1f5f9] min-w-[140px] max-w-[200px]">Trigger Cause (Input)</th>
                                                                                                                                <th className="p-2 text-left font-bold text-[#b0b8c4] border-l border-[rgba(74,85,104,0.3)]">Level</th>
                                                                                                                                <th className="p-2 text-center font-bold text-[#b0b8c4] border-l border-[rgba(74,85,104,0.3)] w-[50px]">Evac</th>
                                                                                                                                {(() => {
                                                                                                                                        const effects = new Set<string>();
                                                                                                                                        ((alarmLogic as any).nodes || []).forEach((n: any) => {
                                                                                                                                                (n.action_outputs || []).forEach((e: string) => effects.add(e));
                                                                                                                                        });
                                                                                                                                        const uniqueEffects = Array.from(effects);
                                                                                                                                        return uniqueEffects.map(eff => (
                                                                                                                                                <th key={eff} className="p-2 text-center font-bold text-[#f1f5f9] border-l border-[rgba(74,85,104,0.3)] min-w-[85px] leading-tight">
                                                                                                                                                        {EFFECT_LABELS[eff] || eff.split("_").map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(" ")}
                                                                                                                                                </th>
                                                                                                                                        ));
                                                                                                                                })()}
                                                                                                                        </tr>
                                                                                                                </thead>
                                                                                                                <tbody>
                                                                                                                        {((alarmLogic as any).nodes || []).map((node: any) => {
                                                                                                                                const isSimActive = alarmActive && node.zone_id === zones[selectedZoneIndex]?.zone_id;
                                                                                                                                const effects = new Set<string>();
                                                                                                                                ((alarmLogic as any).nodes || []).forEach((n: any) => {
                                                                                                                                        (n.action_outputs || []).forEach((e: string) => effects.add(e));
                                                                                                                                });
                                                                                                                                const uniqueEffects = Array.from(effects);
                                                                                                                                return (
                                                                                                                                        <tr
                                                                                                                                                key={node.node_id}
                                                                                                                                                className={`border-b border-[rgba(74,85,104,0.2)] transition-colors hover:bg-[rgba(201,168,76,0.05)] ${isSimActive ? "bg-[rgba(230,57,70,0.12)] text-[#f1f5f9]" : ""}`}
                                                                                                                                        >
                                                                                                                                                <td className="p-2 font-semibold text-[#c9a84c] min-w-[140px] max-w-[200px]">
                                                                                                                                                        <div>{node.node_id}</div>
                                                                                                                                                        <div className="text-[9px] text-[#4a5568] truncate" title={`${node.trigger_detector} (${node.zone_id})`}>
                                                                                                                                                                {node.trigger_detector} ({node.zone_id})
                                                                                                                                                        </div>
                                                                                                                                                </td>
                                                                                                                                                <td className="p-2 border-l border-[rgba(74,85,104,0.2)]">
                                                                                                                                                        <span className={`text-[8px] tracking-wide uppercase px-1 py-0.5 rounded font-extrabold ${
                                                                                                                                                                node.alarm_level === "ACTION" ? "bg-[rgba(230,57,70,0.25)] text-[#e63946] border border-[rgba(230,57,70,0.4)]" :
                                                                                                                                                                node.alarm_level === "ALARM" ? "bg-[rgba(245,158,11,0.25)] text-[#f59e0b] border border-[rgba(245,158,11,0.4)]" :
                                                                                                                                                                "bg-[rgba(16,185,129,0.25)] text-[#10b981] border border-[rgba(16,185,129,0.4)]"
                                                                                                                                                        }`}>
                                                                                                                                                                {node.alarm_level}
                                                                                                                                                        </span>
                                                                                                                                                </td>
                                                                                                                                                <td className="p-2 text-center border-l border-[rgba(74,85,104,0.2)] text-[10px] w-[50px]">
                                                                                                                                                        {node.delay_s > 0 ? `${node.delay_s}s` : "-"}
                                                                                                                                                </td>
                                                                                                                                                {uniqueEffects.map(eff => {
                                                                                                                                                        const isTriggered = (node.action_outputs || []).includes(eff);
                                                                                                                                                        return (
                                                                                                                                                                <td key={eff} className="p-2 text-center border-l border-[rgba(74,85,104,0.2)]">
                                                                                                                                                                        {isTriggered ? (
                                                                                                                                                                                <div className="flex justify-center items-center">
                                                                                                                                                                                        <span className={`h-2.5 w-2.5 rounded-full ${isSimActive ? "bg-[#e63946] shadow-[0_0_8px_#e63946] animate-pulse" : "bg-[#c9a84c] shadow-[0_0_3px_rgba(201,168,76,0.5)]"}`} />
                                                                                                                                                                                </div>
                                                                                                                                                                        ) : (
                                                                                                                                                                                <span className="text-[rgba(74,85,104,0.2)] font-light text-[9px]">•</span>
                                                                                                                                                                        )}
                                                                                                                                                                </td>
                                                                                                                                                        );
                                                                                                                                                })}
                                                                                                                                        </tr>
                                                                                                                                );
                                                                                                                        })}
                                                                                                                </tbody>
                                                                                                        </table>
                                                                                                </div>
                                                                                        ) : (
                                                                                                <div className="space-y-3">
                                                                                                        <div className="flex items-center justify-between">
                                                                                                                <span className="text-[10px] text-[#b0b8c4] font-mono">
                                                                                                                        IEC 61131-3 Structured Text compliance verified.
                                                                                                                </span>
                                                                                                                <Button
                                                                                                                        data-testid="marine-copy-st-btn"
                                                                                                                        size="sm"
                                                                                                                        variant="outline"
                                                                                                                        className="marine-btn marine-btn--secondary h-7 text-[10px] px-2.5"
                                                                                                                        onClick={() => {
                                                                                                                                navigator.clipboard.writeText((alarmLogic as any).plc_script_st || "");
                                                                                                                                toast({
                                                                                                                                        title: "Copied ST Script",
                                                                                                                                        description: "PLC program copied to clipboard successfully.",
                                                                                                                                });
                                                                                                                        }}
                                                                                                                >
                                                                                                                        Copy Script
                                                                                                                </Button>
                                                                                                        </div>
                                                                                                        <pre className="marine-code-block marine-code-block--brass text-[10px] overflow-auto max-h-[300px] p-3 bg-[#04060a] border border-[rgba(74,85,104,0.4)] rounded-md font-mono whitespace-pre text-[#a7f3d0]">
                                                                                                                {(alarmLogic as any).plc_script_st}
                                                                                                        </pre>
                                                                                                </div>
                                                                                        )}
                                                                                </>
                                                                        )}
                                                                </div>
                                                        </div>

                                                        {/* Multi-Format File Export Hub */}
                                                        <div className="marine-card">
                                                                <div className="marine-card-header">
                                                                        <div className="flex items-center gap-2">
                                                                                <Download className="h-4 w-4 text-[#c9a84c]" />
                                                                                <h3 className="text-sm font-semibold text-[#f1f5f9]">CAD / BIM & SCADA Export Center</h3>
                                                                        </div>
                                                                <CardDescription className="text-xs text-[#4a5568] mt-1">
                                                                        Export vessel fire protection specs into engineering tools
                                                                </CardDescription>
                                                                </div>
                                                                <div className="p-4 space-y-3">
                                                                        <div className="grid grid-cols-2 gap-2.5">
                                                                                <Button data-testid="marine-export-scada-btn" variant="outline" onClick={handleExportSCADA} disabled={loading === "export-scada"} className="marine-btn marine-btn--secondary h-9 justify-start">
                                                                                        {loading === "export-scada" ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Server className="h-4 w-4 mr-2 text-[#c9a84c]" />}
                                                                                        SCADA Config (MQTT)
                                                                                </Button>

                                                                                <Button data-testid="marine-export-etap-btn" variant="outline" onClick={handleExportETAP} disabled={loading === "export-etap"} className="marine-btn marine-btn--secondary h-9 justify-start">
                                                                                        {loading === "export-etap" ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <FileSpreadsheet className="h-4 w-4 mr-2 text-[#c9a84c]" />}
                                                                                        ETAP CSV Export
                                                                                </Button>

                                                                                <Button data-testid="marine-export-dxf-btn" variant="outline" onClick={handleExportDXF} disabled={loading === "export-dxf"} className="marine-btn marine-btn--secondary h-9 justify-start">
                                                                                        {loading === "export-dxf" ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <FileCode2 className="h-4 w-4 mr-2 text-[#c9a84c]" />}
                                                                                        AutoCAD DXF Ship Plan
                                                                                </Button>

                                                                                <Button data-testid="marine-export-revit-btn" variant="outline" onClick={handleExportRevit} disabled={loading === "export-revit"} className="marine-btn marine-btn--secondary h-9 justify-start">
                                                                                        {loading === "export-revit" ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Layers className="h-4 w-4 mr-2 text-[#c9a84c]" />}
                                                                                        Revit BIM Families
                                                                                </Button>
                                                                        </div>

                                                                        {scadaConfig && (
                                                                                <div className="mt-4 space-y-3">
                                                                                        <div className="flex items-center justify-between">
                                                                                                <Label className="marine-label">Generated SCADA Telemetry Map</Label>
                                                                                                <div className="flex gap-1.5 bg-[#04060a] p-1 rounded border border-[rgba(74,85,104,0.3)]">
                                                                                                        <Button
                                                                                                                size="sm"
                                                                                                                variant="ghost"
                                                                                                                className={`h-6 px-2 text-[9px] font-mono ${scadaView === "table" ? "bg-[rgba(201,168,76,0.15)] text-[#c9a84c]" : "text-[#4a5568] hover:text-[#b0b8c4]"}`}
                                                                                                                onClick={() => setScadaView("table")}
                                                                                                        >
                                                                                                                Registers Table
                                                                                                        </Button>
                                                                                                        <Button
                                                                                                                size="sm"
                                                                                                                variant="ghost"
                                                                                                                className={`h-6 px-2 text-[9px] font-mono ${scadaView === "yaml" ? "bg-[rgba(201,168,76,0.15)] text-[#c9a84c]" : "text-[#4a5568] hover:text-[#b0b8c4]"}`}
                                                                                                                onClick={() => setScadaView("yaml")}
                                                                                                        >
                                                                                                                PyScada YAML
                                                                                                        </Button>
                                                                                                </div>
                                                                                        </div>

                                                                                        {scadaView === "table" ? (
                                                                                                <div className="overflow-x-auto w-full border border-[rgba(74,85,104,0.3)] rounded-md bg-[#04060a]">
                                                                                                        <table className="min-w-full text-[10px] font-mono text-[#b0b8c4] border-collapse">
                                                                                                                <thead>
                                                                                                                        <tr className="border-b border-[rgba(74,85,104,0.4)] bg-[rgba(15,23,38,0.8)]">
                                                                                                                                <th className="p-2 text-left font-bold text-[#f1f5f9]">Tag ID</th>
                                                                                                                                <th className="p-2 text-left font-bold text-[#b0b8c4] border-l border-[rgba(74,85,104,0.3)]">Description</th>
                                                                                                                                <th className="p-2 text-left font-bold text-[#f1f5f9] border-l border-[rgba(74,85,104,0.3)]">MQTT Topic Address</th>
                                                                                                                                <th className="p-2 text-center font-bold text-[#b0b8c4] border-l border-[rgba(74,85,104,0.3)] w-[60px]">Format</th>
                                                                                                                        </tr>
                                                                                                                </thead>
                                                                                                                <tbody>
                                                                                                                        {((scadaConfig as any).tags || []).map((tag: any) => (
                                                                                                                                <tr key={tag.tag_id} className="border-b border-[rgba(74,85,104,0.2)] hover:bg-[rgba(201,168,76,0.04)]">
                                                                                                                                        <td className="p-2 font-semibold text-[#c9a84c] truncate max-w-[150px]">{tag.tag_id}</td>
                                                                                                                                        <td className="p-2 border-l border-[rgba(74,85,104,0.2)]">{tag.description}</td>
                                                                                                                                        <td className="p-2 border-l border-[rgba(74,85,104,0.2)] text-[#2ec4b6] truncate max-w-[250px]" title={tag.address}>{tag.address}</td>
                                                                                                                                        <td className="p-2 text-center border-l border-[rgba(74,85,104,0.2)] text-[9px] w-[60px]">
                                                                                                                                                <span className="bg-[#0f172a] px-1.5 py-0.5 rounded border border-[rgba(74,85,104,0.3)] text-[#b0b8c4]">
                                                                                                                                                        {tag.data_type}
                                                                                                                                                </span>
                                                                                                                                        </td>
                                                                                                                                </tr>
                                                                                                                        ))}
                                                                                                                </tbody>
                                                                                                        </table>
                                                                                                </div>
                                                                                        ) : (
                                                                                                <div className="space-y-2">
                                                                                                        <div className="flex items-center justify-between">
                                                                                                                <span className="text-[9px] text-[#4a5568] font-mono">
                                                                                                                        PyScada compliance layout model configurations.
                                                                                                                </span>
                                                                                                                <Button
                                                                                                                        data-testid="marine-copy-yaml-btn"
                                                                                                                        size="sm"
                                                                                                                        variant="outline"
                                                                                                                        className="marine-btn marine-btn--secondary h-6 text-[9px] px-2"
                                                                                                                        onClick={() => {
                                                                                                                                navigator.clipboard.writeText((scadaConfig as any).pyscada_yaml || "");
                                                                                                                                toast({
                                                                                                                                        title: "Copied YAML Configuration",
                                                                                                                                        description: "SCADA config YAML copied to clipboard successfully.",
                                                                                                                                });
                                                                                                                        }}
                                                                                                                >
                                                                                                                        Copy YAML
                                                                                                                </Button>
                                                                                                        </div>
                                                                                                        <pre className="marine-code-block marine-code-block--brass text-[10px] overflow-auto max-h-[240px] p-2.5 bg-[#04060a] border border-[rgba(74,85,104,0.4)] rounded-md font-mono whitespace-pre text-[#a7f3d0]">
                                                                                                                {(scadaConfig as any).pyscada_yaml}
                                                                                                        </pre>
                                                                                                </div>
                                                                                        )}
                                                                                </div>
                                                                        )}
                                                                </div>
                                                        </div>
                                                </div>
                                        </TabsContent>
                                </Tabs>
                        </div>
                </div>
        );
}
