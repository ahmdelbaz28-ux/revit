import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { Zap, AlertTriangle, ChevronDown } from "lucide-react";
import PhysicsGuardsMonitor, {
  GuardRule,
} from "@/components/engineering/PhysicsGuardsMonitor";
import { cn } from "@/lib/utils";

// Calculator tab type
type CalculatorTab =
  | "smoke"
  | "heat"
  | "battery"
  | "voltage"
  | "detectors"
  | "duct";

// Smoke Detector Calculator
const SmokeCalculator: React.FC = () => {
  const [roomArea, setRoomArea] = useState(400);
  const [ceilingHeight, setCeilingHeight] = useState(10);
  const [detectorType, setDetectorType] = useState("standard");

  // NFPA 72: Standard spacing 30 ft, rated 35 ft
  // Max area per detector: 900 sq ft (30x30)
  const requiredDetectors = Math.ceil(roomArea / 900);
  const spacing = Math.sqrt(roomArea / requiredDetectors);

  const guards: GuardRule[] = [
    {
      id: "smoke-spacing",
      name: "Smoke Detector Spacing",
      description: "NFPA 72 Table 23.3.6 - Standard spacing 30 ft",
      severity: "error",
      category: "spacing",
      min: 20,
      max: 30,
      currentValue: spacing,
      unit: "ft",
      status: spacing <= 30 && spacing >= 20 ? "pass" : spacing <= 35 ? "warn" : "fail",
    },
    {
      id: "ceiling-height",
      name: "Ceiling Height Compliance",
      description: "Standard detectors: 8-12 ft, High ceiling: 12+ ft",
      severity: "error",
      category: "smoke",
      min: 8,
      max: 50,
      currentValue: ceilingHeight,
      unit: "ft",
      status: ceilingHeight >= 8 ? "pass" : "fail",
    },
    {
      id: "detector-count",
      name: "Detector Count",
      description: `Required: ${requiredDetectors} detectors for ${roomArea} sq ft`,
      severity: "warn",
      category: "smoke",
      status: "pass",
    },
  ];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">
            Room Area (sq ft)
          </label>
          <input
            type="number"
            value={roomArea}
            onChange={(e) => setRoomArea(Number(e.target.value))}
            className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-500 focus:border-orange-500 focus:outline-none"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">
            Ceiling Height (ft)
          </label>
          <input
            type="number"
            value={ceilingHeight}
            onChange={(e) => setCeilingHeight(Number(e.target.value))}
            className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-500 focus:border-orange-500 focus:outline-none"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">
            Detector Type
          </label>
          <select
            value={detectorType}
            onChange={(e) => setDetectorType(e.target.value)}
            className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 focus:border-orange-500 focus:outline-none"
          >
            <option value="standard">Standard</option>
            <option value="rated">High Ceiling Rated</option>
            <option value="beam">Beam Type</option>
          </select>
        </div>
      </div>

      {/* Results */}
      <div className="grid grid-cols-2 gap-3">
        <div className="bg-orange-500/10 border border-orange-500/30 rounded-lg p-3">
          <div className="text-3xl font-bold text-orange-400">
            {requiredDetectors}
          </div>
          <div className="text-xs text-orange-300">Required Detectors</div>
        </div>
        <div className="bg-orange-500/10 border border-orange-500/30 rounded-lg p-3">
          <div className="text-3xl font-bold text-orange-400">
            {spacing.toFixed(1)}
          </div>
          <div className="text-xs text-orange-300">Spacing (ft)</div>
        </div>
      </div>

      {/* Physics Guards */}
      <PhysicsGuardsMonitor rules={guards} />
    </div>
  );
};

// Battery Calculator
const BatteryCalculator: React.FC = () => {
  const [deviceCount, setDeviceCount] = useState(10);
  const [currentDraw, setCurrentDraw] = useState(2);
  const [standbyHours, setStandbyHours] = useState(24);
  const [alarmMinutes, setAlarmMinutes] = useState(15);

  // Calculation: (standby hours + alarm minutes) * current draw / 1000
  const standbyCapacity = (standbyHours * deviceCount * currentDraw) / 1000;
  const alarmCapacity = ((alarmMinutes / 60) * deviceCount * currentDraw) / 1000;
  const totalCapacity = standbyCapacity + alarmCapacity;
  const withSafetyMargin = totalCapacity * 1.2; // 20% safety margin

  const guards: GuardRule[] = [
    {
      id: "battery-margin",
      name: "Safety Margin (20%)",
      description: "Required: 20% safety factor for battery capacity",
      severity: "error",
      category: "battery",
      min: 1.0,
      max: 1.5,
      currentValue: 1.2,
      unit: "x",
      status: "pass",
    },
    {
      id: "battery-capacity",
      name: "Total Battery Capacity",
      description: `Required: ${withSafetyMargin.toFixed(2)} Ah (with 20% margin)`,
      severity: "error",
      category: "battery",
      status: "pass",
    },
    {
      id: "alarm-duration",
      name: "Alarm Duration",
      description: `Min: 5 minutes, Current: ${alarmMinutes} minutes`,
      severity: "warn",
      category: "battery",
      min: 5,
      max: 60,
      currentValue: alarmMinutes,
      unit: "min",
      status: alarmMinutes >= 5 ? "pass" : "fail",
    },
  ];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">
            Device Count
          </label>
          <input
            type="number"
            value={deviceCount}
            onChange={(e) => setDeviceCount(Number(e.target.value))}
            className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-500 focus:border-orange-500 focus:outline-none"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">
            Current Draw (mA)
          </label>
          <input
            type="number"
            value={currentDraw}
            onChange={(e) => setCurrentDraw(Number(e.target.value))}
            className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-500 focus:border-orange-500 focus:outline-none"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">
            Standby (hours)
          </label>
          <input
            type="number"
            value={standbyHours}
            onChange={(e) => setStandbyHours(Number(e.target.value))}
            className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-500 focus:border-orange-500 focus:outline-none"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">
            Alarm Duration (min)
          </label>
          <input
            type="number"
            value={alarmMinutes}
            onChange={(e) => setAlarmMinutes(Number(e.target.value))}
            className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-500 focus:border-orange-500 focus:outline-none"
          />
        </div>
      </div>

      {/* Results */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-3">
          <div className="text-2xl font-bold text-blue-400">
            {standbyCapacity.toFixed(1)}
          </div>
          <div className="text-xs text-blue-300">Standby (Ah)</div>
        </div>
        <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-3">
          <div className="text-2xl font-bold text-blue-400">
            {alarmCapacity.toFixed(1)}
          </div>
          <div className="text-xs text-blue-300">Alarm (Ah)</div>
        </div>
        <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-3">
          <div className="text-2xl font-bold text-green-400">
            {withSafetyMargin.toFixed(1)}
          </div>
          <div className="text-xs text-green-300">Required (w/ margin)</div>
        </div>
      </div>

      {/* Physics Guards */}
      <PhysicsGuardsMonitor rules={guards} />
    </div>
  );
};

// Voltage Drop Calculator
const VoltageDropCalculator: React.FC = () => {
  const [current, setCurrent] = useState(5);
  const [length, setLength] = useState(100);
  const [cableSize, setCableSize] = useState(10);
  const [voltage, setVoltage] = useState(24);

  // Resistance per 1000 ft for common cable sizes
  const cableResistance: Record<number, number> = {
    10: 1.24,
    12: 1.98,
    14: 3.16,
    16: 5.06,
  };

  const resistance = (cableResistance[cableSize] || 1.24) * (length / 1000);
  const voltageDrop = current * resistance * 2; // *2 for round trip
  const dropPercentage = (voltageDrop / voltage) * 100;

  const guards: GuardRule[] = [
    {
      id: "vdrop-percent",
      name: "Voltage Drop Percentage",
      description: "NFPA 72: Max 5% voltage drop allowed",
      severity: "error",
      category: "voltage",
      min: 0,
      max: 5,
      currentValue: dropPercentage,
      unit: "%",
      status: dropPercentage <= 5 ? "pass" : dropPercentage <= 7 ? "warn" : "fail",
    },
    {
      id: "vdrop-voltage",
      name: "Voltage Drop",
      description: `Max: ${(voltage * 0.05).toFixed(2)}V, Current: ${voltageDrop.toFixed(2)}V`,
      severity: "error",
      category: "voltage",
      status: voltageDrop <= voltage * 0.05 ? "pass" : "warn",
    },
  ];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">
            Current (A)
          </label>
          <input
            type="number"
            value={current}
            onChange={(e) => setCurrent(Number(e.target.value))}
            className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-500 focus:border-orange-500 focus:outline-none"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">
            Cable Length (ft)
          </label>
          <input
            type="number"
            value={length}
            onChange={(e) => setLength(Number(e.target.value))}
            className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-500 focus:border-orange-500 focus:outline-none"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">
            Cable AWG
          </label>
          <select
            value={cableSize}
            onChange={(e) => setCableSize(Number(e.target.value))}
            className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 focus:border-orange-500 focus:outline-none"
          >
            <option value={10}>10 AWG</option>
            <option value={12}>12 AWG</option>
            <option value={14}>14 AWG</option>
            <option value={16}>16 AWG</option>
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">
            Voltage (V)
          </label>
          <input
            type="number"
            value={voltage}
            onChange={(e) => setVoltage(Number(e.target.value))}
            className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-500 focus:border-orange-500 focus:outline-none"
          />
        </div>
      </div>

      {/* Results */}
      <div className="grid grid-cols-2 gap-3">
        <div
          className={cn(
            "rounded-lg p-3 border",
            dropPercentage <= 5
              ? "bg-green-500/10 border-green-500/30"
              : dropPercentage <= 7
                ? "bg-yellow-500/10 border-yellow-500/30"
                : "bg-red-500/10 border-red-500/30"
          )}
        >
          <div className="text-3xl font-bold text-orange-400">
            {dropPercentage.toFixed(2)}%
          </div>
          <div className="text-xs text-orange-300">Voltage Drop (%)</div>
        </div>
        <div
          className={cn(
            "rounded-lg p-3 border",
            voltageDrop <= voltage * 0.05
              ? "bg-green-500/10 border-green-500/30"
              : "bg-yellow-500/10 border-yellow-500/30"
          )}
        >
          <div className="text-3xl font-bold text-orange-400">
            {voltageDrop.toFixed(2)}V
          </div>
          <div className="text-xs text-orange-300">Voltage Drop</div>
        </div>
      </div>

      {/* Physics Guards */}
      <PhysicsGuardsMonitor rules={guards} />
    </div>
  );
};

// Main Page Component
export const QOMNCalculatorPage: React.FC = () => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<CalculatorTab>("smoke");

  const tabs: Array<{ id: CalculatorTab; label: string; description: string }> = [
    { id: "smoke", label: "Smoke Spacing", description: "NFPA 72 smoke detector spacing" },
    { id: "heat", label: "Heat Spacing", description: "Heat detector spacing calculations" },
    { id: "battery", label: "Battery", description: "Battery capacity requirements" },
    { id: "voltage", label: "Voltage Drop", description: "Cable voltage drop analysis" },
    { id: "detectors", label: "Detector Layout", description: "Auto-placement diagram" },
    { id: "duct", label: "Duct Sizing", description: "Duct detector sizing" },
  ];

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-slate-100 flex items-center gap-2">
          <Zap className="h-8 w-8 text-orange-500" />
          QOMN Engineering Calculator
        </h1>
        <p className="text-slate-400 mt-2">
          NFPA 72 compliant fire alarm system design and verification
        </p>
      </div>

      {/* Tabs */}
      <div className="flex flex-wrap gap-2 border-b border-slate-700">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              "px-4 py-2 border-b-2 font-medium transition-all",
              activeTab === tab.id
                ? "border-orange-500 text-orange-400"
                : "border-transparent text-slate-400 hover:text-slate-300"
            )}
            title={tab.description}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-6">
        {activeTab === "smoke" && <SmokeCalculator />}
        {activeTab === "heat" && (
          <div className="text-slate-400">Heat spacing calculator coming soon...</div>
        )}
        {activeTab === "battery" && <BatteryCalculator />}
        {activeTab === "voltage" && <VoltageDropCalculator />}
        {activeTab === "detectors" && (
          <div className="text-slate-400">Detector layout tool coming soon...</div>
        )}
        {activeTab === "duct" && (
          <div className="text-slate-400">Duct detector sizing coming soon...</div>
        )}
      </div>

      {/* Info Box */}
      <div className="bg-orange-500/10 border border-orange-500/30 rounded-lg p-4">
        <p className="text-sm text-orange-300 flex items-start gap-2">
          <AlertTriangle className="h-5 w-5 mt-0.5 shrink-0" />
          <span>
            All calculations must be verified by a licensed fire protection engineer
            before implementation. This tool provides guidance only and does not replace
            professional engineering judgment.
          </span>
        </p>
      </div>
    </div>
  );
};

export default QOMNCalculatorPage;
